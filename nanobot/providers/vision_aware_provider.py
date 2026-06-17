"""
Vision-aware provider router.

Routes LLM requests based on whether the messages contain image content:
  - Messages WITH images  → vision_provider (e.g. Codex, Claude, Gemini)
  - Messages WITHOUT images → text_provider (e.g. DeepSeek via DS2API)

This implements the user's design:
  "DeepSeek handles text-only tasks (cheap, fast).
   Codex handles vision tasks (can read images, generates best prompts)."
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse


def _messages_have_images(messages: list[dict[str, Any]]) -> bool:
    """Return True if any message contains an image_url content block."""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    return True
    return False


class VisionAwareProvider(LLMProvider):
    """Route requests to different providers based on image content.

    - text_provider  : handles text-only requests (e.g. DeepSeek via DS2API)
    - vision_provider: handles requests that include images (e.g. Codex)

    The routing decision is made BEFORE the API call, not after an error,
    so there is zero latency penalty and no wasted requests.
    """

    def __init__(
        self,
        text_provider: LLMProvider,
        vision_provider: LLMProvider,
    ) -> None:
        # Do NOT call super().__init__() — api_key/api_base are meaningless here.
        self._text = text_provider
        self._vision = vision_provider

    # ── generation settings passthrough (mirrors FallbackProvider) ──────────

    @property
    def generation(self):
        return self._text.generation

    @generation.setter
    def generation(self, value):
        self._text.generation = value
        self._vision.generation = value

    @property
    def supports_progress_deltas(self) -> bool:
        return bool(getattr(self._text, "supports_progress_deltas", False))

    def get_default_model(self) -> str:
        return self._text.get_default_model()

    # ── routing helper ───────────────────────────────────────────────────────

    def _pick(self, messages: list[dict[str, Any]]) -> tuple[LLMProvider, str]:
        """Return (provider, label) for the given messages."""
        if _messages_have_images(messages):
            return self._vision, "vision"
        return self._text, "text"

    # ── LLMProvider interface ────────────────────────────────────────────────

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        provider, label = self._pick(messages)
        logger.debug("VisionAwareProvider: routing to {} provider ({})", label, provider.get_default_model())
        return await provider.chat(messages=messages, **kwargs)

    async def chat_stream(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        provider, label = self._pick(messages)
        logger.debug("VisionAwareProvider: routing to {} provider ({})", label, provider.get_default_model())
        return await provider.chat_stream(messages=messages, **kwargs)

    async def chat_stream_with_retry(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        provider, label = self._pick(messages)
        logger.debug("VisionAwareProvider: routing to {} provider ({})", label, provider.get_default_model())
        return await provider.chat_stream_with_retry(messages=messages, **kwargs)

    async def chat_with_retry(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        provider, label = self._pick(messages)
        logger.debug("VisionAwareProvider: routing to {} provider ({})", label, provider.get_default_model())
        return await provider.chat_with_retry(messages=messages, **kwargs)
