from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from nanobot.agent.tools.video_generation import VideoGenerationTool, VideoGenerationToolConfig
from nanobot.agent.tools.audio_generation import AudioGenerationTool, AudioGenerationToolConfig
from nanobot.config.loader import set_config_path
from nanobot.config.schema import ProviderConfig
from nanobot.providers.video_generation import GeneratedVideoResponse
from nanobot.providers.audio_generation import GeneratedAudioResponse


class FakeVideoClient:
    instances: list["FakeVideoClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.instances.append(self)

    async def generate(self, **kwargs: Any) -> GeneratedVideoResponse:
        self.calls.append(kwargs)
        return GeneratedVideoResponse(video_bytes=b"fake-mp4-data", raw={})


class FakeAudioClient:
    instances: list["FakeAudioClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.instances.append(self)

    async def generate(self, **kwargs: Any) -> GeneratedAudioResponse:
        self.calls.append(kwargs)
        return GeneratedAudioResponse(audio_bytes=b"fake-mp3-data", raw={})


@pytest.mark.asyncio
async def test_video_generation_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_config_path(tmp_path / "config.json")
    FakeVideoClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.video_generation.VidtoryVideoGenerationClient",
        FakeVideoClient,
    )

    tool = VideoGenerationTool(
        workspace=tmp_path,
        config=VideoGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="vidtory-test-key"),
    )

    result = await tool.execute(
        prompt="a space journey video",
        aspect_ratio="16:9",
        duration=4,
    )

    payload = json.loads(result)
    assert "artifacts" in payload
    assert len(payload["artifacts"]) == 1
    artifact = payload["artifacts"][0]
    assert artifact["mime"] == "video/mp4"
    assert Path(artifact["path"]).is_file()
    assert Path(artifact["path"]).read_bytes() == b"fake-mp4-data"

    fake = FakeVideoClient.instances[0]
    assert fake.kwargs["api_key"] == "vidtory-test-key"
    assert fake.calls[0]["prompt"] == "a space journey video"
    assert fake.calls[0]["aspect_ratio"] == "16:9"
    assert fake.calls[0]["duration"] == 4


@pytest.mark.asyncio
async def test_audio_generation_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_config_path(tmp_path / "config.json")
    FakeAudioClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.audio_generation.VidtoryAudioGenerationClient",
        FakeAudioClient,
    )

    tool = AudioGenerationTool(
        workspace=tmp_path,
        config=AudioGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="vidtory-test-key"),
    )

    result = await tool.execute(
        prompt="Welcome to Vidtory Agent",
        voice_id="custom-voice-id",
        speed=1.1,
        language_code="en",
    )

    payload = json.loads(result)
    assert "artifacts" in payload
    assert len(payload["artifacts"]) == 1
    artifact = payload["artifacts"][0]
    assert artifact["mime"] == "audio/mpeg"
    assert Path(artifact["path"]).is_file()
    assert Path(artifact["path"]).read_bytes() == b"fake-mp3-data"

    fake = FakeAudioClient.instances[0]
    assert fake.kwargs["api_key"] == "vidtory-test-key"
    assert fake.calls[0]["prompt"] == "Welcome to Vidtory Agent"
    assert fake.calls[0]["voice_id"] == "custom-voice-id"
    assert fake.calls[0]["speed"] == 1.1
    assert fake.calls[0]["language_code"] == "en"
