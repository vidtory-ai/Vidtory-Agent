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
        """Wait briefly, then forward buffered media-group as one turn.

        Uses a sliding window: each new message in the album resets the timer.
        This prevents large/slow-uploading albums from being prematurely
        split into multiple generation requests.
        """
        import asyncio as _asyncio
        try:
            mgb = getattr(self, "_media_group_buffers", {})
            buf = mgb.get(key)
            if not buf:
                return
            
            max_wait_at: float = buf.get("_max_flush_at", 0.0)
            delay = min(
                _MEDIA_GROUP_FLUSH_DELAY,
                max(0.0, max_wait_at - __import__("time").monotonic()),
            )
            await _asyncio.sleep(delay)

            mgb = getattr(self, "_media_group_buffers", {})
            if not (buf := mgb.pop(key, None)):
                return
            self._media_group_buffers = mgb

            content = "\n".join(buf["contents"]) or "[empty message]"
            all_media = list(dict.fromkeys(buf["media"]))
            # Patch metadata so _merge_revision_references sees ALL images from
            # the media group, not just the first message's current_media.
            metadata = dict(buf["metadata"])
            metadata["current_media"] = all_media
            await self._handle_message(
                sender_id=buf["sender_id"], chat_id=buf["chat_id"],
                content=content, media=all_media,
                metadata=metadata,
                session_key=buf.get("session_key"),
            )
        except _asyncio.CancelledError:
            raise
        finally:
            mg_tasks = getattr(self, "_media_group_tasks", {})
            if mg_tasks.get(key) is __import__("asyncio").current_task():
                mg_tasks.pop(key, None)
                self._media_group_tasks = mg_tasks

    async def _flush_text_media_buffer(self, key: str) -> None:
        """Sliding-window flush for text+media requests.

        When a user sends multiple photos in rapid succession where only the
        first carries a caption/text, Telegram delivers them as separate
        messages very close in time.  Without buffering, the text+photo
        message would be processed immediately with only 1 image, while the
        remaining photos arrive milliseconds later.

        This method implements a sliding window:
        - Waits up to _TEXT_MEDIA_FLUSH_DELAY seconds for additional images.
        - Each new arriving image resets the timer (cancels the current task
          and schedules a fresh one), so the flush is always "N images have
          arrived and no new one came for 1 second".
        - An absolute cap (_TEXT_MEDIA_MAX_WAIT) prevents indefinite waiting
          when images trickle in slowly: at most 3 s from the first image.
        - Up to 10 images (or more) are handled transparently — there is no
          hard limit in this layer.

        The task clean-up guard in the finally block ensures that a cancelled
        task (which fires finally before the replacement task) never removes
        the key that belongs to the new task.
        """
        import asyncio as _asyncio
        try:
            tmb = getattr(self, "_text_media_buffers", {})
            buf = tmb.get(key)
            if not buf:
                return
            # Calculate actual sleep: respect the absolute cap.
            max_wait_at: float = buf.get("_max_flush_at", 0.0)
            delay = min(
                _TEXT_MEDIA_FLUSH_DELAY,
                max(0.0, max_wait_at - __import__("time").monotonic()),
            )
            await _asyncio.sleep(delay)

            # Pop and dispatch.
            tmb = getattr(self, "_text_media_buffers", {})
            buf = tmb.pop(key, None)
            if not buf:
                return
            self._text_media_buffers = tmb
            all_media = list(dict.fromkeys(buf["media"]))
            metadata = dict(buf["metadata"])
            metadata["current_media"] = all_media
            await self._handle_message(
                sender_id=buf["sender_id"],
                chat_id=buf["chat_id"],
                content=buf["content"],
                media=all_media,
                metadata=metadata,
                session_key=buf["session_key"],
            )
        except _asyncio.CancelledError:
            # Task was cancelled because a new image arrived and the window
            # was extended.  A replacement task already holds the key — do
            # NOT remove it from _text_media_tasks.
            raise
        finally:
            # Only clean up the key when the currently registered task is
            # THIS task (i.e. not a replacement that was just created).
            tmb_tasks = getattr(self, "_text_media_tasks", {})
            if tmb_tasks.get(key) is __import__("asyncio").current_task():
                tmb_tasks.pop(key, None)
                self._text_media_tasks = tmb_tasks


# Sliding-window flush delay (seconds) for text+media buffers.
# Each new image resets this timer; the absolute cap is _TEXT_MEDIA_MAX_WAIT.
_TEXT_MEDIA_FLUSH_DELAY: float = 0.5
_TEXT_MEDIA_MAX_WAIT: float = 2.0

# Sliding-window constants for albums (media_group_id).
# Telegram server usually delivers album items within milliseconds of each other.
_MEDIA_GROUP_FLUSH_DELAY: float = 0.4
_MEDIA_GROUP_MAX_WAIT: float = 2.0

