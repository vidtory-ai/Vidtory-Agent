"""Vidtory Remove Watermark provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import httpx

from nanobot.utils.helpers import detect_image_mime


class WatermarkRemovalError(RuntimeError):
    """Raised when the watermark removal provider fails."""


class WatermarkRemovalResponse:
    """Result of watermark removal."""
    def __init__(self, image_url: str, mask_base: str | None, raw: dict[str, Any]):
        self.image_url = image_url   # CDN URL — no local download
        self.mask_base = mask_base
        self.raw = raw


class VidtoryWatermarkRemovalClient:
    """Async client for Vidtory B2B Remove Watermark via /generative-core/image/remove-watermark."""

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
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/") if api_base else "https://bapi.vidtory.net"
        self.extra_headers = extra_headers or {}
        self.timeout = timeout
        self._client = client

    async def remove_watermark(
        self,
        *,
        image_path: str,
        remove_text: bool = False,
        predict_mode: str = "3.0",
        generation_history_id: str | None = None,
        mask_base: str | None = None,
    ) -> WatermarkRemovalResponse:
        if not self.api_key:
            raise WatermarkRemovalError(self.missing_key_message)

        p = Path(image_path).expanduser().resolve()
        if not p.is_file():
            raise WatermarkRemovalError(f"Image file not found: {image_path}")

        image_bytes = p.read_bytes()
        mime = detect_image_mime(image_bytes)
        if mime is None:
            raise WatermarkRemovalError(f"Unsupported image format: {image_path}")

        headers = {
            "x-api-key": self.api_key,
            **self.extra_headers,
        }

        url = f"{self.api_base}/generative-core/image/remove-watermark"
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            files: dict[str, Any] = {
                "file": (p.name, image_bytes, mime),
            }
            data: dict[str, Any] = {
                "removeText": str(remove_text).lower(),
                "predictMode": predict_mode,
            }
            if generation_history_id:
                data["generationHistoryId"] = generation_history_id
            if mask_base:
                data["maskBase"] = mask_base

            try:
                response = await client.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:500]
                raise WatermarkRemovalError(f"Vidtory remove-watermark failed: {detail}") from exc
            except httpx.RequestError as exc:
                raise WatermarkRemovalError(f"Vidtory remove-watermark request failed: {exc}") from exc

            payload = response.json()
            if not payload.get("success"):
                raise WatermarkRemovalError(f"Vidtory remove-watermark failed: {payload.get('message')}")

            result_data = payload.get("data") or {}
            media = result_data.get("media") or {}
            result_url = (
                media.get("url")
                or media.get("imageUrl")
                or result_data.get("url")
            )
            mask_base_out = result_data.get("maskBase")

            if not result_url:
                raise WatermarkRemovalError("Vidtory remove-watermark did not return an image URL")

            # Return CDN URL directly — no local download
            return WatermarkRemovalResponse(
                image_url=result_url,
                mask_base=mask_base_out,
                raw=payload,
            )
        finally:
            if self._client is None:
                await client.aclose()
