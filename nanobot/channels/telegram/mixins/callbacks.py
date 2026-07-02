from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from nanobot.channels.telegram.channel import TelegramChannel

class TelegramCallbacksMixin:
    def _build_keyboard(self, buttons: list) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | None:
        """Build inline keyboard markup if inline_keyboards is enabled, otherwise fallback to reply keyboard."""
        if not buttons:
            return None
        if self.config.inline_keyboards:
            keyboard = [
                [InlineKeyboardButton(label, callback_data=self._safe_callback_data(label)) for label in row]
                for row in buttons
            ]
            return InlineKeyboardMarkup(keyboard)
        else:
            keyboard = [
                [KeyboardButton(label) for label in row]
                for row in buttons
            ]
            return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    @staticmethod
    def _safe_callback_data(label: str) -> str:
        # Telegram caps callback_data at 64 bytes UTF-8; truncate at a char boundary so the keyboard still sends.
        encoded = label.encode("utf-8")
        if len(encoded) <= 64:
            return label
        return encoded[:64].decode("utf-8", errors="ignore")

    @staticmethod
    def _buttons_as_text(buttons: list[list[str]]) -> str:
        # Buttons are semantic options; when we can't render a keyboard, the user still needs to see them.
        return "\n".join(" ".join(f"[{label}]" for label in row) for row in buttons if row)

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button clicks (callback queries)."""
        if not update.callback_query or not update.effective_user:
            return
        query = update.callback_query
        user = update.effective_user
        chat_id = query.message.chat_id if query.message else None
        sender_id = self._sender_id(user)
        if not chat_id:
            self.logger.warning("Callback query without chat_id")
            return
        query_chat = getattr(query.message, "chat", None) if query.message else None
        is_dm = getattr(query_chat, "type", None) == "private"
        if not self._is_allowed_for_telegram_chat(sender_id, is_dm=is_dm):
            return
        button_label = query.data or ""
        plain_button = self._plain_user_text(button_label)
        requires_key = getattr(self.config, "require_user_api_key", False)
        if (
            requires_key
            and not self.keystore.get_key(sender_id)
            and "tao khong can logo" in plain_button
        ):
            self._remember_logo_prompt_skipped(sender_id.split("|")[0].strip())
            await query.answer()
            if query.message:
                with suppress(Exception):
                    await query.message.edit_reply_markup(reply_markup=None)
                await self._reply_api_key_required(query.message)
            return
        if (
            requires_key
            and not self.keystore.get_key(sender_id)
            and self._is_creative_generation_request(button_label)
        ):
            await query.answer(
                "Brand Profile đã sẵn sàng. Hãy cấu hình API Key trước khi tạo sản phẩm.",
                show_alert=True,
            )
            return
        keyless_setup_buttons = {
            "them logo ngay",
            "gui logo",
            "nhap website",
            "gui website",
            "dung website",
            "chua co logo",
            "khong co logo",
            "ket noi api key",
            "cau hinh api key",
        }
        if (
            self._api_key_required_now(sender_id)
            and plain_button not in keyless_setup_buttons
        ):
            await query.answer(
                "Brand Profile đã sẵn sàng. Hãy cấu hình API Key trước khi tạo sản phẩm.",
                show_alert=True,
            )
            return
        await query.answer()
        if query.message:
            with suppress(Exception):
                await query.message.edit_reply_markup(reply_markup=None)
        self.logger.debug("Inline button tap from {}: {}", sender_id, button_label)
        self._start_typing(str(chat_id))
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat_id),
            content=button_label,
            metadata={
                "callback_query_id": query.id,
                "button_label": button_label,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_callback": True,
            },
            is_dm=is_dm,
        )
