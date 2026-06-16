from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nanobot.bus.queue import MessageBus
from nanobot.channels.telegram.channel import TelegramChannel
from nanobot.channels.telegram.config import TelegramConfig
from nanobot.channels.telegram.keystore import TelegramKeyStore


@pytest.fixture
def isolated_customer_db(tmp_path, monkeypatch):
    from nanobot.db.customer_db import CustomerDatabase

    db = CustomerDatabase(tmp_path / "customers.db")
    monkeypatch.setattr("nanobot.db.customer_db._db_instance", db)
    yield db
    db.close()


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
async def test_telegram_keystore(tmp_path, monkeypatch, isolated_customer_db) -> None:
    # Point data_dir to tmp_path
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)

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
async def test_telegram_multi_user_welcome_prompt(tmp_path, monkeypatch, isolated_customer_db) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    # Alice has no key yet
    update = _FakeUpdate("hello")
    await channel._on_message(update, None)

    # New users can onboard before they need an API key.
    assert len(update.message.replies) == 1
    assert "Vidtory AI Designer" in update.message.replies[0][0]
    assert "logo" in update.message.replies[0][0].lower()


@pytest.mark.asyncio
async def test_start_begins_onboarding_before_requesting_api_key(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    channel = TelegramChannel(config, MessageBus())

    update = _FakeUpdate("/start")
    await channel._on_start(update, None)

    assert len(update.message.replies) == 1
    reply, kwargs = update.message.replies[0]
    assert "Vidtory AI Designer" in reply
    assert "logo" in reply.lower()
    assert "API Key" not in reply
    assert kwargs.get("reply_markup") is not None

    from nanobot.utils.customer_profile import get_onboarding_status

    assert get_onboarding_status("12345") == "in_progress"


@pytest.mark.asyncio
async def test_start_resumes_legacy_minimal_profile_without_api_key(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, get_onboarding_status

    create_minimal_profile("12345", username="alice")
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )

    update = _FakeUpdate("/start")
    await channel._on_start(update, None)

    assert "API Key" not in update.message.replies[0][0]
    assert "logo" in update.message.replies[0][0].lower()
    assert get_onboarding_status("12345") == "in_progress"


@pytest.mark.asyncio
async def test_in_progress_onboarding_reaches_agent_without_api_key(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "nanobot.channels.telegram.mixins.messages.get_workspace_path",
        lambda: tmp_path,
    )
    from nanobot.utils.customer_profile import create_minimal_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "in_progress"
    save_profile("12345", profile)

    bus = MessageBus()
    inbound_messages = []

    async def fake_publish_inbound(msg):
        inbound_messages.append(msg)

    monkeypatch.setattr(bus, "publish_inbound", fake_publish_inbound)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        bus,
    )

    update = _FakeUpdate("Thương hiệu của tôi là Vidtory")
    await channel._on_message(update, None)

    assert update.message.replies == []
    assert len(inbound_messages) == 1
    assert inbound_messages[0].metadata["user_api_key"] == ""


@pytest.mark.asyncio
async def test_missing_logo_is_requested_before_api_key_for_first_creative_request(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "completed"
    save_profile("12345", profile)

    bus = MessageBus()
    inbound_messages = []

    async def fake_publish_inbound(msg):
        inbound_messages.append(msg)

    monkeypatch.setattr(bus, "publish_inbound", fake_publish_inbound)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        bus,
    )

    update = _FakeUpdate("Tạo ảnh sản phẩm mới")
    await channel._on_message(update, None)

    assert len(update.message.replies) == 1
    assert "logo" in update.message.replies[0][0].lower()
    assert "API Key" not in update.message.replies[0][0]
    assert inbound_messages == []


@pytest.mark.asyncio
async def test_creative_request_with_logo_requires_api_key_before_agent(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "minimal"
    profile["brand"]["logoUrl"] = "https://cdn.example/logo.png"
    save_profile("12345", profile)

    bus = MessageBus()
    inbound_messages = []

    async def fake_publish_inbound(msg):
        inbound_messages.append(msg)

    monkeypatch.setattr(bus, "publish_inbound", fake_publish_inbound)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        bus,
    )

    update = _FakeUpdate("Tạo ảnh quảng cáo")
    await channel._on_message(update, None)

    assert len(update.message.replies) == 1
    assert "Vidtory API Key" in update.message.replies[0][0]
    assert inbound_messages == []


