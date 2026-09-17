"""无外部搜索程序时，意图别名仍通过真实索引调用公开门面。"""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


@pytest.fixture
def server(tmp_path, monkeypatch):
    import subprocess

    path = tmp_path / "example.py"
    path.write_text(
        "def example_function():\n    return 1\n\nclass ExampleClass:\n    pass\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(path))
    finally:
        cache.close()
    instance = TreeSitterAnalyzerMCPServer()
    instance.set_project_path(str(tmp_path))
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: pytest.fail("意图检索不得启动外部程序")
    )
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["locate_usage", "find_usage"])
async def test_symbol_alias_matches_public_search(server, alias):
    arguments = {"action": "symbol", "query": "example_function", "limit": 1}
    actual = await server.call_tool(alias, arguments=arguments)
    expected = await server.call_tool("search", arguments=arguments)
    assert actual["success"] is True
    assert actual["results"] == expected["results"]
    assert [m["name"] for m in actual["results"]] == ["example_function"]


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["map_structure", "discover_files"])
async def test_structure_alias_matches_public_sitemap(server, alias):
    arguments = {"mode": "flat", "language": "python"}
    actual = await server.call_tool(alias, arguments=arguments)
    expected = await server.call_tool(
        "structure", arguments={"action": "sitemap", **arguments}
    )
    assert actual["success"] is True
    assert actual["file_count"] == 1
    assert actual["symbols_by_kind"] == expected["symbols_by_kind"]


@pytest.mark.asyncio
async def test_unknown_alias_raises_error(server):
    with pytest.raises(ValueError, match="Unknown tool"):
        await server.call_tool("invalid_alias_name", arguments={})


@pytest.mark.asyncio
async def test_alias_requires_action(server):
    result = await server.call_tool("locate_usage", arguments={})
    assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["content", "grep", "batch"])
async def test_retired_search_action_is_rejected(server, action):
    result = await server.call_tool("locate_usage", arguments={"action": action})
    assert result["success"] is False
    assert action not in result["available_actions"]


@pytest.mark.asyncio
async def test_extract_structure_alias_calls_analyze_code_structure(server, tmp_path):
    # 2026-09-09：检索接口迁移不能删除未退役的结构分析别名职责。
    result = await server.call_tool(
        "extract_structure",
        arguments={"file_path": str(tmp_path / "example.py"), "output_format": "json"},
    )
    assert result["success"] is True
    assert "format_type" in result
    assert "example_function" in str(result)
    assert "ExampleClass" in str(result)
