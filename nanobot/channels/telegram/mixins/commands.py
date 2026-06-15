from __future__ import annotations

import re
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from telegram import Update
from nanobot.command.builtin import build_help_text
from nanobot.config.paths import get_workspace_path
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from nanobot.channels.telegram.channel import TelegramChannel

class TelegramCommandsMixin:
    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            return
        await self._add_reaction(str(update.message.chat_id), update.message.message_id, self.config.react_emoji)

        # When multi-user API key mode is enabled, guide new users to set up their key.
        if getattr(self.config, "require_user_api_key", False):
            key = self.keystore.get_key(sender_id)
            if not key:
                await update.message.reply_text(
                    f"👋 *Xin chào {user.first_name}! Chào mừng bạn đến với Vidtory AI.*\n\n"
                    "🤖 *Vidtory AI* là hệ thống trợ lý thiết kế tự động, đồng hành cùng doanh nghiệp và thương hiệu để tạo ra các ấn phẩm hình ảnh tiếp thị (ảnh sản phẩm, banner quảng cáo, bài viết mạng xã hội) đồng bộ thương hiệu chỉ trong vài giây.\n\n"
                    "💡 **Giải pháp thiết kế từ Vidtory AI mang lại:**\n"
                    "• *Đồng nhất thương hiệu:* Tự động nhận diện logo và màu sắc chủ đạo để áp dụng đồng bộ vào mọi ấn phẩm.\n"
                    "• *Tối ưu hình ảnh tiếp thị:* Định hình phong cách thiết kế riêng biệt cho từng chiến dịch (Brand Marketing hoặc Fashion Studio).\n"
                    "• *Nhanh chóng & Tiết kiệm:* Tạo ra hình ảnh chất lượng cao ngay lập tức mà không cần qua quy trình chỉnh sửa phức tạp.\n\n"
                    "--- \n"
                    "🔑 *Để bắt đầu trải nghiệm, vui lòng kết nối Vidtory API Key của bạn:*\n"
                    "1. Truy cập: https://app.vidtory.net/settings/api\n"
                    "2. Sao chép API Key của bạn\n"
                    "3. Gửi lệnh: `/apikey YOUR_API_KEY` (Ví dụ: `/apikey vidtory_123...`)\n\n"
                    "_Thiết lập này chỉ cần thực hiện một lần duy nhất và hoàn toàn bảo mật._",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return
            await update.message.reply_text(
                f"👋 *Chào mừng quay trở lại, {user.first_name}!* Hệ thống thiết kế thông minh Vidtory AI đã sẵn sàng phục vụ bạn.\n\n"
                "🚀 **Bạn muốn thực hiện công việc nào tiếp theo?**\n"
                "• `/brand` - Xem và quản lý cấu hình thương hiệu (logo, phong cách).\n"
                "• `/new` - Khởi tạo một phiên thiết kế hình ảnh mới.\n"
                "• `/help` - Xem danh sách câu lệnh và hướng dẫn chi tiết.\n\n"
                "Hãy gửi yêu cầu hoặc chọn lệnh để bắt đầu nhé!",
                parse_mode="Markdown",
            )
            return

        buttons = [["Bắt đầu khai báo", "Dùng ngay"]]
        reply_markup = self._build_keyboard(buttons)
        await update.message.reply_text(
            f"👋 *Xin chào {user.first_name}! Chào mừng bạn đến với Vidtory AI.*\n\n"
            "🤖 *Vidtory AI* là hệ thống trợ lý thiết kế tự động, đồng hành cùng doanh nghiệp và thương hiệu để tạo ra các ấn phẩm hình ảnh tiếp thị (ảnh sản phẩm, banner quảng cáo, bài viết mạng xã hội) đồng bộ thương hiệu chỉ trong vài giây.\n\n"
            "💡 **Giải pháp thiết kế từ Vidtory AI mang lại:**\n"
            "• *Đồng nhất thương hiệu:* Tự động nhận diện logo và màu sắc chủ đạo để áp dụng đồng bộ vào mọi ấn phẩm.\n"
            "• *Tối ưu hình ảnh tiếp thị:* Định hình phong cách thiết kế riêng biệt cho từng chiến dịch (Brand Marketing hoặc Fashion Studio).\n"
            "• *Nhanh chóng & Tiết kiệm:* Tạo ra hình ảnh chất lượng cao ngay lập tức mà không cần qua quy trình chỉnh sửa phức tạp.\n\n"
            "--- \n"
            "🚀 **Hãy bắt đầu thiết lập nhanh:**\n"
            "Bạn có thể thiết lập phong cách thương hiệu để AI hiểu chính xác định hướng thiết kế, hoặc trải nghiệm trực tiếp:\n\n"
            "• Chọn **Bắt đầu khai báo** để thiết lập nhanh Brand Profile (~1 phút).\n"
            "• Chọn **Dùng ngay** để trực tiếp gửi yêu cầu thiết kế của bạn.",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )


    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command for allowed users only."""
        if not update.message or not update.effective_user:
            return
        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            return
        await self._add_reaction(str(update.message.chat_id), update.message.message_id, self.config.react_emoji)

        # When multi-user mode is on and user has no key yet, remind them to set it up.
        if getattr(self.config, "require_user_api_key", False):
            if not self.keystore.get_key(sender_id):
                await update.message.reply_text(
                    "❌ Bạn chưa cấu hình API Key.\n"
                    "Hãy dùng lệnh:\n`/apikey YOUR_API_KEY`\n\n"
                    "Để bắt đầu sử dụng bot.",
                    parse_mode="Markdown",
                )
                return

        await update.message.reply_text(build_help_text())

    @staticmethod
    def _looks_like_api_key(text: str) -> bool:
        """Return True if text looks like a bare Vidtory API key (not a slash command)."""
        stripped = text.strip()
        # A Vidtory API key starts with 'vidtory_' and contains only hex/alphanumeric chars.
        # Accept any token that matches the known prefix pattern.
        return bool(re.fullmatch(r'vidtory_[a-fA-F0-9]{64,}', stripped))

    async def _on_api_key_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Dedicated handler for /apikey, /mykey, /clear, /credits, /profile commands."""
        if not update.effective_user:
            return
        if not self.is_allowed(self._sender_id(update.effective_user)):
            return
        if update.message:
            await self._add_reaction(str(update.message.chat_id), update.message.message_id, self.config.react_emoji)

        # Always attempt to handle key-management commands.
        # _handle_api_key_commands returns False when require_user_api_key=False,
        # which means we should forward these commands to the agent bus instead
        # so the LLM can reply with a helpful message.
        handled = await self._handle_api_key_commands(update)
        if not handled:
            # require_user_api_key is off — route the command through the bus
            # so the LLM can respond (e.g. explain what /apikey does).
            message = update.message
            if not message:
                return
            user = update.effective_user
            sender_id = self._sender_id(user)
            self._remember_thread_context(message)
            content = (message.text or "").strip()
            self._start_typing(str(message.chat_id))
            await self._add_reaction(str(message.chat_id), message.message_id, self.config.react_emoji)
            await self._handle_message(
                sender_id=sender_id,
                chat_id=str(message.chat_id),
                content=content,
                metadata=self._build_message_metadata(message, user),
                session_key=self._derive_topic_session_key(message),
                is_dm=message.chat.type == "private",
            )

    async def _handle_api_key_commands(self, update: Update) -> bool:
        """Handle multi-user API key registration/management commands.

        Returns True if a command was handled and no further processing is needed.
        """
        message = update.message
        if not message or not (message.text or message.caption):
            return False

        text = (message.text or message.caption or "").strip()
        cmd = text.split()[0].lower() if text else ""

        if "@" in cmd:
            cmd = cmd.split("@")[0]

        user = update.effective_user
        if not user:
            return False
        sender_id = self._sender_id(user)
        chat_id = str(message.chat_id)

        # /profile no longer exists
        if cmd == "/profile":
            await message.reply_text(
                "❌ Lệnh `/profile` không tồn tại.\n"
                "Vui lòng thử lệnh khác — dùng /brand để xem brand profile.",
                parse_mode="Markdown"
            )
            return True

        # All key-management commands are always handled — no flag restriction.

        if cmd == "/apikey":
            parts = text.split(None, 1)
            if len(parts) < 2:
                await message.reply_text(
                    "🔑 *Cấu hình API Key* theo định dạng:\n"
                    "`/apikey YOUR_API_KEY`\n\n"
                    "Key sẽ được lưu bảo mật và chỉ dùng cho yêu cầu của bạn.",
                    parse_mode="Markdown"
                )
                return True
            key = parts[1].strip()
            self.keystore.set_key(sender_id, key)
            await self._delete_user_message(message.chat_id, message.message_id)
            # Check if user already has a brand profile
            has_profile = False
            try:
                from nanobot.utils.customer_profile import profile_exists
                uid = sender_id.split("|")[0].strip()
                has_profile = profile_exists(uid)
            except Exception:
                pass
            if has_profile:
                await message.reply_text(
                    "✅ *Đã lưu Vidtory API Key thành công!*\n"
                    "Bot đang sẵn sàng phục vụ bạn. Gõ /brand để xem profile.\n\n"
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
            return True

        elif cmd == "/mykey":
            key = self.keystore.get_key(sender_id)
            if not key:
                await message.reply_text(
                    "❌ Bạn *chưa cấu hình API Key*.\n"
                    "Hãy dùng lệnh `/apikey YOUR_API_KEY` để cài đặt.",
                    parse_mode="Markdown"
                )
            else:
                masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "..."
                await message.reply_text(
                    f"🔑 API Key hiện tại của bạn: `{masked}`",
                    parse_mode="Markdown"
                )
            return True

        elif cmd == "/clear":
            self.keystore.remove_key(sender_id)

            # Delete customer profile from DB
            try:
                from nanobot.db.customer_db import get_db
                uid = sender_id.split("|")[0].strip()
                get_db().delete_profile(uid)
            except Exception as e:
                self.logger.warning("Failed to delete customer profile: {}", e)

            session_key = self._derive_topic_session_key(message) or f"telegram:{chat_id}"
            from nanobot.session.manager import SessionManager
            safe_key = SessionManager.safe_key(session_key)
            session_path = get_workspace_path() / "sessions" / f"{safe_key}.jsonl"
            if session_path.exists():
                try:
                    session_path.unlink()
                except Exception as e:
                    self.logger.warning("Failed to delete session file: {}", e)

            user_workspace = get_workspace_path() / "telegram_users" / chat_id
            if user_workspace.exists():
                import shutil
                shutil.rmtree(user_workspace, ignore_errors=True)

            await message.reply_text(
                "🗑️ *Đã xóa toàn bộ dữ liệu!*\n"
                "API key, brand profile, lịch sử hội thoại và workspace của bạn đã được xóa sạch.",
                parse_mode="Markdown"
            )
            return True

        elif cmd == "/credits":
            key = self.keystore.get_key(sender_id)
            if not key:
                await message.reply_text(
                    "❌ *Chưa cấu hình API Key.*\n"
                    "Hãy cài đặt trước: `/apikey YOUR_VIDTORY_API_KEY`",
                    parse_mode="Markdown"
                )
                return True
            # Call Vidtory API to check credits/balance via /merchant/info
            try:
                import httpx
                provider_config = None
                with suppress(Exception):
                    from nanobot.config.loader import load_config
                    cfg = load_config()
                    provider_config = (cfg.providers or {}).get("vidtory")
                api_base = (
                    getattr(provider_config, "api_base", None)
                    or "https://bapi.vidtory.net"
                )
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"{api_base}/merchant/info",
                        headers={"x-api-key": key},
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        balance = data.get("balance", {})
                        current = balance.get("currentBalance", "?")
                        deposited = balance.get("totalDeposited", "?")
                        spent = balance.get("totalSpent", "?")
                        currency = balance.get("currency", "Credit")
                        business = data.get("businessName", "")
                        lines = [
                            f"💳 *Tài khoản Vidtory*",
                            f"",
                            f"🏢 *{business}*" if business else "",
                            f"",
                            f"💰 *Credits còn lại:* `{current} {currency}`",
                            f"📥 *Tổng nạp:* `{deposited}`",
                            f"📤 *Đã dùng:* `{spent}`",
                        ]
                        await message.reply_text(
                            "\n".join(l for l in lines if l is not None),
                            parse_mode="Markdown"
                        )
                    elif resp.status_code == 401:
                        await message.reply_text(
                            "❌ *API Key không hợp lệ.*\nHãy cấu hình lại với `/apikey YOUR_KEY`.",
                            parse_mode="Markdown"
                        )
                    else:
                        await message.reply_text(
                            f"⚠️ Không thể lấy thông tin tài khoản (HTTP {resp.status_code}).\n"
                            "Thử lại sau hoặc kiểm tra tại https://vidtory.net",
                            parse_mode="Markdown"
                        )

            except Exception as e:
                self.logger.warning("Failed to fetch Vidtory credits: {}", e)
                await message.reply_text(
                    "⚠️ Không thể kết nối đến Vidtory API. Vui lòng thử lại sau.",
                    parse_mode="Markdown"
                )
            return True

        elif cmd == "/brand":
            try:
                from nanobot.utils.customer_profile import load_profile, get_logo_url
                uid = sender_id.split("|")[0].strip()
                profile = load_profile(uid)
                if not profile:
                    buttons = [["Bắt đầu khai báo", "Dùng ngay"]]
                    reply_markup = self._build_keyboard(buttons)
                    await message.reply_text(
                        "📋 *Bạn chưa có brand profile.*\n\n"
                        "Mình có thể hỏi vài câu để tạo profile phù hợp — chỉ mất ~1 phút. "
                        "Profile giúp AI tạo nội dung *chuẩn thương hiệu* hơn rất nhiều.\n\n"
                        "Bạn muốn thiết lập ngay không?",
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                else:
                    biz = profile.get("business") or {}
                    brand = profile.get("brand") or {}
                    audience = profile.get("audience") or {}
                    channels = profile.get("contentChannels") or {}
                    onboarding = profile.get("onboarding") or {}
                    learning = profile.get("learningData") or {}
                    status_map = {
                        "minimal": "Cơ bản ✅",
                        "completed": "Hoàn chỉnh ✅",
                        "in_progress": "Đang thiết lập 🔄",
                    }
                    status = status_map.get(onboarding.get("status", ""), onboarding.get("status", "—"))
                    name = biz.get("name") or "—"
                    industry = biz.get("industry") or "—"
                    style = brand.get("style") or "—"
                    colors = brand.get("colorPalette") or {}
                    primary_color = colors.get("primary") or "—"
                    mood = ", ".join(brand.get("moodKeywords") or []) or "—"
                    avoid = ", ".join(brand.get("avoidList") or []) or "—"
                    logo = (brand.get("logoUrl") or "").strip()
                    photo_style = brand.get("photographyStyle") or "—"
                    primary_channels = ", ".join(channels.get("primary") or []) or "—"
                    aud_gender = audience.get("gender") or "—"
                    aud_age = audience.get("ageRange") or "—"
                    aud_seg = audience.get("segment") or "—"
                    total_gens = learning.get("totalGenerations", 0)
                    approved = learning.get("approvedCount", 0)
                    rejected = learning.get("rejectedCount", 0)

                    lines = [
                        "📋 *Brand Profile*",
                        "",
                        "🏢 *Thương hiệu*",
                        f"  Tên: {name}",
                        f"  Ngành: {industry}",
                        "",
                        "🎨 *Phong cách*",
                        f"  Style: {style}",
                        f"  Mood: {mood}",
                        f"  Màu chủ đạo: {primary_color}",
                        f"  Photo style: {photo_style}",
                        f"  Tránh: {avoid}",
                        "",
                    ]

                    if logo:
                        if logo.startswith(("http://", "https://")):
                            lines.append(f"🖼️ *Logo:* [Xem logo]({logo})")
                        else:
                            lines.append(f"🖼️ *Logo:* _Đường dẫn không hợp lệ ({logo})_ — dùng /setlogo để cấu hình lại")
                    else:
                        lines.append("🖼️ *Logo:* _Chưa có_ — dùng /setlogo để thêm")
                    lines.append("")

                    lines.extend([
                        "",
                        "👥 *Đối tượng*",
                        f"  Giới tính: {aud_gender} | Tuổi: {aud_age} | Phân khúc: {aud_seg}",
                        "",
                        f"📱 *Kênh:* {primary_channels}",
                        "",
                        f"📊 *Thống kê:* {total_gens} ảnh tạo | {approved} ✅ | {rejected} ❌",
                        f"✅ *Onboarding:* {status}",
                        "",
                        "━━━━━━━━━━━━━━",
                        "*Thay đổi nhanh:*",
                        "  /setbrand name PTIT",
                        "  /setbrand style luxury",
                        "  /setbrand mood sang trọng, hiện đại",
                        "  /setbrand industry tech",
                        "  /setlogo — để thay đổi logo",
                    ])
                    # Enable web preview when logo exists and is a valid URL so Telegram shows the image inline
                    show_preview = bool(logo) and logo.startswith(("http://", "https://"))
                    await message.reply_text("\n".join(lines), parse_mode="Markdown",
                                            disable_web_page_preview=not show_preview)
            except Exception as e:
                self.logger.warning("Failed to load brand profile: {}", e)
                await message.reply_text(
                    "⚠️ Không thể tải brand profile. Vui lòng thử lại sau.",
                    parse_mode="Markdown"
                )
            return True

        elif cmd == "/setbrand":
            """Quick brand field updater: /setbrand <field> <value>"""
            try:
                from nanobot.utils.customer_profile import profile_exists
                from nanobot.agent.tools.customer_profile_tool import UpdateCustomerProfileTool
                from nanobot.utils.context_vars import telegram_customer_profile
                from nanobot.db.customer_db import get_db as _get_db

                uid = sender_id.split("|")[0].strip()

                parts = text.split(None, 2)  # /setbrand <field> <value...>
                if len(parts) < 3:
                    await message.reply_text(
                        "*Cách dùng /setbrand:*\n\n"
                        "`/setbrand name TÊN THƯƠNG HIỆU`\n"
                        "`/setbrand industry tech`\n"
                        "`/setbrand style luxury`\n"
                        "`/setbrand mood sang trọng, hiện đại`\n"
                        "`/setbrand segment mid`\n"
                        "`/setbrand age 18-35`\n"
                        "`/setbrand channels facebook, instagram`\n\n"
                        "_Sau khi thay đổi, gõ /brand để kiểm tra._",
                        parse_mode="Markdown"
                    )
                    return True

                field = parts[1].lower().strip()
                value = parts[2].strip()

                # Map field aliases → tool parameters
                FIELD_MAP = {
                    "name": "business_name",
                    "ten": "business_name",
                    "brand": "business_name",
                    "industry": "industry",
                    "nganh": "industry",
                    "style": "brand_style",
                    "phongcach": "brand_style",
                    "mood": "mood_keywords",
                    "cam_xuc": "mood_keywords",
                    "photo": "photography_style",
                    "segment": "segment",
                    "phankhuc": "segment",
                    "age": "age_range",
                    "tuoi": "age_range",
                    "gender": "target_gender",
                    "gioitinh": "target_gender",
                    "channels": "channels",
                    "kenh": "channels",
                }

                tool_field = FIELD_MAP.get(field)
                if not tool_field:
                    valid = ", ".join(sorted(set(FIELD_MAP.keys())))
                    await message.reply_text(
                        f"❌ Field `{field}` không hợp lệ.\n\n"
                        f"*Các field hợp lệ:* `{valid}`\n\n"
                        "Ví dụ: `/setbrand style luxury`",
                        parse_mode="Markdown"
                    )
                    return True

                # Load current profile into ContextVar for the tool
                db = _get_db()
                profile = db.load_profile(uid)
                if profile:
                    telegram_customer_profile.set(profile)

                # Parse value for list fields
                list_fields = {"mood_keywords", "channels"}
                kwargs: dict = {}
                if tool_field in list_fields:
                    # "sang trọng, hiện đại" → ["sang trọng", "hiện đại"]
                    kwargs[tool_field] = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
                else:
                    kwargs[tool_field] = value

                tool = UpdateCustomerProfileTool()
                result = await tool.execute(**kwargs)

                # Read updated value to confirm
                updated = db.load_profile(uid)
                biz = updated.get("business", {}) if updated else {}
                br = updated.get("brand", {}) if updated else {}

                await message.reply_text(
                    f"✅ *Brand đã được cập nhật!*\n\n"
                    f"Field: `{field}` → `{value}`\n\n"
                    f"*Hiện tại:* {biz.get('name', '—')} | {br.get('style', '—')} | {biz.get('industry', '—')}\n"
                    "_Gõ /brand để xem đầy đủ._",
                    parse_mode="Markdown"
                )

            except Exception as e:
                self.logger.warning("Failed to handle /setbrand: {}", e)
                await message.reply_text(
                    "⚠️ Lỗi khi cập nhật brand. Vui lòng thử lại.",
                    parse_mode="Markdown"
                )
            return True

        elif cmd == "/setlogo":
            try:
                from nanobot.utils.customer_profile import set_logo_url, get_logo_url, profile_exists
                uid = sender_id.split("|")[0].strip()

                if not profile_exists(uid):
                    await message.reply_text(
                        "❌ *Chưa có profile.*\n"
                        "Hãy bắt đầu chat với bot trước để tạo profile.",
                        parse_mode="Markdown"
                    )
                    return True

                parts = text.split(None, 1)
                logo_url_arg = parts[1].strip() if len(parts) > 1 else ""

                # Case 0: /setlogo clear — remove logo
                if logo_url_arg.lower() == "clear":
                    from nanobot.utils.customer_profile import clear_logo
                    if clear_logo(uid):
                        await message.reply_text(
                            "✅ *Logo đã được xóa.*\n\n"
                            "_Dùng /setlogo để thêm logo mới._",
                            parse_mode="Markdown"
                        )
                    else:
                        await message.reply_text(
                            "⚠️ Không thể xóa logo. Vui lòng thử lại.",
                            parse_mode="Markdown"
                        )
                    return True

                # Case 1: URL provided as argument
                # If already a Vidtory CDN URL → save directly (no re-upload needed).
                # If external URL → upload to Vidtory CDN first to get a permanent URL,
                # same as the product image generation flow.
                if logo_url_arg and logo_url_arg.startswith(("http://", "https://")):
                    try:
                        final_logo_url = logo_url_arg
                        # Non-Vidtory URLs: upload to CDN for permanence
                        if "vidtory" not in logo_url_arg.lower():
                            api_key = self.keystore.get_key(sender_id)
                            cdn_url = await self._upload_image_to_vidtory_cdn(
                                logo_url_arg, api_key=api_key or "", user_id=uid
                            )
                            if not cdn_url:
                                await message.reply_text(
                                    "⚠️ Không thể upload logo lên hệ thống.\n"
                                    "Vui lòng thử lại hoặc gửi trực tiếp file ảnh.",
                                    parse_mode="Markdown"
                                )
                                return True
                            final_logo_url = cdn_url

                        if set_logo_url(uid, final_logo_url):
                            await message.reply_text(
                                "✅ *Logo đã được lưu lên hệ thống!*\n\n"
                                f"🖼️ [Xem logo]({final_logo_url})\n\n"
                                "_Logo sẽ tự động được áp dụng khi tạo ảnh._",
                                parse_mode="Markdown",
                                disable_web_page_preview=True,
                            )
                        else:
                            await message.reply_text(
                                "⚠️ Không thể lưu logo. Vui lòng thử lại.",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        self.logger.warning("Failed to upload logo from URL: {}", e)
                        await message.reply_text(
                            "⚠️ Lỗi khi xử lý logo URL. Vui lòng thử lại.",
                            parse_mode="Markdown"
                        )
                    return True

                # Case 2: Reply to a photo or document (image sent as File)
                # Download photo bytes locally (same as _download_message_media flow),
                # then upload to Vidtory CDN via /media/upload to get a permanent URL.
                reply = getattr(message, "reply_to_message", None)
                reply_media = self._extract_image_file(reply) if reply else None
                if reply_media:
                    try:
                        tg_file = await self._app.bot.get_file(reply_media["file_id"])
                        # Download to local bytes — same pattern as product generation upload flow
                        file_bytes = await tg_file.download_as_bytearray()
                        if not file_bytes:
                            await message.reply_text(
                                "⚠️ Không thể tải ảnh từ Telegram. Vui lòng thử lại.",
                                parse_mode="Markdown"
                            )
                            return True
                        # Upload bytes to Vidtory CDN via POST /media/upload
                        api_key = self.keystore.get_key(sender_id)
                        cdn_url = await self._upload_logo_bytes_to_cdn(
                            bytes(file_bytes),
                            mime_type=reply_media["mime_type"],
                            api_key=api_key or "",
                            user_id=uid,
                        )
                        if cdn_url and set_logo_url(uid, cdn_url):
                            await message.reply_text(
                                "✅ *Logo đã được lưu lên hệ thống!*\n\n"
                                f"🖼️ [Xem logo]({cdn_url})\n"
                                "_Logo sẽ tự động được áp dụng khi tạo ảnh._",
                                parse_mode="Markdown",
                                disable_web_page_preview=True,
                            )
                        else:
                            await message.reply_text(
                                "⚠️ Không thể upload logo lên hệ thống.\n"
                                "Vui lòng thử lại.",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        self.logger.warning("Failed to save logo from photo: {}", e)
                        await message.reply_text(
                            "⚠️ Lỗi khi xử lý ảnh. Vui lòng thử lại.",
                            parse_mode="Markdown"
                        )
                    return True

                # Case 3: Photo or document (image) sent directly with /setlogo
                # Download to local bytes first, then upload to Vidtory CDN.
                direct_media = self._extract_image_file(message)
                if direct_media:
                    try:
                        tg_file = await self._app.bot.get_file(direct_media["file_id"])
                        file_bytes = await tg_file.download_as_bytearray()
                        if not file_bytes:
                            await message.reply_text(
                                "⚠️ Không thể tải ảnh từ Telegram. Vui lòng thử lại.",
                                parse_mode="Markdown"
                            )
                            return True
                        api_key = self.keystore.get_key(sender_id)
                        cdn_url = await self._upload_logo_bytes_to_cdn(
                            bytes(file_bytes),
                            mime_type=direct_media["mime_type"],
                            api_key=api_key or "",
                            user_id=uid,
                        )
                        if cdn_url and set_logo_url(uid, cdn_url):
                            await message.reply_text(
                                "✅ *Logo đã được lưu lên hệ thống!*\n\n"
                                f"🖼️ [Xem logo]({cdn_url})\n"
                                "_Logo sẽ tự động được áp dụng khi tạo ảnh._",
                                parse_mode="Markdown",
                                disable_web_page_preview=True,
                            )
                        else:
                            await message.reply_text(
                                "⚠️ Không thể upload logo lên hệ thống.\n"
                                "Vui lòng thử lại.",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        self.logger.warning("Failed to save logo from photo: {}", e)
                        await message.reply_text(
                            "⚠️ Lỗi khi xử lý ảnh. Vui lòng thử lại.",
                            parse_mode="Markdown"
                        )
                    return True

                # Case 4: Show usage
                current_logo = get_logo_url(uid)
                if current_logo:
                    await message.reply_text(
                        f"🖼️ *Logo hiện tại:* [Xem]({current_logo})\n\n"
                        "*Để thay đổi:*\n"
                        "• `/setlogo https://url-logo-moi.png`\n"
                        "• Hoặc reply một ảnh với `/setlogo`\n\n"
                        "_Để xóa logo, dùng_ `/setlogo clear`",
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                else:
                    await message.reply_text(
                        "🖼️ *Thêm logo thương hiệu*\n\n"
                        "*Cách 1:* Gửi URL\n"
                        "`/setlogo https://link-logo.png`\n\n"
                        "*Cách 2:* Reply một ảnh logo\n"
                        "Reply ảnh + gõ `/setlogo`\n\n"
                        "_Logo sẽ được tự động áp dụng vào mọi sản phẩm._",
                        parse_mode="Markdown"
                    )

                return True

            except Exception as e:
                self.logger.warning("Failed to handle /setlogo: {}", e)
                await message.reply_text(
                    "⚠️ Lỗi xử lý logo. Vui lòng thử lại.",
                    parse_mode="Markdown"
                )
                return True

        return False

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward slash commands to the bus for unified handling in AgentLoop."""
        if not update.message or not update.effective_user:
            return
        message = update.message
        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            return
        await self._add_reaction(str(message.chat_id), message.message_id, self.config.react_emoji)

        if getattr(self.config, "require_user_api_key", False):
            if await self._handle_api_key_commands(update):
                return
            if not self.keystore.get_key(sender_id):
                await message.reply_text(
                    "🔑 *Bạn chưa cấu hình Vidtory API Key.*\n\n"
                    "Để sử dụng bot, vui lòng:\n"
                    "1. Truy cập https://app.vidtory.net/settings/api\n"
                    "2. Lấy API Key của bạn\n"
                    "3. Gửi: `/apikey YOUR_API_KEY`",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return

        self._remember_thread_context(message)

        # Strip @bot_username suffix if present
        content = message.text or ""
        if content.startswith("/") and "@" in content:
            cmd_part, *rest = content.split(" ", 1)
            cmd_part = cmd_part.split("@")[0]
            content = f"{cmd_part} {rest[0]}" if rest else cmd_part
        content = self._normalize_telegram_command(content)

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(message.chat_id),
            content=content,
            metadata=self._build_message_metadata(message, user),
            session_key=self._derive_topic_session_key(message),
            is_dm=message.chat.type == "private",
        )
