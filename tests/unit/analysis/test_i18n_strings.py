"""Tests for i18n String Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.i18n_strings import (
    VIS_INTERNAL,
    VIS_LIKELY,
    VIS_USER,
    I18nFileResult,
    I18nStringDetector,
    I18nSummary,
    _classify_visibility,
)

# --- Visibility classification tests ---


class TestVisibilityClassification:
    def test_short_string_internal(self) -> None:
        assert _classify_visibility("") == VIS_INTERNAL
        assert _classify_visibility("a") == VIS_INTERNAL

    def test_single_word_identifier_internal(self) -> None:
        assert _classify_visibility("utf-8") == VIS_INTERNAL
        assert _classify_visibility("lowercase") == VIS_INTERNAL

    def test_constant_identifier_internal(self) -> None:
        assert _classify_visibility("MAX_SIZE") == VIS_INTERNAL

    def test_numeric_string_internal(self) -> None:
        assert _classify_visibility("42.5") == VIS_INTERNAL
        assert _classify_visibility("100") == VIS_INTERNAL

    def test_file_path_internal(self) -> None:
        assert _classify_visibility("config.json") == VIS_INTERNAL
        assert _classify_visibility("readme.md") == VIS_INTERNAL

    def test_email_internal(self) -> None:
        assert _classify_visibility("user@example.com") == VIS_INTERNAL

    def test_url_internal(self) -> None:
        assert _classify_visibility("https://example.com") == VIS_INTERNAL

    def test_color_code_internal(self) -> None:
        assert _classify_visibility("#ff0000") == VIS_INTERNAL
        assert _classify_visibility("#fff") == VIS_INTERNAL

    def test_whitespace_internal(self) -> None:
        assert _classify_visibility("   ") == VIS_INTERNAL

    def test_sentence_user_visible(self) -> None:
        assert _classify_visibility("File not found") == VIS_USER
        assert _classify_visibility("Hello, world!") == VIS_USER

    def test_error_message_user_visible(self) -> None:
        assert _classify_visibility("Connection failed.") == VIS_USER
        assert _classify_visibility("Invalid input: must be positive") == VIS_USER

    def test_multi_word_likely_visible(self) -> None:
        result = _classify_visibility("some random text")
        assert result in (VIS_LIKELY, VIS_USER)

    def test_camel_case_likely_visible(self) -> None:
        assert _classify_visibility("NotFound") == VIS_LIKELY

    def test_date_string_internal(self) -> None:
        assert _classify_visibility("2024-01-15") == VIS_INTERNAL

    def test_hex_uuid_internal(self) -> None:
        assert _classify_visibility("550e8400-e29b-41d4") == VIS_INTERNAL


# --- Python analysis tests ---


def _write_tmp(content: str, suffix: str = ".py") -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestPythonAnalysis:
    def setup_method(self) -> None:
        self.detector = I18nStringDetector()

    def test_print_statement_detected(self) -> None:
        path = _write_tmp('print("Hello, world!")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
            assert any(s.text == "Hello, world!" for s in result.strings)
            assert any(s.function_name == "print" for s in result.strings)
        finally:
            Path(path).unlink()

    def test_raise_exception_detected(self) -> None:
        path = _write_tmp('raise ValueError("Invalid input provided")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
            assert any("Invalid input" in s.text for s in result.strings)
        finally:
            Path(path).unlink()

    def test_logging_output_detected(self) -> None:
        path = _write_tmp(
            'import logging\n'
            'logger = logging.getLogger(__name__)\n'
            'logger.error("Something went wrong")\n'
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
            assert any("Something went wrong" in s.text for s in result.strings)
        finally:
            Path(path).unlink()

    def test_variable_assignment_not_detected(self) -> None:
        path = _write_tmp('msg = "This is just a variable"\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()

    def test_empty_string_skipped(self) -> None:
        path = _write_tmp('print("")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()

    def test_single_char_skipped(self) -> None:
        path = _write_tmp('print(".")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()

    def test_format_string_detected(self) -> None:
        path = _write_tmp('print(f"User {name} logged in")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_multiple_strings_in_one_call(self) -> None:
        path = _write_tmp('print("Error:", "file not found")\n')
        try:
            result = self.detector.analyze_file(path)
            assert result.user_visible_count >= 1
        finally:
            Path(path).unlink()

    def test_file_result_counts(self) -> None:
        path = _write_tmp(
            'print("User visible message")\n'
            'print("x")\n'
        )
        try:
            result = self.detector.analyze_file(path)
            total = result.user_visible_count + result.likely_visible_count + result.internal_count
            assert total == len(result.strings)
        finally:
            Path(path).unlink()

    def test_unsupported_extension_empty_result(self) -> None:
        path = _write_tmp("some content", suffix=".txt")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
            assert result.user_visible_count == 0
        finally:
            Path(path).unlink()

    def test_nonexistent_file_returns_empty(self) -> None:
        result = self.detector.analyze_file("/nonexistent/path.py")
        assert len(result.strings) == 0

    def test_visibility_filter(self) -> None:
        path = _write_tmp('print("Hello, world!")\nprint("x")\n')
        try:
            result = self.detector.analyze_file(path, visibility_filter={VIS_USER})
            assert all(s.visibility == VIS_USER for s in result.strings)
        finally:
            Path(path).unlink()

    def test_to_dict_roundtrip(self) -> None:
        path = _write_tmp('print("Test message here")\n')
        try:
            result = self.detector.analyze_file(path)
            if result.strings:
                d = result.strings[0].to_dict()
                assert "text" in d
                assert "line" in d
                assert "visibility" in d
        finally:
            Path(path).unlink()

    def test_result_to_dict(self) -> None:
        result = I18nFileResult(
            file_path="test.py",
            strings=(),
            user_visible_count=0,
            likely_visible_count=0,
            internal_count=0,
        )
        d = result.to_dict()
        assert d["file_path"] == "test.py"
        assert d["user_visible_count"] == 0

    def test_summary_to_dict(self) -> None:
        summary = I18nSummary(
            total_files=1,
            total_strings=5,
            user_visible_count=3,
            likely_visible_count=1,
            internal_count=1,
            file_results=(),
        )
        d = summary.to_dict()
        assert d["total_files"] == 1
        assert d["total_strings"] == 5

    def test_sys_stderr_write_detected(self) -> None:
        path = _write_tmp(
            'import sys\n'
            'sys.stderr.write("Error: something failed")\n'
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_triple_quoted_string(self) -> None:
        path = _write_tmp('print("""This is a long error message""")\n')
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()


# --- JavaScript/TypeScript analysis tests ---


class TestJavaScriptAnalysis:
    def setup_method(self) -> None:
        self.detector = I18nStringDetector()

    def test_console_log_detected(self) -> None:
        path = _write_tmp('console.log("Hello, world!");\n', suffix=".js")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
            assert any("Hello, world!" in s.text for s in result.strings)
        finally:
            Path(path).unlink()

    def test_console_error_detected(self) -> None:
        path = _write_tmp('console.error("Something went wrong!");\n', suffix=".js")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_alert_detected(self) -> None:
        path = _write_tmp('alert("Please enter a valid email address");\n', suffix=".js")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_throw_new_error_detected(self) -> None:
        path = _write_tmp('throw new Error("Invalid configuration");\n', suffix=".js")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_variable_assignment_not_detected(self) -> None:
        path = _write_tmp('const msg = "Just a variable";\n', suffix=".js")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()

    def test_typescript_file(self) -> None:
        path = _write_tmp('console.log("TypeScript message here");\n', suffix=".ts")
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()


# --- Java analysis tests ---


class TestJavaAnalysis:
    def setup_method(self) -> None:
        self.detector = I18nStringDetector()

    def test_system_out_println_detected(self) -> None:
        path = _write_tmp(
            'public class Test {\n'
            '    public static void main(String[] args) {\n'
            '        System.out.println("Hello, world!");\n'
            '    }\n'
            '}\n',
            suffix=".java",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_throw_exception_detected(self) -> None:
        path = _write_tmp(
            'public class Test {\n'
            '    void check() {\n'
            '        throw new IllegalArgumentException("Invalid parameter value");\n'
            '    }\n'
            '}\n',
            suffix=".java",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_logger_severe_detected(self) -> None:
        path = _write_tmp(
            'import java.util.logging.Logger;\n'
            'public class Test {\n'
            '    void run() {\n'
            '        Logger.getLogger("test").severe("Critical failure detected");\n'
            '    }\n'
            '}\n',
            suffix=".java",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_variable_not_detected(self) -> None:
        path = _write_tmp(
            'public class Test {\n'
            '    void run() {\n'
            '        String msg = "Just a variable";\n'
            '    }\n'
            '}\n',
            suffix=".java",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()


# --- Go analysis tests ---


class TestGoAnalysis:
    def setup_method(self) -> None:
        self.detector = I18nStringDetector()

    def test_fmt_println_detected(self) -> None:
        path = _write_tmp(
            'package main\n'
            'import "fmt"\n'
            'func main() {\n'
            '    fmt.Println("Hello, world!")\n'
            '}\n',
            suffix=".go",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_fmt_errorf_detected(self) -> None:
        path = _write_tmp(
            'package main\n'
            'import "fmt"\n'
            'func check() error {\n'
            '    return fmt.Errorf("invalid configuration provided")\n'
            '}\n',
            suffix=".go",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_errors_new_detected(self) -> None:
        path = _write_tmp(
            'package main\n'
            'import "errors"\n'
            'func check() error {\n'
            '    return errors.New("something went wrong")\n'
            '}\n',
            suffix=".go",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()

    def test_variable_not_detected(self) -> None:
        path = _write_tmp(
            'package main\n'
            'func main() {\n'
            '    msg := "Just a variable"\n'
            '}\n',
            suffix=".go",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) == 0
        finally:
            Path(path).unlink()

    def test_log_printf_detected(self) -> None:
        path = _write_tmp(
            'package main\n'
            'import "log"\n'
            'func main() {\n'
            '    log.Printf("Processing item %d", 42)\n'
            '}\n',
            suffix=".go",
        )
        try:
            result = self.detector.analyze_file(path)
            assert len(result.strings) >= 1
        finally:
            Path(path).unlink()
