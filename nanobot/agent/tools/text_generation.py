"""Vidtory Text generation tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    ArraySchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.providers.text_generation import (
    TextGenerationError,
    VidtoryTextGenerationClient,
)
from nanobot.security.request_policy import evaluate_request, is_resident_designer_profile


class TextGenerationToolConfig(Base):
    """Text generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "gemini-3-flash-preview"


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "The text/content generation prompt. Describe what content should be generated.",
            min_length=1,
        ),
        model_id=StringSchema(
            "Optional model ID to use, e.g. gemini-3-flash-preview.",
        ),
        start_images=ArraySchema(
            StringSchema("Local path or URL of an image to use as visual context for the text generation."),
            description="Optional images to provide visual context for the text generation.",
        ),
        required=["prompt"],
    )
)
class TextGenerationTool(Tool):
    """Generate text content using the Vidtory B2B text generation API.
    Use this to generate marketing copy, descriptions, scripts, captions, or any text content.
    """

    config_key = "text_generation"

    @classmethod
    def config_cls(cls):
        return TextGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        cfg = getattr(ctx.config, "text_generation", None)
        return cfg.enabled if cfg else True

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        provider_config = ctx.providers.vidtory if ctx.providers else None
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "text_generation", None) or TextGenerationToolConfig(),
            provider_config=provider_config,
            capability_profile=getattr(ctx.config, "capability_profile", "standard"),
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: TextGenerationToolConfig,
        provider_config: Any | None = None,
        capability_profile: str = "standard",
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config
        self.capability_profile = capability_profile

    @property
    def name(self) -> str:
        return "generate_text"

    @property
    def description(self) -> str:
        return (
            "Generate text content (marketing copy, scripts, captions, descriptions) "
            "using Vidtory's AI text generation API. Returns the generated text directly."
        )

    def _provider_client(self) -> VidtoryTextGenerationClient:
        from nanobot.utils.context_vars import telegram_vidtory_api_key
        user_key = telegram_vidtory_api_key.get()
        api_key = user_key or (self.provider_config.api_key if self.provider_config else None)
        api_base = self.provider_config.api_base if self.provider_config else None
        return VidtoryTextGenerationClient(
            api_key=api_key,
            api_base=api_base,
        )

    async def execute(
        self,
        prompt: str,
        model_id: str | None = None,
        start_images: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        if is_resident_designer_profile(self.capability_profile):
            policy = evaluate_request(self.capability_profile, prompt)
            if policy.blocked:
                return (
                    "Error: text generation prompt blocked by resident_designer "
                    f"security policy ({policy.reason})"
                )
            if policy.redacted_text and policy.redacted_text.strip():
                prompt = policy.redacted_text
        client = self._provider_client()

        try:
            response = await client.generate(
                prompt=prompt,
                model_id=model_id or self.config.model,
                start_images=start_images or [],
            )
            return response.text or "No text was generated."

        except (TextGenerationError, OSError) as exc:
            return f"Error: {exc}"
