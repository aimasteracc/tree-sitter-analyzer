"""Contract: the NOT_FOUND envelope of the nav call-graph tools (#981).

Two locked invariants, parametrized over the four nav tools that emit a
verdict for a single symbol lookup:

  ARCH-A5 — ``success`` means "the tool ran without an internal error", NOT
         "it found what you asked". NOT_FOUND is a valid *result* (ran fine,
         found nothing), so it stays ``success is True``; the semantic
         outcome is carried by ``verdict == "NOT_FOUND"``. (The originally
         bundled #983 success-flip was reverted — it broke the envelope
         contract, which requires ``error: str`` whenever ``success`` is
         False.)

  #981 — the not-found hint must be edge-aware. When the index actually
         holds call edges, a missing symbol must NOT be mislabelled
         "index empty" / "--full-index" — the symbol is simply absent.

``--codegraph-navigate`` is included as the already-correct control for the
hint phrasing; it must satisfy the same contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import CodeGraphImpactTool
from tree_sitter_analyzer.mcp.tools.codegraph_navigate_tool import CodeGraphNavigateTool

# A name that is definitely absent from any project below.
_MISSING = "zzz_definitely_absent_symbol_xyz"

_FORBIDDEN_HINT_FRAGMENTS = ("index empty", "--full-index")


def _make_built_index_with_edges(root: Any) -> None:
    """Index a tiny project that contains a real call edge (caller -> target).

    After this, ``has_call_edges()`` is True and the built marker is set, so a
    NOT_FOUND for an absent symbol is the "populated index, symbol missing"
    case — exactly the #981 scenario.
    """
    (root / "sample.py").write_text(
        "def caller():\n    target()\n\ndef target():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(root))
    try:
        cache.index_project(workers=0)
        assert cache.has_call_edges() is True
        assert cache.call_graph_built() is True
    finally:
        cache.close()


async def _run_missing(tool_label: str, root: str) -> dict[str, Any]:
    """Execute the named tool for the missing symbol; return the JSON envelope."""
    if tool_label == "callers":
        tool: Any = CodeGraphCallersTool(root)
        return await tool.execute({"function_name": _MISSING, "output_format": "json"})
    if tool_label == "callees":
        tool = CodeGraphCalleesTool(root)
        return await tool.execute({"function_name": _MISSING, "output_format": "json"})
    if tool_label == "impact":
        tool = CodeGraphImpactTool(root)
        return await tool.execute(
            {
                "mode": "risk_score",
                "function_name": _MISSING,
                "output_format": "json",
            }
        )
    if tool_label == "navigate":
        tool = CodeGraphNavigateTool(root)
        return await tool.execute(
            {"symbol": _MISSING, "mode": "full", "output_format": "json"}
        )
    raise AssertionError(f"unknown tool label: {tool_label!r}")


_TOOL_LABELS = ["callers", "callees", "impact", "navigate"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_label", _TOOL_LABELS)
async def test_missing_symbol_in_populated_index_contract(
    tmp_path: Any, tool_label: str
) -> None:
    """#981: missing symbol, BUILT index WITH edges.

    verdict is NOT_FOUND, the envelope stays success=True (ARCH-A5: NOT_FOUND
    is a valid result, not an internal error), and the hint does not claim the
    index is empty.
    """
    _make_built_index_with_edges(tmp_path)

    result = await _run_missing(tool_label, str(tmp_path))

    assert result["verdict"] == "NOT_FOUND"
    assert result["success"] is True
    next_step = result.get("next_step", "")
    for fragment in _FORBIDDEN_HINT_FRAGMENTS:
        assert fragment not in next_step, (
            f"{tool_label}: next_step must not claim the index is empty when it "
            f"has edges; got: {next_step!r}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_cls",
    [CodeGraphCallersTool, CodeGraphCalleesTool],
)
async def test_edges_without_built_marker_no_empty_index_hint(
    tmp_path: Any,
    tool_cls: type[CodeGraphCallersTool] | type[CodeGraphCalleesTool],
) -> None:
    """#981 defense-in-depth: edges present but the built marker is a
    false-negative.

    The edge probe (has_call_edges) must override the cleared marker, so the
    hint never claims the index is empty.
    """
    from tree_sitter_analyzer.cache import callgraph_state

    (tmp_path / "sample.py").write_text(
        "def caller():\n    target()\n\ndef target():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        assert cache.has_call_edges() is True
        # Simulate the false-negative: clear the built marker while edges remain.
        # #1005: the edges-table safety net recovers the cleared marker to True,
        # so the populated index is never mislabelled "empty".
        callgraph_state.clear_call_graph_built(cache.get_conn())
        assert cache.call_graph_built() is True
    finally:
        cache.close()

    tool = tool_cls(str(tmp_path))
    result = await tool.execute({"function_name": _MISSING, "output_format": "json"})

    assert result["verdict"] == "NOT_FOUND"
    assert result["success"] is True
    next_step = result.get("next_step", "")
    for fragment in _FORBIDDEN_HINT_FRAGMENTS:
        assert fragment not in next_step, (
            f"next_step must not claim the index is empty when edges exist "
            f"(false-negative marker); got: {next_step!r}"
        )
