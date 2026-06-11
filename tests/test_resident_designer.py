"""Comprehensive integration test for the Resident Designer architecture.

Tests the full lifecycle across different user types:
1. Brand-new user (no profile)
2. Existing user with profile (migration scenario)
3. Multi-user isolation
4. Lifecycle stage transitions
5. FPAR calculation and stage gating
6. Design notes building
7. Memory lock semantics
8. Dual-write consistency
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nanobot.db.customer_db import CustomerDatabase


@pytest.fixture
def db(tmp_path: Path) -> CustomerDatabase:
    """Create a fresh test database."""
    return CustomerDatabase(tmp_path / "test.db")


# ---------------------------------------------------------------------------
# 1. Memory Layer CRUD
# ---------------------------------------------------------------------------

class TestMemoryLayers:
    """Test the 5-layer brand memory system."""

    def test_set_and_get_core(self, db: CustomerDatabase):
        """Core layer entries should be created with is_locked=1."""
        db.set_memory("u1", layer="core", key="color_primary", value="#FF0000",
                       source="onboarding", force=True)
        result = db.get_memory("u1", "core", "color_primary")
        assert result is not None
        assert result["value"] == "#FF0000"
        assert result["is_locked"] == 1

    def test_core_lock_rejects_update(self, db: CustomerDatabase):
        """Core entries should reject updates without force=True."""
        db.set_memory("u1", layer="core", key="logo", value="old.png",
                       source="test", force=True)
        # Should fail without force
        result = db.set_memory("u1", layer="core", key="logo", value="new.png",
                                source="test", force=False)
        assert result is False
        # Value should remain unchanged
        assert db.get_memory("u1", "core", "logo")["value"] == "old.png"

    def test_core_force_overrides_lock(self, db: CustomerDatabase):
        """Core entries should accept updates with force=True."""
        db.set_memory("u1", layer="core", key="tone", value="formal",
                       source="test", force=True)
        db.set_memory("u1", layer="core", key="tone", value="casual",
                       source="test", force=True)
        assert db.get_memory("u1", "core", "tone")["value"] == "casual"

    def test_style_layer_locked(self, db: CustomerDatabase):
        """Style layer entries should be locked by default."""
        db.set_memory("u1", layer="style", key="aesthetic", value="minimalist",
                       source="test", force=True)
        entry = db.get_memory("u1", "style", "aesthetic")
        assert entry["is_locked"] == 1

    def test_preference_layer_not_locked(self, db: CustomerDatabase):
        """Preference layer entries should NOT be locked."""
        db.set_memory("u1", layer="preference", key="avoid_dark", value="yes",
                       source="feedback:gen-123")
        entry = db.get_memory("u1", "preference", "avoid_dark")
        assert entry["is_locked"] == 0

    def test_preference_update_without_force(self, db: CustomerDatabase):
        """Preference entries should allow updates without force."""
        db.set_memory("u1", layer="preference", key="like_warm", value="yes",
                       source="feedback:gen-1")
        result = db.set_memory("u1", layer="preference", key="like_warm",
                                value="very much", source="feedback:gen-2")
        assert result is True
        assert db.get_memory("u1", "preference", "like_warm")["value"] == "very much"

    def test_get_all_memory_groups_by_layer(self, db: CustomerDatabase):
        """get_all_memory should group entries by layer."""
        db.set_memory("u1", layer="core", key="c1", value="v1", force=True)
        db.set_memory("u1", layer="style", key="s1", value="v2", force=True)
        db.set_memory("u1", layer="preference", key="p1", value="v3")
        result = db.get_all_memory("u1")
        assert "core" in result
        assert "style" in result
        assert "preference" in result
        assert len(result["core"]) == 1
        assert len(result["style"]) == 1
        assert len(result["preference"]) == 1

    def test_count_memory(self, db: CustomerDatabase):
        """count_memory should return correct total."""
        db.set_memory("u1", layer="core", key="c1", value="v1", force=True)
        db.set_memory("u1", layer="core", key="c2", value="v2", force=True)
        db.set_memory("u1", layer="preference", key="p1", value="v3")
        assert db.count_memory("u1") == 3

    def test_delete_memory(self, db: CustomerDatabase):
        """delete_memory should remove specific entry."""
        db.set_memory("u1", layer="preference", key="p1", value="v1")
        db.delete_memory("u1", "preference", "p1")
        assert db.get_memory("u1", "preference", "p1") is None

    def test_delete_memory_layer(self, db: CustomerDatabase):
        """delete_memory_layer should remove all entries in a layer."""
        db.set_memory("u1", layer="preference", key="p1", value="v1")
        db.set_memory("u1", layer="preference", key="p2", value="v2")
        db.set_memory("u1", layer="core", key="c1", value="v3", force=True)
        db.delete_memory_layer("u1", "preference")
        assert len(db.get_memory_layer("u1", "preference")) == 0
        assert db.get_memory("u1", "core", "c1") is not None  # core untouched

    def test_confidence_stored(self, db: CustomerDatabase):
        """Confidence value should be stored and retrievable."""
        db.set_memory("u1", layer="preference", key="p1", value="v1",
                       source="test", confidence=0.42)
        entry = db.get_memory("u1", "preference", "p1")
        assert abs(entry["confidence"] - 0.42) < 0.01

    def test_source_provenance(self, db: CustomerDatabase):
        """Source field should track provenance."""
        db.set_memory("u1", layer="preference", key="p1", value="v1",
                       source="feedback:gen-abc123")
        entry = db.get_memory("u1", "preference", "p1")
        assert entry["source"] == "feedback:gen-abc123"


# ---------------------------------------------------------------------------
# 2. Multi-User Isolation
# ---------------------------------------------------------------------------

class TestMultiUserIsolation:
    """Verify data isolation between users."""

    def test_memory_isolation(self, db: CustomerDatabase):
        """User A's memory should not be visible to User B."""
        db.set_memory("user_A", layer="core", key="color", value="red", force=True)
        db.set_memory("user_B", layer="core", key="color", value="blue", force=True)
        assert db.get_memory("user_A", "core", "color")["value"] == "red"
        assert db.get_memory("user_B", "core", "color")["value"] == "blue"
        assert db.count_memory("user_A") == 1
        assert db.count_memory("user_B") == 1

    def test_task_isolation(self, db: CustomerDatabase):
        """User A's tasks should not be visible to User B."""
        db.create_task("user_A", task_id="t-a1", brief="A's task", model_used="m1")
        db.create_task("user_B", task_id="t-b1", brief="B's task", model_used="m1")
        assert db.get_task("t-a1")["user_id"] == "user_A"
        assert db.get_task("t-b1")["user_id"] == "user_B"
        # Recent tasks should be isolated
        a_tasks = db.get_recent_tasks("user_A", limit=10)
        assert len(a_tasks) == 1
        assert a_tasks[0]["task_id"] == "t-a1"

    def test_fpar_isolation(self, db: CustomerDatabase):
        """FPAR should be calculated per user."""
        db.create_task("user_A", task_id="t-a1", brief="A1", model_used="m")
        db.update_task_score("t-a1", first_pass_accepted=True)
        db.create_task("user_A", task_id="t-a2", brief="A2", model_used="m")
        db.update_task_score("t-a2", first_pass_accepted=False)

        db.create_task("user_B", task_id="t-b1", brief="B1", model_used="m")
        db.update_task_score("t-b1", first_pass_accepted=True)

        fpar_a = db.calculate_fpar("user_A")
        fpar_b = db.calculate_fpar("user_B")
        assert fpar_a["fpar"] == 50.0  # 1/2
        assert fpar_b["fpar"] == 100.0  # 1/1


