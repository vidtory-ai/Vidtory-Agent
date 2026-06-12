"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
    ReplyParameters,
    Update,
)
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.command.builtin import build_help_text
from nanobot.config.paths import get_media_dir, get_data_dir, get_workspace_path
from nanobot.config.schema import Base
from nanobot.security.network import validate_url_target
from nanobot.utils.helpers import split_message

TELEGRAM_MAX_MESSAGE_LEN = 4000  # Telegram message character limit
# Telegram's actual API limit is 4096; we split raw markdown at 4000 as a
# safety margin for mid-stream edits (plain text).  For _stream_end, we
# convert to HTML first and then split at the true 4096-char boundary so
# the final rendered message never overflows.
TELEGRAM_HTML_MAX_LEN = 4096
TELEGRAM_REPLY_CONTEXT_MAX_LEN = TELEGRAM_MAX_MESSAGE_LEN  # Max length for reply context in user message


def _escape_telegram_html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tool_hint_to_telegram_blockquote(text: str) -> str:
    """Render tool hints as an expandable blockquote (collapsed by default)."""
    return f"<blockquote expandable>{_escape_telegram_html(text)}</blockquote>" if text else ""


def _strip_md(s: str) -> str:
    """Strip markdown inline formatting from text."""
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    s = re.sub(r'~~(.+?)~~', r'\1', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    return s.strip()


def _strip_md_block(text: str) -> str:
    """Strip block-level and inline markdown for readable plain-text preview.

    Used during streaming mid-edits so users see clean text instead of raw
    markdown syntax while the response is still being generated.
    """
    # Code blocks -> just the code
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', r'\1', text)
    # Headers -> plain text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)
    # Bold / italic / strikethrough
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bullet lists
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    # Numbered lists (normalize spacing)
    text = re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)
    return text


def _render_table_box(table_lines: list[str]) -> str:
    """Convert markdown pipe-table to compact aligned text for <pre> display."""

    def dw(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

    rows: list[list[str]] = []
    has_sep = False
    for line in table_lines:
        cells = [_strip_md(c) for c in line.strip().strip('|').split('|')]
        if all(re.match(r'^:?-+:?$', c) for c in cells if c):
            has_sep = True
            continue
        rows.append(cells)
    if not rows or not has_sep:
        return '\n'.join(table_lines)

    ncols = max(len(r) for r in rows)
    for r in rows:
        r.extend([''] * (ncols - len(r)))
    widths = [max(dw(r[c]) for r in rows) for c in range(ncols)]

    def dr(cells: list[str]) -> str:
        return '  '.join(f'{c}{" " * (w - dw(c))}' for c, w in zip(cells, widths))

    out = [dr(rows[0])]
    out.append('  '.join('─' * w for w in widths))
    for row in rows[1:]:
        out.append(dr(row))
    return '\n'.join(out)


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)

    # 1.5. Convert markdown tables to box-drawing (reuse code_block placeholders)
    lines = text.split('\n')
    rebuilt: list[str] = []
    li = 0
    while li < len(lines):
        if re.match(r'^\s*\|.+\|', lines[li]):
            tbl: list[str] = []
            while li < len(lines) and re.match(r'^\s*\|.+\|', lines[li]):
                tbl.append(lines[li])
                li += 1
            box = _render_table_box(tbl)
            if box != '\n'.join(tbl):
                code_blocks.append(box)
                rebuilt.append(f"\x00CB{len(code_blocks) - 1}\x00")
            else:
                rebuilt.extend(tbl)
        else:
            rebuilt.append(lines[li])
            li += 1
    text = '\n'.join(rebuilt)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # 3. Headers # Title -> <b>Title</b> (preserve visual hierarchy)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'⟪B⟫\1⟪/B⟫', text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = _escape_telegram_html(text)

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)

    # 10.5. Numbered lists  1. item -> 1. item (keep number, normalize indent)
    text = re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = _escape_telegram_html(code)
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = _escape_telegram_html(code)
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    # 13. Restore header bold markers (inserted in step 3, after HTML escaping)
    text = text.replace('⟪B⟫', '<b>').replace('⟪/B⟫', '</b>')

    return text


_SEND_MAX_RETRIES = 3
_SEND_RETRY_BASE_DELAY = 0.5  # seconds, doubled each retry
_STREAM_EDIT_INTERVAL_DEFAULT = 0.6  # min seconds between edit_message_text calls


