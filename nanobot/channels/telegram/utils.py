import re
from pathlib import Path

def get_media_type(path: str) -> str:
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

def is_remote_media_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))

def get_extension(
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

def looks_like_api_key(text: str) -> bool:
    """Return True if text looks like a bare Vidtory API key (not a slash command)."""
    stripped = text.strip()
    # A Vidtory API key starts with 'vidtory_' and contains only hex/alphanumeric chars.
    # Accept any token that matches the known prefix pattern.
    return bool(re.fullmatch(r'vidtory_[a-fA-F0-9]{64,}', stripped))

def format_telegram_error(exc: Exception) -> str:
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