# ---------------------------------------------------------------------------
# 3. Generation Tasks & FPAR
# ---------------------------------------------------------------------------

class TestGenerationTasks:
    """Test generation task lifecycle and FPAR metrics."""

    def test_create_task(self, db: CustomerDatabase):
        """Task should be created with all fields."""
        db.create_task("u1", task_id="t1", brief="test image",
                       content_type="image", lifecycle_stage="probation",
                       model_used="gemini", prompt_used="test prompt",
                       enhanced_prompt="enhanced test", design_note="note",
                       result_url="https://cdn.test/img.jpg")
        task = db.get_task("t1")
        assert task["brief"] == "test image"
        assert task["lifecycle_stage"] == "probation"
        assert task["design_note"] == "note"
        assert task["result_url"] == "https://cdn.test/img.jpg"

    def test_update_task_score(self, db: CustomerDatabase):
        """Task scores should be updateable."""
        db.create_task("u1", task_id="t1", brief="test", model_used="m")
        db.update_task_score("t1", score_brand_compliance=4.5,
                             score_brief_fidelity=4.0,
                             score_aesthetic=3.5,
                             score_on_style=4.2,
                             first_pass_accepted=True)
        task = db.get_task("t1")
        assert task["score_brand_compliance"] == 4.5
        assert task["score_brief_fidelity"] == 4.0
        assert task["score_aesthetic"] == 3.5
        assert task["score_on_style"] == 4.2
        assert task["first_pass_accepted"] == 1

    def test_increment_revisions(self, db: CustomerDatabase):
        """Revision count should increment."""
        db.create_task("u1", task_id="t1", brief="test", model_used="m")
        assert db.get_task("t1")["revision_count"] == 0
        db.increment_task_revisions("t1")
        assert db.get_task("t1")["revision_count"] == 1
        db.increment_task_revisions("t1")
        assert db.get_task("t1")["revision_count"] == 2

    def test_complete_task(self, db: CustomerDatabase):
        """Completing a task should set completed_at."""
        db.create_task("u1", task_id="t1", brief="test", model_used="m")
        assert db.get_task("t1")["completed_at"] is None
        db.complete_task("t1")
        assert db.get_task("t1")["completed_at"] is not None

    def test_fpar_basic(self, db: CustomerDatabase):
        """FPAR should correctly calculate pass rate."""
        for i in range(5):
            db.create_task("u1", task_id=f"t{i}", brief=f"task{i}", model_used="m")
            db.update_task_score(f"t{i}", first_pass_accepted=(i < 3))
        result = db.calculate_fpar("u1")
        assert result["fpar"] == 60.0  # 3/5
        assert result["sample_size"] == 5

    def test_fpar_empty(self, db: CustomerDatabase):
        """FPAR with no tasks should return 0."""
        result = db.calculate_fpar("u1")
        assert result["fpar"] == 0.0
        assert result["sample_size"] == 0

    def test_recent_tasks_ordering(self, db: CustomerDatabase):
        """Recent tasks should be ordered by creation time (newest first)."""
        for i in range(5):
            db.create_task("u1", task_id=f"t{i}", brief=f"task{i}", model_used="m")
        tasks = db.get_recent_tasks("u1", limit=3)
        assert len(tasks) == 3
        # Most recent first
        assert tasks[0]["task_id"] == "t4"


