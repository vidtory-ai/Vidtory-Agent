"""Vidtory Remove Watermark tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.path_utils import is_under
from nanobot.agent.tools.schema import (
    BooleanSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.config.paths import get_media_dir
from nanobot.providers.watermark_removal import (
    WatermarkRemovalError,
    VidtoryWatermarkRemovalClient,
)


class WatermarkRemovalToolConfig(Base):
    """Watermark removal tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"


@tool_parameters(
    tool_parameters_schema(
        image_path=StringSchema(
            "Local path of the image to remove watermark from. Must be an existing file.",
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
    Returns a CDN URL of the clean image. Deliver to user via the message tool.
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
            "Upload a local image and get a CDN URL of the clean version back. "
            "Deliver result to user via the message tool."
        )

    def _provider_client(self) -> VidtoryWatermarkRemovalClient:
        from nanobot.utils.context_vars import effective_vidtory_api_key

        api_key = effective_vidtory_api_key(
            self.provider_config.api_key if self.provider_config else None
        )
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
        allowed_roots = [self.workspace.resolve(), get_media_dir().resolve()]
        if not any(is_under(resolved, root) for root in allowed_roots):
            raise WatermarkRemovalError(
                "image_path must be inside the workspace or media directory"
            )
        if not resolved.is_file():
            raise WatermarkRemovalError(f"Image file not found: {value}")
        return str(resolved)

    async def execute(
        self,
        image_path: str,
        remove_text: bool = False,
        **kwargs: Any,
    ) -> str:
        client = self._provider_client()

        try:
            resolved_path = self._resolve_image_path(image_path)
            response = await client.remove_watermark(
                image_path=resolved_path,
                remove_text=remove_text,
            )

            # Return CDN URL directly — no local storage
            return json.dumps(
                {
                    "image_url": response.image_url,
                    "next_step": (
                        "Call the message tool with this URL in the media parameter "
                        "to deliver the clean image to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (WatermarkRemovalError, OSError) as exc:
            return f"Error: {exc}"
