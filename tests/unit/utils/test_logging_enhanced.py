#!/usr/bin/env python3
"""
Enhanced unit tests for logging module.

Fills coverage gaps for setup_safe_logging_shutdown, suppress_output,
SafeStreamHandler.emit, QuietMode, LoggingContext, safe_print,
log_performance, and create_performance_logger.
"""

import logging
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.utils.logging import (
    LoggingContext,
    QuietMode,
    SafeStreamHandler,
    create_performance_logger,
    log_performance,
    safe_print,
    setup_performance_logger,
    setup_safe_logging_shutdown,
    suppress_output,
)

# ---------------------------------------------------------------------------
# setup_safe_logging_shutdown tests
# ---------------------------------------------------------------------------


class TestSetupSafeLoggingShutdown:
    """Test setup_safe_logging_shutdown."""

    def test_setup_safe_logging_shutdown_registers_with_atexit(self):
        """setup_safe_logging_shutdown registers cleanup with atexit."""
        with patch("atexit.register") as mock_register:
            setup_safe_logging_shutdown()
            mock_register.assert_called_once()
            # Verify it registered a callable
            registered_func = mock_register.call_args[0][0]
            assert callable(registered_func)

    def test_cleanup_logging_removes_handlers(self):
        """Cleanup removes handlers from loggers."""
        with patch("atexit.register") as mock_register:
            setup_safe_logging_shutdown()
            cleanup_func = mock_register.call_args[0][0]

        test_logger = logging.getLogger("test_cleanup_logging_remove")
        handler = logging.StreamHandler(StringIO())
        test_logger.addHandler(handler)
        initial_count = len(test_logger.handlers)

        cleanup_func()

        # Handler should be removed (or closed)
        assert (
            len(test_logger.handlers) < initial_count
            or handler not in test_logger.handlers
        )

    def test_cleanup_handles_handler_close_exception(self):
        """Cleanup handles handlers that raise during close."""
        with patch("atexit.register") as mock_register:
            setup_safe_logging_shutdown()
            cleanup_func = mock_register.call_args[0][0]

        mock_handler = MagicMock()
        mock_handler.close.side_effect = OSError("close failed")
        test_logger = logging.getLogger("test_cleanup_handler_error")
        test_logger.handlers.append(mock_handler)

        with patch("sys.stderr", new_callable=StringIO):
            cleanup_func()

        # Should not raise


# ---------------------------------------------------------------------------
# suppress_output decorator tests
# ---------------------------------------------------------------------------


class TestSuppressOutput:
    """Test suppress_output decorator."""

    def test_suppress_output_uses_devnull_on_unix(self):
        """suppress_output uses /dev/null on non-Windows."""
        with (
            patch("sys.platform", "linux"),
            patch("builtins.open", MagicMock(return_value=MagicMock())) as mock_open,
            patch.object(sys, "_testing", False, create=True),
        ):
            decorated = suppress_output(lambda: print("hello"))

            decorated()

            mock_open.assert_called_once_with("/dev/null", "w")

    def test_suppress_output_uses_nul_on_windows(self):
        """suppress_output uses nul on Windows."""
        with (
            patch("sys.platform", "win32"),
            patch("builtins.open", MagicMock(return_value=MagicMock())) as mock_open,
            patch.object(sys, "_testing", False, create=True),
        ):
            decorated = suppress_output(lambda: print("hello"))

            decorated()

            mock_open.assert_called_once_with("nul", "w")

    def test_suppress_output_with_function_that_prints(self):
        """suppress_output suppresses stdout from function."""
        out = StringIO()

        @suppress_output
        def print_something():
            print("secret", file=sys.stdout)

        with (
            patch.object(sys, "_testing", False, create=True),
            patch("sys.stdout", out),
            patch("builtins.open", MagicMock(return_value=MagicMock())),
        ):
            print_something()

        # Output should be suppressed (redirected to devnull/nul)
        assert "secret" not in out.getvalue() or out.getvalue() == ""

    def test_suppress_output_with_testing_true_skips_redirect(self):
        """suppress_output with sys._testing True does not redirect."""
        out = StringIO()

        @suppress_output
        def print_something():
            print("visible")
            return 42

        with patch.object(sys, "_testing", True, create=True), patch("sys.stdout", out):
            result = print_something()

        assert result == 42
        assert "visible" in out.getvalue()

    def test_suppress_output_preserves_return_value(self):
        """suppress_output preserves function return value."""

        @suppress_output
        def return_val():
            return "result"

        with (
            patch.object(sys, "_testing", False, create=True),
            patch("builtins.open", MagicMock(return_value=MagicMock())),
        ):
            r = return_val()
        assert r == "result"

    def test_suppress_output_stdout_close_exception_handled(self):
        """suppress_output handles stdout.close() raising."""
        mock_stream = MagicMock()
        mock_stream.close.side_effect = OSError("close failed")
        with (
            patch.object(sys, "_testing", False, create=True),
            patch("builtins.open", return_value=mock_stream),
            patch("sys.stderr", StringIO()),
        ):
            decorated = suppress_output(lambda: None)
            decorated()


