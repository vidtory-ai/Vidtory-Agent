"""Brand logo upload utility for Vidtory-Agent.

Pre-uploads logo images to the Vidtory Media CDN (POST /media/upload) so they
can be referenced by a stable CDN URL during image generation.

WHY THIS EXISTS
---------------
When a logo is passed as ``refImageUrl`` or ``startImages`` directly to
the Vidtory / Gemini image generation pipeline, the AI model can mistake
the logo for a watermark and erase it (turning it white/blank).

By pre-uploading the logo to the Vidtory Media CDN and using the returned
CDN URL instead, the logo is stored as an immutable asset that can be
referenced separately from the generation prompt — preventing accidental
erasure.

Key SDK parameters used:
- ``preserveFormat=true``  → keeps PNG alpha channel (transparent background)
- ``metadata.type=brand_logo`` → tags the asset for easy identification

Endpoint reference (Vidtory SDK):
    POST /media/upload
    Headers: x-api-key: <key>
    Body: multipart/form-data
        file: <bytes>
        metadata: JSON string (optional)
    Query: preserveFormat=true (for PNG/WebP with transparency)
    Response: { success: true, data: { url: "https://...", id: "..." } }

See: vidtory-sdk/python/src/vidtory/client.py — MediaModule.upload()
"""

from __future__ import annotations

import asyncio
import json as _json
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from nanobot.utils.helpers import detect_image_mime

