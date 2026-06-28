"""RED-first tests for issue #452: nested functions must get correct call edges.

Root cause: _extract_call_edges used dict-iteration + break to attribute calls
to the first function whose line range contained the call site.  For nested
defs the outer function always won (its range is wider and dict insertion order
is outer-first from the walk), so the inner function ended up with no edges.

Fix: pick the *innermost* (smallest line-range) containing function.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.cache.extraction import _extract_call_edges
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(source: str, language: str = "python"):
    result = Parser().parse_code(source, language)
    assert result.success and result.tree is not None, (
        f"parse failed: {result.error_message}"
    )
    return result.tree


# ---------------------------------------------------------------------------
# Unit: _extract_call_edges — innermost-function attribution
# ---------------------------------------------------------------------------


class TestNestedFunctionCallEdgeAttribution:
    """The call inside inner() must be attributed to inner, not outer."""

    _SOURCE = """\
def helper():
    return 1

def outer():
    def inner():
        helper()
"""

    def _edges(self) -> list[dict]:
        tree = _parse(self._SOURCE)
        return _extract_call_edges(tree, self._SOURCE, "python", {"symbols": []})

    def test_inner_is_caller_for_helper(self):
        """helper() call at line 6 lives inside inner() → caller must be inner."""
        edges = self._edges()
        helper_edges = [e for e in edges if e["callee_name"] == "helper"]
        assert len(helper_edges) == 1, (
            f"expected exactly 1 edge to helper, got {helper_edges}"
        )
        assert helper_edges[0]["caller_name"] == "inner", (
            f"expected caller=inner, got caller={helper_edges[0]['caller_name']!r}. "
            "The call was misattributed to the outer/enclosing function."
        )

    def test_outer_has_no_helper_edge(self):
        """outer() itself never calls helper() — only inner() does."""
        edges = self._edges()
        outer_helper = [
            e
            for e in edges
            if e["caller_name"] == "outer" and e["callee_name"] == "helper"
        ]
        assert len(outer_helper) == 0, (
            f"outer should have 0 edges to helper, got {outer_helper}"
        )


class TestDeeplyNestedCallEdgeAttribution:
    """Three levels of nesting: calls in innermost must reach innermost."""

    _SOURCE = """\
def helper():
    pass

def outer():
    def middle():
        def deep():
            helper()
"""

    def test_deep_is_caller(self):
        tree = _parse(self._SOURCE)
        edges = _extract_call_edges(tree, self._SOURCE, "python", {"symbols": []})
        helper_edges = [e for e in edges if e["callee_name"] == "helper"]
        assert len(helper_edges) == 1
        assert helper_edges[0]["caller_name"] == "deep", (
            f"expected caller=deep, got {helper_edges[0]['caller_name']!r}"
        )


class TestMultipleCallsInNested:
    """inner() calls two helpers; both edges should be attributed to inner."""

    _SOURCE = """\
def alpha():
    pass

def beta():
    pass

def outer():
    def inner():
        alpha()
        beta()
