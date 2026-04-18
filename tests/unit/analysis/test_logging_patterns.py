"""Tests for Logging Pattern Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.logging_patterns import (
    SMELL_BARE_RAISE,
    SMELL_PRINT_LOGGING,
    SMELL_SENSITIVE_IN_LOG,
    SMELL_SILENT_CATCH,
    CatchBlock,
    LoggingPatternAnalyzer,
    LoggingPatternResult,
    LoggingSmell,
)


@pytest.fixture
def analyzer() -> LoggingPatternAnalyzer:
    return LoggingPatternAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# --- Python: silent_catch ---

class TestPythonSilentCatch:
    def test_except_with_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError as e:
    logging.error("Failed: %s", e)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_smells == 0
        path.unlink()

    def test_except_without_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError as e:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_smells >= 1
        assert result.catch_blocks[0].smells[0].smell_type == SMELL_SILENT_CATCH
        path.unlink()

    def test_bare_except_no_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    x = compute()
except:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_smells >= 1
        smells = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(smells) >= 1
        path.unlink()

    def test_except_with_print(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception as e:
    print(f"Error: {e}")
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_nested_except(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    try:
        inner()
    except ValueError:
        pass
    outer()
except Exception as e:
    logging.error("Outer failed: %s", e)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_logger_info_call(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception as e:
    logger.info("Handled: %s", e)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_log_error_call(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception as e:
    log.error("Failed", exc_info=True)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()


# --- Python: print_logging ---

class TestPythonPrintLogging:
    def test_print_in_function(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
def process():
    print("Processing started")
    result = compute()
    print(f"Result: {result}")
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        print_smells = result.get_smells_by_type(SMELL_PRINT_LOGGING)
        assert len(print_smells) == 2
        path.unlink()

    def test_no_print(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
def process():
    logger.info("Processing started")
    result = compute()
    return result
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        print_smells = result.get_smells_by_type(SMELL_PRINT_LOGGING)
        assert len(print_smells) == 0
        path.unlink()


# --- Python: sensitive_in_log ---

class TestPythonSensitiveInLog:
    def test_password_in_log(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    login()
except Exception as e:
    logging.error("Failed for password=%s", password)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) >= 1
        path.unlink()

    def test_token_in_log(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    authenticate()
except Exception as e:
    logging.info("Token: %s", access_token)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) >= 1
        path.unlink()

    def test_safe_variable_in_log(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    process()
except Exception as e:
    logging.error("Failed for user %s", username)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) == 0
        path.unlink()

    def test_sensitive_keyword_arg(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    connect()
except Exception as e:
    logging.error("Connection failed", secret_key=config.key)
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) >= 1
        path.unlink()


# --- Python: bare_raise ---

class TestPythonBareRaise:
    def test_raise_without_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError as e:
    raise
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        bare_raises = result.get_smells_by_type(SMELL_BARE_RAISE)
        assert len(bare_raises) >= 1
        # Also should have silent_catch since no logging before raise
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_raise_with_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError as e:
    logging.error("Failed: %s", e)
    raise
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()


# --- JavaScript ---

class TestJavaScriptLogging:
    def test_catch_without_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try {
    risky();
} catch (err) {
    // silent
}
'''
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_catch_with_console_error(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try {
    risky();
} catch (err) {
    console.error("Failed:", err);
}
'''
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_console_log_as_print(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
function process() {
    console.log("Processing");
}
'''
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        print_smells = result.get_smells_by_type(SMELL_PRINT_LOGGING)
        assert len(print_smells) >= 1
        path.unlink()

    def test_sensitive_in_js_log(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try {
    login();
} catch (err) {
    console.error("Failed", password);
}
'''
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) >= 1
        path.unlink()


# --- TypeScript ---

class TestTypeScriptLogging:
    def test_ts_catch_silent(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try {
    await fetchData();
} catch (error) {
    // ignore
}
'''
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_ts_logger_call(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try {
    await fetchData();
} catch (error) {
    logger.error("Fetch failed", error);
}
'''
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()


# --- Java ---

class TestJavaLogging:
    def test_catch_without_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
public class Foo {
    void bar() {
        try {
            risky();
        } catch (Exception e) {
            // silent
        }
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_catch_with_logger(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
public class Foo {
    void bar() {
        try {
            risky();
        } catch (Exception e) {
            logger.error("Failed", e);
        }
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_system_out_as_print(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
public class Foo {
    void bar() {
        System.out.println("Debug output");
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        print_smells = result.get_smells_by_type(SMELL_PRINT_LOGGING)
        assert len(print_smells) >= 1
        path.unlink()

    def test_sensitive_in_java_log(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
public class Foo {
    void bar() {
        try {
            login();
        } catch (Exception e) {
            logger.error("Failed for password=" + password);
        }
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        sensitive = result.get_smells_by_type(SMELL_SENSITIVE_IN_LOG)
        assert len(sensitive) >= 1
        path.unlink()


# --- Go ---

class TestGoLogging:
    def test_error_check_without_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
package main

func process() error {
    result, err := risky()
    if err != nil {
        return err
    }
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_error_check_with_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
package main

import "log"

func process() error {
    result, err := risky()
    if err != nil {
        log.Printf("Failed: %v", err)
        return err
    }
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_fmt_println_as_print(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
package main

import "fmt"

func process() {
    fmt.Println("Processing started")
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        print_smells = result.get_smells_by_type(SMELL_PRINT_LOGGING)
        assert len(print_smells) >= 1
        path.unlink()

    def test_slog_logging(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
package main

import "log/slog"

func process() error {
    result, err := risky()
    if err != nil {
        slog.Error("Failed", "error", err)
        return err
    }
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_non_error_if_ignored(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
package main

func process() {
    if x > 10 {
        doSomething()
    }
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert result.total_catch_blocks == 0
        path.unlink()


# --- Edge cases ---

class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: LoggingPatternAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_smells == 0
        assert result.total_catch_blocks == 0

    def test_unsupported_extension(self, analyzer: LoggingPatternAnalyzer) -> None:
        path = _write_tmp("try { risky(); } catch(e) {}", ".ruby")
        result = analyzer.analyze_file(path)
        assert result.total_smells == 0
        path.unlink()

    def test_empty_file(self, analyzer: LoggingPatternAnalyzer) -> None:
        path = _write_tmp("", ".py")
        result = analyzer.analyze_file(path)
        assert result.total_smells == 0
        path.unlink()

    def test_result_to_dict(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "catch_blocks" in d
        assert "total_smells" in d
        path.unlink()

    def test_catch_block_to_dict(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        if result.catch_blocks:
            d = result.catch_blocks[0].to_dict()
            assert "start_line" in d
            assert "handler_type" in d
            assert "smells" in d
        path.unlink()

    def test_high_severity_filter(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        high = result.get_high_severity_smells()
        assert len(high) >= 1
        path.unlink()

    def test_multiple_catch_types(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except ValueError:
    logging.error("Value error")
except TypeError:
    pass
except Exception as e:
    raise
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_catch_blocks == 3
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) >= 1
        path.unlink()

    def test_logging_exception_call(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception as e:
    logging.exception("Failed to process")
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        silent = result.get_smells_by_type(SMELL_SILENT_CATCH)
        assert len(silent) == 0
        path.unlink()

    def test_result_immutable(self, analyzer: LoggingPatternAnalyzer) -> None:
        code = '''\
try:
    risky()
except Exception:
    pass
'''
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert isinstance(result.catch_blocks, tuple)
        assert isinstance(result.print_logging_calls, tuple)
        path.unlink()