# Official Vidtory SDK endpoint for pure file upload (no AI processing).
# Reference: vidtory-sdk MediaModule.upload() → POST /media/upload
_VIDTORY_UPLOAD_ENDPOINT = "/media/upload"
_UPLOAD_TIMEOUT_S = 60.0
# Max retries for transient server errors (matches SDK default: 3)
_MAX_UPLOAD_RETRIES = 3
# HTTP status codes that warrant a retry (matches SDK: [429, 500, 502, 503, 504])
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
    """Upload a brand logo to Vidtory Media CDN and return the stable CDN URL.

    Uses the official ``POST /media/upload`` endpoint (Vidtory SDK reference:
    ``MediaModule.upload()``).  Automatically retries on transient server
    errors (5xx / 429) up to ``_MAX_UPLOAD_RETRIES`` times.

    The returned URL can be safely used as ``logoUrl`` in image generation
    requests without risking AI erasure, because the logo is stored as an
    immutable CDN asset rather than being passed through an AI pipeline.

    Args:
        logo_source: Local file path, remote HTTP(S) URL, or ``data:`` URL.
        api_key: Vidtory API key (``x-api-key`` header).
        base_url: Vidtory API base URL.
        customer_id: Optional customer ID for metadata tagging.
        timeout: HTTP request timeout in seconds.
        http_client: Optional pre-existing AsyncClient to reuse.

    Returns:
        CDN URL string of the uploaded logo asset.

    Raises:
        LogoUploadError: If the upload fails after all retries.
    """
    source = str(logo_source)

    # ── Fetch image bytes ──────────────────────────────────────────────────
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
    """Upload logo bytes directly to CDN with automatic fallback if /media/upload fails."""
    # ── Try POST /media/upload first ───────────────────────────────────────
    # - preserveFormat=true → preserves PNG alpha channel for transparent logos
    # - metadata.type=brand_logo → tags asset for easy management
    url = base_url.rstrip("/") + _VIDTORY_UPLOAD_ENDPOINT

    metadata: dict[str, Any] = {"type": "brand_logo"}
    if customer_id:
        metadata["customerId"] = customer_id

    files = {
        "file": (file_name, file_bytes, mime_type),
    }
    data = {
        "metadata": _json.dumps(metadata),
    }
    # preserveFormat=true is critical for logos with transparent PNG backgrounds.
    params = {"preserveFormat": "true"}
    headers = {"x-api-key": api_key}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout)
    last_error: Exception | None = None

    try:
        for attempt in range(_MAX_UPLOAD_RETRIES + 1):
            if attempt > 0:
                # Exponential back-off: 0.5s, 1s, 2s (matches SDK retry policy)
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                logger.debug("Logo upload retry {}/{}", attempt, _MAX_UPLOAD_RETRIES)

            try:
                # Files object must be recreated if we want to resubmit, but the bytes are in memory.
                # Since httpx consumes the files tuple, we must recreate it for each attempt.
                attempt_files = {"file": (file_name, file_bytes, mime_type)}
                response = await client.post(
                    url,
                    headers=headers,
                    files=attempt_files,
                    data=data,
                    params=params,
                )
            except httpx.RequestError as exc:
                last_error = LogoUploadError(f"Logo upload network error: {exc}")
                if attempt < _MAX_UPLOAD_RETRIES:
                    continue
                break # break to fallback

            # Retry on transient server errors
            if response.status_code in _RETRY_ON_STATUS and attempt < _MAX_UPLOAD_RETRIES:
                last_error = LogoUploadError(
                    f"Logo upload transient error (HTTP {response.status_code}), retrying…"
                )
                logger.warning(
                    "Logo upload: HTTP {} — will retry ({}/{})",
                    response.status_code, attempt + 1, _MAX_UPLOAD_RETRIES,
                )
                continue

            # Fallback on 5xx or unhandled 4xx error (meaning /media/upload is broken)
            if response.status_code >= 400:
                detail = response.text[:500]
                last_error = LogoUploadError(
                    f"Logo upload failed (HTTP {response.status_code}): {detail}"
                )
                break # break to fallback

            # ── Parse success response ─────────────────────────────────────
            try:
                payload = response.json()
            except Exception as exc:
                last_error = LogoUploadError(
                    f"Logo upload returned non-JSON response: {response.text[:200]}"
                )
                break # break to fallback

            if not payload.get("success"):
                msg = payload.get("message") or "Unknown error"
                last_error = LogoUploadError(f"Logo upload API returned error: {msg}")
                break # break to fallback

            data_obj = payload.get("data") or {}
            cdn_url = (
                data_obj.get("url")
                or data_obj.get("cdnUrl")      # alternate field name per SDK
                or data_obj.get("imageUrl")    # fallback for older API versions
                or ""
            )
            if not cdn_url:
                last_error = LogoUploadError(
                    f"Logo upload succeeded but no CDN URL in response: {payload}"
                )
                break # break to fallback

            logger.info("Brand logo uploaded successfully → {}", cdn_url)
            return cdn_url

        # ── Fallback to /generative-core/image/remove-watermark ────────────
        # If /media/upload failed completely, fallback to the remove-watermark flow
        logger.warning(
            "Primary upload to /media/upload failed: {}. Falling back to /remove-watermark.",
            last_error
        )
        
        fallback_url = base_url.rstrip("/") + "/generative-core/image/remove-watermark"
        fallback_data = {
            "removeText": "false",
            "predictMode": "3.0",
        }
        
        for attempt in range(2): # Only retry once for fallback
            if attempt > 0:
                await asyncio.sleep(1.0)
            
            try:
                fallback_files = {"file": (file_name, file_bytes, mime_type)}
                fallback_response = await client.post(
                    fallback_url,
                    headers=headers,
                    files=fallback_files,
                    data=fallback_data,
                )
                fallback_response.raise_for_status()
                fb_payload = fallback_response.json()
                
                if not fb_payload.get("success"):
                    raise LogoUploadError(f"Fallback API error: {fb_payload.get('message')}")
                    
                fb_data = fb_payload.get("data") or {}
                fb_media = fb_data.get("media") or {}
                cdn_url = (
                    fb_media.get("url")
                    or fb_media.get("imageUrl")
                    or fb_data.get("url")
                )
                
                if not cdn_url:
                    raise LogoUploadError("Fallback API returned no URL")
                    
                logger.info("Brand logo uploaded successfully via fallback → {}", cdn_url)
                return cdn_url
                
            except Exception as fallback_exc:
                logger.error("Fallback upload attempt {} failed: {}", attempt + 1, fallback_exc)
                continue
                
        # If both primary and fallback failed, raise the original error
        raise last_error or LogoUploadError("Logo upload failed on all endpoints")

    finally:
        if owns_client:
            await client.aclose()


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

        # Derive a sensible file name from the URL
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
        # Fallback: guess from extension
        guessed, _ = mimetypes.guess_type(str(p))
        if guessed and guessed.startswith("image/"):
            mime = guessed
        else:
            raise LogoUploadError(
                f"Unsupported image format for logo: {path_str}"
            )

    return raw, p.name, mime


def _decode_data_url(data_url: str) -> tuple[bytes, str, str]:
    """Decode a base64 data URL into (bytes, filename, mime_type).

    Supports: ``data:image/png;base64,<data>``
    """
    import base64

    try:
        header, encoded = data_url.split(",", 1)
        # header: "data:image/png;base64"
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
    """Synchronous wrapper around :func:`upload_logo_to_cdn`.

    Intended for use in migration scripts or admin tooling where an
    async event loop is not available.
    """
    return asyncio.run(
        upload_logo_to_cdn(
            logo_source,
            api_key=api_key,
            base_url=base_url,
            customer_id=customer_id,
            timeout=timeout,
        )
    )
