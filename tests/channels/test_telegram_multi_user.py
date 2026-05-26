import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.telegram import TelegramChannel, TelegramConfig, TelegramKeyStore
from nanobot.config.paths import get_data_dir, get_workspace_path
from nanobot.session.manager import SessionManager


class _FakeMessage:
    def __init__(self, text, chat_id=123, message_id=1):
        self.text = text
        self.chat_id = chat_id
        self.message_id = message_id
        self.chat = SimpleNamespace(type="private", is_forum=False)
        self.reply_to_message = None
        self.location = None
        self.caption = None
        self.photo = None
        self.voice = None
        self.audio = None
        self.document = None
        self.video = None
        self.video_note = None
        self.animation = None
        self.media_group_id = None
        self.message_thread_id = None
        self.replies = []

    async def reply_text(self, text, *args, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=99)


class _FakeUpdate:
    def __init__(self, text, user_id=12345, username="alice", chat_id=123):
        self.message = _FakeMessage(text, chat_id=chat_id)
        self.effective_user = SimpleNamespace(id=user_id, username=username, first_name="Alice")
        self.callback_query = None


@pytest.mark.asyncio
async def test_telegram_keystore(tmp_path, monkeypatch) -> None:
    # Point data_dir to tmp_path
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_data_dir", lambda: tmp_path)

    keystore = TelegramKeyStore()
    assert keystore.get_key("12345|alice") is None

    keystore.set_key("12345|alice", "test-key-123")
    assert keystore.get_key("12345|alice") == "test-key-123"
    assert keystore.get_key("12345") == "test-key-123"  # matches numeric part

    # Reload keystore to test persistence
    keystore2 = TelegramKeyStore()
    assert keystore2.get_key("12345") == "test-key-123"

    keystore2.remove_key("12345")
    assert keystore2.get_key("12345") is None


@pytest.mark.asyncio
async def test_telegram_multi_user_welcome_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_data_dir", lambda: tmp_path)
    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    # Alice has no key yet
    update = _FakeUpdate("hello")
    await channel._on_message(update, None)

    # Check Alice received the welcome prompt
    assert len(update.message.replies) == 1
    assert "Welcome to Vidtory-Agent" in update.message.replies[0][0]


@pytest.mark.asyncio
async def test_telegram_multi_user_configure_and_clear(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.config.paths.get_workspace_path", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_workspace_path", lambda: tmp_path)

    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    # 1. User configures API Key via /apikey
    update_setup = _FakeUpdate("/apikey my-secret-api-key")
    await channel._on_message(update_setup, None)
    assert "configured successfully" in update_setup.message.replies[0][0]
    assert channel.keystore.get_key("12345|alice") == "my-secret-api-key"

    # 2. Check /mykey shows the key masked
    update_mykey = _FakeUpdate("/mykey")
    await channel._on_message(update_mykey, None)
    assert "my-sec...-key" in update_mykey.message.replies[0][0]

    # Create dummy session file & user workspace to check /clear deletes them
    session_file = tmp_path / "sessions" / "telegram_123.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text("dummy history")

    user_ws = tmp_path / "telegram_users" / "123"
    user_ws.mkdir(parents=True, exist_ok=True)
    (user_ws / "some_file.txt").write_text("some user file")

    # 3. Clear data via /clear
    update_clear = _FakeUpdate("/clear")
    await channel._on_message(update_clear, None)
    assert "All data cleared successfully" in update_clear.message.replies[0][0]

    # Check key and files were removed
    assert channel.keystore.get_key("12345|alice") is None
    assert not session_file.exists()
    assert not user_ws.exists()


@pytest.mark.asyncio
async def test_telegram_multi_user_metadata_injection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.config.paths.get_workspace_path", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.get_workspace_path", lambda: tmp_path)

    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    channel.keystore.set_key("12345", "user-key-789")

    # Mock _handle_message to verify metadata injection
    inbound_messages = []
    async def fake_publish_inbound(msg):
        inbound_messages.append(msg)
    monkeypatch.setattr(bus, "publish_inbound", fake_publish_inbound)

    update = _FakeUpdate("hello agent")
    await channel._on_message(update, None)

    assert len(inbound_messages) == 1
    msg = inbound_messages[0]
    assert msg.content == "hello agent"
    assert msg.metadata.get("user_api_key") == "user-key-789"
    assert "telegram_users/123" in msg.metadata.get("user_workspace").replace("\\", "/")
