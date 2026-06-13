"""RED-first tests for issue #638: ghost caller rows (name='', line=0).

Root cause (extraction tier): ``_extract_call_edges`` keyed its per-file
definition spans by bare function name.  Two same-named methods in different
classes (the hyphae_subscribe_tool.py shape: two ``execute`` methods) collide
— only the LAST span survives, so calls inside the EARLIER same-named method
find no containing span and are written as ``caller_name='' / caller_line=0``
edges.  ``nav action=callers`` then emits the un-navigable ghost row
``{name: '', line: 0}`` ranked first.

Same defect cloned in the parse tier: ``CallGraph.build`` collected
``file_funcs`` into a name-keyed dict before ``_find_enclosing_func``.

Query tier decision (#638): genuinely module-level call sites have no
enclosing function BY DESIGN (the edge writer maps them to a file node).
The callers tool must never emit them as ghost rows — it excludes them and
reports ``unattributed_call_sites: N`` so nothing is silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer._ast_extraction import _extract_call_edges
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CallGraph
from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

# ---------------------------------------------------------------------------
# Fixture source — minimal hyphae_subscribe_tool.py shape:
# two classes, each with a same-named method calling fmt(), plus one
# genuinely module-level call.  Line numbers are load-bearing.
# ---------------------------------------------------------------------------

_HYPHAE_SHAPE = """\
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

# Load-bearing line numbers in _HYPHAE_SHAPE:
_FIRST_EXECUTE_DEF_LINE = 13  # SubscribeTool.execute
_FIRST_EXECUTE_CALL_LINE = 15  # fmt(resp)
_SECOND_EXECUTE_DEF_LINE = 22  # UnsubscribeTool.execute
_SECOND_EXECUTE_CALL_LINE = 23  # fmt({})
_MODULE_LEVEL_CALL_LINE = 26  # MODULE_DEFAULT = fmt({})


def _parse(source: str, language: str = "python"):
    result = Parser().parse_code(source, language)
    assert result.success and result.tree is not None, (
        f"parse failed: {result.error_message}"
    )
    return result.tree


def _fmt_edges() -> list[dict]:
    tree = _parse(_HYPHAE_SHAPE)
    edges = _extract_call_edges(tree, _HYPHAE_SHAPE, "python", {"symbols": []})
    return [e for e in edges if e["callee_name"] == "fmt"]


# ---------------------------------------------------------------------------
# Unit: _extract_call_edges — duplicate-name spans must not collide
# ---------------------------------------------------------------------------


class TestDuplicateNameSpanAttribution:
    def test_exact_fmt_edge_count(self) -> None:
        assert len(_fmt_edges()) == 3

    def test_call_in_first_same_named_method_attributed(self) -> None:
        """fmt() at line 15 lives inside SubscribeTool.execute (def line 13).

        RED on the name-keyed dict: the second `execute` span overwrites the
        first, so this call had caller_name='' / caller_line=0 (the #638 ghost).
        """
        edge = next(
            e for e in _fmt_edges() if e["callee_line"] == _FIRST_EXECUTE_CALL_LINE
        )
        assert edge["caller_name"] == "execute", (
            f"expected caller=execute, got {edge['caller_name']!r} — "
            "call inside the FIRST same-named method lost its attribution"
        )
        assert edge["caller_line"] == _FIRST_EXECUTE_DEF_LINE

    def test_call_in_second_same_named_method_attributed(self) -> None:
        edge = next(
            e for e in _fmt_edges() if e["callee_line"] == _SECOND_EXECUTE_CALL_LINE
        )
        assert edge["caller_name"] == "execute"
        assert edge["caller_line"] == _SECOND_EXECUTE_DEF_LINE

    def test_module_level_call_unattributed_by_design(self) -> None:
        """Module-level fmt() at line 26 has no enclosing function.

        Pinned: the extraction layer keeps caller_name='' / caller_line=0 —
        the edge writer maps these to a file-level node; the QUERY layer is
        responsible for never surfacing them as ghost caller rows.
        """
        edge = next(
            e for e in _fmt_edges() if e["callee_line"] == _MODULE_LEVEL_CALL_LINE
        )
        assert edge["caller_name"] == ""
        assert edge["caller_line"] == 0