# ---------------------------------------------------------------------------
# 4. Quality Metrics & Lifecycle
# ---------------------------------------------------------------------------

class TestQualityMetrics:
    """Test quality metrics module."""

    def test_lifecycle_stages(self):
        """Should have 5 valid stages."""
        from nanobot.utils.quality_metrics import LIFECYCLE_STAGES
        assert len(LIFECYCLE_STAGES) == 5
        assert "new_user" in LIFECYCLE_STAGES
        assert "official" in LIFECYCLE_STAGES

    def test_get_set_lifecycle(self, db: CustomerDatabase):
        """Should persist and retrieve lifecycle stage."""
        from nanobot.utils.quality_metrics import get_lifecycle_stage, set_lifecycle_stage
        # Default for unknown user
        stage = get_lifecycle_stage("new_guy", db=db)
        assert stage == "new_user"
        # Create profile first (required for set_lifecycle_stage)
        db.save_profile("new_guy", {"business": {"name": "Test"}})
        # Set and get
        set_lifecycle_stage("new_guy", "probation", db=db)
        assert get_lifecycle_stage("new_guy", db=db) == "probation"

    def test_stage_gate_insufficient_data(self, db: CustomerDatabase):
        """Gate should not pass without enough tasks."""
        from nanobot.utils.quality_metrics import check_stage_gate, set_lifecycle_stage
        # Create a user in probation with no tasks — gate should block
        db.save_profile("u1", {"business": {"name": "Test"}})
        set_lifecycle_stage("u1", "probation", db=db)
        result = check_stage_gate("u1", db=db)
        assert result["can_advance"] is False
        assert any("min_tasks" in str(b) for b in result.get("blockers", []))

    def test_stage_gate_passes(self, db: CustomerDatabase):
        """Gate should pass with good metrics."""
        from nanobot.utils.quality_metrics import check_stage_gate, set_lifecycle_stage

        # Setup: user in probation with 6 good tasks
        db.save_profile("u1", {"business": {"name": "Test"}})
        set_lifecycle_stage("u1", "probation", db=db)
        for i in range(6):
            db.create_task("u1", task_id=f"t{i}", brief=f"task{i}", model_used="m")
            db.update_task_score(f"t{i}", score_brand_compliance=4.5,
                                 first_pass_accepted=True)
        # Add some memory for completeness
        db.set_memory("u1", layer="core", key="c1", value="v", force=True)
        db.set_memory("u1", layer="style", key="s1", value="v", force=True)
        db.set_memory("u1", layer="preference", key="p1", value="v")

        result = check_stage_gate("u1", db=db)
        assert result["can_advance"] is True

    def test_brand_competence_score(self, db: CustomerDatabase):
        """Brand competence should increase with more memory and better FPAR."""
        from nanobot.utils.quality_metrics import calculate_brand_competence

        # Empty user
        score0 = calculate_brand_competence("empty_user", db=db)
        assert score0 == 0

        # User with some memory
        db.set_memory("u1", layer="core", key="c1", value="v1", force=True)
        db.set_memory("u1", layer="style", key="s1", value="v2", force=True)
        score1 = calculate_brand_competence("u1", db=db)
        assert score1 > 0

        # User with memory + good tasks
        for i in range(5):
            db.create_task("u1", task_id=f"t{i}", brief=f"task{i}", model_used="m")
            db.update_task_score(f"t{i}", first_pass_accepted=True)
        score2 = calculate_brand_competence("u1", db=db)
        assert score2 > score1

    def test_quality_summary_lines(self, db: CustomerDatabase):
        """Summary should return non-empty lines."""
        from nanobot.utils.quality_metrics import get_quality_summary
        db.set_memory("u1", layer="core", key="c1", value="v1", force=True)
        lines = get_quality_summary("u1", db=db)
        assert isinstance(lines, list)
        assert len(lines) > 0
        assert any("Lifecycle" in l for l in lines)


