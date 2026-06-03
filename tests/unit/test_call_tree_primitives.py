#!/usr/bin/env python3
"""Tests for the tree primitives: callee_tree / caller_tree.

These primitives return a depth-limited *nested* tree in ONE call so an agent
does not have to iterate ``codegraph_callees`` BFS-style. Mirrors mycelium
RFC-0020 (callee tree) / RFC-0021 (caller tree).

The pure tree-builder (``build_call_tree``) is tested without any DB so the
traversal contract (depth limit, node cap, cycle guard, node shape) is pinned
deterministically. The MCP tool tests use a tiny on-disk fixture project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools._call_tree import build_call_tree

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


# ---------------------------------------------------------------------------
# Pure tree-builder contract (no DB)
# ---------------------------------------------------------------------------


def _graph_expander(graph: dict[str, list[dict]]):
    """Return an expand(name, file) callback backed by an in-memory dict."""

    def expand(name: str, _file: str | None) -> list[dict]:
        return graph.get(name, [])

    return expand


class TestBuildCallTree:
    def test_direct_children_appear_at_level_one(self) -> None:
        graph = {
            "main": [{"name": "a", "file": "f.py", "line": 10}],
            "a": [],
        }
        tree = build_call_tree("main", None, _graph_expander(graph), max_depth=3)
        assert tree["root"]["name"] == "main"
        children = tree["root"]["children"]
        assert len(children) == 1
        assert children[0]["name"] == "a"
        assert children[0]["file"] == "f.py"
        assert children[0]["line"] == 10

    def test_transitive_children_appear_at_depth_two(self) -> None:
        graph = {
            "main": [{"name": "a", "file": "f.py", "line": 10}],
            "a": [{"name": "b", "file": "g.py", "line": 20}],
            "b": [],
        }
        tree = build_call_tree("main", None, _graph_expander(graph), max_depth=3)
        a = tree["root"]["children"][0]
        assert a["children"][0]["name"] == "b"

    def test_max_depth_limits_traversal(self) -> None:
        graph = {
            "main": [{"name": "a", "file": "f.py", "line": 10}],
            "a": [{"name": "b", "file": "g.py", "line": 20}],
            "b": [{"name": "c", "file": "h.py", "line": 30}],
        }
        # max_depth=1 → only direct children, no grandchildren expanded.
        tree = build_call_tree("main", None, _graph_expander(graph), max_depth=1)
        a = tree["root"]["children"][0]
        assert a["name"] == "a"
        assert a["children"] == []

    def test_cycle_produces_leaf_not_infinite_recursion(self) -> None:
        graph = {
            "a": [{"name": "b", "file": "f.py", "line": 1}],
            "b": [{"name": "a", "file": "g.py", "line": 2}],
        }
        tree = build_call_tree("a", None, _graph_expander(graph), max_depth=10)
        # a -> b -> (a already on path) -> leaf
        b = tree["root"]["children"][0]
        assert b["name"] == "b"
        a_again = b["children"][0]
        assert a_again["name"] == "a"
        assert a_again["children"] == []  # cycle broken: leaf

    def test_node_cap_truncates_and_flags(self) -> None:
        # A fan-out wider than the cap must stop and report truncation.
        wide = [{"name": f"child{i}", "file": "f.py", "line": i} for i in range(50)]
        graph = {"root": wide}
        tree = build_call_tree(
            "root", None, _graph_expander(graph), max_depth=3, max_nodes=10
        )
        assert tree["truncated"] is True
        assert tree["node_count"] <= 10

    def test_no_truncation_flag_when_under_cap(self) -> None:
        graph = {"root": [{"name": "a", "file": "f.py", "line": 1}], "a": []}
        tree = build_call_tree(
            "root", None, _graph_expander(graph), max_depth=3, max_nodes=150
        )
        assert tree["truncated"] is False

    def test_node_shape_has_name_file_line_children(self) -> None:
        graph = {"root": [{"name": "a", "file": "f.py", "line": 7}], "a": []}
        tree = build_call_tree("root", None, _graph_expander(graph), max_depth=2)
        node = tree["root"]["children"][0]
        assert set(node) >= {"name", "file", "line", "children"}


# ---------------------------------------------------------------------------
# MCP tool contract
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_project_root(tmp_path):
    """foo -> bar -> baz chain so the tree has real depth."""
    (tmp_path / "sample.py").write_text(
        "def foo():\n    bar()\n\ndef bar():\n    baz()\n\ndef baz():\n    return 1\n",
        encoding="utf-8",
    )
    return str(tmp_path)


class TestCalleeTreeTool:
    @pytest.mark.asyncio
    async def test_returns_nested_tree_one_call(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCalleeTreeTool,
        )

        tool = CodeGraphCalleeTreeTool(chain_project_root)
        result = await tool.execute(
            {"symbol": "foo", "max_depth": 3, "output_format": "json"}
        )
        assert result["success"] is True
        root = result["tree"]["root"]
        assert root["name"] == "foo"
        # foo -> bar present as a direct child.
        bar = next((c for c in root["children"] if c["name"] == "bar"), None)
        assert bar is not None
        # bar -> baz present at depth 2 (the whole point: one call, full tree).
        baz = next((c for c in bar["children"] if c["name"] == "baz"), None)
        assert baz is not None

    @pytest.mark.asyncio
    async def test_deterrent_next_step(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCalleeTreeTool,
        )

        tool = CodeGraphCalleeTreeTool(chain_project_root)
        result = await tool.execute(
            {"symbol": "foo", "max_depth": 3, "output_format": "json"}
        )
        assert "next_step" in result
        # Discourages further per-node iteration / Read.
        assert "no further" in result["next_step"].lower()

    @pytest.mark.asyncio
    async def test_symbol_required(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCalleeTreeTool,
        )

        tool = CodeGraphCalleeTreeTool(chain_project_root)
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})

    @pytest.mark.asyncio
    async def test_toon_format(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCalleeTreeTool,
        )

        tool = CodeGraphCalleeTreeTool(chain_project_root)
        result = await tool.execute({"symbol": "foo", "output_format": "toon"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCalleeTreeTool,
        )

        tool = CodeGraphCalleeTreeTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await tool.execute({"symbol": "foo"})


class TestCallerTreeTool:
    @pytest.mark.asyncio
    async def test_returns_nested_caller_tree(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCallerTreeTool,
        )

        tool = CodeGraphCallerTreeTool(chain_project_root)
        result = await tool.execute(
            {"symbol": "baz", "max_depth": 3, "output_format": "json"}
        )
        assert result["success"] is True
        root = result["tree"]["root"]
        assert root["name"] == "baz"
        # baz is called by bar (direct caller).
        bar = next((c for c in root["children"] if c["name"] == "bar"), None)
        assert bar is not None
        # bar is called by foo (transitive caller, depth 2).
        foo = next((c for c in bar["children"] if c["name"] == "foo"), None)
        assert foo is not None

    @pytest.mark.asyncio
    async def test_symbol_required(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools._call_tree_tool import (
            CodeGraphCallerTreeTool,
        )

        tool = CodeGraphCallerTreeTool(chain_project_root)
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})


class TestNavFacadeTreeActions:
    @pytest.mark.asyncio
    async def test_callee_tree_action(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

        facade = build_nav_facade(chain_project_root)
        result = await facade.execute(
            {
                "action": "callee_tree",
                "symbol": "foo",
                "max_depth": 3,
                "output_format": "json",
            }
        )
        assert result["tree"]["root"]["name"] == "foo"

    @pytest.mark.asyncio
    async def test_caller_tree_action(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

        facade = build_nav_facade(chain_project_root)
        result = await facade.execute(
            {
                "action": "caller_tree",
                "symbol": "baz",
                "max_depth": 3,
                "output_format": "json",
            }
        )
        assert result["tree"]["root"]["name"] == "baz"

    def test_facade_exposes_tree_actions_in_enum(self, chain_project_root) -> None:
        from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

        facade = build_nav_facade(chain_project_root)
        defn = facade.get_tool_definition()
        enum = defn["inputSchema"]["properties"]["action"]["enum"]
        assert "callee_tree" in enum
        assert "caller_tree" in enum
