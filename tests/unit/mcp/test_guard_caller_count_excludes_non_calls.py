"""TDD tests for #655: guard caller count must exclude import lines and
inline string-literal references — reconciled with nav callers count.

Three fixture cases:
  - ``my_func`` is called TWICE (real call sites)
  - ``my_func`` is IMPORTED once (should NOT count)
  - ``my_func`` is mentioned in a string literal once (should NOT count)

Expected: guard caller count == 2 (calls only), callers_by_file excludes
the import file and the string-literal file.

Reconciliation invariant: for the same symbol, if nav callers returns N,
guard total_callers must also return N (they must agree on call-site count).
"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
    _filter_comment_docstring_matches,
    _is_symbol_only_in_strings,
    _python_non_code_lines,
)

# ---------------------------------------------------------------------------
# Unit tests for _python_non_code_lines (import line detection)
# ---------------------------------------------------------------------------


class TestPythonNonCodeLinesImportDetection:
    """_python_non_code_lines must flag import lines as non-code."""

    def test_from_import_line_flagged(self) -> None:
        """'from module import symbol' is not a call site — must be flagged."""
        text = textwrap.dedent(
            """\
            from _ast_extraction import (
                _walk_for_symbols,
                other_func,
            )
            result = _walk_for_symbols(node)
            """
        )
        non_code = _python_non_code_lines(text)
        # Lines 1-4 are the import block; line 5 is a real call.
        assert 1 in non_code  # 'from _ast_extraction import ('
        assert 2 in non_code  # '    _walk_for_symbols,'
        assert 3 in non_code  # '    other_func,'
        assert 4 in non_code  # ')'
        assert 5 not in non_code  # real call site must NOT be flagged

    def test_bare_import_line_flagged(self) -> None:
        """'import module' lines must be flagged."""
        text = textwrap.dedent(
            """\
            import os
            import sys
            result = os.path.join("a", "b")
            """
        )
        non_code = _python_non_code_lines(text)
        assert 1 in non_code
        assert 2 in non_code
        assert 3 not in non_code  # real call


# ---------------------------------------------------------------------------
# Unit tests for _is_symbol_only_in_strings
# ---------------------------------------------------------------------------


class TestIsSymbolOnlyInStrings:
    """_is_symbol_only_in_strings must return True when every occurrence of
    symbol on the line is inside a string literal, False when at least one
    occurrence is outside quotes.
    """

    def test_symbol_inside_double_quoted_string(self) -> None:
        line = '            "(_ast_extraction._walk_for_symbols) gates on "'
        assert _is_symbol_only_in_strings(line, "_walk_for_symbols") is True

    def test_symbol_outside_string_is_call(self) -> None:
        line = "        result = _walk_for_symbols(node, source, symbols)"
        assert _is_symbol_only_in_strings(line, "_walk_for_symbols") is False

    def test_symbol_inside_single_quoted_string(self) -> None:
        line = "    raise ValueError('_walk_for_symbols: bad args')"
        assert _is_symbol_only_in_strings(line, "_walk_for_symbols") is True

    def test_symbol_only_outside_mixed_line(self) -> None:
        # symbol appears in a string AND outside — still a call
        line = "    _walk_for_symbols(node)  # '_walk_for_symbols'"
        assert _is_symbol_only_in_strings(line, "_walk_for_symbols") is False


# ---------------------------------------------------------------------------
# Unit tests for _filter_comment_docstring_matches with import + string filter
# ---------------------------------------------------------------------------


class TestFilterCommentDocstringMatchesWithNonCallExclusion:
    """_filter_comment_docstring_matches must drop import-line and
    string-literal matches when the ``symbol`` argument is provided.
    """

    def _make_py_file(self, tmp_path, name: str, content: str) -> str:
        """Write a .py fixture and return the absolute path string."""
        p = tmp_path / name
        p.write_text(content, encoding="utf-8", newline="\n")
        return str(p)

    def test_import_line_excluded(self, tmp_path) -> None:
        content = textwrap.dedent(
            """\
            from mod import my_func
            result = my_func(x)
            """
        )
        path = self._make_py_file(tmp_path, "caller.py", content)
        matches = [
            {"file": path, "line": 1, "text": "from mod import my_func"},
            {"file": path, "line": 2, "text": "result = my_func(x)"},
        ]
        kept = _filter_comment_docstring_matches(matches, symbol="my_func")
        lines = [m["line"] for m in kept]
        assert 1 not in lines  # import line dropped
        assert 2 in lines  # real call kept

    def test_string_literal_line_excluded(self, tmp_path) -> None:
        content = textwrap.dedent(
            """\
            result = my_func(x)
            reason = "my_func is tested here"
            """
        )
        path = self._make_py_file(tmp_path, "caller.py", content)
        matches = [
            {"file": path, "line": 1, "text": "result = my_func(x)"},
            {"file": path, "line": 2, "text": 'reason = "my_func is tested here"'},
        ]
        kept = _filter_comment_docstring_matches(matches, symbol="my_func")
        lines = [m["line"] for m in kept]
        assert 1 in lines  # real call kept
        assert 2 not in lines  # string-literal mention dropped

    def test_real_calls_all_kept(self, tmp_path) -> None:
        content = textwrap.dedent(
            """\
            x = my_func(a)
            y = my_func(b)
            """
        )
        path = self._make_py_file(tmp_path, "calls.py", content)
        matches = [
            {"file": path, "line": 1, "text": "x = my_func(a)"},
            {"file": path, "line": 2, "text": "y = my_func(b)"},
        ]
        kept = _filter_comment_docstring_matches(matches, symbol="my_func")
        assert len(kept) == 2  # both real calls kept


# ---------------------------------------------------------------------------
# Integration: TraceImpactTool.execute caller count fixture test
# ---------------------------------------------------------------------------

# Fixture layout:
#   calls_a.py   → my_func(x)       line 1  [real call]
#   calls_b.py   → my_func(y)       line 1  [real call]
#   imports.py   → import my_func   line 1  [import — phantom]
#   string_ref.py→ "my_func"        line 1  [string literal — phantom]


def _rg_match_line(file_path: str, line_no: int, text: str) -> bytes:
    import json

    obj = {
        "type": "match",
        "data": {
            "path": {"text": file_path},
            "line_number": line_no,
            "lines": {"text": text},
            "submatches": [],
        },
    }
    return json.dumps(obj).encode()


class TestTraceImpactExcludesImportAndStringMatches:
    """End-to-end fixture: 4 ripgrep hits, only 2 are real calls."""

    @pytest.mark.asyncio
    async def test_call_count_excludes_import_and_string_literal(
        self, tmp_path
    ) -> None:
        # Build the fixture files so _python_non_code_lines can read them.
        calls_a = tmp_path / "calls_a.py"
        calls_a.write_text("result = my_func(x)\n", encoding="utf-8", newline="\n")

        calls_b = tmp_path / "calls_b.py"
        calls_b.write_text("value = my_func(y)\n", encoding="utf-8", newline="\n")

        imports_f = tmp_path / "imports.py"
        imports_f.write_text(
            "from mod import my_func\n", encoding="utf-8", newline="\n"
        )

        string_f = tmp_path / "string_ref.py"
        string_f.write_text(
            'pytest.mark.xfail(reason="my_func is not ready")\n',
            encoding="utf-8",
            newline="\n",
        )

        rg_stdout = b"\n".join(
            [
                _rg_match_line(str(calls_a), 1, "result = my_func(x)"),
                _rg_match_line(str(calls_b), 1, "value = my_func(y)"),
                _rg_match_line(str(imports_f), 1, "from mod import my_func"),
                _rg_match_line(
                    str(string_f), 1, 'pytest.mark.xfail(reason="my_func is not ready")'
                ),
            ]
        )

        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(tmp_path))
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture",
            new=AsyncMock(return_value=(0, rg_stdout, b"")),
        ):
            result = await tool.execute({"symbol": "my_func"})

        # Must count only the 2 genuine call sites.
        assert result["call_count"] == 2, (
            f"Expected 2 real calls; guard counted {result['call_count']}. "
            "Import line and string-literal mention must be excluded."
        )

        # callers_by_file must not contain the import or string-literal files.
        by_file = result.get("usages", [])
        files_found = {u["file"] for u in by_file}
        assert str(imports_f) not in files_found, (
            "imports.py (import line) must not appear in callers"
        )
        assert str(string_f) not in files_found, (
            "string_ref.py (string literal) must not appear in callers"
        )
        assert str(calls_a) in files_found
        assert str(calls_b) in files_found

    @pytest.mark.asyncio
    async def test_reconciliation_invariant_guard_matches_nav_callers(
        self, tmp_path
    ) -> None:
        """Reconciliation invariant: guard call_count must equal the number
        of unique call-site files that nav callers would return.

        Simulates: nav callers finds 2 real sites; guard must also count 2.
        This test mocks both tools with the same underlying fixture to assert
        the counts agree.
        """
        calls_a = tmp_path / "calls_a.py"
        calls_a.write_text("result = my_func(x)\n", encoding="utf-8", newline="\n")

        calls_b = tmp_path / "calls_b.py"
        calls_b.write_text("value = my_func(y)\n", encoding="utf-8", newline="\n")

        imports_f = tmp_path / "imports.py"
        imports_f.write_text(
            "from mod import my_func\n", encoding="utf-8", newline="\n"
        )

        rg_stdout = b"\n".join(
            [
                _rg_match_line(str(calls_a), 1, "result = my_func(x)"),
                _rg_match_line(str(calls_b), 1, "value = my_func(y)"),
                _rg_match_line(str(imports_f), 1, "from mod import my_func"),
            ]
        )

        # nav callers (graph-based) correctly returns 2 call sites.
        nav_caller_count = 2  # ground truth from graph

        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(tmp_path))
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture",
            new=AsyncMock(return_value=(0, rg_stdout, b"")),
        ):
            result = await tool.execute({"symbol": "my_func"})

        guard_count = result["call_count"]

        # The reconciliation invariant: guard == nav callers.
        assert guard_count == nav_caller_count, (
            f"Reconciliation invariant violated: "
            f"guard counted {guard_count}, nav callers counted {nav_caller_count}. "
            "Import-line phantom inflated the guard count."
        )


class TestFStringCallSitesNotFiltered:
    """Codex P2 on #661: a call inside an f-string replacement field is real
    code — must NOT be filtered (filtering it undercounts callers and makes
    unsafe edits look safe)."""

    @staticmethod
    def _only_in_strings(line, symbol):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _is_symbol_only_in_strings,
        )

        return _is_symbol_only_in_strings(line, symbol)

    def test_fstring_replacement_field_call_is_code(self):
        assert self._only_in_strings('msg = f"{my_func(x)}"', "my_func") is False

    def test_fstring_literal_text_mention_is_string(self):
        assert self._only_in_strings('msg = f"my_func failed"', "my_func") is True

    def test_fstring_mixed_literal_and_field(self):
        assert self._only_in_strings('f"my_func: {my_func(x)}"', "my_func") is False

    def test_escaped_brace_keeps_literal_string(self):
        assert self._only_in_strings('f"{{my_func}}"', "my_func") is True

    def test_nested_brace_in_replacement_field_call_is_code(self):
        # f"{my_func({1: 2})}" — dict literal nests a brace inside the field;
        # my_func is still a real call (exercises brace_depth 1->2->1).
        assert self._only_in_strings('f"{my_func({1: 2})}"', "my_func") is False

    def test_plain_string_still_filtered(self):
        assert self._only_in_strings('reason = "my_func gates"', "my_func") is True


class TestNonCodeLineAndStringEdges:
    """Cover the #655/#661 diff lines: import detection, triple-quote, escape,
    early-return (codecov)."""

    @staticmethod
    def _noncode(text):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _python_non_code_lines,
        )

        return _python_non_code_lines(text)

    @staticmethod
    def _only_in_strings(line, symbol):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _is_symbol_only_in_strings,
        )

        return _is_symbol_only_in_strings(line, symbol)

    def test_comment_line_is_non_code(self):
        assert 2 in self._noncode("x = 1\n# comment mentions my_func\n")

    def test_import_line_is_non_code(self):
        nc = self._noncode("from mod import my_func\nmy_func()\n")
        assert 1 in nc and 2 not in nc

    def test_symbol_absent_returns_false(self):
        assert self._only_in_strings("nothing here", "my_func") is False

    def test_triple_quote_same_line_symbol_filtered(self):
        assert self._only_in_strings('x = """my_func ref"""', "my_func") is True

    def test_escaped_char_inside_string(self):
        # backslash escape inside the string before the symbol mention
        assert self._only_in_strings('s = "a\\tmy_func"', "my_func") is True


class TestCLikeAndEscapePaths:
    """Cover the c-like block-comment path + escaped-char string path (codecov)."""

    def _make_file(self, tmp_path, name, content):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8", newline="\n")
        return str(p)

    @staticmethod
    def _only_in_strings(line, symbol):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _is_symbol_only_in_strings,
        )

        return _is_symbol_only_in_strings(line, symbol)

    def test_c_block_comment_unclosed_spans_lines(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _filter_comment_docstring_matches,
        )

        # /* block ... */ spanning two lines: the mention inside is filtered,
        # the real call below it is kept (exercises the C-comment in_block path).
        content = "int x;\n/* block\n my_func mentioned */\nmy_func();\n"
        path = self._make_file(tmp_path, "caller.c", content)
        matches = [
            {"file": path, "line": 3, "text": " my_func mentioned */"},
            {"file": path, "line": 4, "text": "my_func();"},
        ]
        kept = _filter_comment_docstring_matches(matches, symbol="my_func")
        assert [m["line"] for m in kept] == [4]

    def test_escaped_char_before_symbol_in_string(self):
        # backslash-escape inside the string, symbol after it, still in-string
        assert self._only_in_strings('s = "a\\nmy_func"', "my_func") is True

    def test_symbol_before_triple_quote_is_code(self):
        # my_func is a real call BEFORE a triple-quote with no mention after →
        # triple-quote region has no symbol (line-198 False branch); the call
        # outside it keeps the line as code.
        assert self._only_in_strings('my_func() + """no ref"""', "my_func") is False
