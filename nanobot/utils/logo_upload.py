"""Brand logo upload utility for Vidtory-Agent.

Uploads logo images to the Vidtory CDN so they can be referenced by a stable
URL during image generation.

Upload strategy (ordered by priority):
  1. POST /merchant/logo  — dedicated merchant logo endpoint, uploads to GCS
     and returns the CDN URL in the merchant details response.  Field name
     is ``logo`` (not ``file``).  Confirmed working (HTTP 201).
  2. POST /generative-core/image/remove-watermark — fallback if /merchant/logo
     fails.  Uploads to the same GCS bucket but may convert to JPEG.

Endpoint reference (B2B API source: merchant.controller.ts):
    POST /merchant/logo
    Headers: x-api-key: <key>
    Body: multipart/form-data
        logo: <bytes>   (field name = "logo")
    Response: { success: true, data: { ..., logoUrl: "https://..." } }
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

import httpx
from loguru import logger

from nanobot.utils.helpers import detect_image_mime

_UPLOAD_TIMEOUT_S = 60.0
_MAX_RETRIES = 2
_RETRY_ON_STATUS = {429, 500, 502, 503, 504}


class LogoUploadError(RuntimeError):
    """Raised when logo upload to Vidtory CDN fails after all retries."""


async def upload_logo_to_cdn(
    logo_source: str | Path,
    *,
    api_key: str,
    base_url: str = "https://bapi.vidtory.net",
    customer_id: str | None = None,
    timeout: float = _UPLOAD_TIMEOUT_S,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Upload a brand logo and return the stable CDN URL.

    Accepts a local file path, remote HTTP(S) URL, or ``data:`` URL.
    """
    source = str(logo_source)

    if source.startswith("data:"):
        file_bytes, file_name, mime_type = _decode_data_url(source)
    elif source.startswith(("http://", "https://")):
        file_bytes, file_name, mime_type = await _fetch_remote_logo(
            source, timeout=timeout, http_client=http_client
        )
    else:
        file_bytes, file_name, mime_type = _read_local_logo(source)

    logger.info(
        "Uploading brand logo '{}' ({} bytes, {}) to Vidtory CDN",
        file_name, len(file_bytes), mime_type,
    )

    return await upload_logo_bytes_to_cdn(
        file_bytes,
        file_name=file_name,
        mime_type=mime_type,
        api_key=api_key,
        base_url=base_url,
        customer_id=customer_id,
        timeout=timeout,
        http_client=http_client,
    )


