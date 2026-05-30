"""Tests for unreachable_code.py — statement-level dead code detection.

TDD-first: these tests were written BEFORE the refactor of the inner closure
and long-method structural issues. They pin the public contract so the
refactoring stays behaviour-preserving.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from tree_sitter_analyzer.unreachable_code import (
    UnreachableBlock,
    UnreachableCodeResult,
    _is_false_literal,
    _is_true_literal,
    analyze_file_unreachable,
    analyze_project_unreachable,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, name: str, code: str) -> str:
    """Write a Python source file and return its str path."""
    src = tmp_path / name
    src.write_text(textwrap.dedent(code), encoding="utf-8")
    return str(src)


# ---------------------------------------------------------------------------
# Unit tests for pure helpers (no I/O, no tree-sitter)
# ---------------------------------------------------------------------------


class TestIsFalseLiteral:
    def test_python_false(self, mocker):
        node = mocker.MagicMock()
        node.text = b"False"
        assert _is_false_literal(node, "") is True

    def test_js_false(self, mocker):
        node = mocker.MagicMock()
        node.text = b"false"
        assert _is_false_literal(node, "") is True

    def test_null_is_false(self, mocker):
        node = mocker.MagicMock()
        node.text = b"null"
        assert _is_false_literal(node, "") is True

    def test_none_node_returns_false(self):
        assert _is_false_literal(None, "") is False

    def test_truthy_value_returns_false(self, mocker):
        node = mocker.MagicMock()
        node.text = b"x"
        assert _is_false_literal(node, "") is False


class TestIsTrueLiteral:
    def test_python_true(self, mocker):
        node = mocker.MagicMock()
        node.text = b"True"
        assert _is_true_literal(node, "") is True

    def test_js_true(self, mocker):
        node = mocker.MagicMock()
        node.text = b"true"
        assert _is_true_literal(node, "") is True

    def test_integer_one(self, mocker):
        node = mocker.MagicMock()
        node.text = b"1"
        assert _is_true_literal(node, "") is True

    def test_none_node_returns_false(self):
        assert _is_true_literal(None, "") is False

    def test_false_value_returns_false(self, mocker):
        node = mocker.MagicMock()
        node.text = b"False"
        assert _is_true_literal(node, "") is False


# ---------------------------------------------------------------------------
# Integration tests via real tree-sitter parsing
# ---------------------------------------------------------------------------


class TestAnalyzeFileUnreachable:
    """Tests for analyze_file_unreachable() using real temporary source files."""

    def test_clean_file_returns_no_blocks(self, tmp_path):
        path = _write_py(
            tmp_path,
            "clean.py",
            """\
            def greet(name: str) -> str:
                return f"Hello, {name}"
        """,
        )
        result = analyze_file_unreachable(path)
        assert isinstance(result, UnreachableCodeResult)
        assert result.errors == 0
        assert result.unreachable_blocks == []
        assert result.functions_analyzed >= 1

    def test_code_after_return_is_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            "dead_return.py",
            """\
            def compute(x):
                return x * 2
                print("never reaches here")
        """,
        )
        result = analyze_file_unreachable(path)
        assert result.errors == 0
        assert len(result.unreachable_blocks) >= 1
        reasons = [b.reason for b in result.unreachable_blocks]
        assert any("return" in r for r in reasons)

    def test_code_after_raise_is_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            "dead_raise.py",
            """\
            def fail(msg):
                raise ValueError(msg)
                x = 1
        """,
        )
        result = analyze_file_unreachable(path)
        assert any("raise" in b.reason for b in result.unreachable_blocks)

    def test_if_false_branch_is_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            "if_false.py",
            """\
            def check():
                if False:
                    print("dead")
                return 0
        """,
        )
        result = analyze_file_unreachable(path)
        assert any(
            "False" in b.reason or "false" in b.reason.lower()
            for b in result.unreachable_blocks
        )

    def test_if_true_else_is_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            "if_true.py",
            """\
            def check():
                if True:
                    return 1
                else:
                    return 0
        """,
        )
        result = analyze_file_unreachable(path)
        assert any(
            "else" in b.reason or "True" in b.reason for b in result.unreachable_blocks
        )

    def test_unknown_extension_returns_error(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_bytes(b"nothing")
        result = analyze_file_unreachable(str(f))
        assert result.errors >= 1
        assert result.language == "unknown"

    def test_nonexistent_file_returns_error(self, tmp_path):
        result = analyze_file_unreachable(str(tmp_path / "missing.py"))
        assert result.errors >= 1

    def test_language_override(self, tmp_path):
        path = _write_py(
            tmp_path,
            "code.txt",
            """\
            def ok():
                return 1
        """,
        )
        result = analyze_file_unreachable(path, language="python")
        assert result.language == "python"
        assert result.errors == 0

    def test_result_to_dict_schema(self, tmp_path):
        path = _write_py(
            tmp_path,
            "simple.py",
            """\
            def f():
                return 1
        """,
        )
        result = analyze_file_unreachable(path)
        d = result.to_dict()
        assert "file" in d
        assert "language" in d
        assert "functions_analyzed" in d
        assert "unreachable_count" in d
        assert "unreachable_blocks" in d
        assert "errors" in d

    def test_unreachable_block_to_dict_schema(self, tmp_path):
        path = _write_py(
            tmp_path,
            "block.py",
            """\
            def f():
                return 1
                x = 2
        """,
        )
        result = analyze_file_unreachable(path)
        assert result.unreachable_blocks
        d = result.unreachable_blocks[0].to_dict()
        assert "file" in d
        assert "function" in d
        assert "start_line" in d
        assert "end_line" in d
        assert "reason" in d
        assert "severity" in d

    def test_multiple_functions_all_analyzed(self, tmp_path):
        path = _write_py(
            tmp_path,
            "multi.py",
            """\
            def alpha():
                return 1
                x = 2

            def beta():
                return 3
                y = 4
        """,
        )
        result = analyze_file_unreachable(path)
        assert result.functions_analyzed >= 2
        assert len(result.unreachable_blocks) >= 2

    def test_nested_function_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            "nested.py",
            """\
            def outer():
                def inner():
                    return 42
                    dead = True
                return inner()
        """,
        )
        result = analyze_file_unreachable(path)
        assert result.functions_analyzed >= 1
        # inner has unreachable code
        assert len(result.unreachable_blocks) >= 1

    def test_severity_is_warning_for_after_return(self, tmp_path):
        path = _write_py(
            tmp_path,
            "sev.py",
            """\
            def f():
                return 1
                x = 2
        """,
        )
        result = analyze_file_unreachable(path)
        assert result.unreachable_blocks
        assert result.unreachable_blocks[0].severity == "warning"


class TestAnalyzeProjectUnreachable:
    """Tests for analyze_project_unreachable() — directory walk."""

    def test_empty_project_returns_empty(self, tmp_path):
        results = analyze_project_unreachable(str(tmp_path))
        assert results == []

    def test_clean_project_returns_no_results(self, tmp_path):
        _write_py(
            tmp_path,
            "clean.py",
            """\
            def f():
                return 1
        """,
        )
        results = analyze_project_unreachable(str(tmp_path))
        assert results == []

    def test_project_with_dead_code_returns_results(self, tmp_path):
        _write_py(
            tmp_path,
            "dead.py",
            """\
            def g():
                return 0
                y = 1
        """,
        )
        results = analyze_project_unreachable(str(tmp_path))
        assert len(results) >= 1
        assert results[0].unreachable_blocks

    def test_test_files_excluded_by_default(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        src = test_dir / "test_something.py"
        src.write_text(
            textwrap.dedent("""\
            def test_func():
                return 0
                dead = True
        """),
            encoding="utf-8",
        )
        results = analyze_project_unreachable(str(tmp_path))
        # test files should be excluded by default
        assert results == []

    def test_test_files_included_when_opted_in(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        src = test_dir / "test_something.py"
        src.write_text(
            textwrap.dedent("""\
            def test_func():
                return 0
                dead = True
        """),
            encoding="utf-8",
        )
        results = analyze_project_unreachable(str(tmp_path), include_test_files=True)
        assert len(results) >= 1

    def test_max_files_respected(self, tmp_path):
        for i in range(10):
            _write_py(
                tmp_path,
                f"dead_{i}.py",
                f"""\
                def f_{i}():
                    return {i}
                    x = {i}
            """,
            )
        results = analyze_project_unreachable(str(tmp_path), max_files=3)
        # At most 3 files were scanned (only files with findings are returned)
        assert len(results) <= 3

    def test_excludes_dot_dirs(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        src = hidden / "hook.py"
        src.write_text(
            textwrap.dedent("""\
            def hook():
                return 0
                dead = True
        """),
            encoding="utf-8",
        )
        results = analyze_project_unreachable(str(tmp_path))
        # .git directory must be excluded
        assert results == []


class TestUnreachableBlockDataclass:
    def test_defaults(self):
        block = UnreachableBlock(
            file_path="foo.py",
            function_name="bar",
            start_line=10,
            end_line=12,
            reason="code after return",
        )
        assert block.severity == "warning"
        assert block.to_dict()["severity"] == "warning"

    def test_custom_severity(self):
        block = UnreachableBlock(
            file_path="foo.py",
            function_name="bar",
            start_line=5,
            end_line=5,
            reason="if-False",
            severity="info",
        )
        assert block.severity == "info"


class TestUnreachableCodeResultDataclass:
    def test_default_fields(self):
        r = UnreachableCodeResult(file_path="x.py", language="python")
        assert r.unreachable_blocks == []
        assert r.functions_analyzed == 0
        assert r.errors == 0

    def test_to_dict_counts_match(self):
        r = UnreachableCodeResult(
            file_path="x.py",
            language="python",
            unreachable_blocks=[
                UnreachableBlock("x.py", "f", 1, 1, "after return"),
                UnreachableBlock("x.py", "g", 5, 6, "after raise"),
            ],
            functions_analyzed=2,
        )
        d = r.to_dict()
        assert d["unreachable_count"] == 2
        assert len(d["unreachable_blocks"]) == 2
        assert d["functions_analyzed"] == 2
