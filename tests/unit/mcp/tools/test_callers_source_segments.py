"""RFC-0043 Phase C: decorator source segments with the lines split once give
exactly what ``ast.get_source_segment`` gives."""

from __future__ import annotations

import ast

import pytest

from tree_sitter_analyzer.mcp.tools.callers_decorators import (
    _SOURCE_LINE,
    SourceSegments,
    python_definition_table,
)
from tree_sitter_analyzer.resident import parse_facts

_TEXTS = [
    "@a\ndef f():\n    pass\n",
    "@a.b(\n    'x',  # c\n    y=[1,\n       2],\n)\n@ c\nclass K:\n    @property\n"
    "    def p(self): return 1\n",
    "@d\r\ndef g():\r\n    pass\r\n@e(1,\r\n  2)\r\ndef h(): pass",
    "x = 1\r@deco\rdef old_mac(): pass\r",
    "# \u00e9t\u00e9 \u2603\n@r\u00e9gle('\u65e5\u672c', \"\U0001f600\")\ndef \u00e9(): pass\n",
    "\x0c@ff\n\x0cdef f(): pass\n",
    "",
    "def no_newline_at_end(): pass",
]


@pytest.mark.parametrize("text", _TEXTS)
def test_every_node_segment_equals_the_standard_function(text: str) -> None:
    segments = SourceSegments(text)
    nodes = [n for n in ast.walk(ast.parse(text)) if hasattr(n, "end_lineno")]

    for node in nodes:
        assert segments.get(node) == ast.get_source_segment(text, node), ast.dump(node)


@pytest.mark.parametrize("text", [*_TEXTS, "a\r\n\r\rb\n\nc", "\n", "\r", "x\r\n"])
def test_lines_split_like_the_standard_function(text: str) -> None:
    splitter = getattr(ast, "_splitlines_no_ff", None)
    if splitter is None:  # pragma: no cover - private helper of CPython
        pytest.skip("no ast._splitlines_no_ff on this interpreter")
    expected = list(splitter(text))
    # Some CPython versions add one empty line at the end; it holds no node.
    while expected and expected[-1] == "":
        expected.pop()
    assert _SOURCE_LINE.findall(text) == expected


def test_node_without_end_position_has_no_segment() -> None:
    node = ast.Name(id="x", lineno=1, col_offset=0)

    assert SourceSegments("x\n").get(node) is None


def test_definition_table_unchanged_with_the_memo_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    tables = [python_definition_table(text) for text in _TEXTS]

    assert tables[1] is not None
    assert [d.text for d in tables[1][0][3]] == ["@a.b( 'x', # c y=[1, 2], )", "@c"]
