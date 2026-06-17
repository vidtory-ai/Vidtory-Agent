import enum
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider


class Intent(str, enum.Enum):
    FASHION = "fashion"
    ADVERTISEMENT = "advertisement"
    GENERAL = "general"


class IntentRouter:
    """Classifies user intent to route them to the appropriate prompt branch."""

    def __init__(self, provider: LLMProvider, model: str):
        self.provider = provider
        self.model = model

    async def classify(self, user_message: str) -> Intent:
        """Classify the user message into one of the Intent enums."""
        if not user_message or not isinstance(user_message, str):
            return Intent.GENERAL

        system_prompt = (
            "You are an intent classifier. Categorize the user's request into exactly one of these categories:\n"
            "- fashion: Requests about clothing, apparel, fashion models, or fashion design.\n"
            "- advertisement: Requests about marketing, product ads, banners, or commercial videos.\n"
            "- general: Any other request.\n"
            "Respond ONLY with the category name in lowercase (fashion, advertisement, or general)."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message[:1000]}  # Limit input length
        ]

        try:
            # We use temperature 0 for deterministic output and small max_tokens
            response = await self.provider.chat_with_retry(
                messages=messages,
                model=self.model,
                temperature=0.0,
                max_tokens=10
            )

            if response.finish_reason == "error":
                logger.warning(f"Intent classification failed: {response.content}")
                return Intent.GENERAL

            content = (response.content or "").strip().lower()

            if "fashion" in content:
                return Intent.FASHION
            if "advertisement" in content:
                return Intent.ADVERTISEMENT

            return Intent.GENERAL
        except Exception as e:
            logger.warning(f"Intent classification threw exception: {e}. Defaulting to general.")
            return Intent.GENERAL
