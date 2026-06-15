"""Audio generation tool."""

from __future__ import annotations

from contextvars import ContextVar
import json
from pathlib import Path
from typing import Any, Callable, Awaitable

from loguru import logger

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ContextAware, RequestContext
from nanobot.agent.tools.schema import (
    NumberSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.bus.events import OutboundMessage
from nanobot.config.schema import Base
from nanobot.providers.audio_generation import (
    AudioGenerationError,
    VidtoryAudioGenerationClient,
)
from nanobot.utils.artifacts import (
    ArtifactError,
    store_generated_audio_artifact,
    store_remote_audio_artifact,
)

# Module-level ContextVar
_audio_gen_request_ctx: ContextVar[RequestContext | None] = ContextVar(
    "audio_gen_request_context", default=None
)


class AudioGenerationToolConfig(Base):
    """Audio generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "eleven_v3"
    default_voice_id: str = "eZ248pfac00g3092s7h8"
    default_speed: float = 1.0
    default_language: str = "vi"


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "The text prompt or script content to convert into audio speech (TTS).",
            min_length=1,
        ),
        voice_id=StringSchema(
            "Optional voice ID. Use ElevenLabs voice IDs, e.g. default id is eZ248pfac00g3092s7h8.",
        ),
        speed=NumberSchema(
            "Optional speech speed factor (e.g. 1.0 is normal speed, 0.75 is slower, 1.25 is faster).",
            minimum=0.25,
            maximum=2.0,
        ),
        language_code=StringSchema(
            "Optional ISO language code, e.g. vi (Vietnamese), en (English).",
        ),
        required=["prompt"],
    )
)
class AudioGenerationTool(Tool, ContextAware):
    """Generate voice/speech audio (TTS) via Vidtory API."""

    config_key = "audio_generation"

    @classmethod
    def config_cls(cls):
        return AudioGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        cfg = getattr(ctx.config, "audio_generation", None)
        return cfg.enabled if cfg else True

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        provider_config = ctx.providers.vidtory if ctx.providers else None
        send_callback = ctx.bus.publish_outbound if ctx.bus else None
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "audio_generation", None) or AudioGenerationToolConfig(),
            provider_config=provider_config,
            send_callback=send_callback,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: AudioGenerationToolConfig,
        provider_config: Any | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config
        self._send_callback = send_callback

    def set_context(self, ctx: RequestContext) -> None:
        """Receive the current request context (channel, chat_id, metadata)."""
        _audio_gen_request_ctx.set(ctx)

    @property
    def name(self) -> str:
        return "generate_audio"

    @property
    def description(self) -> str:
        return (
            "Generate high-quality voice/speech audio (TTS) from a text script using Vidtory's AI voice models. "
            "Returns a persistent audio artifact for delivery or follow-up use."
        )

    def _provider_client(self) -> VidtoryAudioGenerationClient:
        from nanobot.utils.context_vars import telegram_vidtory_api_key
        user_key = telegram_vidtory_api_key.get()
        api_key = user_key or (self.provider_config.api_key if self.provider_config else None)
        api_base = self.provider_config.api_base if self.provider_config else None
        return VidtoryAudioGenerationClient(
            api_key=api_key,
            api_base=api_base,
        )

    async def execute(
        self,
        prompt: str,
        voice_id: str | None = None,
        speed: float | None = None,
        language_code: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._provider_client()

        # Send a loading/progress message to the user to improve responsiveness
        ctx = _audio_gen_request_ctx.get()
        if ctx and self._send_callback:
            try:
                progress_msg = OutboundMessage(
                    channel=ctx.channel,
                    chat_id=ctx.chat_id,
                    content="🔊 *Đã nhận yêu cầu tạo âm thanh!* Designer đang xử lý giọng nói và âm điệu... Vui lòng đợi trong giây lát nhé! ⏳",
                    metadata={**(ctx.metadata or {}), "_progress": True},
                )
                await self._send_callback(progress_msg)
            except Exception as e:
                logger.debug("Failed to send audio generation progress message: {}", e)

        try:
            response = await client.generate(
                prompt=prompt,
                model_id=self.config.model,
                voice_id=voice_id or self.config.default_voice_id,
                speed=speed or self.config.default_speed,
                language_code=language_code or self.config.default_language,
            )

            selected_voice_id = voice_id or self.config.default_voice_id
            if response.audio_bytes:
                artifact = store_generated_audio_artifact(
                    response.audio_bytes,
                    prompt=prompt,
                    model=self.config.model,
                    voice_id=selected_voice_id,
                    provider=self.config.provider,
                )
            elif response.audio_url:
                artifact = store_remote_audio_artifact(
                    response.audio_url,
                    prompt=prompt,
                    model=self.config.model,
                    voice_id=selected_voice_id,
                    provider=self.config.provider,
                )
            else:
                return "Error: Audio generation did not return media"

            return json.dumps(
                {
                    "artifacts": [artifact],
                    "next_step": (
                        "Call the message tool with this artifact path in the media parameter "
                        "to deliver the audio clip to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (ArtifactError, AudioGenerationError, OSError) as exc:
            return f"Error: {exc}"
