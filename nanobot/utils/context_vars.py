"""Context variables for Telegram multi-user dynamic authentication and workspace isolation."""

from contextvars import ContextVar

# Dynamic API key overrides for OpenAI Compat Provider & Creative tools (Image/Video/Audio)
telegram_user_api_key: ContextVar[str] = ContextVar("telegram_user_api_key", default="")

# Isolated workspace path override for path resolution and shell commands
telegram_user_workspace: ContextVar[str] = ContextVar("telegram_user_workspace", default="")
