"""Vidtory Remove Watermark tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    BooleanSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.providers.watermark_removal import (
    WatermarkRemovalError,
    VidtoryWatermarkRemovalClient,
)
from nanobot.utils.artifacts import store_generated_image_artifact


class WatermarkRemovalToolConfig(Base):
    """Watermark removal tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    save_dir: str = "generated"


@tool_parameters(
    tool_parameters_schema(
        image_path=StringSchema(
            "Local path of the image to remove watermark from. Must be an existing file artifact.",
            min_length=1,
        ),
        remove_text=BooleanSchema(
            description="If true, removes text watermarks as well (may remove all text from image). Default: false.",
            default=False,
        ),
        required=["image_path"],
    )
)
class WatermarkRemovalTool(Tool):
    """Remove watermarks from images using Vidtory's AI dewatermarking API.
    Supports JPEG, PNG, and WEBP images. Returns a clean version of the image as an artifact.
    """

    config_key = "watermark_removal"

    @classmethod
    def config_cls(cls):
        return WatermarkRemovalToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        cfg = getattr(ctx.config, "watermark_removal", None)
        return cfg.enabled if cfg else True

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        provider_config = ctx.providers.vidtory if ctx.providers else None
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "watermark_removal", None) or WatermarkRemovalToolConfig(),
            provider_config=provider_config,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: WatermarkRemovalToolConfig,
        provider_config: Any | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config

    @property
    def name(self) -> str:
        return "remove_watermark"

    @property
    def description(self) -> str:
        return (
            "Remove watermarks from images using Vidtory's AI dewatermarking API. "
            "Upload a local image and get a clean version back as an artifact. "
            "Deliver result to user via the message tool."
        )

    def _provider_client(self) -> VidtoryWatermarkRemovalClient:
        from nanobot.utils.context_vars import telegram_user_api_key
        user_key = telegram_user_api_key.get()
        api_key = user_key or (self.provider_config.api_key if self.provider_config else None)
        api_base = self.provider_config.api_base if self.provider_config else None
        return VidtoryWatermarkRemovalClient(
            api_key=api_key,
            api_base=api_base,
        )

    def _resolve_image_path(self, value: str) -> str:
        raw_path = Path(value).expanduser()
        path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise WatermarkRemovalError(f"Image file not found: {value}") from exc
        return str(resolved)

    async def execute(
        self,
        image_path: str,
        remove_text: bool = False,
        **kwargs: Any,
    ) -> str:
        import json
        client = self._provider_client()

        try:
            resolved_path = self._resolve_image_path(image_path)
            response = await client.remove_watermark(
                image_path=resolved_path,
                remove_text=remove_text,
            )

            # Store cleaned image as artifact
            artifact = store_generated_image_artifact(
                response.image_data_url,
                prompt=f"watermark_removed:{Path(image_path).name}",
                model="dewatermark",
                source_images=[resolved_path],
                save_dir=self.config.save_dir,
                provider="vidtory",
            )

            return json.dumps(
                {
                    "artifacts": [artifact],
                    "mask_base": response.mask_base,
                    "next_step": (
                        "Call the message tool with this artifact path in the media parameter "
                        "to deliver the clean image to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (WatermarkRemovalError, OSError) as exc:
            return f"Error: {exc}"