@pytest.mark.asyncio
async def test_logo_skip_is_remembered_before_api_key_gate(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, load_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "completed"
    save_profile("12345", profile)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )

    skip_update = _FakeUpdate("⏩ Tạo không cần logo")
    await channel._on_message(skip_update, None)

    assert "Vidtory API Key" in skip_update.message.replies[0][0]
    assert load_profile("12345")["preferences"]["logoPromptSkipped"] is True

    next_update = _FakeUpdate("Tạo ảnh quảng cáo")
    await channel._on_message(next_update, None)

    assert len(next_update.message.replies) == 1
    assert "Vidtory API Key" in next_update.message.replies[0][0]
    assert "chưa có logo" not in next_update.message.replies[0][0].lower()


@pytest.mark.asyncio
async def test_onboarding_callback_works_without_api_key(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "in_progress"
    save_profile("12345", profile)

    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            require_user_api_key=True,
            inline_keyboards=True,
        ),
        MessageBus(),
    )
    handled = []

    async def capture_handle(**kwargs):
        handled.append(kwargs)

    channel._handle_message = capture_handle
    query = SimpleNamespace(
        id="cb_1",
        data="Clean Premium",
        answer=AsyncMock(),
        message=SimpleNamespace(
            chat_id=123,
            edit_reply_markup=AsyncMock(),
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="alice", first_name="Alice"),
    )

    await channel._on_callback_query(update, None)

    query.answer.assert_awaited_once_with()
    assert handled[0]["content"] == "Clean Premium"


@pytest.mark.asyncio
async def test_callback_does_not_require_key_when_multi_user_mode_is_off(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            require_user_api_key=False,
            inline_keyboards=True,
            allow_from=["*"],
        ),
        MessageBus(),
    )
    handled = []

    async def capture_handle(**kwargs):
        handled.append(kwargs)

    channel._handle_message = capture_handle
    query = SimpleNamespace(
        id="cb_2",
        data="Tạo ảnh quảng cáo",
        answer=AsyncMock(),
        message=SimpleNamespace(
            chat_id=123,
            edit_reply_markup=AsyncMock(),
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="alice", first_name="Alice"),
    )

    await channel._on_callback_query(update, None)

    query.answer.assert_awaited_once_with()
    assert handled[0]["content"] == "Tạo ảnh quảng cáo"


@pytest.mark.asyncio
async def test_telegram_multi_user_configure_and_clearall(tmp_path, monkeypatch, isolated_customer_db) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.config.paths.get_workspace_path", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.mixins.commands.get_workspace_path", lambda: tmp_path)

    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    command_names = {command.command for command in channel.BOT_COMMANDS}
    assert "clear" not in command_names
    assert {"clearall", "clearkey"}.issubset(command_names)

    # 1. User configures API Key via /apikey
    update_setup = _FakeUpdate("/apikey my-secret-api-key")
    await channel._on_api_key_management(update_setup, None)
    assert "Vidtory API Key" in update_setup.message.replies[0][0]
    assert channel.keystore.get_key("12345|alice") == "my-secret-api-key"

    # 2. Check /mykey shows the key masked
    update_mykey = _FakeUpdate("/mykey")
    await channel._on_api_key_management(update_mykey, None)
    assert "my-sec...-key" in update_mykey.message.replies[0][0]

    from nanobot.utils.customer_profile import create_minimal_profile, profile_exists
    from nanobot.db.customer_db import get_db

    create_minimal_profile("12345", username="alice")
    get_db().set_memory("12345", layer="core", key="color_primary", value="#E53935")

    # Create dummy session file & user workspace to check /clearall deletes them
    session_file = tmp_path / "sessions" / "telegram_123.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text("dummy history")

    user_ws = tmp_path / "telegram_users" / "123"
    user_ws.mkdir(parents=True, exist_ok=True)
    (user_ws / "some_file.txt").write_text("some user file")

    # 3. Clear all data via /clearall
    update_clear = _FakeUpdate("/clearall")
    await channel._on_api_key_management(update_clear, None)
    assert "API key" in update_clear.message.replies[0][0]

    # Check key and files were removed
    assert channel.keystore.get_key("12345|alice") is None
    assert not profile_exists("12345")
    assert get_db().get_memory("12345", "core", "color_primary") is None
    assert not session_file.exists()
    assert not user_ws.exists()