# ---------------------------------------------------------------------------
# SafeStreamHandler.emit edge cases
# ---------------------------------------------------------------------------


class TestSafeStreamHandlerEmit:
    """Test SafeStreamHandler.emit edge cases."""

    def test_emit_with_closed_stream(self):
        """Emit with closed stream does not raise."""
        stream = StringIO()
        stream.close()
        handler = SafeStreamHandler(stream)
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        handler.emit(record)

    def test_emit_with_stream_raising_on_write(self):
        """Emit with stream that raises on write."""
        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.write.side_effect = OSError("write failed")
        mock_stream.writable.return_value = True
        handler = SafeStreamHandler(mock_stream)
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        handler.emit(record)

    def test_emit_with_unicode_content(self):
        """Emit with Unicode content."""
        out = StringIO()
        handler = SafeStreamHandler(out)
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "Unicode: 你好 🌍", (), None
        )
        handler.emit(record)
        assert "Unicode" in out.getvalue()

    def test_emit_with_none_record_message(self):
        """Emit with record that has None-like message."""
        out = StringIO()
        handler = SafeStreamHandler(out)
        record = logging.LogRecord("test", logging.INFO, "", 0, None, (), None)
        handler.emit(record)

    def test_emit_stream_without_write_attr(self):
        """Emit when stream has no write attribute."""
        mock_stream = MagicMock(spec=[])  # No attributes
        del mock_stream.write
        handler = SafeStreamHandler(mock_stream)
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        handler.emit(record)


# ---------------------------------------------------------------------------
# QuietMode context manager
# ---------------------------------------------------------------------------


class TestQuietMode:
    """Test QuietMode context manager."""

    def test_quiet_mode_enabled_suppresses_output(self):
        """QuietMode enabled=True suppresses output."""
        from tree_sitter_analyzer.utils.logging import logger

        orig_level = logger.level
        with QuietMode(enabled=True):
            assert logger.level == logging.ERROR
        assert logger.level == orig_level

    def test_quiet_mode_disabled_no_op(self):
        """QuietMode enabled=False is no-op."""
        from tree_sitter_analyzer.utils.logging import logger

        orig_level = logger.level
        with QuietMode(enabled=False):
            assert logger.level == orig_level
        assert logger.level == orig_level

    def test_quiet_mode_restores_level_on_exception(self):
        """QuietMode restores level when exception occurs."""
        from tree_sitter_analyzer.utils.logging import logger

        orig_level = logger.level
        try:
            with QuietMode(enabled=True):
                raise ValueError("test")
        except ValueError:
            pass
        assert logger.level == orig_level


# ---------------------------------------------------------------------------
# LoggingContext context manager
# ---------------------------------------------------------------------------


class TestLoggingContextEnhanced:
    """Test LoggingContext enhanced scenarios."""

    def test_logging_context_with_custom_level(self):
        """LoggingContext with custom level."""
        test_logger = logging.getLogger("test_logging_context_custom")
        test_logger.setLevel(logging.INFO)
        orig = test_logger.level
        ctx = LoggingContext(enabled=True, level=logging.DEBUG)
        ctx.target_logger = test_logger
        with ctx:
            assert test_logger.level == logging.DEBUG
        assert test_logger.level == orig

    def test_logging_context_level_restoration_after_exit(self):
        """LoggingContext restores level after exit."""
        test_logger = logging.getLogger("test_logging_context_restore")
        test_logger.setLevel(logging.WARNING)
        ctx = LoggingContext(enabled=True, level=logging.INFO)
        ctx.target_logger = test_logger
        with ctx:
            pass
        assert test_logger.level == logging.WARNING

    def test_logging_context_nested(self):
        """LoggingContext nested contexts restore correctly."""
        test_logger = logging.getLogger("test_logging_context_nested")
        test_logger.setLevel(logging.INFO)
        outer = LoggingContext(enabled=True, level=logging.ERROR)
        outer.target_logger = test_logger
        inner = LoggingContext(enabled=True, level=logging.DEBUG)
        inner.target_logger = test_logger
        with outer:
            with inner:
                assert test_logger.level == logging.DEBUG
            assert test_logger.level == logging.ERROR
        assert test_logger.level == logging.INFO


# ---------------------------------------------------------------------------
# safe_print edge cases
# ---------------------------------------------------------------------------


