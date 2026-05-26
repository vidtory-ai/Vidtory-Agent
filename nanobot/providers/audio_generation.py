"""Vidtory Audio generation provider."""

from __future__ import annotations

import asyncio
import time
from typing import Any
import httpx

class AudioGenerationError(RuntimeError):
    """Raised when the audio generation provider cannot return audio."""

class GeneratedAudioResponse:
    """Audio returned by the provider."""
    def __init__(self, audio_bytes: bytes, raw: dict[str, Any]):
        self.audio_bytes = audio_bytes
        self.raw = raw

class VidtoryAudioGenerationClient:
    """Async client for Vidtory B2B Audio Generation."""

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
        timeout: float = 120.0,
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
        voice_id: str | None = None,
        speed: float | None = None,
        language_code: str | None = None,
        model_id: str | None = None,
    ) -> GeneratedAudioResponse:
        if not self.api_key:
            raise AudioGenerationError(self.missing_key_message)

        body: dict[str, Any] = {
            "prompt": prompt,
            "voiceId": voice_id or "eZ248pfac00g3092s7h8",  # Default ElevenLabs voice
            "speed": speed or 1.0,
            "languageCode": language_code or "vi",
            "modelId": model_id or "eleven_v3",
        }

        body.update(self.extra_body)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        url = f"{self.api_base}/generative-core/audio"
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            # Initiate job
            response = await client.post(url, headers=headers, json=body)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:500]
                raise AudioGenerationError(f"Vidtory audio generation initiation failed: {detail}") from exc

            init_data = response.json()
            if not init_data.get("success"):
                raise AudioGenerationError(f"Vidtory audio generation failed: {init_data.get('message')}")

            job_data = init_data.get("data") or {}
            job_id = job_data.get("generationHistoryId")
            if not job_id:
                raise AudioGenerationError("Vidtory did not return a generationHistoryId")

            # Polling loop
            poll_url = f"{self.api_base}/generative-core/jobs/{job_id}/status"
            start_time = time.monotonic()
            while True:
                if time.monotonic() - start_time > self.timeout:
                    raise AudioGenerationError("Vidtory audio generation timed out while polling status")

                await asyncio.sleep(2.0)
                poll_resp = await client.get(poll_url, headers=headers)
                try:
                    poll_resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = poll_resp.text[:500]
                    raise AudioGenerationError(f"Vidtory job status polling failed: {detail}") from exc

                status_payload = poll_resp.json()
                if not status_payload.get("success"):
                    raise AudioGenerationError(f"Vidtory job status check failed: {status_payload.get('message')}")

                status_data = status_payload.get("data") or {}
                status = status_data.get("status")
                if status == "COMPLETED":
                    result = status_data.get("result") or {}
                    result_url = result.get("url")
                    if not result_url:
                        raise AudioGenerationError("Vidtory job completed but did not return a result URL")
                    
                    # Download the audio bytes
                    audio_resp = await client.get(result_url)
                    audio_resp.raise_for_status()
                    return GeneratedAudioResponse(
                        audio_bytes=audio_resp.content,
                        raw=status_payload,
                    )
                elif status == "FAILED":
                    err_msg = status_data.get("error") or "Job failed"
                    raise AudioGenerationError(f"Vidtory job execution failed: {err_msg}")
        finally:
            if self._client is None:
                await client.aclose()