@pytest.mark.asyncio
async def test_telegram_clearkey_keeps_brand_profile(tmp_path, monkeypatch, isolated_customer_db) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, profile_exists

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )
    channel.keystore.set_key("12345", "user-key-789")
    create_minimal_profile("12345", username="alice")

    update = _FakeUpdate("/clearkey")
    await channel._on_api_key_management(update, None)

    assert "đã xóa api key" in update.message.replies[0][0].lower()
    assert channel.keystore.get_key("12345|alice") is None
    assert profile_exists("12345")


@pytest.mark.asyncio
async def test_onboarding_website_button_uses_scripted_reply(tmp_path, monkeypatch, isolated_customer_db) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.utils.customer_profile import create_minimal_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "in_progress"
    save_profile("12345", profile)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )

    update = _FakeUpdate("Nhập website")
    await channel._on_message(update, None)

    assert len(update.message.replies) == 1
    reply = update.message.replies[0][0]
    assert "https://vidtory.ai" in reply
    assert "ptit.edu.vn" not in reply.lower()


@pytest.mark.asyncio
async def test_pending_image_set_logo_choice_is_handled_without_llm(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )
    saved = []

    async def fake_save_logo(*, chat_id: str, sender_id: str, media_path: str) -> bool:
        saved.append((chat_id, sender_id, media_path))
        return True

    monkeypatch.setattr(channel, "_save_logo_from_media_path", fake_save_logo)
    channel._pending_media_choices = {
        "123:12345|alice": {
            "media": [str(tmp_path / "logo.png")],
            "metadata": {},
            "session_key": "telegram:123",
            "expires_at": 9999999999,
        }
    }

    await channel._handle_message(
        sender_id="12345|alice",
        chat_id="123",
        content="Dat lam logo",
        metadata={},
        session_key="telegram:123",
    )

    assert saved == [("123", "12345|alice", str(tmp_path / "logo.png"))]


@pytest.mark.asyncio
async def test_logo_reminder_decline_defers_ten_generations(
    tmp_path, monkeypatch, isolated_customer_db
) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    from nanobot.db.customer_db import get_db
    from nanobot.utils.customer_profile import create_minimal_profile, load_profile, save_profile

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "completed"
    profile.setdefault("preferences", {})["logoReminderAwaitingUpload"] = True
    save_profile("12345", profile)
    for index in range(3):
        get_db().record_generation("12345", prompt=f"gen {index}")

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True),
        MessageBus(),
    )
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    )

    await channel._handle_message(
        sender_id="12345|alice",
        chat_id="123",
        content="Chua, nhac sau",
        metadata={},
        session_key="telegram:123",
    )

    prefs = load_profile("12345")["preferences"]
    assert prefs["logoReminderAwaitingUpload"] is False
    assert prefs["logoReminderNextGeneration"] == 13


@pytest.mark.asyncio
async def test_telegram_multi_user_metadata_injection(tmp_path, monkeypatch, isolated_customer_db) -> None:
    monkeypatch.setattr("nanobot.config.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.config.paths.get_workspace_path", lambda: tmp_path)
    monkeypatch.setattr("nanobot.channels.telegram.mixins.commands.get_workspace_path", lambda: tmp_path)

    config = TelegramConfig(enabled=True, token="123:abc", require_user_api_key=True)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    channel.keystore.set_key("12345", "user-key-789")
    monkeypatch.setattr(
        "nanobot.utils.customer_profile.get_onboarding_status",
        lambda uid: "minimal",
    )

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
