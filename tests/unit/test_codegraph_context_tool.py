"""Focused tests for codegraph_context."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache


@pytest.fixture
def indexed_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return {'id': user_id}\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    return svc.get_user(1)\n",
        encoding="utf-8",
    )
    (project / "routes.py").write_text(
        "from app import handle_request\n"
        "\n"
        "def dispatch(request):\n"
        "    return handle_request(request)\n",
        encoding="utf-8",
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=20)
    cache.close()
    return project


def test_codegraph_context_registered() -> None:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _, lookup = create_tool_registry(project_root=None)
    assert "codegraph_context" in lookup


def test_extract_symbol_candidates_handles_identifiers() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    candidates = _extract_symbol_candidates(
        "trace `UserService.get_user` through handle_request"
    )

    assert "UserService" in candidates
    assert "get_user" in candidates
    assert "handle_request" in candidates
    assert "trace" not in candidates


def test_schema_requires_task() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool()
    with pytest.raises(ValueError, match="task"):
        tool.validate_arguments({})


@pytest.mark.asyncio
async def test_context_returns_entry_points_graph_and_source(
    indexed_project: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["verdict"] == "INFO"
    assert result["entry_points"]
    assert result["nodes"]
    assert result["stats"]["nodes"] == len(result["nodes"])
    assert result["code_blocks"]
    names = {node["name"] for node in result["nodes"]}
    assert {"handle_request", "UserService"} & names
    assert any("handle_request" in block["content"] for block in result["code_blocks"])


@pytest.mark.asyncio
async def test_context_not_found_is_a_successful_stop_signal(
    indexed_project: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {"task": "XyzNeverDefinedFlow", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["verdict"] == "NOT_FOUND"
    assert result["entry_points"] == []
    assert "codegraph_symbol_search" in result["agent_summary"]["next_step"]