# ---------------------------------------------------------------------------
# Parse tier: CallGraph.build — same name-keyed collision
# ---------------------------------------------------------------------------


class TestCallGraphParseTierAttribution:
    @pytest.fixture
    def project(self, tmp_path: Path) -> str:
        (tmp_path / "sample.py").write_text(_HYPHAE_SHAPE, encoding="utf-8")
        return str(tmp_path)

    def test_fmt_callers_are_both_execute_methods(self, project: str) -> None:
        """Callers of fmt at the parse tier resolve to BOTH execute methods.

        RED before the fix: the call at line 15 fell back to the nearest
        preceding surviving span (helper_a) — a wrong-name attribution.
        """
        graph = CallGraph(project)
        callers = graph.callers_of("fmt")
        named = {(c["name"], c["line"]) for c in callers}
        assert ("execute", _FIRST_EXECUTE_DEF_LINE) in named, (
            f"SubscribeTool.execute missing from callers of fmt: {named}"
        )
        assert ("execute", _SECOND_EXECUTE_DEF_LINE) in named
        assert "helper_a" not in {c["name"] for c in callers}, (
            f"helper_a never calls fmt — wrong-name attribution: {named}"
        )


# ---------------------------------------------------------------------------
# Tool tier: CodeGraphCallersTool over a fresh index (SQL path)
# ---------------------------------------------------------------------------


@pytest.fixture
def indexed_project(tmp_path: Path) -> str:
    (tmp_path / "sample.py").write_text(_HYPHAE_SHAPE, encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


class TestCallersToolGhostRows:
    @pytest.mark.asyncio
    async def test_no_result_row_has_empty_name_or_line_zero(
        self, indexed_project: str
    ) -> None:
        """Structural pin (#638): a caller row is navigable or it is not a row."""
        tool = CodeGraphCallersTool(indexed_project)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        assert result.get("success") is True, f"tool errored: {result}"
        assert result.get("data_source") == "sql"
        ghost = [
            c
            for c in result.get("callers", [])
            if not c.get("name") or c.get("line") == 0
        ]
        assert ghost == [], f"ghost caller rows leaked to the response: {ghost}"

    @pytest.mark.asyncio
    async def test_real_call_sites_resolve_to_enclosing_methods(
        self, indexed_project: str
    ) -> None:
        """Both in-method call sites attribute to their own execute definition.

        After #647: the SQL dedup key includes caller_line so the two same-named
        methods (execute@13, execute@22) each produce their own listed row.
        caller_count is 2, not 1.
        """
        tool = CodeGraphCallersTool(indexed_project)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        rows = sorted(
            [
                (c["name"], c["line"])
                for c in result.get("callers", [])
                if c["file"].endswith("sample.py")
            ],
            key=lambda t: t[1],
        )
        assert rows == [
            ("execute", _FIRST_EXECUTE_DEF_LINE),
            ("execute", _SECOND_EXECUTE_DEF_LINE),
        ]
        assert result.get("caller_count") == 2

    @pytest.mark.asyncio
    async def test_module_level_call_counted_not_emitted(
        self, indexed_project: str
    ) -> None:
        """The module-level fmt() call is excluded with a counted note."""
        tool = CodeGraphCallersTool(indexed_project)
        result = await tool.execute({"function_name": "fmt", "output_format": "json"})
        assert result.get("unattributed_call_sites") == 1

    @pytest.mark.asyncio
    async def test_no_unattributed_key_when_all_attributed(
        self, indexed_project: str
    ) -> None:
        """helper_a is only called inside a method — no counted note emitted."""
        tool = CodeGraphCallersTool(indexed_project)
        result = await tool.execute(
            {"function_name": "helper_a", "output_format": "json"}
        )
        assert result.get("success") is True, f"tool errored: {result}"
        assert "unattributed_call_sites" not in result
