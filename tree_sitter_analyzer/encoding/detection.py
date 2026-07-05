"""Internal encoding detection helpers."""

from collections.abc import Callable
from typing import Any


def detect_data_encoding(
    data: bytes,
    *,
    default_encoding: str,
    file_path: str | None,
    cache: Any,
    chardet_module: Any | None,
    log_debug: Callable[[str], None],
) -> str:
    """Detect byte encoding with optional file-path cache support."""
    if not data:
        return default_encoding

    cached_encoding = get_cached_encoding(file_path, cache, log_debug)
    if cached_encoding:
        return cached_encoding

    detected_encoding = detect_uncached_encoding(
        data,
        default_encoding=default_encoding,
        chardet_module=chardet_module,
        log_debug=log_debug,
    )
    cache_detected_encoding(file_path, cache, detected_encoding)
    return detected_encoding


def get_cached_encoding(
    file_path: str | None, cache: Any, log_debug: Callable[[str], None]
) -> str | None:
    """Return cached encoding for a file path, when available."""
    if not file_path:
        return None

    cached_encoding: str | None = cache.get(file_path)
    if cached_encoding:
        log_debug(f"Using cached encoding for {file_path}: {cached_encoding}")
    return cached_encoding


def detect_uncached_encoding(
    data: bytes,
    *,
    default_encoding: str,
    chardet_module: Any | None,
    log_debug: Callable[[str], None],
) -> str:
    """Detect encoding without consulting or mutating the file cache."""
    if is_utf8(data):
        return "utf-8"

    bom_encoding = detect_bom_encoding(data)
    if bom_encoding:
        return bom_encoding

    return detect_with_chardet(
        data,
        default_encoding=default_encoding,
        chardet_module=chardet_module,
        log_debug=log_debug,
    )


def is_utf8(data: bytes) -> bool:
    """Return whether data can be decoded as UTF-8."""
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def detect_bom_encoding(data: bytes) -> str | None:
    """Detect UTF BOM encodings after the UTF-8 fast path."""
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return None


def detect_with_chardet(
    data: bytes,
    *,
    default_encoding: str,
    chardet_module: Any | None,
    log_debug: Callable[[str], None],
) -> str:
    """Use chardet as the slower fallback detector when available."""
    if chardet_module is None:
        return default_encoding

    try:
        detection = chardet_module.detect(data[:32768])
    except Exception as exc:
        log_debug(f"Chardet detection failed: {exc}")
        return default_encoding

    if not detection or not detection["encoding"]:
        return default_encoding

    confidence = detection.get("confidence", 0)
    if confidence <= 0.7:
        return default_encoding

    detected_encoding: str = detection["encoding"].lower()
    log_debug(f"Detected encoding via chardet: {detected_encoding} ({confidence:.2f})")
    return detected_encoding


def cache_detected_encoding(file_path: str | None, cache: Any, encoding: str) -> None:
    """Cache a detected encoding when the caller supplied a file path."""
    if file_path:
        cache.set(file_path, encoding)
