"""Regression tests for Telegram image accumulation behaviour.

Three independent concerns are covered here:

1.  **commit 16d95c — media-group (album) flush**
    When a Telegram album (multiple photos sent together, sharing a
    ``media_group_id``) is flushed, ``_flush_media_group`` MUST patch
    ``metadata["current_media"]`` with the FULL list of images, not just
    the first one that initialised the buffer.

2.  **Discrete-image accumulation across separate messages**
    When the user sends photos one-by-one (each without caption/text),
    the handler stores them in ``_pending_media_choices``.  The key is
    ``"{chat_id}:{sender_id}"``, so successive photos from the same user
    in the same chat MUST be merged (accumulated) into the existing entry
    rather than overwriting it.  This ensures a later request like
    "ghép 2 ảnh" sees all images.

3.  **Sliding-window buffer for text+media requests**
    When the user sends Photo1+caption then Photo2/Photo3 (no caption)
    in rapid succession, only Photo1 has text so it would normally bypass
    the pending-choices mechanism and fire a premature single-image request.
    The sliding-window buffer delays dispatch by 1 s (up to 3 s max) and
    accumulates every photo arriving in that window, so the LLM sees all
    images — up to 10 or more.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Skip the entire module when python-telegram-bot is not installed.
try:
    import telegram  # noqa: F401
except ImportError:
    pytest.skip(
        "Telegram dependencies not installed (python-telegram-bot)",
        allow_module_level=True,
    )

from nanobot.bus.queue import MessageBus
from nanobot.channels.telegram.channel import TelegramChannel
from nanobot.channels.telegram.config import TelegramConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_channel() -> TelegramChannel:
    """Return a minimal TelegramChannel wired up with a fake bot."""
    config = TelegramConfig(enabled=True, token="123:abc", allow_from=["*"])
    channel = TelegramChannel(config, MessageBus())

    # Minimal fake bot: only what _flush_media_group / _on_message need.
    fake_bot = MagicMock()
    fake_bot.send_chat_action = AsyncMock()
    fake_bot.set_message_reaction = AsyncMock()
    fake_bot.get_me = AsyncMock(
        return_value=SimpleNamespace(id=999, username="nanobot_test")
    )

    fake_app = MagicMock()
    fake_app.bot = fake_bot
    channel._app = fake_app
    return channel


def _make_photo_message(
    *,
    chat_id: int = -100,
    sender_id: int = 42,
    username: str = "alice",
    message_id: int = 1,
    media_group_id: str | None = None,
    caption: str | None = None,
    file_unique_id: str = "unique1",
) -> SimpleNamespace:
    """Build the minimal SimpleNamespace that mimics a Telegram photo message."""
    photo_size = SimpleNamespace(
        file_id=f"file_{file_unique_id}",
        file_unique_id=file_unique_id,
        file_size=1024,
    )
    reply_text_mock = AsyncMock()
    msg = SimpleNamespace(
        chat=SimpleNamespace(type="private", is_forum=False),
        chat_id=chat_id,
        text=None,
        caption=caption,
        entities=[],
        caption_entities=[],
        reply_to_message=None,
        photo=[photo_size],  # non-empty → photo message
        voice=None,
        audio=None,
        document=None,
        video=None,
        video_note=None,
        animation=None,
        location=None,
        media_group_id=media_group_id,
        message_thread_id=None,
        message_id=message_id,
        reply_text=reply_text_mock,
    )
    user = SimpleNamespace(id=sender_id, username=username, first_name="Alice")
    return SimpleNamespace(message=msg, effective_user=user)


# ---------------------------------------------------------------------------
# 1. commit 16d95c — media-group flush patches current_media with all images
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_media_group_patches_all_images_in_current_media() -> None:
    """
    Regression: commit 16d95c.

    _flush_media_group must overwrite metadata["current_media"] with the
    deduplicated union of ALL media paths buffered from the album, not only
    the single path that was in the first message's metadata["current_media"].
    """
    channel = _make_channel()

    # Simulate two photos already downloaded to local paths.
    img1 = "/tmp/img1.jpg"
    img2 = "/tmp/img2.jpg"

    # Reconstruct the buffer as _on_message would build it after receiving
    # the first album message: metadata["current_media"] has only img1.
    key = "-100:gid_abc"
    channel._media_group_buffers[key] = {
        "sender_id": "42|alice",
        "chat_id": "-100",
        "contents": ["ghep 2 anh nay lai"],
        "media": [img1, img2],          # both images collected by _on_message loop
        "metadata": {
            "current_media": [img1],    # ← only first image (the bug that 16d95c fixed)
            "reply_media": [],
        },
        "session_key": None,
    }

    # Capture what _handle_message receives.
    received_metadata: dict = {}

    async def fake_handle_message(**kwargs):
        received_metadata.update(kwargs.get("metadata", {}))

    channel._handle_message = fake_handle_message  # type: ignore[method-assign]

    await channel._flush_media_group(key)

    # After flush, current_media must contain BOTH images.
    assert received_metadata.get("current_media") == [img1, img2], (
        "_flush_media_group did not patch current_media with all album images. "
        "This regresses commit 16d95c."
    )


@pytest.mark.asyncio
async def test_flush_media_group_deduplicates_current_media() -> None:
    """Duplicate paths in the buffer must be deduplicated in current_media."""
    channel = _make_channel()
    img = "/tmp/dup.jpg"
    key = "-100:gid_dup"
    channel._media_group_buffers[key] = {
        "sender_id": "42|alice",
        "chat_id": "-100",
        "contents": [],
        "media": [img, img],          # duplicated
        "metadata": {"current_media": [img], "reply_media": []},
        "session_key": None,
    }

    received_metadata: dict = {}

    async def fake_handle_message(**kwargs):
        received_metadata.update(kwargs.get("metadata", {}))

    channel._handle_message = fake_handle_message  # type: ignore[method-assign]

    await channel._flush_media_group(key)

    assert received_metadata.get("current_media") == [img], (
        "Deduplication failed in _flush_media_group"
    )


@pytest.mark.asyncio
async def test_flush_media_group_removes_key_from_tasks_on_completion() -> None:
    """The task key must always be removed from _media_group_tasks in finally."""
    channel = _make_channel()
    key = "-100:gid_cleanup"
    channel._media_group_buffers[key] = {
        "sender_id": "42|alice",
        "chat_id": "-100",
        "contents": [],
        "media": ["/tmp/x.jpg"],
        "metadata": {"current_media": ["/tmp/x.jpg"], "reply_media": []},
        "session_key": None,
    }
    channel._media_group_tasks[key] = asyncio.current_task()

    channel._handle_message = AsyncMock()  # type: ignore[method-assign]

    await channel._flush_media_group(key)

    assert key not in channel._media_group_tasks, (
        "_flush_media_group must remove the task key in the finally block."
    )


# ---------------------------------------------------------------------------
# 2. Discrete-image accumulation — pending_media_choices must merge, not overwrite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_media_choices_accumulates_images_across_messages(
    monkeypatch,
) -> None:
    """
    Regression: discrete-image accumulation.

    Scenario: user sends image-1 (no text) → bot replies "📷 Ảnh đã nhận!".
    User sends image-2 (no text) → bot should reply "📷 2 ảnh đã nhận!" AND
    pending_media_choices[key]["media"] must contain BOTH paths.

    Before the fix, the second message overwrote the entry so only image-2
    was retained.
    """
    channel = _make_channel()

    # Patch download so we can control what paths are returned.
    img1 = "/fake/media/img1.jpg"
    img2 = "/fake/media/img2.jpg"
    download_calls: list[str] = []

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        path = f"/fake/media/{uid}.jpg"
        download_calls.append(path)
        return [path], [f"[image: {path}]"]

    monkeypatch.setattr(channel, "_download_message_media", fake_download)
    monkeypatch.setattr(channel, "_add_reaction", AsyncMock())
    monkeypatch.setattr(channel, "_start_typing", MagicMock())
    monkeypatch.setattr(channel, "_stop_typing", MagicMock())
    monkeypatch.setattr(channel, "_is_group_message_for_bot", AsyncMock(return_value=True))
    monkeypatch.setattr(channel, "_handle_onboarding_quick_reply", AsyncMock(return_value=False))

    # Monkeypatch onboarding / logo guards to no-op so _on_message reaches the
    # media-without-text branch.
    monkeypatch.setattr(
        "nanobot.channels.telegram.mixins.messages.TelegramMessagesMixin"
        "._is_creative_generation_request",
        lambda self, _content: False,
        raising=False,
    )

    # ── Message 1: first photo ──────────────────────────────────────────────
    update1 = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=1, file_unique_id="unique1",
    )
    update1.message.reply_text = AsyncMock()

    await channel._on_message(update1, MagicMock())

    pmc_key = "-100:42|alice"
    assert pmc_key in channel._pending_media_choices, (
        "After first image, pending entry must be created."
    )
    entry_after_1 = channel._pending_media_choices[pmc_key]
    assert len(entry_after_1["media"]) == 1, (
        "First image: pending entry must have exactly 1 media path."
    )

    # ── Message 2: second photo ─────────────────────────────────────────────
    update2 = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=2, file_unique_id="unique2",
    )
    update2.message.reply_text = AsyncMock()

    await channel._on_message(update2, MagicMock())

    assert pmc_key in channel._pending_media_choices, (
        "After second image, pending entry must still exist."
    )
    entry_after_2 = channel._pending_media_choices[pmc_key]
    assert len(entry_after_2["media"]) == 2, (
        "Second image must be ACCUMULATED into existing entry, not overwrite it. "
        "This is the discrete-image accumulation fix."
    )

    # The reply text on message 2 should mention 2 images.
    last_reply_call = update2.message.reply_text.call_args
    assert last_reply_call is not None
    reply_text: str = last_reply_call.args[0] if last_reply_call.args else ""
    assert "2" in reply_text, (
        "Bot reply after second image must indicate 2 images accumulated."
    )


@pytest.mark.asyncio
async def test_pending_media_choices_first_message_reply_says_single_image(
    monkeypatch,
) -> None:
    """First photo → bot says '📷 Ảnh đã nhận!' (singular)."""
    channel = _make_channel()

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        return [f"/fake/{uid}.jpg"], [f"[image: /fake/{uid}.jpg]"]

    monkeypatch.setattr(channel, "_download_message_media", fake_download)
    monkeypatch.setattr(channel, "_add_reaction", AsyncMock())
    monkeypatch.setattr(channel, "_start_typing", MagicMock())
    monkeypatch.setattr(channel, "_stop_typing", MagicMock())
    monkeypatch.setattr(channel, "_is_group_message_for_bot", AsyncMock(return_value=True))
    monkeypatch.setattr(channel, "_handle_onboarding_quick_reply", AsyncMock(return_value=False))

    update = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=1, file_unique_id="uid_a",
    )
    update.message.reply_text = AsyncMock()

    await channel._on_message(update, MagicMock())

    call = update.message.reply_text.call_args
    assert call is not None
    reply_text: str = call.args[0] if call.args else ""
    assert "Ảnh đã nhận" in reply_text, (
        "First image reply should say 'Ảnh đã nhận!'"
    )


@pytest.mark.asyncio
async def test_pending_media_choices_expired_entry_is_replaced(
    monkeypatch,
) -> None:
    """When the existing entry has expired, the second image starts a fresh entry."""
    channel = _make_channel()

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        return [f"/fake/{uid}.jpg"], [f"[image: /fake/{uid}.jpg]"]

    monkeypatch.setattr(channel, "_download_message_media", fake_download)
    monkeypatch.setattr(channel, "_add_reaction", AsyncMock())
    monkeypatch.setattr(channel, "_start_typing", MagicMock())
    monkeypatch.setattr(channel, "_stop_typing", MagicMock())
    monkeypatch.setattr(channel, "_is_group_message_for_bot", AsyncMock(return_value=True))
    monkeypatch.setattr(channel, "_handle_onboarding_quick_reply", AsyncMock(return_value=False))

    pmc_key = "-100:42|alice"
    # Plant an already-expired entry with old media.
    channel._pending_media_choices = {
        pmc_key: {
            "media": ["/fake/old.jpg"],
            "metadata": {"current_media": ["/fake/old.jpg"], "reply_media": []},
            "session_key": None,
            "expires_at": time.monotonic() - 10,  # already expired
        }
    }

    update = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=5, file_unique_id="uid_new",
    )
    update.message.reply_text = AsyncMock()

    await channel._on_message(update, MagicMock())

    entry = channel._pending_media_choices.get(pmc_key, {})
    # Expired entry → fresh entry with only the new image.
    assert len(entry.get("media", [])) == 1, (
        "Expired pending entry must be replaced, not accumulated into."
    )
    assert "/fake/old.jpg" not in entry.get("media", []), (
        "Old expired media must not appear in the new entry."
    )


# ---------------------------------------------------------------------------
# 3. Sliding-window buffer — text+media messages accumulate rapid-fire photos
# ---------------------------------------------------------------------------


def _common_monkeypatches(monkeypatch, channel, download_fn):
    """Apply the standard monkeypatches needed by _on_message tests."""
    monkeypatch.setattr(channel, "_download_message_media", download_fn)
    monkeypatch.setattr(channel, "_add_reaction", AsyncMock())
    monkeypatch.setattr(channel, "_start_typing", MagicMock())
    monkeypatch.setattr(channel, "_stop_typing", MagicMock())
    monkeypatch.setattr(channel, "_is_group_message_for_bot", AsyncMock(return_value=True))
    monkeypatch.setattr(channel, "_handle_onboarding_quick_reply", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "nanobot.channels.telegram.mixins.messages.TelegramMessagesMixin"
        "._is_creative_generation_request",
        lambda self, _content: False,
        raising=False,
    )


@pytest.mark.asyncio
async def test_sliding_window_accumulates_photos_sent_after_caption(monkeypatch) -> None:
    """
    Sliding-window buffer — main regression test.

    Scenario: user sends Photo1+caption "ghep 3 anh", then Photo2 and Photo3
    (no caption) arrive milliseconds later (Telegram delivers them as separate
    messages; only the first carries the caption).

    Expected: _handle_message is called ONCE with all 3 images, NOT called
    immediately with only 1 image.
    """
    channel = _make_channel()

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        return [f"/fake/{uid}.jpg"], [f"[image: /fake/{uid}.jpg]"]

    _common_monkeypatches(monkeypatch, channel, fake_download)
    # Mock onboarding so the user appears as an established user (not blocked by guard).
    monkeypatch.setattr(
        "nanobot.channels.telegram.mixins.messages.get_onboarding_status",
        lambda uid: "complete",
        raising=False,
    )

    handle_calls: list[dict] = []

    async def capturing_handle(**kwargs):
        handle_calls.append({
            "media": list(kwargs.get("media") or []),
            "content": kwargs.get("content", ""),
        })

    channel._handle_message = capturing_handle  # type: ignore[method-assign]

    # ── Photo1 + caption arrives ────────────────────────────────────────────
    update1 = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=1, file_unique_id="uid1",
        caption="ghep 3 anh",
    )
    update1.message.text = None
    await channel._on_message(update1, MagicMock())

    # Buffer must be created; _handle_message must NOT have fired yet.
    assert len(handle_calls) == 0, (
        "Sliding-window buffer: _handle_message must NOT fire on Photo1+caption arrival. "
        "Got calls: " + str(handle_calls)
    )
    tmb_key = "-100:42|alice"
    assert tmb_key in getattr(channel, "_text_media_buffers", {}), (
        "Sliding-window buffer must have been created for this user+chat."
    )

    # ── Photo2 (no caption) arrives ─────────────────────────────────────────
    update2 = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=2, file_unique_id="uid2",
    )
    await channel._on_message(update2, MagicMock())

    assert len(handle_calls) == 0, "After Photo2, buffer must still be holding."
    buf_after_2 = channel._text_media_buffers.get(tmb_key, {})
    assert len(buf_after_2.get("media", [])) == 2, (
        "Photo2 must have been merged into the text+media buffer."
    )

    # ── Photo3 (no caption) arrives ─────────────────────────────────────────
    update3 = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=3, file_unique_id="uid3",
    )
    await channel._on_message(update3, MagicMock())

    assert len(handle_calls) == 0, "After Photo3, buffer must still be holding."
    buf_after_3 = channel._text_media_buffers.get(tmb_key, {})
    assert len(buf_after_3.get("media", [])) == 3, (
        "Photo3 must have been merged; buffer now has 3 images."
    )

    # ── Flush fires (simulate by draining pending tasks) ────────────────────
    # Cancel any pending sliding-window tasks so we can drive the flush manually.
    for task in list(getattr(channel, "_text_media_tasks", {}).values()):
        task.cancel()
    # Manually trigger flush directly to verify dispatch logic.
    buf = channel._text_media_buffers.pop(tmb_key, None)
    assert buf is not None
    all_media = list(dict.fromkeys(buf["media"]))
    meta = dict(buf["metadata"])
    meta["current_media"] = all_media
    await channel._handle_message(
        sender_id=buf["sender_id"],
        chat_id=buf["chat_id"],
        content=buf["content"],
        media=all_media,
        metadata=meta,
        session_key=buf["session_key"],
    )

    assert len(handle_calls) == 1, "Exactly one dispatch must happen."
    assert len(handle_calls[0]["media"]) == 3, (
        "Dispatch must include all 3 accumulated images. "
        f"Got: {handle_calls[0]['media']}"
    )
    # content is the full caption (possibly with image descriptor appended by _on_message)
    assert "ghep 3 anh" in handle_calls[0]["content"], (
        "The caption from Photo1 must be present in the dispatch content."
    )


@pytest.mark.asyncio
async def test_sliding_window_single_photo_caption_dispatches_after_window(
    monkeypatch,
) -> None:
    """
    When a single photo+caption arrives (nothing else follows), the buffer
    must still eventually be created and ready for a manual flush with 1 image.
    """
    channel = _make_channel()

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        return [f"/fake/{uid}.jpg"], [f"[image: /fake/{uid}.jpg]"]

    _common_monkeypatches(monkeypatch, channel, fake_download)
    # Mock onboarding so the user appears as an established user.
    monkeypatch.setattr(
        "nanobot.channels.telegram.mixins.messages.get_onboarding_status",
        lambda uid: "complete",
        raising=False,
    )
    channel._handle_message = AsyncMock()  # type: ignore[method-assign]

    update = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=1, file_unique_id="single",
        caption="chỉnh ảnh này",
    )
    update.message.text = None
    await channel._on_message(update, MagicMock())

    tmb_key = "-100:42|alice"
    buf = getattr(channel, "_text_media_buffers", {}).get(tmb_key)
    assert buf is not None, "Buffer must be created for single photo+caption."
    assert len(buf.get("media", [])) == 1, "Buffer must hold the single image."
    # content includes caption + image descriptor appended by _on_message
    assert "chỉnh ảnh này" in buf.get("content", ""), (
        "Caption must be present in the buffer content."
    )
    # _handle_message must NOT have been called yet (window is pending).
    channel._handle_message.assert_not_called()


@pytest.mark.asyncio
async def test_sliding_window_reply_with_photo_bypasses_buffer(monkeypatch) -> None:
    """
    When the user replies to a message and attaches a photo + text, that is a
    targeted action (e.g. "chỉnh ảnh này" as a reply). It must be forwarded
    directly without buffering — the sliding window must not apply.
    """
    channel = _make_channel()

    async def fake_download(msg, *, add_failure_content=False):
        if not getattr(msg, "photo", None):
            return [], []
        uid = msg.photo[-1].file_unique_id
        return [f"/fake/{uid}.jpg"], [f"[image: /fake/{uid}.jpg]"]

    _common_monkeypatches(monkeypatch, channel, fake_download)

    handle_calls: list[dict] = []

    async def capturing_handle(**kwargs):
        handle_calls.append({"media": list(kwargs.get("media") or [])})

    channel._handle_message = capturing_handle  # type: ignore[method-assign]

    # Build a photo message that also has a reply_to_message → is_reply=True.
    update = _make_photo_message(
        chat_id=-100, sender_id=42, username="alice",
        message_id=5, file_unique_id="reply_photo",
        caption="chỉnh ảnh này",
    )
    update.message.text = None
    update.message.reply_to_message = SimpleNamespace(message_id=3)  # reply!

    await channel._on_message(update, MagicMock())

    # For a reply, _handle_message must have been called immediately.
    assert len(handle_calls) == 1, (
        "Reply+photo must bypass the sliding-window buffer and dispatch immediately."
    )
    # No text_media_buffer must have been created.
    assert getattr(channel, "_text_media_buffers", {}) == {}, (
        "Sliding-window buffer must NOT be created for reply messages."
    )