"""

    def test_both_callees_attributed_to_inner(self):
        tree = _parse(self._SOURCE)
        edges = _extract_call_edges(tree, self._SOURCE, "python", {"symbols": []})
        inner_callees = {e["callee_name"] for e in edges if e["caller_name"] == "inner"}
        assert "alpha" in inner_callees, (
            f"alpha not attributed to inner. All edges: {edges}"
        )
        assert "beta" in inner_callees, (
            f"beta not attributed to inner. All edges: {edges}"
        )


# ---------------------------------------------------------------------------
# Unit: same-line sibling calls — column-aware attribution (Codex P2 / #484)
# ---------------------------------------------------------------------------


class TestSameLineSiblingCallAttribution:
    """Compact brace-style code: a call that sits on the same line as a nested
    function definition but *after* its closing brace must be attributed to the
    outer enclosing function, not the inner one.

    JS example:
        function outer() {
          function inner() {} helper();
        }

    ``helper()`` is on line 2 (same as inner's start/end) but column 22 >
    inner's end column 21, so it is outside inner's body.  A line-only
    containment check would incorrectly attribute it to inner (the narrower
    span); column-aware check correctly attributes it to outer.
    """

    _JS_SOURCE = "function outer() {\n  function inner() {} helper();\n}\n"

    def _js_edges(self) -> list[dict]:
        result = Parser().parse_code(self._JS_SOURCE, "javascript")
        assert result.success and result.tree is not None, (
            f"JS parse failed: {result.error_message}"
        )
        return _extract_call_edges(
            result.tree, self._JS_SOURCE, "javascript", {"symbols": []}
        )

    def test_helper_attributed_to_outer_not_inner(self):
        """helper() is OUTSIDE inner's body column-wise → caller must be outer."""
        edges = self._js_edges()
        helper_edges = [e for e in edges if e["callee_name"] == "helper"]
        assert len(helper_edges) == 1, (
            f"expected exactly 1 edge to helper, got {helper_edges}"
        )
        assert helper_edges[0]["caller_name"] == "outer", (
            f"expected caller=outer (column-aware attribution), "
            f"got caller={helper_edges[0]['caller_name']!r}. "
            "helper() sits past inner's end column on the same line; "
            "line-only containment incorrectly steals it for inner."
        )

    def test_inner_has_no_helper_edge(self):
        """inner() has an empty body — it must not appear as caller of helper."""
        edges = self._js_edges()
        inner_helper = [
            e
            for e in edges
            if e["caller_name"] == "inner" and e["callee_name"] == "helper"
        ]
        assert len(inner_helper) == 0, (
            f"inner should have 0 edges to helper (empty body), got {inner_helper}"
        )


# ---------------------------------------------------------------------------
# Integration: ASTCache index + callees/callers tools
# ---------------------------------------------------------------------------


@pytest.fixture
def nested_indexed_project(tmp_path: Path) -> str:
    """Index a file containing outer() { def inner(): calls helper() }."""
    (tmp_path / "sample.py").write_text(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def outer():\n"
        "    def inner():\n"
        "        return helper()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


class TestNestedFunctionCalleesTool:
    """nav action=callees on a nested function should return edges, not NOT_FOUND."""

    @pytest.mark.asyncio
    async def test_inner_callees_returns_info_verdict(
        self, nested_indexed_project: str
    ) -> None:
        """inner() calls helper() → verdict INFO, callee_count==1."""
        tool = CodeGraphCalleesTool(nested_indexed_project)
        result = await tool.execute({"function_name": "inner", "output_format": "json"})
        assert result.get("success") is True, f"tool errored: {result}"
        assert result.get("verdict") == "INFO", (
            f"Expected verdict=INFO (edges found) but got {result.get('verdict')!r}. "
            "Nested function call edges were not extracted — "
            "calls inside inner() were misattributed to outer()."
        )
        assert result.get("callee_count") == 1, (
            f"Expected callee_count=1, got {result.get('callee_count')}"
        )
        callees = result.get("callees", [])
        callee_names = [c.get("name") for c in callees]
        assert "helper" in callee_names, (
            f"Expected helper in callees but got {callee_names}"
        )

    @pytest.mark.asyncio
    async def test_inner_not_not_found(self, nested_indexed_project: str) -> None:
        """The NOT_FOUND-for-indexed-symbol contradiction must be gone.

        inner IS in the index (it's a named function def); callees must not
        return NOT_FOUND just because edges were previously misattributed.
        """
        tool = CodeGraphCalleesTool(nested_indexed_project)
        result = await tool.execute({"function_name": "inner", "output_format": "json"})
        assert result.get("verdict") != "NOT_FOUND", (
            "inner is indexed but callees returned NOT_FOUND — "
            "the indexed-symbol / no-edges contradiction is still present."
        )


class TestNestedFunctionCallersTool:
    """nav action=callers on helper should include inner as a caller."""

    @pytest.mark.asyncio
    async def test_helper_callers_includes_inner(
        self, nested_indexed_project: str
    ) -> None:
        """helper() is called by inner() → inner appears in callers of helper."""
        tool = CodeGraphCallersTool(nested_indexed_project)
        result = await tool.execute(
            {"function_name": "helper", "output_format": "json"}
        )
        assert result.get("success") is True, f"tool errored: {result}"
        callers = result.get("callers", [])
        caller_names = [c.get("name") for c in callers]
        assert "inner" in caller_names, (
            f"Expected inner in callers of helper, got {caller_names}. "
            "The inner nested function should appear as a caller once "
            "call-edge attribution is fixed."
        )
        # outer() does NOT directly call helper() — it defines inner() which does.
        assert "outer" not in caller_names, (
            f"outer should NOT be in callers of helper (outer only defines inner), "
            f"but got {caller_names}"
        )
