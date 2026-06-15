from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from nanobot.channels.telegram.format import TELEGRAM_REPLY_CONTEXT_MAX_LEN
from nanobot.channels.telegram.media_groups import MediaGroupPart
from nanobot.channels.telegram.utils import get_extension
from nanobot.config.paths import get_media_dir, get_workspace_path

class TelegramMessagesMixin:
    @staticmethod
    def _matches_telegram_allowlist(sender_id: str, allow_list: list[str]) -> bool:
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True

        if sender_str.count("|") != 1:
            return False

        sid, username = sender_str.split("|", 1)
        if not sid.isdigit() or not username:
            return False

        return sid in allow_list or username in allow_list

    @staticmethod
    def _normalize_telegram_command(content: str) -> str:
        """Map Telegram-safe command aliases back to canonical nanobot commands."""
        if not content.startswith("/"):
            return content
        if content == "/dream_log" or content.startswith("/dream_log "):
            return content.replace("/dream_log", "/dream-log", 1)
        if content == "/dream_restore" or content.startswith("/dream_restore "):
            return content.replace("/dream_restore", "/dream-restore", 1)
        return content

    @staticmethod
    def _sender_id(user) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    @staticmethod
    def _derive_topic_session_key(message) -> str | None:
        """Derive topic-scoped session key for Telegram chats with threads."""
        message_thread_id = getattr(message, "message_thread_id", None)
        if message_thread_id is None:
            return None
        return f"telegram:{message.chat_id}:topic:{message_thread_id}"

    @staticmethod
    def _build_message_metadata(message, user) -> dict:
        """Build common Telegram inbound metadata payload."""
        reply_to = getattr(message, "reply_to_message", None)
        return {
            "message_id": message.message_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_group": message.chat.type != "private",
            "message_thread_id": getattr(message, "message_thread_id", None),
            "is_forum": bool(getattr(message.chat, "is_forum", False)),
            "reply_to_message_id": getattr(reply_to, "message_id", None) if reply_to else None,
        }

    async def _extract_reply_context(self, message) -> str | None:
        """Extract text from the message being replied to, if any."""
        reply = getattr(message, "reply_to_message", None)
        if not reply:
            return None
        text = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
        if len(text) > TELEGRAM_REPLY_CONTEXT_MAX_LEN:
            text = text[:TELEGRAM_REPLY_CONTEXT_MAX_LEN] + "..."

        if not text:
            return None

        bot_id, _ = await self._ensure_bot_identity()
        reply_user = getattr(reply, "from_user", None)

        if bot_id and reply_user and getattr(reply_user, "id", None) == bot_id:
            return f"[Reply to bot: {text}]"
        elif reply_user and getattr(reply_user, "username", None):
            return f"[Reply to @{reply_user.username}: {text}]"
        elif reply_user and getattr(reply_user, "first_name", None):
            return f"[Reply to {reply_user.first_name}: {text}]"
        else:
            return f"[Reply to: {text}]"

    @staticmethod
    def _extract_image_file(msg) -> dict[str, str] | None:
        """Extract image file info from a Telegram message (photo or image document).

        Returns ``{"file_id": ..., "mime_type": ...}`` when the message
        carries an image, or ``None`` otherwise.  Handles both the native
        Photo attachment and Documents whose MIME starts with ``image/``.
        """
        if msg is None:
            return None
        if getattr(msg, "photo", None):
            photo = msg.photo[-1]  # Largest resolution
            return {"file_id": photo.file_id, "mime_type": "image/jpeg"}
        doc = getattr(msg, "document", None)
        if doc:
            doc_mime = getattr(doc, "mime_type", "") or ""
            if doc_mime.startswith("image/"):
                return {"file_id": doc.file_id, "mime_type": doc_mime}
        return None

    async def _download_message_media(
        self, msg, *, add_failure_content: bool = False
    ) -> tuple[list[str], list[str]]:
        """Download media from a message (current or reply). Returns (media_paths, content_parts)."""
        media_file = None
        media_type = None
        if getattr(msg, "photo", None):
            media_file = msg.photo[-1]
            media_type = "image"
        elif getattr(msg, "voice", None):
            media_file = msg.voice
            media_type = "voice"
        elif getattr(msg, "audio", None):
            media_file = msg.audio
            media_type = "audio"
        elif getattr(msg, "document", None):
            media_file = msg.document
            # When a user sends an image/video via Telegram's "File" mode
            # instead of "Photo or Video", it arrives as a Document.
            # Reclassify based on MIME so downstream treats it like a native
            # photo/video (correct extension, vision blocks, etc.).
            doc_mime = getattr(media_file, "mime_type", "") or ""
            if doc_mime.startswith("image/"):
                media_type = "image"
            elif doc_mime.startswith("video/"):
                media_type = "video"
            else:
                media_type = "file"
        elif getattr(msg, "video", None):
            media_file = msg.video
            media_type = "video"
        elif getattr(msg, "video_note", None):
            media_file = msg.video_note
            media_type = "video"
        elif getattr(msg, "animation", None):
            media_file = msg.animation
            media_type = "animation"
        if not media_file or not self._app:
            return [], []
        try:
            file = await self._app.bot.get_file(media_file.file_id)
            doc_mime_type = getattr(media_file, "mime_type", None)
            doc_file_name = getattr(media_file, "file_name", None)
            ext = get_extension(media_type, doc_mime_type, doc_file_name)
            media_dir = get_media_dir("telegram")
            unique_id = getattr(media_file, "file_unique_id", media_file.file_id)
            file_path = media_dir / f"{unique_id}{ext}"
            await file.download_to_drive(str(file_path))
            path_str = str(file_path)
            self.logger.debug(
                "Downloaded media: type={}, mime={}, filename={}, saved={}",
                media_type, doc_mime_type, doc_file_name, file_path.name,
            )
            if media_type in ("voice", "audio"):
                transcription = await self.transcribe_audio(file_path)
                if transcription:
                    self.logger.info("Transcribed {}: {}...", media_type, transcription[:50])
                    return [path_str], [f"[transcription: {transcription}]"]
                return [path_str], [f"[{media_type}: {path_str}]"]
            return [path_str], [f"[{media_type}: {path_str}]"]
        except Exception as e:
            self.logger.warning("Failed to download message media: {}", e)
            if add_failure_content:
                return [], [f"[{media_type}: download failed]"]
            return [], []

    async def _ensure_bot_identity(self) -> tuple[int | None, str | None]:
        """Load bot identity once and reuse it for mention/reply checks."""
        if self._bot_user_id is not None or self._bot_username is not None:
            return self._bot_user_id, self._bot_username
        if not self._app:
            return None, None
        bot_info = await self._app.bot.get_me()
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        return self._bot_user_id, self._bot_username

    @staticmethod
    def _has_mention_entity(
        text: str,
        entities,
        bot_username: str,
        bot_id: int | None,
    ) -> bool:
        """Check Telegram mention entities against the bot username."""
        handle = f"@{bot_username}".lower()
        for entity in entities or []:
            entity_type = getattr(entity, "type", None)
            if entity_type == "text_mention":
                user = getattr(entity, "user", None)
                if user is not None and bot_id is not None and getattr(user, "id", None) == bot_id:
                    return True
                continue
            if entity_type != "mention":
                continue
            offset = getattr(entity, "offset", None)
            length = getattr(entity, "length", None)
            if offset is None or length is None:
                continue
            if text[offset : offset + length].lower() == handle:
                return True
        return handle in text.lower()

    async def _is_group_message_for_bot(self, message) -> bool:
        """Allow group messages when policy is open, @mentioned, or replying to the bot."""
        if message.chat.type == "private" or self.config.group_policy == "open":
            return True

        bot_id, bot_username = await self._ensure_bot_identity()
        if bot_username:
            text = message.text or ""
            caption = message.caption or ""
            if self._has_mention_entity(
                text,
                getattr(message, "entities", None),
                bot_username,
                bot_id,
            ):
                return True
            if self._has_mention_entity(
                caption,
                getattr(message, "caption_entities", None),
                bot_username,
                bot_id,
            ):
                return True

        reply_user = getattr(getattr(message, "reply_to_message", None), "from_user", None)
        return bool(bot_id and reply_user and reply_user.id == bot_id)

    def _remember_thread_context(self, message) -> None:
        """Cache Telegram thread context by chat/message id for follow-up replies."""
        message_thread_id = getattr(message, "message_thread_id", None)
        if message_thread_id is None:
            return
        key = (str(message.chat_id), message.message_id)
        self._message_threads[key] = message_thread_id
        if len(self._message_threads) > 1000:
            self._message_threads.pop(next(iter(self._message_threads)))

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)
        is_new_api_key_customer = (
            getattr(self.config, "require_user_api_key", False)
            and not self.keystore.get_key(sender_id)
        )
        if not is_new_api_key_customer and not self.is_allowed(sender_id):
            return

        if getattr(self.config, "require_user_api_key", False):
            if not self.keystore.get_key(sender_id):
                if self._looks_like_api_key(raw_text := (message.text or "").strip()):
                    self.keystore.set_key(sender_id, raw_text)
                    await self._delete_user_message(message.chat_id, message.message_id)
                    # Check if user already has a brand profile
                    has_profile = False
                    try:
                        from nanobot.utils.customer_profile import profile_exists
                        uid_check = sender_id.split("|")[0].strip()
                        has_profile = profile_exists(uid_check)
                    except Exception:
                        pass
                    if has_profile:
                        await message.reply_text(
                            "✅ *Đã lưu Vidtory API Key thành công!*\n"
                            "Bot đang sẵn sàng. Gõ /help để xem danh sách lệnh.\n\n"
                            "_(Vì lý do bảo mật, tin nhắn chứa API Key của bạn đã được xóa tự động)_",
                            parse_mode="Markdown"
                        )
                    else:
                        buttons = [["Bắt đầu khai báo", "Dùng ngay"]]
                        reply_markup = self._build_keyboard(buttons)
                        await message.reply_text(
                            "✅ *Đã lưu Vidtory API Key thành công!*\n\n"
                            "🎯 Để bot tạo nội dung *bám sát thương hiệu* của bạn, "
                            "mình cần biết thêm một chút về brand.\n\n"
                            "Bạn muốn thiết lập brand profile ngay không?\n"
                            "_(Chỉ mất khoảng 1 phút — rất đáng làm!)_\n\n"
                            "_(Vì lý do bảo mật, tin nhắn chứa API Key của bạn đã được xóa tự động)_",
                            parse_mode="Markdown",
                            reply_markup=reply_markup,
                        )
                    return
                else:
                    await message.reply_text(
                        "🔑 *Bạn chưa có Vidtory API Key.*\n\n"
                        "*Cách lấy API Key:*\n"
                        "1\u20e3 Truy cập: https://app.vidtory.net/settings/api\n"
                        "2\u20e3 Đăng nhập và tạo/copy API Key\n"
                        "3\u20e3 Gửi lệnh: `/apikey YOUR_API_KEY`\n\n"
                        "_Chỉ cần thực hiện một lần duy nhất!_",
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                    return
        else:
            # Even when require_user_api_key=False, auto-detect and save bare
            # Vidtory API keys so the user doesn't have to use /apikey explicitly.
            raw_text = (message.text or "").strip()
            if self._looks_like_api_key(raw_text):
                self.keystore.set_key(sender_id, raw_text)
                await self._delete_user_message(message.chat_id, message.message_id)
                has_profile = False
                try:
                    from nanobot.utils.customer_profile import profile_exists
                    uid_check = sender_id.split("|")[0].strip()
                    has_profile = profile_exists(uid_check)
                except Exception:
                    pass
                if has_profile:
                    await message.reply_text(
                        "✅ *Đã lưu Vidtory API Key thành công!*\n"
                        "Bot đang sẵn sàng phục vụ bạn.\n\n"
                        "_(Vì lý do bảo mật, tin nhắn chứa API Key của bạn đã được xóa tự động)_",
                        parse_mode="Markdown"
                    )
                else:
                    buttons = [["Bắt đầu khai báo", "Dùng ngay"]]
                    reply_markup = self._build_keyboard(buttons)
                    await message.reply_text(
                        "✅ *Đã lưu Vidtory API Key thành công!*\n\n"
                        "🎯 Để bot tạo nội dung *bám sát thương hiệu* của bạn, "
                        "mình cần biết thêm một chút về brand.\n\n"
                        "Bạn muốn thiết lập brand profile ngay không?\n"
                        "_(Chỉ mất khoảng 1 phút — rất đáng làm!)_\n\n"
                        "_(Vì lý do bảo mật, tin nhắn chứa API Key của bạn đã được xóa tự động)_",
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                return

        self._remember_thread_context(message)

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id
        str_chat_id = str(chat_id)

        if not await self._is_group_message_for_bot(message):
            return

        media_group_id = getattr(message, "media_group_id", None)
        media_group_key = (
            f"{str_chat_id}:{media_group_id}" if media_group_id else None
        )
        if media_group_key:
            self._media_group_collector.begin_part(media_group_key)

        # Build content from text and/or media
        content_parts = []
        media_paths = []

        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Location content
        if message.location:
            lat = message.location.latitude
            lon = message.location.longitude
            content_parts.append(f"[location: {lat}, {lon}]")

        try:
            # Download current message media
            current_media_paths, current_media_parts = await self._download_message_media(
                message, add_failure_content=True
            )
            media_paths.extend(current_media_paths)
            content_parts.extend(current_media_parts)
            if current_media_paths:
                self.logger.debug("Downloaded message media to {}", current_media_paths[0])

            # Reply context: text and/or media from the replied-to message
            reply_media: list[str] = []
            reply = getattr(message, "reply_to_message", None)
            if reply is not None:
                reply_ctx = await self._extract_reply_context(message)
                reply_media, reply_media_parts = await self._download_message_media(reply)
                if reply_media:
                    media_paths = reply_media + media_paths
                    self.logger.debug("Attached replied-to media: {}", reply_media[0])
                tag = reply_ctx or (f"[Reply to: {reply_media_parts[0]}]" if reply_media_parts else None)
                if tag:
                    content_parts.insert(0, tag)
        except Exception:
            if media_group_key:
                self._media_group_collector.abort_part(media_group_key)
            raise
        content = "\n".join(content_parts) if content_parts else "[empty message]"

        self.logger.debug("message from {}: {}...", sender_id, content[:50])

        metadata = self._build_message_metadata(message, user)
        metadata["reply_media"] = list(reply_media)
        metadata["current_media"] = list(current_media_paths)
        session_key = self._derive_topic_session_key(message)

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_key:
            is_first_part = not self._media_group_collector.groups[media_group_key].parts
            self._media_group_collector.finish_part(
                media_group_key,
                MediaGroupPart(
                    message_id=message.message_id,
                    sender_id=sender_id,
                    chat_id=str_chat_id,
                    content=content,
                    media=list(media_paths),
                    metadata=metadata,
                    session_key=session_key,
                    current_media=list(current_media_paths),
                    reply_media=list(reply_media),
                ),
            )
            if is_first_part:
                self._start_typing(str_chat_id)
                await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)
            if media_group_key not in self._media_group_tasks:
                self._media_group_tasks[media_group_key] = asyncio.create_task(
                    self._flush_media_group(media_group_key)
                )
            return

        # Guard: When user sends photo/document without any text or caption,
        # ask what they want to do instead of auto-generating content.
        has_media = bool(media_paths)
        has_text = bool(message.text or message.caption)
        is_reply = reply is not None
        if has_media and not has_text and not is_reply:
            # Bypass this guard during onboarding since the user is expected to send a logo/signal
            in_onboarding = False
            try:
                from nanobot.utils.customer_profile import get_onboarding_status
                uid_check = sender_id.split("|")[0].strip()
                in_onboarding = get_onboarding_status(uid_check) == "in_progress"
            except Exception:
                pass

            if not in_onboarding:
                # Determine if this is a document file (not image/video)
                doc = getattr(message, "document", None)
                is_document_file = (
                    doc is not None
                    and not (getattr(doc, "mime_type", "") or "").startswith(("image/", "video/"))
                )

                if is_document_file:
                    file_name = getattr(doc, "file_name", "file") or "file"

                    # Early rejection for blocked file types
                    from nanobot.utils.document_sanitizer import sanitize_document
                    if media_paths:
                        scan = sanitize_document(media_paths[0])
                        if scan.status == "blocked":
                            await message.reply_text(
                                scan.user_message,
                                parse_mode="Markdown",
                            )
                            return

                    pending = getattr(self, "_pending_media_choices", {})
                    pending[f"{str_chat_id}:{sender_id}"] = {
                        "media": list(media_paths),
                        "metadata": dict(metadata),
                        "session_key": session_key,
                        "expires_at": time.monotonic() + 600,
                    }
                    self._pending_media_choices = pending
                    await message.reply_text(
                        f"📄 *File đã nhận: `{file_name}`*\n\n"
                        "Bạn muốn tôi dùng file này theo cách nào?",
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard([
                            ["Cập nhật thương hiệu", "Dùng làm brief"],
                            ["Đọc và tóm tắt"],
                        ]),
                    )
                else:
                    pending = getattr(self, "_pending_media_choices", {})
                    pending[f"{str_chat_id}:{sender_id}"] = {
                        "media": list(media_paths),
                        "metadata": dict(metadata),
                        "session_key": session_key,
                        "expires_at": time.monotonic() + 600,
                    }
                    self._pending_media_choices = pending
                    await message.reply_text(
                        "📷 *Ảnh đã nhận!*\n\n"
                        "Bạn muốn tôi làm gì với ảnh này?",
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard([
                            ["Đặt làm logo", "Chỉnh ảnh này"],
                            ["Dùng làm tham chiếu"],
                        ]),
                    )
                return

        # Guard: New user onboarding prompt
        try:
            from nanobot.utils.customer_profile import get_onboarding_status
            uid = sender_id.split("|")[0].strip()
            if get_onboarding_status(uid) == "none":
                raw_text = (message.text or "").strip().lower()
                # If user hasn't made a choice yet, show the prompt and stop processing
                if raw_text not in ("dùng ngay", "bỏ qua, dùng ngay", "bắt đầu khai báo", "khai báo thông tin"):
                    buttons = [
                        ["Bắt đầu khai báo", "Dùng ngay"]
                    ]
                    reply_markup = self._build_keyboard(buttons)
                    await message.reply_text(
                        "👋 *Chào mừng bạn đến với Vidtory Agent!*\n\n"
                        "Để tôi có thể tạo ra hình ảnh và video bám sát nhận diện thương hiệu của bạn, "
                        "chúng ta nên thực hiện một bài khai báo ngắn (khoảng 3 câu hỏi).\n\n"
                        "Bạn muốn khai báo ngay, hay bỏ qua để dùng thử profile cơ bản?",
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                    return
        except Exception as e:
            self.logger.warning("Error checking onboarding status for prompt: {}", e)

        # Guard: Logo pre-flight for ad/marketing image requests
        # When user asks to create advertising/promotional content but has no logo set,
        # prompt them to add a logo first (or explicitly skip) before proceeding.
        try:
            from nanobot.utils.customer_profile import get_logo_url, profile_exists
            uid_logo = sender_id.split("|")[0].strip()
            raw_req = (message.text or message.caption or "").strip().lower()
            _AD_KEYWORDS = (
                # Quảng cáo / marketing
                "quảng cáo", "quảng bá", "banner", "poster", "flyer", "truyền thông",
                "marketing", "khuyến mãi", "sale", "promotion", "advertis",
                "social media", "facebook ads", "instagram", "thumbnail", "cover", "landing",
                # Thương hiệu / sản phẩm
                "sản phẩm", "thương hiệu", "brand", "nhãn hàng",
                # Sự kiện / tổ chức
                "sự kiện", "tuyển sinh", "vinh danh", "tri ân", "kỷ niệm", "chào mừng",
                "lễ tốt nghiệp", "hội nghị", "hội thảo", "khai giảng", "bế giảng",
                "giải thưởng", "thành tích", "chương trình", "hoạt động",
                # Tổ chức / trường học
                "trường", "cục", "phòng", "viện", "nhà trường", "nhà máy", "công ty",
            )
            _LOGO_SKIP_PHRASES = (
                "không có logo", "bỏ qua logo", "không cần logo",
                "skip logo", "no logo", "tạo không cần logo",
            )
            is_ad_request = any(kw in raw_req for kw in _AD_KEYWORDS)
            user_skipping_logo = any(kw in raw_req for kw in _LOGO_SKIP_PHRASES)
            if (
                is_ad_request
                and not user_skipping_logo
                and profile_exists(uid_logo)
                and not get_logo_url(uid_logo)
            ):
                buttons = [["📤 Thêm logo ngay", "⏩ Tạo không cần logo"]]
                reply_markup = self._build_keyboard(buttons)
                await message.reply_text(
                    "🖼️ *Bạn chưa có logo thương hiệu!*\n\n"
                    "Logo giúp ảnh quảng cáo trông chuyên nghiệp và nhận diện thương hiệu hơn rất nhiều.\n\n"
                    "*Cách thêm logo:*\n"
                    "• Gửi URL: `/setlogo https://link-logo.png`\n"
                    "• Gửi file: reply ảnh logo + gõ `/setlogo`\n\n"
                    "Bạn muốn thêm logo trước, hay tạo ảnh không cần logo?",
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return
        except Exception as e:
            self.logger.warning("Error in logo pre-flight check: {}", e)

        # Start typing indicator before processing
        self._start_typing(str_chat_id)
        await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)

        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
            session_key=session_key,
        )

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
        is_dm: bool = False,
    ) -> None:
        metadata = dict(metadata or {})

        pending_choices = getattr(self, "_pending_media_choices", {})
        pending = pending_choices.pop(f"{chat_id}:{sender_id}", None)
        if pending and float(pending.get("expires_at") or 0) < time.monotonic():
            pending = None
        choice_prompts = {
            "đặt làm logo": "Đặt ảnh đính kèm làm logo thương hiệu và tự cập nhật phong cách theo logo mới.",
            "chỉnh ảnh này": "Tôi muốn chỉnh ảnh đính kèm. Hãy hỏi một câu ngắn kèm các nút gợi ý sát với ảnh.",
            "dùng làm tham chiếu": "Dùng ảnh đính kèm làm ảnh tham chiếu cho yêu cầu sáng tạo tiếp theo.",
            "cập nhật thương hiệu": "Đọc file đính kèm và cập nhật Brand Profile từ toàn bộ thông tin phù hợp.",
            "dùng làm brief": "Đọc file đính kèm như design brief và đề xuất hướng thực hiện sát nội dung.",
            "đọc và tóm tắt": "Đọc và tóm tắt file đính kèm bằng tiếng Việt.",
        }
        normalized_choice = content.strip().lower()
        if pending:
            media = list(pending.get("media") or []) + list(media or [])
            pending_metadata = dict(pending.get("metadata") or {})
            pending_metadata.update(metadata)
            metadata = pending_metadata
            metadata["current_media"] = list(media)
            session_key = session_key or pending.get("session_key")
            content = choice_prompts.get(normalized_choice, content)

        # Handle logo pre-flight button responses
        _raw_content = content.strip().lower()
        if _raw_content in ("\ud83d\udce4 th\u00eam logo ngay", "th\u00eam logo ngay"):
            # User wants to add a logo — send setlogo guide and stop
            if self._app:
                with suppress(Exception):
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "\ud83d\uddbc\ufe0f *H\u01b0\u1edbng d\u1eabn th\u00eam logo th\u01b0\u01a1ng hi\u1ec7u:*\n\n"
                            "*C\u00e1ch 1 \u2014 G\u1eedi URL logo:*\n"
                            "`/setlogo https://link-logo-cua-ban.png`\n\n"
                            "*C\u00e1ch 2 \u2014 G\u1eedi file \u1ea3nh tr\u1ef1c ti\u1ebfp:*\n"
                            "1\ufe0f\u20e3 G\u1eedi \u1ea3nh logo v\u00e0o chat\n"
                            "2\ufe0f\u20e3 Reply \u1ea3nh \u0111\u00f3 v\u00e0 g\u00f5 `/setlogo`\n\n"
                            "*C\u00e1ch 3 \u2014 G\u1eedi \u1ea3nh k\u00e8m l\u1ec7nh:*\n"
                            "G\u1eedi \u1ea3nh logo v\u1edbi caption `/setlogo`\n\n"
                            "_Sau khi th\u00eam logo xong, b\u1ea1n c\u00f3 th\u1ec3 ti\u1ebfp t\u1ee5c y\u00eau c\u1ea7u t\u1ea1o \u1ea3nh ban \u0111\u1ea7u._"
                        ),
                        parse_mode="Markdown",
                    )
            return
        if _raw_content in ("\u23e9 t\u1ea1o kh\u00f4ng c\u1ea7n logo", "t\u1ea1o kh\u00f4ng c\u1ea7n logo"):
            # User explicitly skips logo — pass through with a hint so LLM knows
            metadata["logo_skipped"] = True
            content = content + "\n[Người dùng chọn tạo ảnh không cần logo thương hiệu]"

        # Always inject keystore API key into metadata so Vidtory tools receive the
        # merchant key regardless of require_user_api_key setting.
        # user_workspace is also always set to a per-user directory.
        key = self.keystore.get_key(sender_id)
        user_workspace = str(get_workspace_path() / "telegram_users" / chat_id)
        metadata["user_api_key"] = key or ""
        metadata["user_workspace"] = user_workspace
        Path(user_workspace).mkdir(parents=True, exist_ok=True)

        # Load customer profile and inject into metadata for brand-aware context.
        # For new users (status='none'), silently create a minimal profile so they
        # can start working immediately — no onboarding questionnaire needed.
        try:
            from nanobot.utils.customer_profile import (
                create_minimal_profile,
                get_onboarding_status,
                load_profile,
                save_profile,
            )
            from nanobot.utils.brand_intelligence import build_adaptive_onboarding_step
            uid = sender_id.split("|")[0].strip()
            onboarding_status = get_onboarding_status(uid)
            raw_content = content.strip().lower()

            if raw_content in ("đúng ý", "ưng ý"):
                from nanobot.utils.customer_profile import record_latest_task_feedback

                result = record_latest_task_feedback(uid, rating="approved")
                if result.get("recorded"):
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text="Cảm ơn bạn, mình đã ghi nhận gu này cho các lần tạo sau.",
                        reply_markup=self._build_keyboard([["Tạo ảnh mới"]]),
                    )
                    self._stop_typing(chat_id)
                    return

            if raw_content in ("cần chỉnh", "chưa đúng ý"):
                from nanobot.utils.customer_profile import record_latest_task_feedback

                record_latest_task_feedback(uid, rating="rejected")
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text="Bạn muốn chỉnh phần nào? Có thể bấm nút hoặc mô tả trực tiếp.",
                    reply_markup=self._build_keyboard([
                        ["Màu sắc", "Bố cục", "Chữ trên ảnh"],
                        ["Phong cách", "Logo", "Chi tiết khác"],
                    ]),
                )
                self._stop_typing(chat_id)
                return


            # Handle new user onboarding choice
            if onboarding_status == "none":
                if raw_content in ("dùng ngay", "bỏ qua, dùng ngay"):
                    username = metadata.get("username") or ""
                    create_minimal_profile(uid, username=username)
                    onboarding_status = "minimal"
                    # Translate to a clear instruction for the LLM
                    content = "Tôi muốn bỏ qua khai báo và bắt đầu sử dụng bot ngay."
                elif raw_content in ("bắt đầu khai báo", "khai báo thông tin"):
                    username = metadata.get("username") or ""
                    profile = create_minimal_profile(uid, username=username)
                    profile["onboarding"]["status"] = "in_progress"
                    save_profile(uid, profile)
                    step = build_adaptive_onboarding_step(profile)
                    try:
                        await self._app.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "🎨 *Thiết lập Brand Profile*\n\n"
                                f"{step['prompt']}\n\n"
                                "_Bạn có thể bấm nút hoặc nhập câu trả lời theo cách tự nhiên._"
                            ),
                            parse_mode="Markdown",
                            reply_markup=self._build_keyboard(step["buttons"]) if step["buttons"] else None,
                        )
                    except Exception as e:
                        self.logger.warning("Failed to send onboarding template: {}", e)
                    finally:
                        self._stop_typing(chat_id)
                    return
                else:
                    # Fallback for non-Telegram channels or unexpected flows
                    username = metadata.get("username") or ""
                    create_minimal_profile(uid, username=username)
                    onboarding_status = "minimal"

            elif raw_content in ("bổ sung nhanh", "tiếp tục onboarding", "khai báo thông tin"):
                profile = load_profile(uid) or create_minimal_profile(uid)
                profile.setdefault("onboarding", {})["status"] = "in_progress"
                save_profile(uid, profile)
                step = build_adaptive_onboarding_step(profile)
                try:
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "🧭 *Bổ sung Brand Profile*\n\n"
                            f"{step['prompt']}\n\n"
                            "_Bạn có thể bấm nút, nhập text, gửi URL hoặc tải file._"
                        ),
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard(step["buttons"]) if step["buttons"] else None,
                    )
                finally:
                    self._stop_typing(chat_id)
                return


            metadata["onboarding_status"] = onboarding_status  # 'minimal'|'completed'

            customer_profile = load_profile(uid)
            if customer_profile:
                metadata["customer_profile"] = customer_profile
        except Exception:
            pass  # Non-critical: never block the message if profile load fails

        await super()._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media,
            metadata=metadata,
            session_key=session_key,
            is_dm=is_dm,
        )
