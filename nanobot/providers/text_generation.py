"""Vidtory Text generation provider."""

from __future__ import annotations

import asyncio
import time
from typing import Any
import httpx


class TextGenerationError(RuntimeError):
    """Raised when the text generation provider cannot return text."""


class GeneratedTextResponse:
    """Text returned by the provider."""
    def __init__(self, text: str, raw: dict[str, Any]):
        self.text = text
        self.raw = raw


class VidtoryTextGenerationClient:
    """Async client for Vidtory B2B Text Generation via /generative-core/text."""

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
        model_id: str | None = None,
        start_images: list[str] | None = None,
    ) -> GeneratedTextResponse:
        if not self.api_key:
            raise TextGenerationError(self.missing_key_message)

        body: dict[str, Any] = {
            "prompt": prompt,
            "workerId": "worker-mini-veo3-ultra1",
            "modelId": model_id or "gemini-3-flash-preview",
        }

        if start_images:
            body["startImages"] = start_images

        body.update(self.extra_body)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        url = f"{self.api_base}/generative-core/text"
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            # Initiate job
            response = await client.post(url, headers=headers, json=body)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:500]
                raise TextGenerationError(f"Vidtory text generation initiation failed: {detail}") from exc

            init_data = response.json()
            if not init_data.get("success"):
                raise TextGenerationError(f"Vidtory text generation failed: {init_data.get('message')}")

            job_data = init_data.get("data") or {}
            job_id = job_data.get("generationHistoryId")
            if not job_id:
                raise TextGenerationError("Vidtory did not return a generationHistoryId")

            # Polling loop
            poll_url = f"{self.api_base}/generative-core/jobs/{job_id}/status"
            start_time = time.monotonic()
            while True:
                if time.monotonic() - start_time > self.timeout:
                    raise TextGenerationError("Vidtory text generation timed out while polling status")

                await asyncio.sleep(2.0)
                poll_resp = await client.get(poll_url, headers=headers)
                try:
                    poll_resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = poll_resp.text[:500]
                    raise TextGenerationError(f"Vidtory job status polling failed: {detail}") from exc

                status_payload = poll_resp.json()
                if not status_payload.get("success"):
                    raise TextGenerationError(f"Vidtory job status check failed: {status_payload.get('message')}")

                status_data = status_payload.get("data") or {}
                status = status_data.get("status")
                if status == "COMPLETED":
                    result = status_data.get("result") or {}
                    # result.text is returned directly (primary path confirmed via API test)
                    text_out = (
                        result.get("text")
                        or result.get("content")
                        or result.get("output")
                        or ""
                    )
                    # Fallback: if no inline text, try downloading from URL
                    if not text_out:
                        result_url = result.get("url")
                        if result_url and result_url.startswith("http"):
                            try:
                                url_resp = await client.get(result_url)
                                if url_resp.status_code == 200:
                                    text_out = url_resp.text
                            except Exception:
                                pass
                    return GeneratedTextResponse(text=str(text_out).strip(), raw=status_payload)
                elif status == "FAILED":
                    err_msg = status_data.get("error") or "Job failed"
                    raise TextGenerationError(f"Vidtory job execution failed: {err_msg}")
        finally:
            if self._client is None:
                await client.aclose()