async def upload_logo_bytes_to_cdn(
    file_bytes: bytes,
    *,
    file_name: str,
    mime_type: str,
    api_key: str,
    base_url: str = "https://bapi.vidtory.net",
    customer_id: str | None = None,
    timeout: float = _UPLOAD_TIMEOUT_S,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Upload raw logo bytes to CDN.

    Strategy:
      1. POST /merchant/logo  (dedicated endpoint, confirmed working)
      2. POST /generative-core/image/remove-watermark  (fallback)
    """
    base = base_url.rstrip("/")
    headers = {"x-api-key": api_key}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout)

    try:
        # ── Strategy 1: POST /merchant/logo ────────────────────────────────
        # Field name = "logo" (not "file"), returns { data: { logoUrl: "..." } }
        merchant_logo_url = base + "/merchant/logo"
        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

            try:
                resp = await client.post(
                    merchant_logo_url,
                    headers=headers,
                    files={"logo": (file_name, file_bytes, mime_type)},
                )
            except httpx.RequestError as exc:
                logger.warning("Logo upload network error (attempt {}): {}", attempt + 1, exc)
                if attempt < _MAX_RETRIES:
                    continue
                break

            if resp.status_code in _RETRY_ON_STATUS and attempt < _MAX_RETRIES:
                logger.warning("Logo upload: HTTP {} — retrying ({}/{})",
                               resp.status_code, attempt + 1, _MAX_RETRIES)
                continue

            if resp.status_code >= 400:
                logger.warning("POST /merchant/logo failed (HTTP {}): {}",
                               resp.status_code, resp.text[:200])
                break

            # Parse success
            try:
                payload = resp.json()
            except Exception:
                logger.warning("POST /merchant/logo returned non-JSON: {}", resp.text[:200])
                break

            data_obj = payload.get("data") or {}
            cdn_url = data_obj.get("logoUrl") or data_obj.get("url") or ""
            if cdn_url:
                logger.info("Brand logo uploaded via /merchant/logo -> {}", cdn_url)
                return cdn_url

            logger.warning("POST /merchant/logo: no logoUrl in response: {}", payload)
            break

        # ── Strategy 2: POST /generative-core/image/remove-watermark ───────
        logger.warning("Falling back to /generative-core/image/remove-watermark")
        fallback_url = base + "/generative-core/image/remove-watermark"

        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                await asyncio.sleep(1.0)

            try:
                resp = await client.post(
                    fallback_url,
                    headers=headers,
                    files={"file": (file_name, file_bytes, mime_type)},
                    data={"removeText": "false", "predictMode": "3.0"},
                )
                resp.raise_for_status()
                fb = resp.json()

                if not fb.get("success"):
                    raise LogoUploadError(f"Fallback API error: {fb.get('message')}")

                fb_data = fb.get("data") or {}
                fb_media = fb_data.get("media") or {}
                cdn_url = (
                    fb_media.get("url")
                    or fb_media.get("imageUrl")
                    or fb_data.get("url")
                    or ""
                )
                if cdn_url:
                    logger.info("Brand logo uploaded via fallback -> {}", cdn_url)
                    return cdn_url

                raise LogoUploadError("Fallback API returned no URL")

            except Exception as exc:
                logger.error("Fallback upload attempt {} failed: {}", attempt + 1, exc)
                if attempt < _MAX_RETRIES:
                    continue

        raise LogoUploadError("Logo upload failed on all endpoints")

    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

async def _fetch_remote_logo(
    url: str,
    *,
    timeout: float,
    http_client: httpx.AsyncClient | None,
) -> tuple[bytes, str, str]:
    """Download a remote logo image and return (bytes, filename, mime_type)."""
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await client.get(url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LogoUploadError(
                f"Failed to download logo from {url}: HTTP {response.status_code}"
            ) from exc

        raw = response.content
        mime = detect_image_mime(raw)
        if mime is None:
            raise LogoUploadError(
                f"Remote URL did not return a supported image: {url}"
            )

        path_part = url.rstrip("/").split("/")[-1].split("?")[0]
        ext_from_mime = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(mime, ".png")
        if not any(path_part.lower().endswith(e) for e in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
            path_part = f"logo{ext_from_mime}"

        return raw, path_part, mime
    finally:
        if owns_client:
            await client.aclose()


def _read_local_logo(path_str: str) -> tuple[bytes, str, str]:
    """Read a local logo file and return (bytes, filename, mime_type)."""
    p = Path(path_str).expanduser().resolve()
    if not p.is_file():
        raise LogoUploadError(f"Logo file not found: {path_str}")

    raw = p.read_bytes()
    mime = detect_image_mime(raw)
    if mime is None:
        guessed, _ = mimetypes.guess_type(str(p))
        if guessed and guessed.startswith("image/"):
            mime = guessed
        else:
            raise LogoUploadError(
                f"Unsupported image format for logo: {path_str}"
            )

    return raw, p.name, mime


def _decode_data_url(data_url: str) -> tuple[bytes, str, str]:
    """Decode a base64 data URL into (bytes, filename, mime_type)."""
    import base64

    try:
        header, encoded = data_url.split(",", 1)
        mime_part = header.split(":")[1].split(";")[0]
        raw = base64.b64decode(encoded)
    except Exception as exc:
        raise LogoUploadError(f"Invalid data URL format: {exc}") from exc

    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_map.get(mime_part, ".png")
    return raw, f"logo{ext}", mime_part


# ---------------------------------------------------------------------------
# Sync convenience wrapper (for non-async contexts)
# ---------------------------------------------------------------------------

def upload_logo_to_cdn_sync(
    logo_source: str | Path,
    *,
    api_key: str,
    base_url: str = "https://bapi.vidtory.net",
    customer_id: str | None = None,
    timeout: float = _UPLOAD_TIMEOUT_S,
) -> str:
    """Synchronous wrapper around :func:`upload_logo_to_cdn`."""
    return asyncio.run(
        upload_logo_to_cdn(
            logo_source,
            api_key=api_key,
            base_url=base_url,
            customer_id=customer_id,
            timeout=timeout,
        )
    )
