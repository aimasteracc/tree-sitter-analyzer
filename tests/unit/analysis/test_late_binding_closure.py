"""Tests for Late-Binding Closure Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.late_binding_closure import (
    ISSUE_LATE_BINDING_ARROW,
    ISSUE_LATE_BINDING_FUNC,
    ISSUE_LATE_BINDING_LAMBDA,
    LateBindingClosureAnalyzer,
)

analyzer = LateBindingClosureAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python: lambda in for loop ──


def test_python_lambda_captures_for_var() -> None:
    path = _write_tmp(
        "funcs = []\nfor i in range(5):\n    funcs.append(lambda: i)\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(
        i.issue_type == ISSUE_LATE_BINDING_LAMBDA for i in result.issues
    )
    assert any("i" == i.loop_variable for i in result.issues)


def test_python_lambda_in_while_no_loop_var() -> None:
    """while loops don't bind variables, so no late-binding detection."""
    path = _write_tmp(
        "x = 0\nfuncs = []\nwhile x < 5:\n"
        "    funcs.append(lambda: x)\n    x += 1\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_lambda_no_capture() -> None:
    path = _write_tmp(
        "for i in range(5):\n    f = lambda: 42\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_lambda_default_arg_binds() -> None:
    path = _write_tmp(
        "for i in range(5):\n    f = lambda i=i: i\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_python_list_comprehension_lambda() -> None:
    path = _write_tmp(
        "funcs = [lambda: i for i in range(5)]\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(i.loop_variable == "i" for i in result.issues)


# ── JavaScript: function in for loop ──


def test_js_function_captures_var() -> None:
    path = _write_tmp(
        "var funcs = [];\nfor (var i = 0; i < 5; i++) {\n"
        "    funcs.push(function() { return i; });\n}\n",
        suffix=".js",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(
        i.issue_type == ISSUE_LATE_BINDING_FUNC for i in result.issues
    )


def test_js_arrow_captures_var() -> None:
    path = _write_tmp(
        "var funcs = [];\nfor (var i = 0; i < 5; i++) {\n"
        "    funcs.push(() => i);\n}\n",
        suffix=".js",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(
        i.issue_type == ISSUE_LATE_BINDING_ARROW for i in result.issues
    )


# ── TypeScript: arrow in for-in ──


def test_ts_arrow_captures_forin() -> None:
    path = _write_tmp(
        "const funcs: (() => string)[] = [];\n"
        "for (const key in obj) {\n"
        "    funcs.push(() => key);\n}\n",
        suffix=".ts",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Java: lambda in enhanced for ──


def test_java_lambda_captures_loop_var() -> None:
    path = _write_tmp(
        "List<Runnable> list = new ArrayList<>();\n"
        "for (String s : items) {\n"
        "    list.add(() -> System.out.println(s));\n}\n",
        suffix=".java",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Edge cases ──


def test_no_loops_no_issues() -> None:
    path = _write_tmp("x = lambda: 42\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_lambda_references_unrelated_var() -> None:
    path = _write_tmp(
        "y = 10\nfor i in range(5):\n    f = lambda: y\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_nested_loop_both_vars() -> None:
    path = _write_tmp(
        "funcs = []\nfor i in range(3):\n"
        "    for j in range(3):\n"
        "        funcs.append(lambda: i)\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_empty_file() -> None:
    path = _write_tmp("", suffix=".py")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0
    assert result.total_closures == 0


def test_unsupported_extension() -> None:
    path = _write_tmp("for i in range(5):\n    f = lambda: i\n", suffix=".go")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_result_to_dict() -> None:
    path = _write_tmp(
        "for i in range(5):\n    f = lambda: i\n"
    )
    result = analyzer.analyze_file(path)
    d = result.to_dict()
    assert "file_path" in d
    assert "total_closures" in d
    assert "issue_count" in d
    assert "issues" in d


def test_issue_to_dict() -> None:
    path = _write_tmp(
        "for i in range(5):\n    f = lambda: i\n"
    )
    result = analyzer.analyze_file(path)
    if result.issues:
        d = result.issues[0].to_dict()
        assert "line" in d
        assert "issue_type" in d
        assert "severity" in d
        assert "loop_variable" in d


def test_file_not_found() -> None:
    result = analyzer.analyze_file("/nonexistent/file.py")
    assert result.issue_count == 0


def test_for_loop_tuple_unpack() -> None:
    path = _write_tmp(
        "pairs = [(1, 2)]\nfor a, b in pairs:\n"
        "    f = lambda: a\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(i.loop_variable == "a" for i in result.issues)