class TestSafePrintEnhanced:
    """Test safe_print edge cases."""

    def test_safe_print_none_message(self):
        """safe_print with None message."""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print(None)
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "None"

    def test_safe_print_quiet_true_returns_early(self):
        """safe_print with quiet=True does not log."""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("hello", quiet=True)
            mock_log.assert_not_called()

    def test_safe_print_level_info(self):
        """safe_print with level info."""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("hi", level="info")
            mock_log.assert_called_once_with("hi")

    def test_safe_print_level_warning(self):
        """safe_print with level warning."""
        with patch("tree_sitter_analyzer.utils.logging.log_warning") as mock_log:
            safe_print("warn", level="warning")
            mock_log.assert_called_once_with("warn")

    def test_safe_print_level_error(self):
        """safe_print with level error."""
        with patch("tree_sitter_analyzer.utils.logging.log_error") as mock_log:
            safe_print("err", level="error")
            mock_log.assert_called_once_with("err")

    def test_safe_print_level_debug(self):
        """safe_print with level debug."""
        with patch("tree_sitter_analyzer.utils.logging.log_debug") as mock_log:
            safe_print("dbg", level="debug")
            mock_log.assert_called_once_with("dbg")

    def test_safe_print_invalid_level_defaults_to_info(self):
        """safe_print with invalid level defaults to info."""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("hi", level="invalid")
            mock_log.assert_called_once_with("hi")

    def test_safe_print_log_error_handling(self):
        """safe_print when log_info's logger raises uses stderr fallback."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            mock_logger.info.side_effect = OSError("broken pipe")
            with patch("sys.stderr", StringIO()):
                safe_print("test")


# ---------------------------------------------------------------------------
# log_performance tests
# ---------------------------------------------------------------------------


class TestLogPerformanceEnhanced:
    """Test log_performance function."""

    def test_log_performance_with_execution_time(self):
        """log_performance with execution_time."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_perf:
            log_performance("op", execution_time=1.23)
            mock_perf.debug.assert_called_once()
            assert "1.2300" in mock_perf.debug.call_args[0][0]

    def test_log_performance_with_details_dict(self):
        """log_performance with details as dict."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_perf:
            log_performance("op", details={"k": 1, "v": 2})
            mock_perf.debug.assert_called_once()
            call_msg = mock_perf.debug.call_args[0][0]
            assert "k: 1" in call_msg or "v: 2" in call_msg

    def test_log_performance_with_details_string(self):
        """log_performance with details as string."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_perf:
            log_performance("op", details="some detail")
            mock_perf.debug.assert_called_once()
            assert "some detail" in mock_perf.debug.call_args[0][0]

    def test_log_performance_without_details(self):
        """log_performance without details."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_perf:
            log_performance("op")
            mock_perf.debug.assert_called_once()
            assert mock_perf.debug.call_args[0][0] == "op"

    def test_log_performance_exception_handling(self):
        """log_performance when debug raises uses stderr fallback."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_perf:
            mock_perf.debug.side_effect = OSError("broken pipe")
            with patch("sys.stderr", StringIO()):
                log_performance("op")


# ---------------------------------------------------------------------------
# create_performance_logger / setup_performance_logger
# ---------------------------------------------------------------------------


class TestCreatePerformanceLogger:
    """Test create_performance_logger."""

    def test_create_performance_logger_returns_logger(self):
        """create_performance_logger returns logger with correct name."""
        logger = create_performance_logger("test_enhanced")
        assert logger.name == "test_enhanced.performance"

    def test_create_performance_logger_has_handlers(self):
        """create_performance_logger sets up handlers."""
        logger = create_performance_logger("test_enhanced_handlers")
        assert len(logger.handlers) >= 1

    def test_create_performance_logger_no_duplicate_handlers(self):
        """create_performance_logger does not add duplicate handlers."""
        logger1 = create_performance_logger("test_enhanced_dup")
        count1 = len(logger1.handlers)
        logger2 = create_performance_logger("test_enhanced_dup")
        assert logger1 is logger2
        assert len(logger2.handlers) == count1


class TestSetupPerformanceLogger:
    """Test setup_performance_logger."""

    def test_setup_performance_logger_returns_logger(self):
        """setup_performance_logger returns logger named performance."""
        logger = setup_performance_logger()
        assert logger.name == "performance"

    def test_setup_performance_logger_has_handlers(self):
        """setup_performance_logger sets up handlers."""
        logger = setup_performance_logger()
        assert len(logger.handlers) >= 1

    def test_setup_performance_logger_no_duplicate_handlers(self):
        """setup_performance_logger does not add duplicate handlers."""
        logger1 = setup_performance_logger()
        count1 = len(logger1.handlers)
        logger2 = setup_performance_logger()
        assert logger1 is logger2
        assert len(logger2.handlers) == count1
