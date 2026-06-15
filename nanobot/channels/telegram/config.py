from typing import Literal

from pydantic import Field

from nanobot.config.schema import Base

_STREAM_EDIT_INTERVAL_DEFAULT = 0.6  # min seconds between edit_message_text calls

class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    proxy: str | None = None
    reply_to_message: bool = False
    react_emoji: str = "👀"
    remove_react_emoji: bool = True
    react_remove_delay: float = 5.0
    group_policy: Literal["open", "mention"] = "mention"
    connection_pool_size: int = 32
    pool_timeout: float = 5.0
    streaming: bool = True
    # Enable inline keyboard buttons in Telegram messages.
    inline_keyboards: bool = False
    stream_edit_interval: float = Field(default=_STREAM_EDIT_INTERVAL_DEFAULT, ge=0.1)
    require_user_api_key: bool = False
