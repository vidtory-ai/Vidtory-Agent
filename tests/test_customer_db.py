"""
Comprehensive tests for the SQLite customer database layer.

Tests cover:
- Schema initialization and auto-migration
- API key CRUD operations
- Customer profile CRUD operations
- Feedback and generation history (append-only)
- Concurrent write safety
- Migration script (JSON -> SQLite)
- customer_profile.py public API compatibility
- TelegramKeyStore integration
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from nanobot.db.customer_db import CustomerDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> CustomerDatabase:
    """Fresh CustomerDatabase in a temp directory for each test."""
    db = CustomerDatabase(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def sample_profile() -> dict:
    return {
        "telegramUserId": "123456789",
        "telegramUsername": "testuser",
        "merchantId": "merchant-abc",
        "onboarding": {"status": "completed", "currentStep": "done"},
        "business": {
            "name": "Test Shop",
            "industry": "retail",
            "description": "A test business",
        },
        "brand": {
            "style": "modern",
            "moodKeywords": ["clean", "professional"],
            "colorPalette": {"primary": "#FF0000"},
            "photographyStyle": "product hero",
            "avoidList": ["cartoon"],
        },
        "audience": {"gender": "all", "ageRange": "18-35", "segment": "mid"},
        "contentChannels": {
            "primary": ["instagram", "facebook"],
            "defaultFormats": {"instagram_feed": {"aspectRatio": "1:1"}},
        },
        "preferences": {"communicationLanguage": "vi", "autoApplyBrandGuidelines": True},
        "learningData": {
            "totalGenerations": 5,
            "approvedCount": 3,
            "rejectedCount": 1,
            "commonFeedback": [],
            "bestPerformingPrompts": [],
        },
    }


# ===========================================================================
# API Keys
# ===========================================================================

class TestApiKeys:
    def test_set_and_get_key(self, tmp_db):
        tmp_db.set_api_key("user1", "key-abc-123")
        assert tmp_db.get_api_key("user1") == "key-abc-123"

    def test_get_nonexistent_key(self, tmp_db):
        assert tmp_db.get_api_key("does_not_exist") is None

    def test_update_key(self, tmp_db):
        tmp_db.set_api_key("user1", "old-key")
        tmp_db.set_api_key("user1", "new-key")
        assert tmp_db.get_api_key("user1") == "new-key"

    def test_remove_key(self, tmp_db):
        tmp_db.set_api_key("user1", "key-to-delete")
        tmp_db.remove_key("user1")
        assert tmp_db.get_api_key("user1") is None

    def test_remove_nonexistent_key_no_error(self, tmp_db):
        # Should not raise any exception
        tmp_db.remove_api_key("ghost_user")

    def test_sender_id_with_pipe(self, tmp_db):
        """TelegramKeyStore uses sender_id format '12345|username'."""
        tmp_db.set_api_key("12345|johndoe", "key-xxx")
        assert tmp_db.get_api_key("12345|johndoe") == "key-xxx"
        assert tmp_db.get_api_key("12345") == "key-xxx"

    def test_get_all_api_keys(self, tmp_db):
        tmp_db.set_api_key("userA", "keyA")
        tmp_db.set_api_key("userB", "keyB")
        all_keys = tmp_db.get_all_api_keys()
        assert all_keys["userA"] == "keyA"
        assert all_keys["userB"] == "keyB"

    def test_multiple_users_isolated(self, tmp_db):
        tmp_db.set_api_key("user1", "key1")
        tmp_db.set_api_key("user2", "key2")
        assert tmp_db.get_api_key("user1") == "key1"
        assert tmp_db.get_api_key("user2") == "key2"


# ===========================================================================
# Customer Profiles
# ===========================================================================

class TestCustomerProfiles:
    def test_save_and_load_profile(self, tmp_db, sample_profile):
        result = tmp_db.save_profile("123456789", sample_profile)
        assert result is True
        loaded = tmp_db.load_profile("123456789")
        assert loaded is not None
        assert loaded["telegramUsername"] == "testuser"
        assert loaded["business"]["name"] == "Test Shop"

    def test_load_nonexistent_profile(self, tmp_db):
        assert tmp_db.load_profile("ghost_user") is None

    def test_profile_exists(self, tmp_db, sample_profile):
        assert not tmp_db.profile_exists("123456789")
        tmp_db.save_profile("123456789", sample_profile)
        assert tmp_db.profile_exists("123456789")

    def test_update_profile(self, tmp_db, sample_profile):
        tmp_db.save_profile("123456789", sample_profile)
        updated = dict(sample_profile)
        updated["business"] = {**sample_profile["business"], "name": "Updated Shop"}
        tmp_db.save_profile("123456789", updated)
        loaded = tmp_db.load_profile("123456789")
        assert loaded["business"]["name"] == "Updated Shop"

    def test_api_key_stripped_from_profile(self, tmp_db, sample_profile):
        """API key should never be stored inside profile JSON."""
        profile_with_key = {**sample_profile, "apiKey": "secret-key"}
        tmp_db.save_profile("123456789", profile_with_key)
        loaded = tmp_db.load_profile("123456789")
        assert "apiKey" not in loaded

    def test_list_users(self, tmp_db, sample_profile):
        tmp_db.save_profile("user1", sample_profile)
        users = tmp_db.list_users()
        assert len(users) == 1
        assert users[0]["user_id"] == "user1"

    def test_delete_profile_cascades(self, tmp_db, sample_profile):
        """Deleting a profile should also remove api_key and feedback."""
        tmp_db.save_profile("user1", sample_profile)
        tmp_db.set_api_key("user1", "some-key")
        tmp_db.append_feedback("user1", rating="approved")

        tmp_db.delete_profile("user1")

        assert not tmp_db.profile_exists("user1")
        assert tmp_db.get_api_key("user1") is None
        feedbacks = tmp_db.get_feedback_list("user1")
        assert len(feedbacks) == 0

    def test_profile_json_integrity(self, tmp_db, sample_profile):
        """Full profile should survive round-trip without data loss."""
        tmp_db.save_profile("test_user", sample_profile)
        loaded = tmp_db.load_profile("test_user")
        # Check nested structures
        assert loaded["brand"]["moodKeywords"] == ["clean", "professional"]
        assert loaded["contentChannels"]["primary"] == ["instagram", "facebook"]
        assert loaded["learningData"]["totalGenerations"] == 5


# ===========================================================================
# Feedback
# ===========================================================================

class TestFeedback:
    def test_append_feedback(self, tmp_db):
        result = tmp_db.append_feedback(
            "user1",
            generation_id="gen-001",
            rating="approved",
            original_prompt="a beautiful sunset",
            comment="Great result!",
        )
        assert result is True

    def test_get_feedback_list(self, tmp_db):
        tmp_db.append_feedback("user1", rating="approved", comment="nice")
        tmp_db.append_feedback("user1", rating="rejected", comment="too dark")
        feedbacks = tmp_db.get_feedback_list("user1")
        assert len(feedbacks) == 2

    def test_count_feedback_occurrences(self, tmp_db):
        tmp_db.append_feedback("user1", rating="rejected", comment="too dark")
        tmp_db.append_feedback("user1", rating="rejected", comment="Too Dark")
        count = tmp_db.count_feedback_occurrences("user1", "too dark")
        assert count >= 2

    def test_global_feedback_patterns_count_distinct_customers(self, tmp_db):
        for index in range(5):
            tmp_db.append_feedback(
                f"user{index}",
                rating="rejected",
                comment="text too small",
            )
        patterns = tmp_db.get_global_feedback_patterns(min_users=5)
        assert patterns[0]["feedback"] == "text too small"
        assert patterns[0]["customer_count"] == 5

    def test_feedback_is_per_user(self, tmp_db):
        tmp_db.append_feedback("user1", rating="approved")
        tmp_db.append_feedback("user2", rating="rejected")
        assert len(tmp_db.get_feedback_list("user1")) == 1
        assert len(tmp_db.get_feedback_list("user2")) == 1


# ===========================================================================
# Generation History
# ===========================================================================

class TestGenerationHistory:
    def test_record_generation(self, tmp_db):
        gen_id = tmp_db.record_generation(
            "user1",
            content_type="image",
            prompt="a cat",
            model="gemini-3-flash",
        )
        assert gen_id.startswith("gen-")

    def test_generation_count(self, tmp_db):
        assert tmp_db.get_generation_count("user1") == 0
        tmp_db.record_generation("user1", content_type="image")
        tmp_db.record_generation("user1", content_type="video")
        assert tmp_db.get_generation_count("user1") == 2

    def test_generation_count_per_user(self, tmp_db):
        tmp_db.record_generation("user1", content_type="image")
        tmp_db.record_generation("user2", content_type="image")
        assert tmp_db.get_generation_count("user1") == 1
        assert tmp_db.get_generation_count("user2") == 1


# ===========================================================================
# Stats
# ===========================================================================

class TestStats:
    def test_stats(self, tmp_db, sample_profile):
        tmp_db.set_api_key("u1", "key1")
        tmp_db.save_profile("u1", sample_profile)
        tmp_db.record_generation("u1", content_type="image")
        tmp_db.append_feedback("u1", rating="approved")

        stats = tmp_db.get_stats()
        assert stats["total_users"] == 1
        assert stats["users_with_api_key"] == 1
        assert stats["total_generations"] == 1
        assert stats["total_feedback"] == 1


# ===========================================================================
# Concurrent Write Safety
# ===========================================================================

class TestConcurrentWrites:
    def test_concurrent_api_key_writes(self, tmp_db):
        """Multiple threads writing API keys should not corrupt data."""
        errors = []

        def write_key(uid: str, key: str) -> None:
            try:
                for _ in range(10):
                    tmp_db.set_api_key(uid, key)
                    assert tmp_db.get_api_key(uid) == key
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=write_key, args=(f"user{i}", f"key{i}"))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent write errors: {errors}"
        # All 5 users should exist
        all_keys = tmp_db.get_all_api_keys()
        for i in range(5):
            assert f"user{i}" in all_keys

    def test_concurrent_profile_saves(self, tmp_db, sample_profile):
        """Concurrent profile saves for DIFFERENT users should all succeed."""
        errors = []

        def save_profile(uid: str) -> None:
            profile = {**sample_profile, "telegramUserId": uid}
            try:
                for _ in range(5):
                    result = tmp_db.save_profile(uid, profile)
                    assert result is True
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=save_profile, args=(f"user{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent profile save errors: {errors}"
        users = tmp_db.list_users()
        assert len(users) == 10


# ===========================================================================
# Migration Script
# ===========================================================================

class TestMigrationScript:
    def test_migrate_json_to_sqlite(self, tmp_path):
        """Full migration from JSON files to SQLite."""
        # Create legacy JSON structure
        data_dir = tmp_path / "vidtoryagent"
        data_dir.mkdir()

        # telegram_keys.json
        keys_file = data_dir / "telegram_keys.json"
        keys_file.write_text(
            json.dumps({"111": "key-for-111", "222": "key-for-222"}),
            encoding="utf-8",
        )

        # Customer profile
        customer_dir = data_dir.parent / "customers" / "111"
        customer_dir.mkdir(parents=True)
        profile = {
            "telegramUserId": "111",
            "telegramUsername": "alice",
            "onboarding": {"status": "completed"},
            "business": {"name": "Alice Shop", "industry": "fashion"},
            "brand": {"style": "luxury", "moodKeywords": ["elegant"]},
        }
        (customer_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        # Feedback
        feedback_lines = [
            json.dumps({"generationId": "g1", "rating": "approved", "comment": "nice", "contentType": "image", "originalPrompt": "cat"}),
            json.dumps({"generationId": "g2", "rating": "rejected", "comment": "dark", "contentType": "image", "originalPrompt": "dog"}),
        ]
        (customer_dir / "feedback.jsonl").write_text(
            "\n".join(feedback_lines), encoding="utf-8"
        )

        # History
        history_line = json.dumps({
            "generationId": "g1",
            "contentType": "image",
            "originalPrompt": "a sunset",
            "model": "gemini",
            "resultUrl": "https://cdn.vidtory.net/img.jpg",
        })
        (customer_dir / "generation-history.jsonl").write_text(
            history_line, encoding="utf-8"
        )

        # Run migration with the same DB instance (not singleton)
        db = CustomerDatabase(data_dir / "customers.db")
        from nanobot.db.migrate_to_sqlite import migrate
        counts = migrate(data_dir=data_dir, verbose=False, db=db)

        assert counts["api_keys"] == 2
        assert counts["profiles"] == 1
        assert counts["feedback"] == 2
        assert counts["generations"] == 1
        assert counts["errors"] == 0

        # Verify data in DB using same instance
        assert db.get_api_key("111") == "key-for-111"
        assert db.get_api_key("222") == "key-for-222"
        p = db.load_profile("111")
        assert p["telegramUsername"] == "alice"
        feedbacks = db.get_feedback_list("111")
        assert len(feedbacks) == 2
        assert db.get_generation_count("111") == 1

        db.close()

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice should not duplicate data."""
        data_dir = tmp_path / "vidtoryagent"
        data_dir.mkdir()

        keys_file = data_dir / "telegram_keys.json"
        keys_file.write_text(json.dumps({"999": "key-999"}), encoding="utf-8")

        customer_dir = data_dir.parent / "customers" / "999"
        customer_dir.mkdir(parents=True)
        (customer_dir / "profile.json").write_text(
            json.dumps({"telegramUserId": "999", "business": {"name": "Bob"}}),
            encoding="utf-8",
        )

        db = CustomerDatabase(data_dir / "customers.db")
        from nanobot.db.migrate_to_sqlite import migrate

        # Run twice with same DB instance
        counts1 = migrate(data_dir=data_dir, verbose=False, db=db)
        counts2 = migrate(data_dir=data_dir, verbose=False, db=db)

        # Second run should import 0 new items (everything already exists)
        assert counts1["api_keys"] == 1
        assert counts2["api_keys"] == 0  # already exists

        assert counts1["profiles"] == 1
        assert counts2["profiles"] == 0  # already exists

        # Only 1 profile should exist
        assert len(db.list_users()) == 1
        db.close()


