from __future__ import annotations

import base64
from typing import Any
import pytest
import httpx

from nanobot.providers.image_generation import VidtoryImageGenerationClient, ImageGenerationError
from nanobot.providers.video_generation import VidtoryVideoGenerationClient, VideoGenerationError
from nanobot.providers.audio_generation import VidtoryAudioGenerationClient, AudioGenerationError

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDATx\xdacd\xfc\xff\x1f\x00\x03\x03"
    b"\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        status_code: int = 200,
        content: bytes = b"",
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.content = content
        self.request = httpx.Request("POST", "https://bapi.vidtory.net")

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request, text=self.text)
            raise httpx.HTTPStatusError("failed", request=self.request, response=response)


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self.responses.pop(0)

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_vidtory_image_generation() -> None:
    responses = [
        FakeResponse({"success": True, "data": {"generationHistoryId": "img-123"}}),
        FakeResponse({"success": True, "data": {"status": "COMPLETED", "result": {"url": "https://cdn/img.png"}}}),
        FakeResponse({}, content=PNG_BYTES),
    ]
    fake = FakeClient(responses)
    client = VidtoryImageGenerationClient(
        api_key="test-api-key",
        api_base="https://bapi.vidtory.net",
        client=fake,  # type: ignore[arg-type]
    )

    res = await client.generate(
        prompt="astronaut in space",
        model="gemini-3.1-flash-image-preview",
        aspect_ratio="16:9",
        image_size="1K",
    )

    assert len(res.images) == 1
    assert res.images[0].startswith("data:image/png;base64,")
    
    assert len(fake.calls) == 3
    init_call = fake.calls[0]
    assert init_call["method"] == "POST"
    assert init_call["url"] == "https://bapi.vidtory.net/generative-core/image"
    assert init_call["json"]["aspectRatio"] == "IMAGE_ASPECT_RATIO_LANDSCAPE"
    assert init_call["json"]["modelId"] == "gemini-3.1-flash-image-preview"

    poll_call = fake.calls[1]
    assert poll_call["method"] == "GET"
    assert poll_call["url"] == "https://bapi.vidtory.net/generative-core/jobs/img-123/status"


@pytest.mark.asyncio
async def test_vidtory_video_generation() -> None:
    responses = [
        FakeResponse({"success": True, "data": {"generationHistoryId": "vid-123"}}),
        FakeResponse({"success": True, "data": {"status": "COMPLETED", "result": {"url": "https://cdn/vid.mp4"}}}),
        FakeResponse({}, content=b"fake-video-bytes"),
    ]
    fake = FakeClient(responses)
    client = VidtoryVideoGenerationClient(
        api_key="test-api-key",
        api_base="https://bapi.vidtory.net",
        client=fake,  # type: ignore[arg-type]
    )

    res = await client.generate(
        prompt="a cinematic panning shot",
        model="veo-3.1-fast-generate-001",
        aspect_ratio="16:9",
        duration=8,
    )

    assert res.video_bytes == b"fake-video-bytes"
    assert len(fake.calls) == 3
    init_call = fake.calls[0]
    assert init_call["method"] == "POST"
    assert init_call["url"] == "https://bapi.vidtory.net/generative-core/video"
    assert init_call["json"]["aspectRatio"] == "VIDEO_ASPECT_RATIO_LANDSCAPE"
    
    poll_call = fake.calls[1]
    assert poll_call["method"] == "GET"
    assert poll_call["url"] == "https://bapi.vidtory.net/generative-core/jobs/vid-123/status"


@pytest.mark.asyncio
async def test_vidtory_audio_generation() -> None:
    responses = [
        FakeResponse({"success": True, "data": {"generationHistoryId": "aud-123"}}),
        FakeResponse({"success": True, "data": {"status": "COMPLETED", "result": {"url": "https://cdn/aud.mp3"}}}),
        FakeResponse({}, content=b"fake-audio-bytes"),
    ]
    fake = FakeClient(responses)
    client = VidtoryAudioGenerationClient(
        api_key="test-api-key",
        api_base="https://bapi.vidtory.net",
        client=fake,  # type: ignore[arg-type]
    )

    res = await client.generate(
        prompt="Hello from Vidtory",
        voice_id="eZ248pfac00g3092s7h8",
        speed=1.0,
        language_code="vi",
    )

    assert res.audio_bytes == b"fake-audio-bytes"
    assert len(fake.calls) == 3
    init_call = fake.calls[0]
    assert init_call["method"] == "POST"
    assert init_call["url"] == "https://bapi.vidtory.net/generative-core/audio"
    assert init_call["json"]["voiceId"] == "eZ248pfac00g3092s7h8"
    
    poll_call = fake.calls[1]
    assert poll_call["method"] == "GET"
    assert poll_call["url"] == "https://bapi.vidtory.net/generative-core/jobs/aud-123/status"
