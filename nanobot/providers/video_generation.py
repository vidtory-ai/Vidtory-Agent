"""Vidtory Video generation provider."""

from __future__ import annotations

import asyncio
import time
from typing import Any
import httpx

class VideoGenerationError(RuntimeError):
    """Raised when the video generation provider cannot return video."""

class GeneratedVideoResponse:
    """Video returned by the provider."""
    def __init__(self, video_bytes: bytes, raw: dict[str, Any]):
        self.video_bytes = video_bytes
        self.raw = raw

class VidtoryVideoGenerationClient:
    """Async client for Vidtory B2B Video Generation."""

    provider_name = "vidtory"
    missing_key_message = (
        "Vidtory API key is not configured. Set providers.vidtory.apiKey."
    )

    def __init__(
        self,
        *,
        api_key: str | None,
        api_base: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
        timeout: float = 300.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/") if api_base else "https://bapi.vidtory.net"
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}
        self.timeout = timeout
        self._client = client

    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        reference_images: list[str] | None = None,
        aspect_ratio: str | None = None,
        duration: int | None = None,
        mode: str | None = None,
    ) -> GeneratedVideoResponse:
        if not self.api_key:
            raise VideoGenerationError(self.missing_key_message)

        # Aspect ratio mapping
        ar_map = {
            "16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT",
        }
        vidtory_ar = ar_map.get(aspect_ratio or "16:9", "VIDEO_ASPECT_RATIO_LANDSCAPE")

        body: dict[str, Any] = {
            "prompt": prompt,
            "aspectRatio": vidtory_ar,
            "duration": duration or 8,
            "modelId": model or "veo-3.1-fast-generate-001",
            "mode": mode or "t2v",
        }

        # Reference images
        from nanobot.providers.image_generation import image_path_to_data_url
        refs = list(reference_images or [])
        if refs:
            body["refImageUrl"] = image_path_to_data_url(refs[0])
            body["mode"] = mode or "i2v"  # Default to image-to-video if reference image is present
            if len(refs) > 1:
                body["startImages"] = [image_path_to_data_url(r) for r in refs[1:]]

        body.update(self.extra_body)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        url = f"{self.api_base}/generative-core/video"
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            # Initiate job
            response = await client.post(url, headers=headers, json=body)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:500]
                raise VideoGenerationError(f"Vidtory video generation initiation failed: {detail}") from exc

            init_data = response.json()
            if not init_data.get("success"):
                raise VideoGenerationError(f"Vidtory video generation failed: {init_data.get('message')}")

            job_data = init_data.get("data") or {}
            job_id = job_data.get("generationHistoryId")
            if not job_id:
                raise VideoGenerationError("Vidtory did not return a generationHistoryId")

            # Polling loop
            poll_url = f"{self.api_base}/generative-core/jobs/{job_id}/status"
            start_time = time.monotonic()
            while True:
                if time.monotonic() - start_time > self.timeout:
                    raise VideoGenerationError("Vidtory video generation timed out while polling status")

                await asyncio.sleep(4.0)  # Video takes longer, poll every 4s
                poll_resp = await client.get(poll_url, headers=headers)
                try:
                    poll_resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = poll_resp.text[:500]
                    raise VideoGenerationError(f"Vidtory job status polling failed: {detail}") from exc

                status_payload = poll_resp.json()
                if not status_payload.get("success"):
                    raise VideoGenerationError(f"Vidtory job status check failed: {status_payload.get('message')}")

                status_data = status_payload.get("data") or {}
                status = status_data.get("status")
                if status == "COMPLETED":
                    result = status_data.get("result") or {}
                    result_url = result.get("url")
                    if not result_url:
                        raise VideoGenerationError("Vidtory job completed but did not return a result URL")
                    
                    # Download the video bytes
                    video_resp = await client.get(result_url)
                    video_resp.raise_for_status()
                    return GeneratedVideoResponse(
                        video_bytes=video_resp.content,
                        raw=status_payload,
                    )
                elif status == "FAILED":
                    err_msg = status_data.get("error") or "Job failed"
                    raise VideoGenerationError(f"Vidtory job execution failed: {err_msg}")
        finally:
            if self._client is None:
                await client.aclose()
