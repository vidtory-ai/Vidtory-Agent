"""Video generation tool."""

from __future__ import annotations

from contextvars import ContextVar
import json
from pathlib import Path
from typing import Any, Callable, Awaitable

from loguru import logger

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ContextAware, RequestContext
from nanobot.agent.tools.path_utils import is_under
from nanobot.agent.tools.schema import (
    ArraySchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.bus.events import OutboundMessage
from nanobot.config.paths import get_media_dir
from nanobot.config.schema import Base
from nanobot.providers.video_generation import (
    VideoGenerationError,
    VidtoryVideoGenerationClient,
)
from nanobot.security.request_policy import evaluate_request, is_resident_designer_profile
from nanobot.utils.artifacts import (
    ArtifactError,
    store_generated_video_artifact,
    store_remote_video_artifact,
)

# Module-level ContextVar
_video_gen_request_ctx: ContextVar[RequestContext | None] = ContextVar(
    "video_gen_request_context", default=None
)


class VideoGenerationToolConfig(Base):
    """Video generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "veo-3.1-fast-generate-001"
    default_aspect_ratio: str = "16:9"
    default_duration: int = 8


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "Detailed video generation prompt. Include motion, lighting, style, subject, and composition.",
            min_length=1,
        ),
        reference_images=ArraySchema(
            StringSchema("CDN URL or local path of an image to use as a starting frame / reference."),
            description="Optional image URLs or paths. When provided, automatically switches model to Image-to-Video (i2v) mode.",
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
class VideoGenerationTool(Tool, ContextAware):
    """Generate videos from text prompts or starting image frames via Vidtory API."""

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
        send_callback = ctx.bus.publish_outbound if ctx.bus else None
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "video_generation", None) or VideoGenerationToolConfig(),
            provider_config=provider_config,
            send_callback=send_callback,
            capability_profile=getattr(ctx.config, "capability_profile", "standard"),
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: VideoGenerationToolConfig,
        provider_config: Any | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        capability_profile: str = "standard",
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config
        self._send_callback = send_callback
        self.capability_profile = capability_profile

    def set_context(self, ctx: RequestContext) -> None:
        """Receive the current request context (channel, chat_id, metadata)."""
        _video_gen_request_ctx.set(ctx)

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generate cinematic videos from text prompts or starting image frames via Vidtory API. "
            "Returns a persistent video artifact for delivery or follow-up use."
        )

    def _provider_client(self) -> VidtoryVideoGenerationClient:
        from nanobot.utils.context_vars import telegram_vidtory_api_key
        user_key = telegram_vidtory_api_key.get()
        api_key = user_key or (self.provider_config.api_key if self.provider_config else None)
        api_base = self.provider_config.api_base if self.provider_config else None
        return VidtoryVideoGenerationClient(
            api_key=api_key,
            api_base=api_base,
        )

    def _resolve_reference_image(self, value: str) -> str:
        """Resolve a reference image path or URL.

        HTTP(S) URLs (e.g. Vidtory CDN) are returned as-is.
        Local paths are resolved to absolute paths.
        """
        if value.startswith(("http://", "https://")):
            return value
        raw_path = Path(value).expanduser()
        path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise VideoGenerationError(f"reference image not found: {value}") from exc
        allowed_roots = [self.workspace.resolve(), get_media_dir().resolve()]
        if not any(is_under(resolved, root) for root in allowed_roots):
            raise VideoGenerationError(
                "reference_images must be inside the workspace or media directory"
            )
        if not resolved.is_file():
            raise VideoGenerationError(f"reference image is not a file: {value}")
        from nanobot.utils.helpers import detect_image_mime
        if detect_image_mime(resolved.read_bytes()) is None:
            raise VideoGenerationError(f"unsupported reference image: {value}")
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
        if is_resident_designer_profile(self.capability_profile):
            policy = evaluate_request(self.capability_profile, prompt)
            if policy.blocked:
                return (
                    "Error: video generation prompt blocked by resident_designer "
                    f"security policy ({policy.reason})"
                )
            if policy.redacted_text and policy.redacted_text.strip():
                prompt = policy.redacted_text
        client = self._provider_client()

        # Send a loading/progress message to the user to improve responsiveness
        ctx = _video_gen_request_ctx.get()
        if ctx and self._send_callback:
            try:
                progress_msg = OutboundMessage(
                    channel=ctx.channel,
                    chat_id=ctx.chat_id,
                    content="🎬 *Đã nhận yêu cầu dựng video!* Designer đang bắt đầu biên tập chuyển động và làm việc chăm chỉ... Vui lòng đợi trong giây lát nhé! ⏳",
                    metadata={**(ctx.metadata or {}), "_progress": True},
                )
                await self._send_callback(progress_msg)
            except Exception as e:
                logger.debug("Failed to send video generation progress message: {}", e)

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

            if response.video_bytes:
                artifact = store_generated_video_artifact(
                    response.video_bytes,
                    prompt=prompt,
                    model=self.config.model,
                    source_images=refs,
                    provider=self.config.provider,
                )
            elif response.video_url:
                artifact = store_remote_video_artifact(
                    response.video_url,
                    prompt=prompt,
                    model=self.config.model,
                    source_images=refs,
                    provider=self.config.provider,
                )
            else:
                return "Error: Video generation did not return media"

            return json.dumps(
                {
                    "artifacts": [artifact],
                    "next_step": (
                        "Call the message tool with this artifact path in the media parameter "
                        "to deliver the video to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (ArtifactError, VideoGenerationError, OSError) as exc:
            return f"Error: {exc}"
