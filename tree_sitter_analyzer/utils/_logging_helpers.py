"""Internal helpers for logging setup and cleanup."""

import contextlib
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

STREAM_EMIT_ERRORS = (ValueError, OSError, AttributeError, UnicodeError)


def coerce_log_level(level: int | str) -> int:
    """Convert a user-facing log level into a logging module level."""
    if isinstance(level, str):
        return _LOG_LEVELS.get(level.upper(), logging.WARNING)
    return level


def resolve_configured_log_level(level: int | str) -> int:
    """Resolve the requested level, including LOG_LEVEL override."""
    resolved_level = coerce_log_level(level)
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    return _LOG_LEVELS.get(env_level, resolved_level)


def file_logging_enabled() -> bool:
    """Return whether optional file logging is enabled."""
    return os.environ.get("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "").lower() == "true"


def create_log_formatter() -> logging.Formatter:
    """Create the standard runtime log formatter."""
    return logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def write_stderr_safely(message: str) -> None:
    """Best-effort write to stderr without disrupting runtime behavior."""
    if not (hasattr(sys, "stderr") and hasattr(sys.stderr, "write")):
        return

    with contextlib.suppress(Exception):
        sys.stderr.write(message)


def should_skip_stream_emit(stream: object) -> bool:
    """Return whether a stream handler should skip emitting to this stream."""
    if hasattr(stream, "closed") and stream.closed:
        return True
    if not hasattr(stream, "write"):
        return True
    if is_pytest_capture_stream(stream):
        return False
    return not is_stream_writable(stream)


def is_pytest_capture_stream(stream: object) -> bool:
    """Detect pytest capture streams that should avoid pre-flush checks."""
    stream_name = getattr(stream, "name", "")
    return stream_name is None or "pytest" in str(type(stream)).lower()


def is_stream_writable(stream: object) -> bool:
    """Best-effort writable check that treats stream errors as not writable."""
    try:
        return not (hasattr(stream, "writable") and not stream.writable())
    except STREAM_EMIT_ERRORS:
        return False


def clear_logger_handlers(logger: logging.Logger) -> None:
    """Close and remove all handlers from a logger."""
    for handler in logger.handlers[:]:
        with contextlib.suppress(Exception):
            handler.close()
        logger.removeHandler(handler)


def configure_default_handlers(
    logger: logging.Logger,
    handler_factory: Callable[[], logging.Handler],
    level: int,
    enable_file_log: bool,
) -> int:
    """Attach default stream and optional file handlers, returning file level."""
    formatter = create_log_formatter()
    handler = handler_factory()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if enable_file_log:
        return add_file_handler(logger, formatter, level)
    return level


def add_file_handler(
    logger: logging.Logger, formatter: logging.Formatter, level: int
) -> int:
    """Attach optional file logging and return the configured file level."""
    try:
        log_path = resolve_log_path()
        file_log_level = resolve_file_log_level(level)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_log_level)
        logger.addHandler(file_handler)
        write_stderr_safely(f"[logging_setup] File logging enabled: {log_path}\n")
        return file_log_level
    except Exception as exc:
        write_stderr_safely(f"[logging_setup] file handler init skipped: {exc}\n")
        return level


def resolve_log_path() -> Path:
    """Resolve the file logging destination path."""
    log_dir = os.environ.get("TREE_SITTER_ANALYZER_LOG_DIR")
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        return Path(log_dir) / "tree_sitter_analyzer.log"

    return Path(tempfile.gettempdir()) / "tree_sitter_analyzer.log"


def resolve_file_log_level(level: int) -> int:
    """Resolve optional file handler level, falling back to main logger level."""
    file_level = os.environ.get("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "").upper()
    return _LOG_LEVELS.get(file_level, level)


def resolve_final_logger_level(
    level: int, file_log_level: int, enable_file_log: bool
) -> int:
    """Return the lowest level required by any configured handler."""
    if enable_file_log:
        return min(level, file_log_level)
    return level


def apply_test_logger_settings(logger: logging.Logger, level: int) -> None:
    """Keep test loggers isolated from parent logger configuration."""
    if not logger.name.startswith("test_"):
        return

    logger.propagate = False
    logger.level = level


def cleanup_all_logging_handlers() -> None:
    """Close and remove handlers from all known loggers during shutdown."""
    try:
        for logger in iter_known_loggers():
            close_handlers_for_shutdown(logger)
    except Exception as exc:
        write_stderr_safely(f"[logging_cleanup] cleanup skipped: {exc}\n")


def iter_known_loggers() -> list[logging.Logger]:
    """Return the root logger plus all named loggers."""
    return [logging.getLogger()] + [
        logging.getLogger(name) for name in logging.Logger.manager.loggerDict
    ]


def close_handlers_for_shutdown(logger: logging.Logger) -> None:
    """Close and remove each handler while reporting best-effort failures."""
    for handler in logger.handlers[:]:
        try:
            handler.close()
            logger.removeHandler(handler)
        except Exception as exc:
            write_stderr_safely(
                f"[logging_cleanup] handler close/remove skipped: {exc}\n"
            )