# ---------------------------------------------------------------------------
# 5. Design Notes
# ---------------------------------------------------------------------------

class TestDesignNotes:
    """Test design note building."""

    def test_build_design_note_no_memory(self, db: CustomerDatabase):
        """Design note with no memory should still produce output."""
        from nanobot.utils.design_notes import build_design_note
        note = build_design_note(
            user_id="no_memory_user",
            original_prompt="test prompt",
            enhanced_prompt="test prompt, professional",
            db=db,
        )
        assert isinstance(note, str)
        # Should at least have prompt info
        assert len(note) > 0

    def test_build_design_note_with_memory(self, db: CustomerDatabase):
        """Design note with memory should cite layers."""
        from nanobot.utils.design_notes import build_design_note
        db.set_memory("u1", layer="core", key="color_primary", value="#FF0000",
                       source="test", force=True)
        db.set_memory("u1", layer="style", key="aesthetic", value="minimalist",
                       source="test", force=True)
        note = build_design_note(
            user_id="u1",
            original_prompt="product photo",
            enhanced_prompt="product photo, minimalist clean, #FF0000 accents",
            db=db,
        )
        assert "Core" in note or "core" in note.lower() or "#FF0000" in note

    def test_format_for_chat(self):
        """Chat format should truncate long notes."""
        from nanobot.utils.design_notes import format_design_note_for_chat
        long_note = "Line1\nLine2\nLine3\nLine4\nLine5\nLine6\nLine7"
        short = format_design_note_for_chat(long_note, max_lines=3)
        # Should have max_lines body lines + "..." + header + footer = 3+1+1+1 = 6 lines
        assert "Line1" in short
        assert "Line3" in short
        assert "Line4" not in short  # truncated
        assert "..." in short


# ---------------------------------------------------------------------------
# 6. Profile Completeness
# ---------------------------------------------------------------------------

