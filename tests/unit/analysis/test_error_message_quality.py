"""Tests for Error Message Quality Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.error_message_quality import (
    ErrorMessageQualityAnalyzer,
    ErrorMessageResult,
    PoorMessage,
    _classify_quality,
)

ANALYZER = ErrorMessageQualityAnalyzer


# ── Classification tests ───────────────────────────────────────────────


class TestClassification:
    def test_good_message(self) -> None:
        assert _classify_quality("File not found: /path/to/file") == "good"

    def test_empty_message(self) -> None:
        assert _classify_quality("") == "empty"

    def test_generic_message(self) -> None:
        assert _classify_quality("error") == "generic"

    def test_generic_failed(self) -> None:
        assert _classify_quality("failed") == "generic"

    def test_generic_error_msg(self) -> None:
        assert _classify_quality("Error") == "generic"

    def test_good_with_context(self) -> None:
        assert _classify_quality("Connection refused: localhost:8080") == "good"

    def test_none_message(self) -> None:
        assert _classify_quality(None) == "empty"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_poor_message_frozen(self) -> None:
        m = PoorMessage(line_number=10, message="error", quality="generic", error_type="ValueError")
        with pytest.raises(AttributeError):
            m.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = ErrorMessageResult(
            total_raises=5,
            poor_messages=2,
            messages=(),
            file_path="test.py",
        )
        assert result.total_raises == 5
        assert result.poor_messages == 2


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_raises == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("raise 'error'")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonErrors:
    def test_no_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "noraise.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 0

    def test_good_raise(self, tmp_path: Path) -> None:
        f = tmp_path / "good.py"
        f.write_text("raise ValueError('Invalid input: empty string')\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 1
        assert result.poor_messages == 0

    def test_generic_raise(self, tmp_path: Path) -> None:
        f = tmp_path / "generic.py"
        f.write_text("raise ValueError('error')\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 1
        assert result.poor_messages == 1

    def test_empty_raise(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("raise ValueError()\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 1
        assert result.poor_messages == 1

    def test_bare_raise(self, tmp_path: Path) -> None:
        f = tmp_path / "bare.py"
        f.write_text("raise\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1

    def test_raise_exception_msg(self, tmp_path: Path) -> None:
        f = tmp_path / "msg.py"
        f.write_text("raise Exception('failed')\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages >= 1

    def test_good_with_format(self, tmp_path: Path) -> None:
        f = tmp_path / "fmt.py"
        f.write_text("raise ValueError(f'Invalid config: {key}')\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages == 0

    def test_multiple_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.py"
        f.write_text(
            "raise ValueError('error')\n"
            "raise TypeError('bad type: expected int')\n"
            "raise RuntimeError()\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_raises == 3
        assert result.poor_messages >= 2


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptErrors:
    def test_throw_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text("throw 'error';")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages >= 1

    def test_throw_new_error(self, tmp_path: Path) -> None:
        f = tmp_path / "good.js"
        f.write_text("throw new Error('Failed to connect: timeout');")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages == 0

    def test_throw_new_error_generic(self, tmp_path: Path) -> None:
        f = tmp_path / "generic.js"
        f.write_text("throw new Error('error');")
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaErrors:
    def test_throw_new(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  void foo() {\n"
            "    throw new RuntimeException('Invalid input: null');\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages == 0

    def test_throw_generic(self, tmp_path: Path) -> None:
        f = tmp_path / "Generic.java"
        f.write_text(
            "public class Generic {\n"
            "  void foo() {\n"
            "    throw new RuntimeException('error');\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages >= 1


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoErrors:
    def test_errors_new(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            'import "errors"\n\n'
            "func foo() error {\n"
            '    return errors.New("not found: missing config")\n'
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages == 0

    def test_errors_new_generic(self, tmp_path: Path) -> None:
        f = tmp_path / "generic.go"
        f.write_text(
            "package main\n\n"
            'import "errors"\n\n'
            "func foo() error {\n"
            '    return errors.New("error")\n'
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_raises >= 1
        assert result.poor_messages >= 1
