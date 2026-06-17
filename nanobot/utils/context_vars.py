"""Context variables for Telegram multi-user dynamic auth and workspace isolation."""

from contextvars import ContextVar
from typing import Any

# Per-user Vidtory merchant key stored in TelegramKeyStore.
telegram_vidtory_api_key: ContextVar[str] = ContextVar("telegram_vidtory_api_key", default="")

# True when a Telegram request is expected to spend the user's own Vidtory key.
telegram_requires_user_vidtory_api_key: ContextVar[bool] = ContextVar(
    "telegram_requires_user_vidtory_api_key", default=False
)

# Dynamic API key override for OpenAI Compat Provider (LLM calls).
# Only set this when the user provides their own non-Vidtory LLM API key.
# In the standard requireUserApiKey=True flow, users provide a Vidtory key,
# so this should remain empty. LLM uses telegram_vidtory_api_key instead.
telegram_user_api_key: ContextVar[str] = ContextVar("telegram_user_api_key", default="")

# Isolated workspace path override for path resolution and shell commands.
telegram_user_workspace: ContextVar[str] = ContextVar("telegram_user_workspace", default="")

# Customer profile for brand-aware prompt optimization (dict or None).
telegram_customer_profile: ContextVar[dict[str, Any] | None] = ContextVar(
    "telegram_customer_profile", default=None
)


def effective_vidtory_api_key(config_api_key: str | None = None) -> str | None:
    """Return the Vidtory key allowed for the current operation."""

    user_key = (telegram_vidtory_api_key.get() or "").strip()
    if user_key:
        return user_key
    if telegram_requires_user_vidtory_api_key.get():
        return None
    return config_api_key
