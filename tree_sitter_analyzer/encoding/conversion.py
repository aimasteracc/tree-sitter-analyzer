"""Internal helpers for safe text encoding and decoding."""

from collections.abc import Callable, Sequence


def safe_encode_text(
    text: str | None,
    *,
    target_encoding: str,
    default_encoding: str,
    fallback_encodings: Sequence[str],
    log_debug: Callable[[str], None],
    log_warning: Callable[[str], None],
) -> bytes:
    """Encode text with configured fallbacks."""
    if text is None:
        return b""

    try:
        return text.encode(target_encoding)
    except UnicodeEncodeError as exc:
        log_debug(f"Failed to encode with {target_encoding}, trying fallbacks: {exc}")

    encoded = encode_with_fallbacks(text, target_encoding, fallback_encodings)
    if encoded is not None:
        return encoded

    log_warning(f"Using error replacement for encoding: {text[:50]}...")
    return text.encode(default_encoding, errors="replace")


def encode_with_fallbacks(
    text: str, target_encoding: str, fallback_encodings: Sequence[str]
) -> bytes | None:
    """Try fallback encodings, skipping the encoding that already failed."""
    for fallback in fallback_encodings:
        if fallback == target_encoding:
            continue
        try:
            return text.encode(fallback, errors="replace")
        except UnicodeEncodeError:
            continue
    return None


def safe_decode_bytes(
    data: bytes | None,
    *,
    encoding: str | None,
    default_encoding: str,
    fallback_encodings: Sequence[str],
    detect_encoding: Callable[[bytes], str],
    log_debug: Callable[[str], None],
    log_warning: Callable[[str], None],
) -> str:
    """Decode bytes with detected encoding and configured fallbacks."""
    if data is None or len(data) == 0:
        return ""

    target_encoding = encoding or detect_encoding(data)
    try:
        return data.decode(target_encoding)
    except UnicodeDecodeError as exc:
        log_debug(f"Failed to decode with {target_encoding}, trying fallbacks: {exc}")

    decoded = decode_with_fallbacks(data, target_encoding, fallback_encodings)
    if decoded is not None:
        return decoded

    log_warning(f"Using error replacement for decoding data (length: {len(data)})")
    return data.decode(default_encoding, errors="replace")


def decode_with_fallbacks(
    data: bytes, target_encoding: str, fallback_encodings: Sequence[str]
) -> str | None:
    """Try fallback decoders, skipping the encoding that already failed."""
    for fallback in fallback_encodings:
        if fallback == target_encoding:
            continue
        try:
            return data.decode(fallback, errors="replace")
        except UnicodeDecodeError:
            continue
    return None