@dataclass
class _StreamBuf:
    """Per-chat streaming accumulator for progressive message editing."""
    text: str = ""
    message_id: int | None = None
    last_edit: float = 0.0
    stream_id: str | None = None


class TelegramKeyStore:
    """Secure SQLite-backed storage mapping sender_ids to their configured API keys.

    Falls back to importing the legacy JSON file on first use if the DB is empty,
    providing automatic migration without any manual intervention.
    """

    def __init__(self) -> None:
        self._migrated = False

    def _db(self):
        from nanobot.db.customer_db import get_db
        return get_db()

    def _ensure_migrated(self) -> None:
        """One-time import of legacy telegram_keys.json into SQLite (if needed)."""
        if self._migrated:
            return
        self._migrated = True
        try:
            from nanobot.config.paths import get_data_dir
            legacy_path = get_data_dir() / "telegram_keys.json"
            if not legacy_path.exists():
                return
            # Only migrate if DB is empty
            if self._db().get_all_api_keys():
                return
            import json
            with open(legacy_path, encoding="utf-8") as f:
                keys: dict = json.load(f)
            count = 0
            for uid, key in keys.items():
                if uid and key:
                    self._db().set_api_key(uid, key)
                    count += 1
            if count:
                import logging
                logging.getLogger(__name__).info(
                    "Migrated %d API keys from telegram_keys.json to SQLite", count
                )
        except Exception:
            pass  # Non-critical — never block startup

    def get_key(self, sender_id: str) -> str | None:
        self._ensure_migrated()
        return self._db().get_api_key(sender_id)

    def set_key(self, sender_id: str, key: str) -> None:
        self._ensure_migrated()
        self._db().set_api_key(sender_id, key)

    def remove_key(self, sender_id: str) -> None:
        self._ensure_migrated()
        self._db().remove_api_key(sender_id)


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    proxy: str | None = None
    reply_to_message: bool = False
    react_emoji: str = "👀"
    group_policy: Literal["open", "mention"] = "mention"
    connection_pool_size: int = 32
    pool_timeout: float = 5.0
    streaming: bool = True
    # Enable inline keyboard buttons in Telegram messages.
    inline_keyboards: bool = False
    stream_edit_interval: float = Field(default=_STREAM_EDIT_INTERVAL_DEFAULT, ge=0.1)
    require_user_api_key: bool = False


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.

    Simple and reliable - no webhook/public IP needed.
    """

    name = "telegram"
    display_name = "Telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("apikey", "Set your Vidtory API key"),
        BotCommand("mykey", "View your current API key (masked)"),
        BotCommand("credits", "Check your remaining Vidtory credits"),
        BotCommand("brand", "View & manage your brand profile"),
        BotCommand("setbrand", "Update a brand field: /setbrand style luxury"),
        BotCommand("setlogo", "Set or change your brand logo"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("clear", "Delete all your data and API key"),
        BotCommand("stop", "Stop the current task"),
        BotCommand("status", "Show bot status and model info"),
        BotCommand("model", "Switch AI model preset"),
        BotCommand("help", "List all available commands"),
    ]

    # Regex for slash commands routed to AgentLoop via ``_forward_command``.
    # Hyphenated ``dream-*`` commands stay on a separate handler (below).
    TELEGRAM_BUS_SLASH_COMMAND_RE = re.compile(
        r"^/(?:new|stop|restart|status|dream|history|goal|pairing|model)(?:@\w+)?(?:\s+.*)?$"
    )

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return TelegramConfig().model_dump(by_alias=True)

    def __init__(self, config: Any, bus: MessageBus):
        if isinstance(config, dict):
            config = TelegramConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task
        self._media_group_buffers: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task] = {}
        self._message_threads: dict[tuple[str, int], int] = {}
        self._bot_user_id: int | None = None
        self._bot_username: str | None = None
        self._stream_bufs: dict[str, _StreamBuf] = {}  # chat_id -> streaming state
        self.keystore = TelegramKeyStore()

    def is_allowed(self, sender_id: str) -> bool:
        """Preserve Telegram's legacy id|username allowlist matching."""
        if getattr(self.config, "require_user_api_key", False):
            return True

        if super().is_allowed(sender_id):
            return True

        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list or "*" in allow_list:
            return False

        sender_str = str(sender_id)
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

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            self.logger.error("bot token not configured")
            return

        self._running = True

        proxy = self.config.proxy or None

        # Separate pools so long-polling (getUpdates) never starves outbound sends.
        api_request = HTTPXRequest(
            connection_pool_size=self.config.connection_pool_size,
            pool_timeout=self.config.pool_timeout,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=proxy,
        )
        poll_request = HTTPXRequest(
            connection_pool_size=4,
            pool_timeout=self.config.pool_timeout,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=proxy,
        )
        builder = (
            Application.builder()
            .token(self.config.token)
            .request(api_request)
            .get_updates_request(poll_request)
        )
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Add command handlers (using Regex to support @username suffixes before bot initialization)
        self._app.add_handler(MessageHandler(filters.Regex(r"^/start(?:@\w+)?$"), self._on_start))
        self._app.add_handler(
            MessageHandler(
                filters.Regex(TelegramChannel.TELEGRAM_BUS_SLASH_COMMAND_RE),
                self._forward_command,
            )
        )
        self._app.add_handler(
            MessageHandler(
                filters.Regex(r"^/(dream-log|dream_log|dream-restore|dream_restore)(?:@\w+)?(?:\s+.*)?$"),
                self._forward_command,
            )
        )
        self._app.add_handler(MessageHandler(filters.Regex(r"^/help(?:@\w+)?$"), self._on_help))
        # API key management commands (multi-user mode)
        self._app.add_handler(
            MessageHandler(
                filters.Regex(r"^/(apikey|mykey|clear|credits|brand|setbrand|setlogo|profile)(?:@\w+)?(?:\s+.*)?$"),
                self._on_api_key_management,
            )
        )
        # Handle photos/documents sent with /setlogo as caption
        self._app.add_handler(
            MessageHandler(
                (filters.PHOTO | filters.Document.IMAGE)
                & filters.CaptionRegex(r"^/setlogo(?:@\w+)?(?:\s+.*)?$"),
                self._on_api_key_management,
            )
        )

        # Add message handler for text, photos, video, voice, documents, and locations
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VIDEO_NOTE
                 | filters.ANIMATION | filters.VOICE | filters.AUDIO
                 | filters.Document.ALL | filters.LOCATION)
                & ~filters.COMMAND,
                self._on_message
            )
        )

        # Conditionally register inline keyboard callback handler
        if self.config.inline_keyboards:
            self._app.add_handler(CallbackQueryHandler(self._on_callback_query))
            allowed_updates = ["message", "callback_query"]
            self.logger.debug("inline keyboards enabled")
        else:
            allowed_updates = ["message"]

        self.logger.info("Starting bot (polling mode)...")

        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()

        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        self.logger.info("bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            self.logger.debug("bot commands registered")
        except Exception as e:
            self.logger.warning("Failed to register bot commands: {}", e)

        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=allowed_updates,
            drop_pending_updates=True,  # Prevent Conflict errors on restart
            error_callback=self._on_polling_error,
        )

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()

        if self._app:
            self.logger.info("Stopping bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    @staticmethod
    def _get_media_type(path: str) -> str:
        """Guess media type from file extension.

        Strips URL query params/fragments before extracting extension so that
        CDN URLs like https://cdn.vidtory.net/vid.mp4?token=xxx are detected
        correctly as video instead of document.
        """
        # Strip query string and fragment for URL-based paths
        clean = path.split("?")[0].split("#")[0]
        ext = clean.rsplit(".", 1)[-1].lower() if "." in clean else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext in ("mp4", "mov", "avi", "mkv", "webm", "3gp"):
            return "video"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    @staticmethod
    def _is_remote_media_url(path: str) -> bool:
        return path.startswith(("http://", "https://"))

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            self.logger.warning("bot not running")
            return

        # Only stop typing indicator and remove reaction for final responses
        if not msg.metadata.get("_progress", False):
            self._stop_typing(msg.chat_id)
            if reply_to_message_id := msg.metadata.get("message_id"):
                with suppress(ValueError):
                    await self._remove_reaction(msg.chat_id, int(reply_to_message_id))

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            self.logger.exception("Invalid chat_id: {}", msg.chat_id)
            return
        reply_to_message_id = msg.metadata.get("message_id")
        message_thread_id = msg.metadata.get("message_thread_id")
        if message_thread_id is None and reply_to_message_id is not None:
            message_thread_id = self._message_threads.get((msg.chat_id, reply_to_message_id))
        thread_kwargs = {}
        if message_thread_id is not None:
            thread_kwargs["message_thread_id"] = message_thread_id

        reply_params = None
        if self.config.reply_to_message:
            if reply_to_message_id:
                reply_params = ReplyParameters(
                    message_id=reply_to_message_id,
                    allow_sending_without_reply=True
                )

        # Send media files
        for media_path in (msg.media or []):
            try:
                media_type = self._get_media_type(media_path)
                sender = {
                    "photo": self._app.bot.send_photo,
                    "video": self._app.bot.send_video,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = {
                    "photo": "photo",
                    "video": "video",
                    "voice": "voice",
                    "audio": "audio",
                }.get(media_type, "document")
                extra: dict[str, Any] = {}
                if media_type == "video":
                    extra["supports_streaming"] = True

                # Telegram Bot API accepts HTTP(S) URLs directly for media params.
                if self._is_remote_media_url(media_path):
                    ok, error = validate_url_target(media_path)
                    if not ok:
                        raise ValueError(f"unsafe media URL: {error}")
                    await self._call_with_retry(
                        sender,
                        chat_id=chat_id,
                        **{param: media_path},
                        reply_parameters=reply_params,
                        **thread_kwargs,
                        **extra,
                    )
                    continue

                media_bytes = Path(media_path).read_bytes()
                filename = Path(media_path).name
                send_kwargs = {param: media_bytes, "filename": filename}
                await self._call_with_retry(
                    sender,
                    chat_id=chat_id,
                    reply_parameters=reply_params,
                    **thread_kwargs,
                    **extra,
                    **send_kwargs,
                )
            except Exception:
                filename = media_path.rsplit("/", 1)[-1]
                self.logger.exception("Failed to send media {}", media_path)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[Failed to send: {filename}]",
                    reply_parameters=reply_params,
                    **thread_kwargs,
                )

        # Send text content
        if msg.content and msg.content != "[empty message]":
            render_as_blockquote = bool(msg.metadata.get("_tool_hint"))
            buttons = getattr(msg, "buttons", None) or []
            reply_markup = self._build_keyboard(buttons) if buttons else None
            text = msg.content
            # Fallback: no native keyboard → splice labels into the message so the choices survive.
            if buttons and reply_markup is None:
                text = f"{text}\n\n{self._buttons_as_text(buttons)}"
            chunks = split_message(text, TELEGRAM_MAX_MESSAGE_LEN)
            for i, chunk in enumerate(chunks):
                is_last = (i == len(chunks) - 1)
                await self._send_text(
                    chat_id, chunk, reply_params, thread_kwargs,
                    render_as_blockquote=render_as_blockquote,
                    reply_markup=reply_markup if is_last else None,
                )

    async def _call_with_retry(self, fn, *args, **kwargs):
        """Call an async Telegram API function with retry on pool/network timeout and RetryAfter."""
        from telegram.error import RetryAfter

        for attempt in range(1, _SEND_MAX_RETRIES + 1):
            try:
                return await fn(*args, **kwargs)
            except TimedOut:
                if attempt == _SEND_MAX_RETRIES:
                    raise
                delay = _SEND_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                self.logger.warning(
                    "timeout (attempt {}/{}), retrying in {:.1f}s",
                    attempt, _SEND_MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            except RetryAfter as e:
                if attempt == _SEND_MAX_RETRIES:
                    raise
                delay = float(e.retry_after)
                self.logger.warning(
                    "Flood Control (attempt {}/{}), retrying in {:.1f}s",
                    attempt, _SEND_MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)

    async def _send_text(
        self,
        chat_id: int,
        text: str,
        reply_params=None,
        thread_kwargs: dict | None = None,
        render_as_blockquote: bool = False,
        reply_markup=None,
    ) -> None:
        """Send a plain text message with HTML fallback."""
        try:
            html = _tool_hint_to_telegram_blockquote(text) if render_as_blockquote else _markdown_to_telegram_html(text)
            await self._call_with_retry(
                self._app.bot.send_message,
                chat_id=chat_id, text=html, parse_mode="HTML",
                reply_parameters=reply_params,
                reply_markup=reply_markup,
                **(thread_kwargs or {}),
            )
        except BadRequest as e:
            self.logger.warning("HTML parse failed, falling back to plain text: {}", e)
            try:
                await self._call_with_retry(
                    self._app.bot.send_message,
                    chat_id=chat_id,
                    text=text,
                    reply_parameters=reply_params,
                    reply_markup=reply_markup,
                    **(thread_kwargs or {}),
                )
            except Exception:
                self.logger.exception("Error sending message")
                raise

    @staticmethod
    def _is_not_modified_error(exc: Exception) -> bool:
        return isinstance(exc, BadRequest) and "message is not modified" in str(exc).lower()

    async def send_delta(self, chat_id: str, delta: str, metadata: dict[str, Any] | None = None) -> None:
        """Progressive message editing: send on first delta, edit on subsequent ones."""
        if not self._app:
            return
        meta = metadata or {}
        int_chat_id = int(chat_id)
        stream_id = meta.get("_stream_id")

        if meta.get("_stream_end"):
            buf = self._stream_bufs.get(chat_id)
            if not buf or not buf.message_id or not buf.text:
                return
            if stream_id is not None and buf.stream_id is not None and buf.stream_id != stream_id:
                return
            self._stop_typing(chat_id)
            if reply_to_message_id := meta.get("message_id"):
                with suppress(ValueError):
                    await self._remove_reaction(chat_id, int(reply_to_message_id))
            thread_kwargs = {}
            if message_thread_id := meta.get("message_thread_id"):
                thread_kwargs["message_thread_id"] = message_thread_id
            raw_text = buf.text
            html = _markdown_to_telegram_html(raw_text)
            if len(html) <= TELEGRAM_HTML_MAX_LEN:
                primary_html = html
                extra_html_chunks = []
            else:
                html_chunks = split_message(html, TELEGRAM_HTML_MAX_LEN)
                primary_html = html_chunks[0]
                extra_html_chunks = html_chunks[1:]
            try:
                await self._call_with_retry(
                    self._app.bot.edit_message_text,
                    chat_id=int_chat_id, message_id=buf.message_id,
                    text=primary_html, parse_mode="HTML",
                )
            except BadRequest as e:
                # Only fall back to plain text on actual HTML parse/format errors.
                # Network errors (TimedOut, NetworkError) should propagate immediately
                # to avoid doubling connection demand during pool exhaustion.
                if self._is_not_modified_error(e):
                    self.logger.debug("Final stream edit already applied for {}", chat_id)
                    self._stream_bufs.pop(chat_id, None)
                    return
                self.logger.debug("Final stream edit failed (HTML), trying plain: {}", e)
                # Fall back to raw markdown (not HTML) so users don't see raw tags.
                primary_plain = split_message(raw_text, TELEGRAM_MAX_MESSAGE_LEN)[0] if len(raw_text) > TELEGRAM_MAX_MESSAGE_LEN else raw_text
                try:
                    await self._call_with_retry(
                        self._app.bot.edit_message_text,
                        chat_id=int_chat_id, message_id=buf.message_id,
                        text=primary_plain,
                    )
                except Exception as e2:
                    if self._is_not_modified_error(e2):
                        self.logger.debug("Final stream plain edit already applied for {}", chat_id)
                    else:
                        self.logger.warning("Final stream edit failed: {}", e2)
                        raise  # Let ChannelManager handle retry
            for extra_html_chunk in extra_html_chunks:
                try:
                    await self._call_with_retry(
                        self._app.bot.send_message,
                        chat_id=int_chat_id, text=extra_html_chunk,
                        parse_mode="HTML",
                        **thread_kwargs,
                    )
                except Exception:
                    # Fall back to _send_text which handles HTML→plain gracefully.
                    await self._send_text(int_chat_id, extra_html_chunk)
            self._stream_bufs.pop(chat_id, None)
            return

        buf = self._stream_bufs.get(chat_id)
        if buf is None or (stream_id is not None and buf.stream_id is not None and buf.stream_id != stream_id):
            buf = _StreamBuf(stream_id=stream_id)
            self._stream_bufs[chat_id] = buf
        elif buf.stream_id is None:
            buf.stream_id = stream_id
        buf.text += delta

        if not buf.text.strip():
            return

        now = time.monotonic()
        thread_kwargs = {}
        if message_thread_id := meta.get("message_thread_id"):
            thread_kwargs["message_thread_id"] = message_thread_id
        if buf.message_id is None:
            preview = _strip_md_block(buf.text)
            try:
                sent = await self._call_with_retry(
                    self._app.bot.send_message,
                    chat_id=int_chat_id, text=preview,
                    **thread_kwargs,
                )
                buf.message_id = sent.message_id
                buf.last_edit = now
            except Exception as e:
                self.logger.warning("Stream initial send failed: {}", e)
                raise  # Let ChannelManager handle retry
        elif (now - buf.last_edit) >= self.config.stream_edit_interval:
            if len(buf.text) > TELEGRAM_MAX_MESSAGE_LEN:
                await self._flush_stream_overflow(int_chat_id, buf, thread_kwargs)
                buf.last_edit = now
                return
            preview = _strip_md_block(buf.text)
            try:
                await self._call_with_retry(
                    self._app.bot.edit_message_text,
                    chat_id=int_chat_id, message_id=buf.message_id,
                    text=preview,
                )
                buf.last_edit = now
            except Exception as e:
                if self._is_not_modified_error(e):
                    buf.last_edit = now
                    return
                self.logger.warning("Stream edit failed: {}", e)
                raise  # Let ChannelManager handle retry

    async def _flush_stream_overflow(
        self,
        chat_id: int,
        buf: "_StreamBuf",
        thread_kwargs: dict,
    ) -> None:
        """Split an oversized stream buffer mid-flight.

        Edits the current stream message with the first chunk, sends any
        intermediate chunks as standalone messages, then opens a new message
        for the tail so subsequent deltas continue streaming into it.
        """
        chunks = split_message(buf.text, TELEGRAM_MAX_MESSAGE_LEN)
        if len(chunks) <= 1:
            return
        try:
            await self._call_with_retry(
                self._app.bot.edit_message_text,
                chat_id=chat_id, message_id=buf.message_id,
                text=chunks[0],
            )
        except Exception as e:
            if not self._is_not_modified_error(e):
                self.logger.warning("Stream overflow edit failed: {}", e)
                raise
        for chunk in chunks[1:-1]:
            await self._call_with_retry(
                self._app.bot.send_message,
                chat_id=chat_id, text=chunk, **thread_kwargs,
            )
        tail = chunks[-1]
        sent = await self._call_with_retry(
            self._app.bot.send_message,
            chat_id=chat_id, text=tail, **thread_kwargs,
        )
        buf.message_id = sent.message_id
        buf.text = tail

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            return

        # When multi-user API key mode is enabled, guide new users to set up their key.
        if getattr(self.config, "require_user_api_key", False):
            key = self.keystore.get_key(sender_id)
            if not key:
                await update.message.reply_text(
                    f"👋 *Xin chào {user.first_name}!* Chào mừng bạn đến với Vidtory AI.\n\n"
                    "Để bắt đầu sử dụng bot, bạn cần cung cấp *Vidtory API Key* của mình.\n\n"
                    "🔑 *Cách lấy API Key:*\n"
                    "1. Truy cập: https://app.vidtory.net/settings/api\n"
                    "2. Tạo hoặc copy API Key có sẵn\n"
                    "3. Gửi lệnh: `/apikey YOUR_API_KEY`\n\n"
                    "_Bạn chỉ cần cài đặt một lần duy nhất._",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return
            await update.message.reply_text(
                f"👋 Xin chào lại, *{user.first_name}*! Bot đang sẵn sàng.\n"
                "Gõ /help để xem danh sách lệnh.",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm nanobot.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command for allowed users only."""
        if not update.message or not update.effective_user:
            return
        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            return

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
            ext = self._get_extension(media_type, doc_mime_type, doc_file_name)
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
                    "Bot đang sẵn sàng phục vụ bạn. Gõ /brand để xem profile.",
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
                    "_(Chỉ mất khoảng 1 phút — rất đáng làm!)_",
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
                        lines.append(f"🖼️ *Logo:* [Xem logo]({logo})")
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
                    # Enable web preview when logo exists so Telegram shows the image inline
                    await message.reply_text("\n".join(lines), parse_mode="Markdown",
                                            disable_web_page_preview=not bool(logo))
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
                            "Bot đang sẵn sàng. Gõ /help để xem danh sách lệnh.",
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
                            "_(Chỉ mất khoảng 1 phút — rất đáng làm!)_",
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
                        "Bot đang sẵn sàng phục vụ bạn.",
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
                        "_(Chỉ mất khoảng 1 phút — rất đáng làm!)_",
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
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
        session_key = self._derive_topic_session_key(message)

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_id := getattr(message, "media_group_id", None):
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                self._media_group_buffers[key] = {
                    "sender_id": sender_id, "chat_id": str_chat_id,
                    "contents": [], "media": [],
                    "metadata": metadata,
                    "session_key": session_key,
                }
                self._start_typing(str_chat_id)
                await self._add_reaction(str_chat_id, message.message_id, self.config.react_emoji)
            buf = self._media_group_buffers[key]
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)
            if key not in self._media_group_tasks:
                self._media_group_tasks[key] = asyncio.create_task(self._flush_media_group(key))
            return

        # Guard: When user sends photo/document without any text or caption,
        # ask what they want to do instead of auto-generating content.
        has_media = bool(media_paths)
        has_text = bool(message.text or message.caption)
        is_reply = reply is not None
        if has_media and not has_text and not is_reply:
            await message.reply_text(
                "📷 *Ảnh đã nhận!*\n\n"
                "Bạn muốn tôi làm gì với ảnh này?\n\n"
                "• Reply ảnh + gõ `/setlogo` — đặt làm logo\n"
                "• Reply ảnh + mô tả yêu cầu — tạo ảnh/video\n"
                "• Reply ảnh + `/removewm` — xoá watermark",
                parse_mode="Markdown",
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
            )
            uid = sender_id.split("|")[0].strip()
            onboarding_status = get_onboarding_status(uid)

            # Handle new user onboarding choice
            if onboarding_status == "none":
                raw_content = content.strip().lower()
                if raw_content in ("dùng ngay", "bỏ qua, dùng ngay"):
                    username = metadata.get("username") or ""
                    create_minimal_profile(uid, username=username)
                    onboarding_status = "minimal"
                    # Translate to a clear instruction for the LLM
                    content = "Tôi muốn bỏ qua khai báo và bắt đầu sử dụng bot ngay."
                elif raw_content in ("bắt đầu khai báo", "khai báo thông tin"):
                    # Send the onboarding template directly
                    username = metadata.get("username") or ""
                    profile = create_minimal_profile(uid, username=username)
                    profile["onboarding"]["status"] = "in_progress"
                    from nanobot.utils.customer_profile import save_profile
                    save_profile(uid, profile)
                    
                    try:
                        await self._app.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "📝 *Tuyệt vời! Dưới đây là mẫu thông tin cơ bản:*\n\n"
                                "• *Tên thương hiệu:* ...\n"
                                "• *Ngành nghề:* ...\n"
                                "• *Phong cách thiết kế:* ...\n"
                                "• *Màu sắc chủ đạo:* ...\n"
                                "• *Logo:* (xem hướng dẫn bên dưới)\n\n"
                                "_💡 Mẹo: Điền càng chi tiết thì AI tạo nội dung càng chuẩn xác. "
                                "Tuy nhiên nếu bạn không điền đủ cũng không sao, "
                                "sau này trong quá trình làm việc hệ thống sẽ tự động quan sát và học dần dần. "
                                "Bạn không cần phải ép mình trả lời hoàn hảo ngay từ đầu!_\n\n"
                                "Hãy copy mẫu trên, điền thông tin và gửi lại cho tôi nhé.\n\n"
                                "━━━━━━━━━━━━━━\n"
                                "🖼️ *Thêm logo thương hiệu (tuỳ chọn nhưng rất nên có):*\n\n"
                                "*Cách 1 — Gửi URL logo:*\n"
                                "`/setlogo https://link-logo-cua-ban.png`\n\n"
                                "*Cách 2 — Gửi file ảnh:*\n"
                                "Reply bất kỳ ảnh logo nào + gõ `/setlogo`\n\n"
                                "_Logo sẽ được tự động chèn vào mọi ảnh quảng cáo bạn tạo._"
                            ),
                            parse_mode="Markdown"
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
            api_key: User's Vidtory API key. Falls back to system config key.
            user_id: Telegram user ID (used as customer_id in CDN metadata).

        Returns:
            Permanent CDN URL string on success, or None on any failure.
        """
        # Resolve system API key from config (preferred — merchant key has upload rights)
        effective_key = api_key
        api_base = "https://bapi.vidtory.net"

        try:
            from nanobot.config.loader import load_config
            cfg = load_config()
            provider_cfg = (cfg.providers or {}).get("vidtory") if cfg.providers else None
            if provider_cfg:
                api_base = getattr(provider_cfg, "api_base", None) or api_base
                sys_key = getattr(provider_cfg, "api_key", None) or ""
                if sys_key:
                    effective_key = sys_key
        except Exception:
            pass

        if not effective_key:
            self.logger.debug("setlogo CDN upload skipped: no API key available")
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
            api_key: User's Vidtory API key. Falls back to system config key.
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

        # Resolve system API key
        effective_key = api_key
        api_base = "https://bapi.vidtory.net"

        try:
            from nanobot.config.loader import load_config
            cfg = load_config()
            provider_cfg = (cfg.providers or {}).get("vidtory") if cfg.providers else None
            if provider_cfg:
                api_base = getattr(provider_cfg, "api_base", None) or api_base
                sys_key = getattr(provider_cfg, "api_key", None) or ""
                if sys_key:
                    effective_key = sys_key
        except Exception:
            pass

        if not effective_key:
            self.logger.debug("setlogo bytes upload skipped: no API key available")
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

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _add_reaction(self, chat_id: str, message_id: int, emoji: str) -> None:
        """Add emoji reaction to a message (best-effort, non-blocking)."""
        if not self._app or not emoji:
            return
        try:
            await self._app.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
        except Exception as e:
            self.logger.debug("reaction failed: {}", e)

    async def _remove_reaction(self, chat_id: str, message_id: int) -> None:
        """Remove emoji reaction from a message (best-effort, non-blocking)."""
        if not self._app:
            return
        try:
            await self._app.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=message_id,
                reaction=[],
            )
        except Exception as e:
            self.logger.debug("reaction removal failed: {}", e)

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            with suppress(asyncio.CancelledError):
                while self._app:
                    await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                    await asyncio.sleep(4)
        except Exception as e:
            self.logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    @staticmethod
    def _format_telegram_error(exc: Exception) -> str:
        """Return a short, readable error summary for logs."""
        text = str(exc).strip()
        if text:
            return text
        if exc.__cause__ is not None:
            cause = exc.__cause__
            cause_text = str(cause).strip()
            if cause_text:
                return f"{exc.__class__.__name__} ({cause_text})"
            return f"{exc.__class__.__name__} ({cause.__class__.__name__})"
        return exc.__class__.__name__

    def _on_polling_error(self, exc: Exception) -> None:
        """Keep long-polling network failures to a single readable line."""
        summary = self._format_telegram_error(exc)
        if isinstance(exc, (NetworkError, TimedOut)):
            self.logger.warning("polling network issue: {}", summary)
        else:
            self.logger.error("polling error: {}", summary)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        summary = self._format_telegram_error(context.error)

        if isinstance(context.error, (NetworkError, TimedOut)):
            self.logger.warning("network issue: {}", summary)
        else:
            self.logger.error("error: {}", summary)

    def _get_extension(
        self,
        media_type: str,
        mime_type: str | None,
        filename: str | None = None,
    ) -> str:
        """Get file extension based on media type or original filename."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "image/webp": ".webp",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
                "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
                "video/x-matroska": ".mkv", "video/3gpp": ".3gp",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        # Prefer the original filename's extension when available (documents
        # sent via Telegram's "File" mode always carry their filename).
        if filename:
            suffixes = "".join(Path(filename).suffixes)
            if suffixes:
                return suffixes

        # Fallback: guess extension from MIME type (handles image/bmp → .bmp etc.)
        if mime_type:
            import mimetypes as _mt
            guessed = _mt.guess_extension(mime_type, strict=False)
            if guessed:
                return guessed

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "video": ".mp4", "file": ""}
        if ext := type_map.get(media_type, ""):
            return ext

        return ""

    def _build_keyboard(self, buttons: list) -> InlineKeyboardMarkup | None:
        """Build inline keyboard markup if inline_keyboards is enabled."""
        if not buttons or not self.config.inline_keyboards:
            return None
        keyboard = [
            [InlineKeyboardButton(label, callback_data=self._safe_callback_data(label)) for label in row]
            for row in buttons
        ]
        return InlineKeyboardMarkup(keyboard)

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
        if not self.is_allowed(sender_id):
            return
        if getattr(self.config, "require_user_api_key", False):
            if not self.keystore.get_key(sender_id):
                await query.answer("Vui lòng cấu hình API Key trước bằng lệnh /apikey", show_alert=True)
                return
        button_label = query.data or ""
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
        )