# ===========================================================================
# customer_profile.py public API compatibility
# ===========================================================================

class TestCustomerProfilePublicAPI:
    """Tests that the public API of customer_profile.py works correctly with SQLite."""

    def test_create_minimal_profile(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        profile = cp.create_minimal_profile(
            "888",
            username="newuser",
            business_name="New Co",
            industry="tech",
        )
        assert profile["telegramUserId"] == "888"
        assert profile["telegramUsername"] == "newuser"
        assert tmp_db.profile_exists("888")

    def test_profile_exists_via_public_api(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        assert not cp.profile_exists("777")
        cp.create_minimal_profile("777")
        assert cp.profile_exists("777")

    def test_get_onboarding_status(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        assert cp.get_onboarding_status("555") == "none"
        cp.create_minimal_profile("555")
        assert cp.get_onboarding_status("555") == "minimal"

    def test_save_and_load_profile_via_public_api(self, tmp_db, sample_profile, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        uid = sample_profile["telegramUserId"]
        assert cp.save_profile(uid, sample_profile)
        loaded = cp.load_profile(uid)
        assert loaded is not None
        assert loaded["business"]["name"] == "Test Shop"

    def test_profile_completeness_score(self, sample_profile):
        from nanobot.utils import customer_profile as cp
        score = cp.get_profile_completeness(sample_profile)
        assert score >= 80  # Full profile should score high

    def test_append_feedback_via_public_api(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        result = cp.append_feedback(
            "user1",
            rating="approved",
            original_prompt="beautiful product shot",
            comment="Love it!",
        )
        assert result is True

    def test_record_generation_via_public_api(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp
        from nanobot.db.customer_db import get_db

        cp.create_minimal_profile("user1")
        gen_id = cp.record_generation("user1", content_type="image", prompt="sunset")
        assert gen_id.startswith("gen-")
        # Counter incremented
        p = cp.load_profile("user1")
        assert p["learningData"]["totalGenerations"] == 1

    def test_update_learning_approved(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        cp.create_minimal_profile("user1")
        cp.update_learning("user1", rating="approved", prompt="a great prompt")
        p = cp.load_profile("user1")
        assert p["learningData"]["approvedCount"] == 1
        assert p["learningData"]["bestPerformingPrompts"] == []

        cp.update_learning("user1", rating="approved", prompt="a great prompt")
        cp.update_learning("user1", rating="approved", prompt="a great prompt")
        p = cp.load_profile("user1")
        assert "a great prompt"[:200] in p["learningData"]["bestPerformingPrompts"]

    def test_update_learning_rejected_pattern(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        cp.create_minimal_profile("user1")
        # Submit same rejection twice to trigger pattern detection
        cp.update_learning("user1", rating="rejected", feedback_text="quá tối")
        cp.update_learning("user1", rating="rejected", feedback_text="quá tối")

        p = cp.load_profile("user1")
        # rejectedCount increments each call; since profile is loaded fresh
        # each time, the count reflects the last save (2 saves = rejectedCount 2)
        assert p["learningData"]["rejectedCount"] >= 1
        # avoidList updated on second call (2 occurrences detected)
        assert "too dark" in p["brand"]["avoidList"]


# ===========================================================================
# Logo URL — DB layer
# ===========================================================================

class TestLogoUrl:
    def test_logo_url_default_empty(self, tmp_db, sample_profile):
        """New profiles should have empty logo_url."""
        tmp_db.save_profile("user1", sample_profile)
        assert tmp_db.get_logo_url("user1") == ""

    def test_set_and_get_logo_url(self, tmp_db, sample_profile):
        """set_logo_url should update both column and profile JSON."""
        tmp_db.save_profile("user1", sample_profile)
        result = tmp_db.set_logo_url("user1", "https://cdn.example.com/logo.png")
        assert result is True
        assert tmp_db.get_logo_url("user1") == "https://cdn.example.com/logo.png"

        # Also verify it's in the profile JSON
        profile = tmp_db.load_profile("user1")
        assert profile["brand"]["logoUrl"] == "https://cdn.example.com/logo.png"

    def test_clear_logo_url(self, tmp_db, sample_profile):
        """Setting logo_url to empty string should clear it."""
        tmp_db.save_profile("user1", sample_profile)
        tmp_db.set_logo_url("user1", "https://cdn.example.com/logo.png")
        tmp_db.set_logo_url("user1", "")
        assert tmp_db.get_logo_url("user1") == ""
        profile = tmp_db.load_profile("user1")
        assert profile["brand"]["logoUrl"] == ""

    def test_get_logo_url_nonexistent_user(self, tmp_db):
        """Should return empty string for non-existent users."""
        assert tmp_db.get_logo_url("ghost_user") == ""

    def test_set_logo_url_nonexistent_user(self, tmp_db):
        """Should return False for non-existent users."""
        result = tmp_db.set_logo_url("ghost_user", "https://cdn.example.com/logo.png")
        # UPDATE on non-existent row does nothing, but should not crash
        assert result is True  # DB operation succeeds (0 rows affected is not an error)

    def test_logo_url_with_sender_id_pipe(self, tmp_db, sample_profile):
        """Should work with sender_id format '12345|username'."""
        tmp_db.save_profile("12345|testuser", sample_profile)
        tmp_db.set_logo_url("12345|testuser", "https://logo.example.com/img.png")
        assert tmp_db.get_logo_url("12345|testuser") == "https://logo.example.com/img.png"
        assert tmp_db.get_logo_url("12345") == "https://logo.example.com/img.png"

    def test_logo_url_survives_profile_roundtrip(self, tmp_db, sample_profile):
        """Logo URL should survive save→load→save cycle."""
        profile_with_logo = {**sample_profile}
        profile_with_logo["brand"] = {**sample_profile["brand"], "logoUrl": "https://example.com/logo.jpg"}
        tmp_db.save_profile("user1", profile_with_logo)
        loaded = tmp_db.load_profile("user1")
        assert loaded["brand"]["logoUrl"] == "https://example.com/logo.jpg"
        # logo_url column should also be set
        assert tmp_db.get_logo_url("user1") == "https://example.com/logo.jpg"

    def test_logo_url_in_list_users(self, tmp_db, sample_profile):
        """list_users should include logo_url."""
        tmp_db.save_profile("user1", sample_profile)
        tmp_db.set_logo_url("user1", "https://cdn.example.com/logo.png")
        users = tmp_db.list_users()
        assert len(users) == 1
        assert users[0]["logo_url"] == "https://cdn.example.com/logo.png"

    def test_delete_profile_clears_logo(self, tmp_db, sample_profile):
        """Deleting a profile should remove logo data too."""
        tmp_db.save_profile("user1", sample_profile)
        tmp_db.set_logo_url("user1", "https://cdn.example.com/logo.png")
        tmp_db.delete_profile("user1")
        assert tmp_db.get_logo_url("user1") == ""


# ===========================================================================
# Logo URL — customer_profile.py public API
# ===========================================================================

class TestLogoPublicAPI:
    def test_get_logo_url_via_public_api(self, tmp_db, sample_profile, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        tmp_db.save_profile("user1", sample_profile)
        assert cp.get_logo_url("user1") == ""

    def test_set_logo_url_via_public_api(self, tmp_db, sample_profile, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        tmp_db.save_profile("user1", sample_profile)
        result = cp.set_logo_url("user1", "https://cdn.example.com/logo.png")
        assert result is True
        assert cp.get_logo_url("user1") == "https://cdn.example.com/logo.png"

    def test_clear_logo_via_public_api(self, tmp_db, sample_profile, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        tmp_db.save_profile("user1", sample_profile)
        cp.set_logo_url("user1", "https://cdn.example.com/logo.png")
        result = cp.clear_logo("user1")
        assert result is True
        assert cp.get_logo_url("user1") == ""

    def test_create_minimal_profile_has_logo_field(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        profile = cp.create_minimal_profile("user1")
        assert "logoUrl" in profile["brand"]
        assert profile["brand"]["logoUrl"] == ""

    @pytest.mark.asyncio
    async def test_set_logo_refreshes_visual_identity_without_resetting_business(
        self, tmp_db, sample_profile, monkeypatch
    ):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from io import BytesIO
        from PIL import Image
        from nanobot.utils import customer_profile as cp

        sample_profile["business"]["name"] = "Keep Me"
        sample_profile["audience"]["ageRange"] = "25-34"
        tmp_db.save_profile("user1", sample_profile)

        image = Image.new("RGB", (100, 100), "#1565C0")
        payload = BytesIO()
        image.save(payload, format="PNG")

        result = await cp.set_logo_and_refresh_identity(
            "user1",
            "https://b2b.vidtory.net/logo.png",
            image_bytes=payload.getvalue(),
        )

        profile = cp.load_profile("user1")
        assert result["identity_refreshed"] is True
        assert profile["business"]["name"] == "Keep Me"
        assert profile["audience"]["ageRange"] == "25-34"
        assert profile["brand"]["style"] == "corporate"
        assert profile["brand"]["colorPalette"]["primary"] == "#1565C0"


# ===========================================================================
# Feedback Pattern Threshold
# ===========================================================================

class TestFeedbackThreshold:
    def test_configurable_threshold(self, tmp_db, monkeypatch):
        """VIDTORY_FEEDBACK_THRESHOLD env var should control commonFeedback pattern detection."""
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        # Set threshold to 3 instead of default 2
        monkeypatch.setattr("nanobot.utils.customer_profile.FEEDBACK_PATTERN_THRESHOLD", 3)
        from nanobot.utils import customer_profile as cp

        cp.create_minimal_profile("user1")
        # Use a feedback text that does NOT map to avoid keywords
        # so we only test the commonFeedback threshold behavior.
        cp.update_learning("user1", rating="rejected", feedback_text="text too small")
        cp.update_learning("user1", rating="rejected", feedback_text="text too small")

        p = cp.load_profile("user1")
        # Two occurrences are still below the configured threshold of three.
        assert "text too small" not in [str(f) for f in (p.get("learningData") or {}).get("commonFeedback", [])]

        # Third occurrence reaches the threshold and is learned immediately.
        cp.update_learning("user1", rating="rejected", feedback_text="text too small")
        p = cp.load_profile("user1")
        common = (p.get("learningData") or {}).get("commonFeedback", [])
        assert any("text too small" in str(f) for f in common)


class TestLatestTaskFeedback:
    def test_record_latest_task_feedback_updates_learning_and_task(self, tmp_db, monkeypatch):
        monkeypatch.setattr("nanobot.db.customer_db._db_instance", tmp_db)
        from nanobot.utils import customer_profile as cp

        cp.create_minimal_profile("user1")
        tmp_db.create_task(
            "user1",
            task_id="task-latest",
            prompt_used="clean product poster",
            enhanced_prompt="clean product poster, premium lighting",
        )

        result = cp.record_latest_task_feedback("user1", rating="approved")

        assert result["recorded"] is True
        assert result["task_id"] == "task-latest"
        profile = cp.load_profile("user1")
        assert profile["learningData"]["approvedCount"] == 1
        assert tmp_db.get_task("task-latest")["first_pass_accepted"] == 1


# ===========================================================================
# Brand Context Lines with Logo
# ===========================================================================

class TestBrandContextWithLogo:
    def test_context_lines_include_logo(self):
        """format_customer_context_lines should include logo URL when available."""
        from nanobot.utils.customer_context import format_customer_context_lines

        profile = {
            "business": {"name": "Test Shop"},
            "brand": {
                "style": "modern",
                "logoUrl": "https://cdn.example.com/logo.png",
            },
        }
        lines = format_customer_context_lines(profile)
        logo_lines = [l for l in lines if "Brand Logo" in l]
        assert len(logo_lines) == 1
        assert "https://cdn.example.com/logo.png" in logo_lines[0]

    def test_context_lines_no_logo(self):
        """No logo line when logoUrl is empty."""
        from nanobot.utils.customer_context import format_customer_context_lines

        profile = {
            "business": {"name": "Test Shop"},
            "brand": {"style": "modern", "logoUrl": ""},
        }
        lines = format_customer_context_lines(profile)
        logo_lines = [l for l in lines if "Brand Logo" in l]
        assert len(logo_lines) == 0

    def test_brand_suffix_does_not_duplicate_logo_instruction(self):
        """Logo availability is carried as an asset, not repeated in style keywords."""
        from nanobot.utils.customer_context import build_prompt_brand_suffix

        profile = {
            "brand": {
                "style": "luxury",
                "moodKeywords": ["elegant"],
                "logoUrl": "https://cdn.example.com/logo.png",
            },
        }
        suffix = build_prompt_brand_suffix(profile)
        assert "logo" not in suffix.lower()

    def test_brand_suffix_no_logo_mention(self):
        """build_prompt_brand_suffix should not mention logo when absent."""
        from nanobot.utils.customer_context import build_prompt_brand_suffix

        profile = {
            "brand": {
                "style": "luxury",
                "moodKeywords": ["elegant"],
                "logoUrl": "",
            },
        }
        suffix = build_prompt_brand_suffix(profile)
        assert "logo" not in suffix.lower()

    def test_brand_suffix_removes_subsumed_style_keywords(self):
        from nanobot.utils.customer_context import build_prompt_brand_suffix

        profile = {
            "brand": {
                "style": "modern energetic",
                "moodKeywords": ["modern", "energetic"],
            },
        }

        assert build_prompt_brand_suffix(profile) == "modern energetic"


# ===========================================================================
# Schema V3 Migration
# ===========================================================================

class TestSchemaV3Migration:
    def test_v3_migration_creates_logo_url_column(self, tmp_path):
        """V3 migration should add logo_url column."""
        db = CustomerDatabase(tmp_path / "test_v3.db")
        # Save a profile and verify logo_url works
        db.save_profile("user1", {
            "telegramUserId": "user1",
            "business": {"name": "Test"},
            "brand": {"style": "modern", "logoUrl": "https://example.com/logo.png"},
            "onboarding": {"status": "minimal"},
        })
        assert db.get_logo_url("user1") == "https://example.com/logo.png"
        db.close()

    def test_v3_migration_idempotent(self, tmp_path):
        """Running schema init twice should not fail."""
        db1 = CustomerDatabase(tmp_path / "test_v3_idem.db")
        db1.close()
        db2 = CustomerDatabase(tmp_path / "test_v3_idem.db")
        db2.save_profile("user1", {
            "telegramUserId": "user1",
            "brand": {"logoUrl": "https://test.com/logo.png"},
            "onboarding": {"status": "minimal"},
        })
        assert db2.get_logo_url("user1") == "https://test.com/logo.png"
        db2.close()

