from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanobot.channels.telegram.channel import TelegramChannel

class TelegramMediaMixin:
    async def _upload_image_to_vidtory_cdn(
        self,
        image_source: str,
        *,
        filename: str = "logo.png",
        api_key: str = "",
        user_id: str = "",
    ) -> str | None:
        """Upload a logo image to the Vidtory Media CDN via POST /media/upload.

        Uses the official Vidtory SDK endpoint (MediaModule.upload) for a pure
        file storage operation — no AI processing is applied to the image.

        This replaces the previous workaround that used the
        /generative-core/image/remove-watermark endpoint, which ran an AI model
        on the uploaded logo and could inadvertently alter or degrade it.

        Args:
            image_source: A remote HTTP(S) URL or local file path of the logo.
            filename: Suggested filename (mime type is auto-detected from content).
            api_key: User's Vidtory API key. Required — no system key fallback.
            user_id: Telegram user ID (used as customer_id in CDN metadata).

        Returns:
            Permanent CDN URL string on success, or None on any failure.
        """
        # Use only the user-supplied key — no system key fallback.
        # api_base is still read from config for endpoint routing.
        effective_key = api_key
        api_base = "https://bapi.vidtory.net"

        try:
            from nanobot.config.loader import load_config
            cfg = load_config()
            provider_cfg = (cfg.providers or {}).get("vidtory") if cfg.providers else None
            if provider_cfg:
                api_base = getattr(provider_cfg, "api_base", None) or api_base
        except Exception:
            pass

        if not effective_key:
            self.logger.debug("setlogo CDN upload skipped: no user API key available")
            return None

        try:
            from nanobot.utils.logo_upload import upload_logo_to_cdn, LogoUploadError

            cdn_url = await upload_logo_to_cdn(
                image_source,
                api_key=effective_key,
                base_url=api_base,
                customer_id=user_id or None,
            )
            self.logger.info("setlogo: logo uploaded to Vidtory CDN: {}", cdn_url)
            return cdn_url

        except Exception as exc:
            self.logger.warning("setlogo CDN upload error: {}", exc)
            return None

    async def _upload_logo_bytes_to_cdn(
        self,
        image_bytes: bytes,
        *,
        mime_type: str = "image/jpeg",
        api_key: str = "",
        user_id: str = "",
    ) -> str | None:
        """Upload raw image bytes to Vidtory Media CDN.

        This is the preferred method for Telegram photo uploads: the bot downloads
        the photo bytes directly via Telegram Bot API (download_as_bytearray),
        then uploads them here — same flow as when user images are sent for product
        generation. This avoids any Telegram temporary URL entirely.

        Args:
            image_bytes: Raw image bytes downloaded from Telegram.
            mime_type: MIME type of the image (auto-detected from magic bytes when possible).
            api_key: User's Vidtory API key. Required — no system key fallback.
            user_id: Telegram user ID (used as customer_id in CDN metadata).

        Returns:
            Permanent Vidtory CDN URL on success, or None on any failure.
        """
        from nanobot.utils.helpers import detect_image_mime

        # Auto-detect actual MIME type from magic bytes (important for PNG logos with alpha)
        detected = detect_image_mime(image_bytes)
        if detected:
            mime_type = detected

        ext_map = {
            "image/png": "logo.png",
            "image/jpeg": "logo.jpg",
            "image/webp": "logo.webp",
            "image/gif": "logo.gif",
        }
        filename = ext_map.get(mime_type, "logo.jpg")

        # Use only the user-supplied key — no system key fallback.
        # api_base is still read from config for endpoint routing.
        effective_key = api_key
        api_base = "https://bapi.vidtory.net"

        try:
            from nanobot.config.loader import load_config
            cfg = load_config()
            provider_cfg = (cfg.providers or {}).get("vidtory") if cfg.providers else None
            if provider_cfg:
                api_base = getattr(provider_cfg, "api_base", None) or api_base
        except Exception:
            pass

        if not effective_key:
            self.logger.debug("setlogo bytes upload skipped: no user API key available")
            return None

        try:
            from nanobot.utils.logo_upload import upload_logo_bytes_to_cdn

            cdn_url = await upload_logo_bytes_to_cdn(
                image_bytes,
                file_name=filename,
                mime_type=mime_type,
                api_key=effective_key,
                base_url=api_base,
                customer_id=user_id or None,
            )
            self.logger.info("setlogo: logo bytes uploaded to Vidtory CDN: {}", cdn_url)
            return cdn_url

        except Exception as exc:
            self.logger.warning("setlogo bytes upload error: {}", exc)
            return None

    async def _flush_media_group(self, key: str) -> None:

        """Wait briefly, then forward buffered media-group as one turn."""

        try:
            await asyncio.sleep(0.6)
            if not (buf := self._media_group_buffers.pop(key, None)):
                return
            content = "\n".join(buf["contents"]) or "[empty message]"
            await self._handle_message(
                sender_id=buf["sender_id"], chat_id=buf["chat_id"],
                content=content, media=list(dict.fromkeys(buf["media"])),
                metadata=buf["metadata"],
                session_key=buf.get("session_key"),
            )
        finally:
            self._media_group_tasks.pop(key, None)
