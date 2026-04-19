"""Tests for Discarded Return Value Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.discarded_return import (
    DiscardedReturnAnalyzer,
    ISSUE_DISCARDED_RESULT,
    ISSUE_DISCARDED_AWAIT,
    ISSUE_DISCARDED_ERROR,
)

import pytest


@pytest.fixture
def analyzer() -> DiscardedReturnAnalyzer:
    return DiscardedReturnAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


# ── Python tests ──────────────────────────────────────────


class TestPythonDiscardedReturn:
    def test_discarded_result_basic(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_calls >= 1
        assert any(i.issue_type == ISSUE_DISCARDED_RESULT for i in result.issues)

    def test_assigned_result_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "x = compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_print_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'print("hello")\n'
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("print" in i.function_name for i in result.issues)

    def test_append_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "items.append(42)\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("append" in i.function_name for i in result.issues)

    def test_method_call_discarded(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "obj.compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any("compute" in i.function_name for i in result.issues)

    def test_method_call_assigned(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "result = obj.compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_multiple_calls(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute()\nsave(data)\nx = process()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        names = [i.function_name for i in result.issues]
        assert "compute" in names
        assert "save" in names or any("save" in n for n in names)
        assert "process" not in names

    def test_return_call_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "def f():\n    return compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_if_call_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "if is_valid():\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("is_valid" in i.function_name for i in result.issues)

    def test_assert_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "assert is_valid()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any("is_valid" in i.function_name for i in result.issues)

    def test_empty_file(self, analyzer: DiscardedReturnAnalyzer) -> None:
        path = _write_tmp("", ".py")
        result = analyzer.analyze_file(path)
        assert result.total_calls == 0
        assert len(result.issues) == 0

    def test_result_to_dict(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_calls" in d
        assert "issues" in d


# ── JavaScript/TypeScript tests ────────────────────────────


class TestJSDiscardedReturn:
    def test_discarded_result(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute();\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_RESULT for i in result.issues)

    def test_assigned_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "const x = compute();\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_async_fetch_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "fetch('/api');\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_AWAIT for i in result.issues)

    def test_console_log_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'console.log("hello");\n'
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert not any("log" in i.function_name for i in result.issues)

    def test_awaited_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "await fetch('/api');\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert not any("fetch" in i.function_name for i in result.issues)

    def test_typescript_discarded(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute();\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_RESULT for i in result.issues)


# ── Java tests ────────────────────────────────────────────


class TestJavaDiscardedReturn:
    def test_discarded_result(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "class Test {\n  void run() {\n    compute();\n  }\n}\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_RESULT for i in result.issues)

    def test_assigned_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "class Test {\n  void run() {\n    int x = compute();\n  }\n}\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_system_out_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = (
            "class Test {\n"
            "  void run() {\n"
            '    System.out.println("hello");\n'
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert not any("println" in i.function_name for i in result.issues)

    def test_return_call_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "class Test {\n  int run() {\n    return compute();\n  }\n}\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)


# ── Go tests ──────────────────────────────────────────────


class TestGoDiscardedReturn:
    def test_discarded_result(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'package main\n\nfunc main() {\n\tcompute()\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_RESULT for i in result.issues)

    def test_assigned_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'package main\n\nfunc main() {\n\tx := compute()\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert not any("compute" in i.function_name for i in result.issues)

    def test_error_return_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'package main\n\nimport "os"\n\nfunc main() {\n\tos.Open("file.txt")\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DISCARDED_ERROR for i in result.issues)

    def test_error_assigned_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'package main\n\nimport "os"\n\nfunc main() {\n\tf, err := os.Open("file.txt")\n\t_ = f\n\t_ = err\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert not any("Open" in i.function_name for i in result.issues)

    def test_fmt_println_not_flagged(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hello")\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert not any("Println" in i.function_name for i in result.issues)


# ── Edge case tests ────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: DiscardedReturnAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_calls == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self, analyzer: DiscardedReturnAnalyzer) -> None:
        path = _write_tmp("compute()", ".txt")
        result = analyzer.analyze_file(path)
        assert result.total_calls == 0

    def test_issue_to_dict(self, analyzer: DiscardedReturnAnalyzer) -> None:
        code = "compute()\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "function_name" in d
            assert "severity" in d