class TestProfileCompleteness:
    """Test the profile completeness scorer."""

    def test_empty_profile(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        assert get_profile_completeness({}) == 0

    def test_minimal_profile(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = {
            "business": {"name": "Test", "industry": "tech"},
        }
        score = get_profile_completeness(profile)
        assert score == 20  # name(10) + industry(10)

    def test_full_profile(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = {
            "business": {"name": "X", "industry": "tech", "description": "desc"},
            "brand": {
                "style": "minimalist",
                "colorPalette": {"primary": "#FFF", "secondary": "#000", "accent": "#F00"},
                "moodKeywords": ["clean"],
                "photographyStyle": "studio",
                "logoUrl": "https://logo.png",
            },
            "audience": {"gender": "all", "ageRange": "25-35", "segment": "mid"},
            "contentChannels": {"primary": ["instagram"], "defaultFormats": {"instagram_feed": {"aspectRatio": "1:1"}}},
            "preferences": {"communicationLanguage": "vi"},
        }
        score = get_profile_completeness(profile)
        assert score == 100


# ---------------------------------------------------------------------------
# 7. Migration
# ---------------------------------------------------------------------------

class TestMigration:
    """Test profile → brand_memory migration."""

    def test_migrate_profile_to_brand_memory(self, db: CustomerDatabase):
        """Migration should split profile fields into memory layers."""
        from nanobot.db.migrate_to_sqlite import migrate_profile_to_brand_memory

        # Save a rich profile
        profile = {
            "business": {"name": "TestBrand"},
            "brand": {
                "style": "luxury",
                "colorPalette": {"primary": "#000", "secondary": "#FFF"},
                "moodKeywords": ["elegant", "premium"],
                "photographyStyle": "studio soft",
                "avoidList": ["cartoon", "low quality"],
                "logoUrl": "https://logo.png",
            },
            "learningData": {
                "commonFeedback": ["too dark"],
                "bestPerformingPrompts": ["luxury product shot"],
            },
        }
        db.save_profile("u1", profile)

        result = migrate_profile_to_brand_memory("u1", db=db)
        assert result is True

        # Verify core layer
        assert db.get_memory("u1", "core", "color_primary")["value"] == "#000"
        assert db.get_memory("u1", "core", "color_secondary")["value"] == "#FFF"
        assert db.get_memory("u1", "core", "logo")["value"] == "https://logo.png"

        # Verify style layer
        assert db.get_memory("u1", "style", "aesthetic")["value"] == "luxury"
        assert db.get_memory("u1", "style", "photography_style")["value"] == "studio soft"
        assert db.get_memory("u1", "style", "avoid_0")["value"] == "cartoon"

        # Verify preference layer
        pref_layer = db.get_memory_layer("u1", "preference")
        assert len(pref_layer) >= 2  # feedback + prompt

    def test_migrate_empty_profile(self, db: CustomerDatabase):
        """Migration of empty profile should return False."""
        from nanobot.db.migrate_to_sqlite import migrate_profile_to_brand_memory
        db.save_profile("u1", {})
        result = migrate_profile_to_brand_memory("u1", db=db)
        assert result is False

    def test_migrate_idempotent(self, db: CustomerDatabase):
        """Running migration twice should not create duplicates."""
        from nanobot.db.migrate_to_sqlite import migrate_profile_to_brand_memory
        profile = {
            "brand": {"colorPalette": {"primary": "#F00"}, "style": "luxury"},
        }
        db.save_profile("u1", profile)
        migrate_profile_to_brand_memory("u1", db=db)
        count_1 = db.count_memory("u1")
        migrate_profile_to_brand_memory("u1", db=db)
        count_2 = db.count_memory("u1")
        assert count_1 == count_2  # No duplicates


# ---------------------------------------------------------------------------
# 8. Dual-Write Consistency
# ---------------------------------------------------------------------------

class TestDualWriteConsistency:
    """Test that profile tool and learning tool write to both stores."""

    def test_profile_tool_dual_write(self, db: CustomerDatabase):
        """update_customer_profile should write to both profile_json and brand_memory.
        
        This is an integration test that verifies the CONCEPT - actual tool
        execution requires full agent context, so we test the DB operations directly.
        """
        # Simulate what the profile tool does
        db.save_profile("u1", {
            "business": {"name": "Test"},
            "brand": {"colorPalette": {"primary": "#FF0000"}, "style": "luxury"},
        })
        # Dual-write
        db.set_memory("u1", layer="core", key="color_primary",
                       value="#FF0000", source="profile_update:test", force=True)
        db.set_memory("u1", layer="style", key="aesthetic",
                       value="luxury", source="profile_update:test", force=True)

        # Both stores should have consistent data
        profile = db.load_profile("u1")
        assert profile["brand"]["colorPalette"]["primary"] == "#FF0000"
        assert db.get_memory("u1", "core", "color_primary")["value"] == "#FF0000"
        assert db.get_memory("u1", "style", "aesthetic")["value"] == "luxury"
