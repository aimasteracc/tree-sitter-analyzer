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

from tests.unit._ast_cache_helpers import legacy_cache
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
    cache = legacy_cache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        assert cache.has_call_edges() is True
        # Simulate a legacy false-negative without today's incomplete sentinel.
        callgraph_state.clear_call_graph_built(cache.get_conn())
        cache.get_conn().execute("DELETE FROM ast_call_graph_state WHERE id = 2")
        cache.get_conn().commit()
        assert cache.call_graph_built() is False
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


_REEXPORT_PROJECT = {
    "pkg/__init__.py": "from .extractor import Extractor\nfrom .mixin import Mixin\n",
    "pkg/mixin.py": (
        "class Mixin:\n    def _inherited(self):\n        return 2\n\n"
        "    def _unused(self):\n        return 0\n"
    ),
    "pkg/extractor.py": (
        "from .mixin import Mixin\n\n\nclass Extractor(Mixin):\n    pass\n"
    ),
    # PEP 562 惰性再导出：静态分析无法从 lazy/__init__.py 找到 LazySub。
    "lazy/__init__.py": (
        "def __getattr__(name):\n    from . import impl\n\n"
        "    return getattr(impl, name)\n"
    ),
    "lazy/impl.py": (
        "class LazyBase:\n    def _hidden(self):\n        return 3\n\n\n"
        "class LazySub(LazyBase):\n    pass\n"
    ),
    "tests/test_use.py": (
        "import pytest\n\nfrom lazy import LazySub\nfrom pkg import Extractor\n\n\n"
        "class TestUse:\n"
        "    @pytest.fixture\n    def extractor(self) -> Extractor:\n"
        "        return Extractor()\n\n"
        "    @pytest.fixture\n    def lazy(self) -> LazySub:\n"
        "        return LazySub()\n\n"
        "    def test_inherited(self, extractor: Extractor) -> None:\n"
        "        assert extractor._inherited() == 2\n\n"
        "    def test_lazy(self, lazy: LazySub) -> None:\n"
        "        assert lazy._hidden() == 3\n"
    ),
}


async def _reexport_callers(root: Any, symbol: str) -> dict[str, Any]:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _REEXPORT_PROJECT.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return await CodeGraphCallersTool(str(root)).execute(
        {"function_name": symbol, "include_bodies": False}
    )


@pytest.mark.asyncio
async def test_qualified_callers_follow_reexport_to_base_class_method(
    tmp_path: Any,
) -> None:
    # #1578：调用边解析到 pkg/__init__.py（Extractor 由包再导出），方法定义在基类
    # Mixin 中；限定名查询必须沿再导出与继承找到它，而不是回答 NOT_FOUND。
    result = await _reexport_callers(tmp_path, "Mixin._inherited")
    assert [(c["name"], c["file"]) for c in result["callers"]] == [
        ("test_inherited", "tests/test_use.py")
    ]


@pytest.mark.asyncio
async def test_unbound_edge_to_existing_symbol_is_never_complete_absence(
    tmp_path: Any,
) -> None:
    # #1578：符号存在、且有一条无法静态绑定的同名入边时，答案只能是 unknown。
    result = await _reexport_callers(tmp_path, "LazyBase._hidden")
    assert (result["verdict"], result["completeness"]) == ("NOT_FOUND", "unknown")


@pytest.mark.asyncio
async def test_existing_symbol_is_never_reported_missing_from_index(
    tmp_path: Any,
) -> None:
    # #1578：索引中有定义、确实无人调用的符号，不得被提示为 "not in the index"
    # 并建议重建索引；零调用方是关于调用边的事实。
    result = await _reexport_callers(tmp_path, "Mixin._unused")
    assert (result["completeness"], result["next_step"]) == (
        "complete",
        "'Mixin._unused' is defined in the index and no resolved call edge reaches it.",
    )
