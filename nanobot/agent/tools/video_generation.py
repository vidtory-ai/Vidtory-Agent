"""Video generation tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any


from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    ArraySchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.providers.video_generation import (
    VideoGenerationError,
    VidtoryVideoGenerationClient,
)
from nanobot.utils.artifacts import store_generated_video_artifact

class VideoGenerationToolConfig(Base):
    """Video generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "veo-3.1-fast-generate-001"
    default_aspect_ratio: str = "16:9"
    default_duration: int = 8
    save_dir: str = "generated"


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "Detailed video generation prompt. Include motion, lighting, style, subject, and composition.",
            min_length=1,
        ),
        reference_images=ArraySchema(
            StringSchema("Local path of an existing image artifact or user-provided image to use as a starting frame / reference image."),
            description="Optional local image paths. When provided, automatically switches model to Image-to-Video (i2v) mode.",
        ),
        aspect_ratio=StringSchema(
            "Optional output aspect ratio: 16:9, 9:16.",
        ),
        duration=IntegerSchema(
            description="Optional video duration in seconds (typically 4 or 8).",
            minimum=1,
            maximum=30,
        ),
        mode=StringSchema(
            "Optional generation mode: t2v (text to video), i2v (image to video), r2v (ref image to video), seedance.",
        ),
        required=["prompt"],
    )
)
class VideoGenerationTool(Tool):
    """Generate persistent video artifacts through the Vidtory video provider."""

    config_key = "video_generation"

    @classmethod
    def config_cls(cls):
        return VideoGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        cfg = getattr(ctx.config, "video_generation", None)
        return cfg.enabled if cfg else True

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        provider_config = ctx.providers.vidtory if ctx.providers else None
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "video_generation", None) or VideoGenerationToolConfig(),
            provider_config=provider_config,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: VideoGenerationToolConfig,
        provider_config: Any | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generate cinematic videos from text prompts or starting image frames and save them as persistent artifacts. "
            "Returns video metadata including artifact IDs and local file paths. Deliver to user via the message tool."
        )

    def _provider_client(self) -> VidtoryVideoGenerationClient:
        from nanobot.utils.context_vars import telegram_user_api_key
        user_key = telegram_user_api_key.get()
        api_key = user_key or (self.provider_config.api_key if self.provider_config else None)
        api_base = self.provider_config.api_base if self.provider_config else None
        return VidtoryVideoGenerationClient(
            api_key=api_key,
            api_base=api_base,
        )

    def _resolve_reference_image(self, value: str) -> str:
        raw_path = Path(value).expanduser()
        path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise VideoGenerationError(f"reference image not found: {value}") from exc
        return str(resolved)

    def _resolve_reference_images(self, values: list[str] | None) -> list[str]:
        if not values:
            return []
        return [self._resolve_reference_image(value) for value in values if value]

    async def execute(
        self,
        prompt: str,
        reference_images: list[str] | None = None,
        aspect_ratio: str | None = None,
        duration: int | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._provider_client()

        try:
            refs = self._resolve_reference_images(reference_images)
            response = await client.generate(
                prompt=prompt,
                model=self.config.model,
                reference_images=refs,
                aspect_ratio=aspect_ratio or self.config.default_aspect_ratio,
                duration=duration or self.config.default_duration,
                mode=mode,
            )

            # Store video as artifact
            artifact = store_generated_video_artifact(
                response.video_bytes,
                prompt=prompt,
                model=self.config.model,
                source_images=refs,
                save_dir=self.config.save_dir,
            )

            import json
            return json.dumps(
                {
                    "artifacts": [artifact],
                    "next_step": (
                        "Call the message tool with this video artifact path in the media parameter "
                        "to deliver the video to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (VideoGenerationError, OSError) as exc:
            return f"Error: {exc}"
