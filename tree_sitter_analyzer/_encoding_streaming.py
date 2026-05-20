"""Internal helpers for streaming file reads with detected encodings."""

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any


def read_file_safe_streaming_context(
    file_path: str | Path,
    *,
    default_encoding: str,
    detect_encoding: Callable[[bytes, str | None], str],
    log_warning: Callable[[str], None],
) -> Any:
    """Return a context manager that streams a file with detected encoding."""
    path = Path(file_path)
    detected_encoding = detect_streaming_encoding(
        path,
        default_encoding=default_encoding,
        detect_encoding=detect_encoding,
        log_warning=log_warning,
    )
    return open_streaming_context(path, detected_encoding, log_warning)


def detect_streaming_encoding(
    file_path: Path,
    *,
    default_encoding: str,
    detect_encoding: Callable[[bytes, str | None], str],
    log_warning: Callable[[str], None],
) -> str:
    """Detect encoding for streaming reads using a small file sample."""
    try:
        sample_data = read_encoding_sample(file_path)
    except OSError as exc:
        log_warning(f"Failed to read file for encoding detection {file_path}: {exc}")
        raise

    if not sample_data:
        return default_encoding
    return detect_encoding(sample_data, str(file_path))


def read_encoding_sample(file_path: Path) -> bytes:
    """Read the leading bytes used for streaming encoding detection."""
    with open(file_path, "rb") as handle:
        return handle.read(8192)


@contextlib.contextmanager
def open_streaming_context(
    file_path: Path, detected_encoding: str, log_warning: Callable[[str], None]
) -> Iterator[Any]:
    """Open a detected-encoding file handle for line-by-line reading."""
    try:
        with open(file_path, encoding=detected_encoding, errors="replace") as handle:
            yield handle
    except OSError as exc:
        log_warning(f"Failed to open file for streaming {file_path}: {exc}")
        raise
