"""
Unit tests for call_index regex fallback path.

Phase C: W-3 — ensures the regex-based call scanning fallback
works correctly when AST-based extraction is unavailable.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map.call_index import (
    build_call_index,
    extract_call_sites,
)
from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, SymbolInfo


def _sym(name: str, file: str, line_start: int = 1, line_end: int = 10,
         kind: str = "function") -> SymbolInfo:
    return SymbolInfo(
        name=name, kind=kind, file=file,
        line_start=line_start, line_end=line_end,
    )


class TestBuildCallIndexRegexFallback:
    """Test the regex-based fallback path in build_call_index."""

    def test_regex_fallback_detects_calls(self, tmp_path: Path):
        """When call_sites is empty and project_dir is set, regex fallback activates."""
        # Create a temporary source file
        src = tmp_path / "helper.py"
        src.write_text(
            "def caller():\n"
            "    result = helper_func(42)\n"
            "    return result\n"
            "\n"
            "def helper_func(x):\n"
            "    return x * 2\n",
            encoding="utf-8",
        )

        module = ModuleInfo(
            path="helper.py",
            language="python",
            lines=6,
            functions=[
                {"name": "caller", "line_start": 1, "line_end": 3},
                {"name": "helper_func", "line_start": 5, "line_end": 6},
            ],
            call_sites={},  # Empty → triggers regex fallback
        )

        symbols = [
            _sym("caller", "helper.py", 1, 3),
            _sym("helper_func", "helper.py", 5, 6),
        ]

        caller_map, callee_map = build_call_index(
            modules=[module],
            symbols=symbols,
            module_dependencies=[],
            project_dir=str(tmp_path),
        )

        # caller() calls helper_func() → helper_func should appear in callee_map[caller]
        caller_fqn = "helper.py:caller"
        helper_fqn = "helper.py:helper_func"

        assert caller_fqn in callee_map, "caller should have callees"
        assert helper_fqn in callee_map[caller_fqn], "helper_func should be a callee of caller"

    def test_regex_fallback_skips_missing_file(self, tmp_path: Path):
        """Regex fallback should gracefully skip files that don't exist."""
        module = ModuleInfo(
            path="nonexistent.py",
            language="python",
            lines=10,
            functions=[{"name": "foo", "line_start": 1, "line_end": 5}],
            call_sites={},
        )
        symbols = [_sym("foo", "nonexistent.py")]

        # Should not raise
        caller_map, callee_map = build_call_index(
            modules=[module],
            symbols=symbols,
            module_dependencies=[],
            project_dir=str(tmp_path),
        )
        assert isinstance(caller_map, dict)

    def test_no_project_dir_skips_regex(self):
        """Without project_dir, regex fallback should not activate."""
        module = ModuleInfo(
            path="foo.py",
            language="python",
            lines=10,
            call_sites={},
        )
        symbols = [_sym("foo", "foo.py")]

        caller_map, callee_map = build_call_index(
            modules=[module],
            symbols=symbols,
            module_dependencies=[],
            project_dir="",  # Empty → skip regex
        )
        assert len(caller_map) == 0
        assert len(callee_map) == 0


class TestExtractCallSitesNoAST:
    """Test extract_call_sites returns empty when AST node is None."""

    def test_none_ast_returns_empty(self):
        result = extract_call_sites(None, "python", [], [])
        assert result == {}
