from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nanobot.bus.queue import MessageBus
from nanobot.channels.telegram.channel import TelegramChannel
from nanobot.channels.telegram.config import TelegramConfig


@pytest.mark.asyncio
async def test_brand_command_renders_profile_with_html_and_buttons(monkeypatch) -> None:
    profile = {
        "business": {
            "name": "Vidtory & Co",
            "industry": "technology",
            "description": "Công ty công nghệ hiện đại",
        },
        "brand": {
            "style": "minimalist",
            "moodKeywords": ["hiện đại", "công nghệ"],
            "colorPalette": "#17250D",
            "photographyStyle": "modern clean tech aesthetic",
            "logoUrl": "https://example.com/logo.png?size=2&mode=fit",
            "avoidList": [],
        },
        "audience": {"ageRange": "", "segment": "mid"},
        "contentChannels": {"primary": []},
        "onboarding": {"status": "minimal"},
        "learningData": {},
    }
    monkeypatch.setattr(
        "nanobot.utils.customer_profile.load_profile",
        lambda _user_id: profile,
    )

    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            allow_from=["*"],
            group_policy="open",
            inline_keyboards=True,
        ),
        MessageBus(),
    )
    message = SimpleNamespace(
        text="/brand",
        caption=None,
        chat_id=12345,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(
            id=7196691509,
            username="toan",
            first_name="Toan",
        ),
    )

    handled = await channel._handle_api_key_commands(update)

    assert handled is True
    message.reply_text.assert_awaited_once()
    call = message.reply_text.await_args
    assert "<b>Brand Profile</b>" in call.args[0]
    assert "Vidtory &amp; Co" in call.args[0]
    assert call.kwargs["parse_mode"] == "HTML"
    assert call.kwargs["reply_markup"] is not None
