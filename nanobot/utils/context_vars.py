"""Context variables for Telegram multi-user dynamic authentication and workspace isolation."""

from contextvars import ContextVar
from typing import Any

# Vidtory API key for ALL Vidtory-backed operations:
# - LLM text generation (VidtoryLLMProvider → /generative-core/text)
# - Image generation (VidtoryImageGenerationClient → /generative-core/image)
# - Video, audio, watermark removal tools
# This is the per-user Vidtory merchant key stored in TelegramKeyStore.
# Set before each agent invocation so all providers pick it up from context.
telegram_vidtory_api_key: ContextVar[str] = ContextVar("telegram_vidtory_api_key", default="")

# Dynamic API key override for OpenAI Compat Provider (LLM calls).
# Only set this when the user provides their own non-Vidtory LLM API key.
# In the standard requireUserApiKey=True flow, users provide a Vidtory key,
# so this should remain empty — LLM uses telegram_vidtory_api_key instead.
telegram_user_api_key: ContextVar[str] = ContextVar("telegram_user_api_key", default="")

# Isolated workspace path override for path resolution and shell commands
telegram_user_workspace: ContextVar[str] = ContextVar("telegram_user_workspace", default="")

# Customer profile for brand-aware prompt optimization (dict or None)
telegram_customer_profile: ContextVar[dict[str, Any] | None] = ContextVar(
    "telegram_customer_profile", default=None
)
