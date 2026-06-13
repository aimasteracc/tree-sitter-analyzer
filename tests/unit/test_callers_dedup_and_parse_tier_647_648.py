"""RED-first tests for issues #647 and #648.

#647 — SQL-tier dedup collapses same-named methods in one file
---------------------------------------------------------------
The dedup key ``(file, caller_name)`` drops the second row when two methods
with the same name (e.g. two ``execute`` overloads in the same file) are both
callers of a function.  Fix: extend the key with ``caller_line`` so each
distinct method definition produces its own listed row.

#648 — parse-tier _find_enclosing_func misattributes module-level calls
-----------------------------------------------------------------------
When a call site lives at module level (no enclosing function), the fallback
branch of ``_find_enclosing_func`` attributes the call to the NEAREST PRECEDING
function — producing a wrong-name edge.  The SQL tier already excludes these
sites (#638); the parse tier must mirror: return ``None`` from
``_find_enclosing_func`` when no function's range contains the call, and the
existing ``if caller_ref is None: continue`` in ``CallGraph.build`` will then
silently drop the spurious edge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CallGraph
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

# ---------------------------------------------------------------------------
# Shared fixture source — two same-named execute methods + one module-level call
# ---------------------------------------------------------------------------

_TWO_EXECUTE_SOURCE = """\
def fmt(resp):
    return resp


def helper_a():
    return 1


class SubscribeTool:
    def get_schema(self):
        return {}

    def execute(self):
        resp = helper_a()
        return fmt(resp)


class UnsubscribeTool:
    def get_schema(self):
        return {}

    def execute(self):
        return fmt({})


MODULE_DEFAULT = fmt({})
"""

# Load-bearing line numbers (1-indexed, matching _TWO_EXECUTE_SOURCE):
_FIRST_EXECUTE_DEF_LINE = 13  # SubscribeTool.execute
_SECOND_EXECUTE_DEF_LINE = 22  # UnsubscribeTool.execute
_MODULE_LEVEL_CALL_LINE = 26  # MODULE_DEFAULT = fmt({})


# ---------------------------------------------------------------------------
# #648 — parse-tier: no wrong-name edge from module-level call
# ---------------------------------------------------------------------------


class TestParseTierModuleLevelExclusion:
    """_find_enclosing_func must return None for module-level call sites.

    Before the fix the fallback branch picks the nearest PRECEDING function
    (UnsubscribeTool.execute@22 for the call at line 26) and emits a wrong
    edge — execute@22 appears to call fmt once more than it actually does.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> str:
        (tmp_path / "sample.py").write_text(
            _TWO_EXECUTE_SOURCE, encoding="utf-8", newline="\n"
        )
        return str(tmp_path)

    def test_call_edge_count_excludes_module_level_call(self, project: str) -> None:
        """The parse-tier should produce exactly 3 edges, not 4.

        Correct edges:
          execute@13 -> helper_a@5  (call at line 14)
          execute@13 -> fmt@1       (call at line 15)
          execute@22 -> fmt@1       (call at line 23)

        Wrong edge (bug):
          execute@22 -> fmt@1       (call at line 26 — module-level, no enclosing)
        """
        graph = CallGraph(project)
        graph.build()
        edge_count = len(graph._call_edges)
        assert edge_count == 3, (
            f"expected 3 call edges (module-level call excluded), got {edge_count}: "
            f"{[(c.name, e.name, ln) for c, e, ln in graph._call_edges]}"
        )

    def test_no_call_edge_at_module_level_line(self, project: str) -> None:
        """No call edge should be sourced from the module-level call line 26."""
        graph = CallGraph(project)
        graph.build()
        bad_edges = [
            (c.name, e.name, ln)
            for c, e, ln in graph._call_edges
            if ln == _MODULE_LEVEL_CALL_LINE
        ]
        assert bad_edges == [], (
            f"call at module-level line {_MODULE_LEVEL_CALL_LINE} produced edges: {bad_edges}"
        )

    def test_execute_22_has_exactly_one_fmt_callee(self, project: str) -> None:
        """UnsubscribeTool.execute calls fmt once (line 23); the module-level
        call must NOT inflate its callee list.
        """
        graph = CallGraph(project)
        graph.build()
        # Identify the execute@22 FunctionRef
        refs = [
            r
            for r in graph._functions
            if r.name == "execute" and r.start_line == _SECOND_EXECUTE_DEF_LINE
        ]
        assert len(refs) == 1, (
            f"expected exactly one execute@22 FunctionRef, got {refs}"
        )
        execute_22 = refs[0]
        callees = graph._callees.get(execute_22, [])
        fmt_callees = [c for c in callees if c.name == "fmt"]
        assert len(fmt_callees) == 1, (
            f"execute@22 should have exactly 1 fmt callee, got {len(fmt_callees)}: {[(c.name, c.start_line) for c in fmt_callees]}"
        )


# ---------------------------------------------------------------------------
# #647 — SQL-tier: two same-named methods produce two listed rows
# ---------------------------------------------------------------------------


@pytest.fixture
def indexed_project_647(tmp_path: Path) -> str:
    (tmp_path / "sample.py").write_text(
        _TWO_EXECUTE_SOURCE, encoding="utf-8", newline="\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


class TestSQLTierDedupKeepsBothMethods:
    """The SQL dedup key must include caller_line so same-named methods in
    one file are NOT collapsed to a single listed row.
    """

    @pytest.mark.asyncio
    async def test_two_execute_methods_produce_two_rows(
        self, indexed_project_647: str
    ) -> None:
        """Both execute methods are distinct callers of fmt — both must appear.

        Bug: key=(file, caller_name) keeps only the first-seen edge and
        silently drops the second execute@22 row.
        """
        tool = CodeGraphCallersTool(indexed_project_647)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        assert result.get("success") is True, f"tool errored: {result}"
        assert result.get("data_source") == "sql"

        rows = sorted(
            [
                (c["name"], c["line"])
                for c in result.get("callers", [])
                if c["file"].endswith("sample.py") and c["name"] == "execute"
            ],
            key=lambda t: t[1],
        )
        assert rows == [
            ("execute", _FIRST_EXECUTE_DEF_LINE),
            ("execute", _SECOND_EXECUTE_DEF_LINE),
        ], f"expected both execute methods listed, got {rows}"

    @pytest.mark.asyncio
    async def test_caller_count_reflects_both_methods(
        self, indexed_project_647: str
    ) -> None:
        """caller_count must be 2 (both execute methods), not 1 (collapsed)."""
        tool = CodeGraphCallersTool(indexed_project_647)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        assert result.get("caller_count") == 2, (
            f"caller_count should be 2 after dedup fix, got {result.get('caller_count')}"
        )

    @pytest.mark.asyncio
    async def test_no_ghost_rows_after_dedup_fix(
        self, indexed_project_647: str
    ) -> None:
        """After the dedup fix, no ghost rows (empty name or line=0) are emitted."""
        tool = CodeGraphCallersTool(indexed_project_647)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        ghost = [
            c
            for c in result.get("callers", [])
            if not c.get("name") or c.get("line") == 0
        ]
        assert ghost == [], f"ghost rows after dedup fix: {ghost}"

    @pytest.mark.asyncio
    async def test_module_level_call_still_counted_not_emitted(
        self, indexed_project_647: str
    ) -> None:
        """The module-level fmt() call is still excluded and counted (#638 invariant
        preserved after the dedup key change).
        """
        tool = CodeGraphCallersTool(indexed_project_647)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        assert result.get("unattributed_call_sites") == 1, (
            f"expected unattributed_call_sites=1, got {result.get('unattributed_call_sites')}"
        )
