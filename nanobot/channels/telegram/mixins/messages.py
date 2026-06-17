from __future__ import annotations

import asyncio
import time
import unicodedata
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.ext import ContextTypes

from nanobot.config.paths import get_media_dir, get_workspace_path
from nanobot.channels.telegram.format import TELEGRAM_REPLY_CONTEXT_MAX_LEN
from nanobot.channels.telegram.utils import get_extension, is_remote_media_url

if TYPE_CHECKING:
    from nanobot.channels.telegram.channel import TelegramChannel

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
    def _plain_user_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text.lower())
        without_marks = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )
        return " ".join(without_marks.split())

    @classmethod
    def _is_logo_skip_request(cls, text: str) -> bool:
        value = cls._plain_user_text(text)
        return any(
            phrase in value
            for phrase in (
                "khong co logo",
                "bo qua logo",
                "khong can logo",
                "skip logo",
                "no logo",
                "tao khong can logo",
            )
        )

    @classmethod
    def _is_creative_generation_request(cls, text: str) -> bool:
        value = cls._plain_user_text(text)
        if not value:
            return False
        if "tao khong can logo" in value:
            return True
        generation_terms = ("tao", "ve", "thiet ke", "lam", "generate")
        output_terms = (
            "anh",
            "hinh",
            "poster",
            "banner",
            "quang cao",
            "creative",
            "visual",
            "san pham",
            "thumbnail",
            "cover",
            "flyer",
            "story",
            "reels",
        )
        return any(term in value for term in generation_terms) and any(
            term in value for term in output_terms
        )

    def _remember_logo_prompt_skipped(self, uid: str) -> None:
        try:
            from nanobot.utils.customer_profile import load_profile, save_profile

            profile = load_profile(uid)
            if not profile:
                return
            profile.setdefault("preferences", {})["logoPromptSkipped"] = True
            save_profile(uid, profile)
        except Exception as e:
            self.logger.warning("Failed to remember logo skip preference: {}", e)

    @staticmethod
    def _profile_needs_brand_prompt(profile: dict, generation_count: int) -> bool:
        """Return True nếu cần hiển thị brand onboarding prompt trước khi tạo ảnh.

        Logic nhắc lại thông minh:
        - Nếu completeness >= 60% → không bao giờ nhắc (đủ dữ liệu).
        - Lần 1 bỏ qua → nhắc lại ở generation thứ 3.
        - Lần 2 bỏ qua → nhắc lại ở generation thứ 5.
        - Lần 3+ bỏ qua → không nhắc nữa (user đã quyết định rõ ràng).
        """
        try:
            from nanobot.utils.customer_profile import get_profile_completeness
            completeness = get_profile_completeness(profile)
            if completeness >= 60:
                return False
        except Exception:
            pass

        preferences = profile.get("preferences") or {}
        skip_count = int(preferences.get("brandPromptSkipCount", 0))
        if skip_count >= 3:
            return False  # User đã bỏ qua 3 lần — không nhắc nữa

        next_gen = int(preferences.get("brandPromptNextGeneration", 0))
        if next_gen == 0:
            # Chưa từng hỏi → hỏi ngay
            return True
        return generation_count >= next_gen

    async def _handle_onboarding_quick_reply(
        self,
        *,
        chat_id: str,
        content: str,
        sender_id: str,
        reply_message=None,
    ) -> bool:
        value = self._plain_user_text(content)
        text = ""
        buttons: list[list[str]] | None = None

        # ── Brand Prompt: Đồng ý → bắt đầu onboarding ────────────────────────
        if value == "dong y":
            try:
                from nanobot.utils.brand_intelligence import build_adaptive_onboarding_step
                from nanobot.utils.customer_profile import load_profile, save_profile
                uid_ob = sender_id.split("|")[0].strip()
                profile_ob = load_profile(uid_ob) or {}
                
                # Check guard: only trigger if they actually need onboarding
                if not self._profile_needs_brand_prompt(profile_ob, 999999) and profile_ob.get("onboarding", {}).get("status") != "minimal":
                    return False
                    
                profile_ob.setdefault("onboarding", {})["status"] = "in_progress"
                save_profile(uid_ob, profile_ob)
                step = build_adaptive_onboarding_step(profile_ob)
                if self._app:
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
                return True
            except Exception as e:
                self.logger.warning("Brand prompt agree handler error: {}", e)

        # ── Brand Prompt: Bỏ qua → nhắc lại sau theo generation count ────────
        if value == "bo qua":
            try:
                from nanobot.utils.customer_profile import load_profile, save_profile
                from nanobot.db.customer_db import get_db as _brand_skip_get_db
                uid_skip = sender_id.split("|")[0].strip()
                profile_skip = load_profile(uid_skip) or {}
                prefs_skip = profile_skip.setdefault("preferences", {})
                skip_count = int(prefs_skip.get("brandPromptSkipCount", 0)) + 1
                prefs_skip["brandPromptSkipCount"] = skip_count
                # Schedule next reminder: skip 1 → gen 3, skip 2 → gen 5
                REMIND_AT = {1: 3, 2: 5}
                current_gen = _brand_skip_get_db().get_generation_count(uid_skip)
                remind_offset = REMIND_AT.get(skip_count, 0)
                if remind_offset:
                    prefs_skip["brandPromptNextGeneration"] = current_gen + remind_offset
                else:
                    # 3rd skip — mark as never remind again
                    prefs_skip["brandPromptNextGeneration"] = 999999
                save_profile(uid_skip, profile_skip)
            except Exception as e:
                self.logger.warning("Brand prompt skip handler error: {}", e)
            # Do NOT return True — let the original request fall through to LLM
            return False

        if value == "gui logo":
            # Set flag: next photo from this user = set as logo directly
            pending_intent = getattr(self, "_pending_logo_intent", {})
            pending_intent[sender_id] = time.monotonic() + 600
            self._pending_logo_intent = pending_intent
            text = "Bạn gửi ảnh logo vào đây, mình đặt làm logo thương hiệu luôn nhé."
        elif value in {"nhap website", "gui website", "dung website"}:
            text = (
                "Bạn gửi link website của thương hiệu vào đây nhé.\n\n"
                "Ví dụ:\n"
                "• https://vidtory.ai\n\n"
                "Mình sẽ dựa vào website để nhận diện:\n"
                "• tên thương hiệu\n"
                "• màu sắc chính\n"
                "• phong cách hình ảnh\n"
                "• mô tả ngắn về lĩnh vực hoạt động\n\n"
                "Bạn gửi URL website đi, mình xem cho."
            )
        elif value in {"chua co logo", "khong co logo"}:
            self._remember_logo_prompt_skipped(sender_id.split("|")[0].strip())
            text = (
                "Không sao, mình vẫn có thể thiết lập gu thiết kế trước.\n\n"
                "Bạn chọn một style reference gần nhất nhé:\n"
                "1. Clean Premium - tối giản, cao cấp, sạch và dễ dùng.\n"
                "2. Bold Performance - nổi bật, mạnh, hợp quảng cáo chuyển đổi.\n"
                "3. Editorial Fashion - giàu cảm xúc, có chất biên tập và nghệ thuật.\n\n"
                "Sau này khi có logo, bạn gửi thêm để hệ thống bám nhận diện tốt hơn."
            )
            buttons = [["Clean Premium", "Bold Performance", "Editorial Fashion"]]
        else:
            return False

        reply_markup = self._build_keyboard(buttons) if buttons else None
        if reply_message is not None:
            await reply_message.reply_text(text, reply_markup=reply_markup)
            return True
        if self._app:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            return True
        return False

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
        if not self.is_allowed(sender_id):
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
                            "✅ *API Key đã được cấu hình. Hệ thống sẵn sàng.*\n"
                            "Gửi yêu cầu tạo ảnh hoặc video bất kỳ lúc nào.\n\n"
                            "_(Để bảo mật, tin nhắn chứa API Key đã được xóa tự động)_",
                            parse_mode="Markdown"
                        )
                    else:
                        await message.reply_text(
                            "✅ *API Key đã được cấu hình. Hệ thống sẵn sàng.*\n\n"
                            "Gửi yêu cầu tạo ảnh, video hoặc gửi logo thương hiệu để bắt đầu.\n\n"
                            "_(Để bảo mật, tin nhắn chứa API Key đã được xóa tự động)_",
                            parse_mode="Markdown",
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
                        "✅ *API Key đã được cấu hình. Hệ thống sẵn sàng.*\n"
                        "Gửi yêu cầu tạo ảnh hoặc video bất kỳ lúc nào.\n\n"
                        "_(Để bảo mật, tin nhắn chứa API Key đã được xóa tự động)_",
                        parse_mode="Markdown"
                    )
                else:
                    await message.reply_text(
                        "✅ *API Key đã được cấu hình. Hệ thống sẵn sàng.*\n\n"
                        "Gửi yêu cầu tạo ảnh, video hoặc gửi logo thương hiệu để bắt đầu.\n\n"
                        "_(Để bảo mật, tin nhắn chứa API Key đã được xóa tự động)_",
                        parse_mode="Markdown",
                    )
                return

        self._remember_thread_context(message)

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        if not await self._is_group_message_for_bot(message):
            return

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
        content = "\n".join(content_parts) if content_parts else "[empty message]"

        self.logger.debug("message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)
        metadata = self._build_message_metadata(message, user)
        metadata["reply_media"] = list(reply_media)
        metadata["current_media"] = list(current_media_paths)
        session_key = self._derive_topic_session_key(message)

        if await self._handle_onboarding_quick_reply(
            chat_id=str_chat_id,
            content=content,
            sender_id=sender_id,
            reply_message=message,
        ):
            return

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_id := getattr(message, "media_group_id", None):
            from nanobot.channels.telegram.mixins.media import _MEDIA_GROUP_MAX_WAIT
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                self._media_group_buffers[key] = {
                    "sender_id": sender_id, "chat_id": str_chat_id,
                    "contents": [], "media": [],
                    "metadata": metadata,
                    "session_key": session_key,
                    "_max_flush_at": time.monotonic() + _MEDIA_GROUP_MAX_WAIT,
                }
                self._start_typing(str_chat_id)
                await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)
            
            buf = self._media_group_buffers[key]
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)

            # Reset sliding window
            mg_tasks = getattr(self, "_media_group_tasks", {})
            old_task = mg_tasks.get(key)
            if old_task and not old_task.done() and time.monotonic() < buf.get("_max_flush_at", 0):
                old_task.cancel()
            
            mg_tasks[key] = asyncio.create_task(self._flush_media_group(key))
            self._media_group_tasks = mg_tasks
            return

        # Guard: When user sends photo/document without any text or caption,
        # ask what they want to do instead of auto-generating content.
        has_media = bool(media_paths)
        has_text = bool(message.text or message.caption)
        is_reply = reply is not None
        if has_media and not has_text and not is_reply:
            # If a text+media buffer is pending for this user (photo+caption arrived
            # just before, waiting to collect siblings), merge this image into it
            # and reset the sliding-window timer so the flush waits for us too.
            _tmb = getattr(self, "_text_media_buffers", {})
            _tmb_key = f"{str_chat_id}:{sender_id}"
            if _tmb_key in _tmb:
                _tmb[_tmb_key]["media"] = list(dict.fromkeys(
                    _tmb[_tmb_key]["media"] + list(media_paths)
                ))
                _tmb[_tmb_key]["metadata"]["current_media"] = _tmb[_tmb_key]["media"]
                self._text_media_buffers = _tmb
                # Reset the sliding window: cancel existing task, start fresh 1s timer.
                _tmb_tasks = getattr(self, "_text_media_tasks", {})
                _old_task = _tmb_tasks.get(_tmb_key)
                _max_flush_at = _tmb[_tmb_key].get("_max_flush_at", 0.0)
                if _old_task and not _old_task.done() and time.monotonic() < _max_flush_at:
                    _old_task.cancel()
                    _tmb_tasks[_tmb_key] = asyncio.create_task(
                        self._flush_text_media_buffer(_tmb_key)
                    )
                    self._text_media_tasks = _tmb_tasks
                await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)
                return

            # Add reaction immediately — this path returns early and never reaches
            # the normal _add_reaction call later in the flow.
            await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)
            doc = getattr(message, "document", None)
            is_document_file = (
                doc is not None
                and not (getattr(doc, "mime_type", "") or "").startswith(("image/", "video/"))
            )

            # Fast-path: user is in "gui logo" intent flow → set photo as logo directly
            pending_logo_intent = getattr(self, "_pending_logo_intent", {})
            logo_intent_expires = pending_logo_intent.get(sender_id, 0)
            if not is_document_file and logo_intent_expires > time.monotonic():
                # Clear the intent
                pending_logo_intent.pop(sender_id, None)
                self._pending_logo_intent = pending_logo_intent
                # Show typing indicator while processing
                self._start_typing(str_chat_id)
                # Trigger logo save directly — inject as choice selection
                pending_choices = getattr(self, "_pending_media_choices", {})
                pending_choices[f"{str_chat_id}:{sender_id}"] = {
                    "media": list(media_paths),
                    "metadata": dict(metadata),
                    "session_key": session_key,
                    "expires_at": time.monotonic() + 60,
                }
                self._pending_media_choices = pending_choices
                # Re-invoke handler with "Đặt logo" as the choice
                await self._handle_message(
                    sender_id=sender_id,
                    chat_id=str_chat_id,
                    content="Đặt logo",
                    media=list(media_paths),
                    metadata=metadata,
                    session_key=session_key,
                )
                return

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
                pmc_key = f"{str_chat_id}:{sender_id}"
                existing = pending.get(pmc_key)
                if (
                    existing
                    and float(existing.get("expires_at") or 0) > time.monotonic()
                ):
                    # Accumulate: user sent another image — merge into existing entry
                    # instead of overwriting, so later requests see ALL images.
                    merged_media = list(dict.fromkeys(
                        list(existing.get("media") or []) + list(media_paths)
                    ))
                    existing["media"] = merged_media
                    existing["metadata"]["current_media"] = merged_media
                    existing["expires_at"] = time.monotonic() + 600
                    pending[pmc_key] = existing
                    self._pending_media_choices = pending
                    img_count = len(merged_media)
                    await message.reply_text(
                        f"📷 *{img_count} ảnh đã nhận!*\n\n"
                        "Bạn muốn làm gì với các ảnh này?",
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard([
                            ["Đặt logo", "Chỉnh ảnh này"],
                            ["Dùng làm tham chiếu"],
                        ]),
                    )
                else:
                    # First image from this user — create a new pending entry.
                    pending[pmc_key] = {
                        "media": list(media_paths),
                        "metadata": dict(metadata),
                        "session_key": session_key,
                        "expires_at": time.monotonic() + 600,
                    }
                    self._pending_media_choices = pending
                    await message.reply_text(
                        "📷 *Ảnh đã nhận!*\n\n"
                        "Bạn muốn làm gì với ảnh này?",
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard([
                            ["Đặt logo", "Chỉnh ảnh này"],
                            ["Dùng làm tham chiếu"],
                        ]),
                    )
            return


        creative_request = self._is_creative_generation_request(content)
        onboarding_status = "none"

        # Guard: New user onboarding prompt
        try:
            from nanobot.utils.customer_profile import get_onboarding_status
            uid = sender_id.split("|")[0].strip()
            status = get_onboarding_status(uid)
            onboarding_status = status
            if status == "none" or (
                status == "minimal"
                and not self.keystore.get_key(sender_id)
                and not creative_request
            ):
                await self._begin_onboarding(message, user)
                return
        except Exception as e:
            self.logger.warning("Error checking onboarding status for prompt: {}", e)

        # Guard: Logo pre-flight for ad/marketing image requests
        # When user asks to create advertising/promotional content but has no logo set,
        # prompt them to add a logo first (or explicitly skip) before proceeding.
        try:
            from nanobot.utils.customer_profile import (
                get_logo_url,
                get_onboarding_status,
                load_profile,
                profile_exists,
            )
            uid_logo = sender_id.split("|")[0].strip()
            raw_req = (message.text or message.caption or "").strip()
            user_skipping_logo = self._is_logo_skip_request(raw_req)
            if user_skipping_logo:
                self._remember_logo_prompt_skipped(uid_logo)
            profile = load_profile(uid_logo) or {}
            preferences = profile.get("preferences") if isinstance(profile, dict) else {}
            logo_prompt_skipped = bool((preferences or {}).get("logoPromptSkipped"))
            if (
                creative_request
                and not user_skipping_logo
                and not logo_prompt_skipped
                and get_onboarding_status(uid_logo) != "in_progress"
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

        # Guard: Brand Profile empty — prompt user to provide brand info before generating
        # Only when creative request + profile is nearly empty (completeness < 60%).
        # Reminder schedule: skip 1 → remind at gen+3; skip 2 → remind at gen+5;
        # skip 3+ → stop reminding. Never blocks when completeness >= 60%.
        try:
            from nanobot.utils.customer_profile import load_profile, profile_exists
            from nanobot.db.customer_db import get_db as _gen_count_db
            uid_brand = sender_id.split("|")[0].strip()
            if (
                creative_request
                and onboarding_status not in ("in_progress",)
            ):
                profile_brand = load_profile(uid_brand) or {}
                gen_count = _gen_count_db().get_generation_count(uid_brand)
                if self._profile_needs_brand_prompt(profile_brand, gen_count):
                    brand_buttons = [["Đồng ý", "Bỏ qua"]]
                    await message.reply_text(
                        "📋 *Thông tin thương hiệu của bạn còn khá ít!*\n\n"
                        "Cung cấp thêm thông tin giúp AI tạo ảnh *bám sát thương hiệu* hơn rất nhiều — "
                        "tên thương hiệu, phong cách, lĩnh vực hoạt động, v.v.\n\n"
                        "Bạn có muốn khai báo nhanh (~1 phút) để có kết quả tốt hơn không?",
                        parse_mode="Markdown",
                        reply_markup=self._build_keyboard(brand_buttons),
                    )
                    return
        except Exception as e:
            self.logger.warning("Error in brand profile pre-flight check: {}", e)

        if (
            getattr(self.config, "require_user_api_key", False)
            and not self.keystore.get_key(sender_id)
            and onboarding_status != "in_progress"
            and (creative_request or self._api_key_required_now(sender_id))
        ):
            await self._reply_api_key_required(message)
            return

        # Start typing indicator before processing
        self._start_typing(str_chat_id)
        await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)

        # When media is attached (and this is not a reply), hold the request in a
        # sliding-window buffer so that additional photos arriving in rapid succession
        # (Telegram delivers them as separate messages, only the first has a caption)
        # are accumulated before dispatch.  The window is 1 s, resetting on each new
        # image, with a hard cap of 3 s from the first image.  Handles up to 10+
        # images transparently.  Text-only and reply messages are forwarded immediately.
        if has_media and not is_reply:
            from nanobot.channels.telegram.mixins.media import _TEXT_MEDIA_MAX_WAIT
            _tmb = getattr(self, "_text_media_buffers", {})
            _tmb_key = f"{str_chat_id}:{sender_id}"
            if _tmb_key in _tmb:
                # Another text+media message arrived while buffer is pending:
                # take the latest text and merge media, then reset timer.
                _tmb[_tmb_key]["content"] = content
                _tmb[_tmb_key]["media"] = list(dict.fromkeys(
                    _tmb[_tmb_key]["media"] + list(media_paths)
                ))
                _tmb[_tmb_key]["metadata"]["current_media"] = _tmb[_tmb_key]["media"]
                self._text_media_buffers = _tmb
                _tmb_tasks = getattr(self, "_text_media_tasks", {})
                _old_task = _tmb_tasks.get(_tmb_key)
                _max_flush_at = _tmb[_tmb_key].get("_max_flush_at", 0.0)
                if _old_task and not _old_task.done() and time.monotonic() < _max_flush_at:
                    _old_task.cancel()
                    _tmb_tasks[_tmb_key] = asyncio.create_task(
                        self._flush_text_media_buffer(_tmb_key)
                    )
                    self._text_media_tasks = _tmb_tasks
            else:
                # First text+media message — create the buffer entry.
                _tmb[_tmb_key] = {
                    "sender_id": sender_id,
                    "chat_id": str_chat_id,
                    "content": content,
                    "media": list(media_paths),
                    "metadata": dict(metadata),
                    "session_key": session_key,
                    "_max_flush_at": time.monotonic() + _TEXT_MEDIA_MAX_WAIT,
                }
                self._text_media_buffers = _tmb
                _tmb_tasks = getattr(self, "_text_media_tasks", {})
                _tmb_tasks[_tmb_key] = asyncio.create_task(
                    self._flush_text_media_buffer(_tmb_key)
                )
                self._text_media_tasks = _tmb_tasks
            return  # _flush_text_media_buffer will call _handle_message

        # Text-only or reply-with-media: forward directly without buffering.
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

        if await self._handle_onboarding_quick_reply(
            chat_id=chat_id,
            content=content,
            sender_id=sender_id,
        ):
            self._stop_typing(chat_id)
            return

        pending_choices = getattr(self, "_pending_media_choices", {})
        pending = pending_choices.pop(f"{chat_id}:{sender_id}", None)
        if pending and float(pending.get("expires_at") or 0) < time.monotonic():
            pending = None
        choice_prompts = {
            "đặt logo": "Đặt ảnh đính kèm làm logo thương hiệu và tự cập nhật phong cách theo logo mới.",
            "đặt làm logo": "Đặt ảnh đính kèm làm logo thương hiệu và tự cập nhật phong cách theo logo mới.",
            "đặt làm logo thương hiệu": "Đặt ảnh đính kèm làm logo thương hiệu và tự cập nhật phong cách theo logo mới.",
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

        # --- Direct logo save: when user explicitly selects "Đặt làm logo thương hiệu" ---
        # Bypass LLM — read file bytes from disk then call _upload_logo_bytes_to_cdn,
        # identical to the /setlogo Case 2 & 3 flow (most reliable path).
        plain_nc = self._plain_user_text(normalized_choice)
        if plain_nc in ("dat logo", "dat lam logo thuong hieu", "dat lam logo") and pending is not None:
            media_to_save = list(pending.get("media") or []) + list(media or [])
            if media_to_save:
                # Show typing while processing logo upload
                self._start_typing(chat_id)
                uid_save = sender_id.split("|")[0].strip()
                key_save = self.keystore.get_key(sender_id)
                # Guard: API key required to upload to Vidtory CDN
                if not key_save:
                    if self._app:
                        with suppress(Exception):
                            await self._app.bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "🔐 *Để lưu logo vào hồ sơ thương hiệu, bạn cần kết nối tài khoản Vidtory.*\n\n"
                                    "Sau khi kết nối, logo sẽ tự động xuất hiện trên mọi ảnh tạo ra.\n\n"
                                    "*Thiết lập chỉ mất 1 phút:*\n"
                                    "1️⃣ Vào https://app.vidtory.net/settings/api\n"
                                    "2️⃣ Sao chép key\n"
                                    "3️⃣ Gửi: `/apikey YOUR_KEY`\n\n"
                                    "_Gửi lại logo ngay sau khi hoàn tất là xong._"
                                ),
                                parse_mode="Markdown",
                                disable_web_page_preview=True,
                            )
                    self._stop_typing(chat_id)
                    return
                cdn_url_save = None
                try:
                    import mimetypes as _mimetypes
                    logo_path = media_to_save[0]
                    logo_bytes = Path(logo_path).read_bytes()
                    logo_mime = _mimetypes.guess_type(logo_path)[0] or "image/jpeg"
                    cdn_url_save = await self._upload_logo_bytes_to_cdn(
                        logo_bytes,
                        mime_type=logo_mime,
                        api_key=key_save,
                        user_id=uid_save,
                    )
                except Exception as _read_err:
                    self.logger.warning("Logo save: failed to read/upload file {}: {}", media_to_save[0], _read_err)
                if cdn_url_save:
                    try:
                        from nanobot.utils.customer_profile import set_logo_and_refresh_identity
                        await set_logo_and_refresh_identity(uid_save, cdn_url_save)
                    except Exception as _e:
                        self.logger.warning("set_logo_and_refresh_identity failed: {}", _e)
                    if self._app:
                        with suppress(Exception):
                            await self._app.bot.send_message(
                                chat_id=chat_id,
                                text="✅ *Logo đã được lưu thành công!*\nMọi ảnh tạo tiếp theo sẽ tự động chèn logo này.",
                                parse_mode="Markdown",
                            )
                else:
                    if self._app:
                        with suppress(Exception):
                            await self._app.bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "⚠️ *Upload logo thất bại.*\n\n"
                                    "Có thể do kết nối mạng hoặc API Key chưa đúng.\n"
                                    "Vui lòng thử lại hoặc dùng lệnh `/setlogo` để kiểm tra."
                                ),
                                parse_mode="Markdown",
                            )
            self._stop_typing(chat_id)
            return

        # --- Silent logo CDN upload for brand-profile update with image ---
        # When user selects "Cập nhật thương hiệu" and the pending media is an IMAGE
        # (not a document), upload that image to CDN and set it as logo BEFORE
        # sending to LLM. This ensures the profile already has logo_url populated
        # when the LLM processes the brand update, so it will never say
        # "file logo gốc chưa upload được lên CDN".
        if plain_nc == "cap nhat thuong hieu" and pending is not None:
            image_media = [
                p for p in (pending.get("media") or []) + list(media or [])
                if p  # non-empty path
            ]
            # Only auto-set logo for image files (not PDFs/documents)
            if image_media:
                import mimetypes
                first_mime = mimetypes.guess_type(image_media[0])[0] or ""
                is_image = first_mime.startswith("image/") or image_media[0].lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".gif")
                )
                if is_image:
                    # Fire-and-forget: upload to CDN silently. Even if this fails,
                    # we still proceed with the brand-profile LLM update.
                    try:
                        uid_logo_auto = sender_id.split("|")[0].strip()
                        key_logo_auto = self.keystore.get_key(sender_id) or ""
                        if key_logo_auto:
                            cdn_url = await self._upload_image_to_vidtory_cdn(
                                image_media[0],
                                api_key=key_logo_auto,
                                user_id=uid_logo_auto,
                            )
                            if cdn_url:
                                from nanobot.utils.customer_profile import set_logo_and_refresh_identity
                                await set_logo_and_refresh_identity(uid_logo_auto, cdn_url)
                                self.logger.info(
                                    "Auto-set logo from brand update image for {}: {}",
                                    uid_logo_auto, cdn_url,
                                )
                                # Patch metadata so LLM gets up-to-date profile with logo_url
                                try:
                                    from nanobot.utils.customer_profile import load_profile
                                    fresh_profile = load_profile(uid_logo_auto)
                                    if fresh_profile:
                                        metadata["customer_profile"] = fresh_profile
                                except Exception:
                                    pass
                    except Exception as _logo_auto_exc:
                        self.logger.debug(
                            "Silent logo CDN upload on brand update failed (non-critical): {}",
                            _logo_auto_exc,
                        )

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
            self._remember_logo_prompt_skipped(sender_id.split("|")[0].strip())
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
                        reply_markup=self._build_keyboard([["Tạo biến thể", "Tạo ảnh mới"]]),
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

            if raw_content == "tạo biến thể":
                content = (
                    "Tạo một biến thể mới từ kết quả gần nhất, giữ đúng brief và thương hiệu "
                    "nhưng thay đổi bố cục hoặc cách thể hiện để có thêm lựa chọn."
                )

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
