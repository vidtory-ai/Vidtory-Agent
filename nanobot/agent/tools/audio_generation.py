"""Audio generation tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any


from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    NumberSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.providers.audio_generation import (
    AudioGenerationError,
    VidtoryAudioGenerationClient,
)
from nanobot.utils.artifacts import store_generated_audio_artifact

class AudioGenerationToolConfig(Base):
    """Audio generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "eleven_v3"
    default_voice_id: str = "eZ248pfac00g3092s7h8"  # Default ElevenLabs voice
    default_speed: float = 1.0
    default_language: str = "vi"
    save_dir: str = "generated"


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
class AudioGenerationTool(Tool):
    """Generate persistent audio speech artifacts through the Vidtory audio provider."""

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
        return cls(
            workspace=ctx.workspace,
            config=getattr(ctx.config, "audio_generation", None) or AudioGenerationToolConfig(),
            provider_config=provider_config,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: AudioGenerationToolConfig,
        provider_config: Any | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_config = provider_config

    @property
    def name(self) -> str:
        return "generate_audio"

    @property
    def description(self) -> str:
        return (
            "Generate high-quality voice/speech audio (TTS) from a text script using Vidtory's AI voice models. "
            "Returns audio metadata including artifact IDs and local file paths. Deliver to user via the message tool."
        )

    def _provider_client(self) -> VidtoryAudioGenerationClient:
        from nanobot.utils.context_vars import telegram_user_api_key
        user_key = telegram_user_api_key.get()
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

        try:
            effective_voice = voice_id or self.config.default_voice_id
            response = await client.generate(
                prompt=prompt,
                model_id=self.config.model,
                voice_id=effective_voice,
                speed=speed or self.config.default_speed,
                language_code=language_code or self.config.default_language,
            )

            # Store audio as artifact
            artifact = store_generated_audio_artifact(
                response.audio_bytes,
                prompt=prompt,
                model=self.config.model,
                voice_id=effective_voice,
                save_dir=self.config.save_dir,
            )

            import json
            return json.dumps(
                {
                    "artifacts": [artifact],
                    "next_step": (
                        "Call the message tool with this audio artifact path in the media parameter "
                        "to deliver the audio clip to the user."
                    ),
                },
                ensure_ascii=False,
            )

        except (AudioGenerationError, OSError) as exc:
            return f"Error: {exc}"
