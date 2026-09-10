"""跨请求刷新、请求内固定与派生数据隔离契约。"""

import sqlite3

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.generation_indexing import mutate_index_path
from tree_sitter_analyzer.cache.generation_reads import generation_read_scope
from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
from tree_sitter_analyzer.cache.generation_store import Superseded
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool


@pytest.mark.asyncio
async def test_warm_query_refreshes_at_next_invocation(tmp_path):
    from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import CodeGraphQueryTool

    source = tmp_path / "a.py"
    source.write_text("def original(): return 1\n", encoding="utf-8")
    builder = CodeGraphFullIndexTool(str(tmp_path))
    assert (await builder.execute({"mode": "full"}))["published"] is True
    query = CodeGraphQueryTool(str(tmp_path))
    try:
        first = await query.execute({"query": "search('original')"})
        assert [row["name"] for row in first["symbols"]] == ["original"]
        cache = query.get_cache()
        source.write_text("def replacement(): return 2\n", encoding="utf-8")
        assert (await builder.execute({"mode": "full"}))["published"] is True
        second = await query.execute({"query": "search('replacement')"})
        assert query.get_cache() is cache
        assert [row["name"] for row in second["symbols"]] == ["replacement"]
        assert (await query.execute({"query": "search('original')"}))["symbols"] == []
    finally:
        query.get_cache().close()


@pytest.mark.asyncio
async def test_one_scope_pins_readers_and_next_scope_refreshes(tmp_path):
    source = tmp_path / "a.py"
    source.write_text("def original(): return 1\n", encoding="utf-8")
    builder = CodeGraphFullIndexTool(str(tmp_path))
    assert (await builder.execute({"mode": "full"}))["published"] is True
    cache = ASTCache(str(tmp_path))
    try:
        with generation_read_scope():
            old_path = cache.db_path
            source.write_text("def replacement(): return 2\n", encoding="utf-8")
            assert (await builder.execute({"mode": "full"}))["published"] is True
            with generation_read_scope():
                assert cache.db_path == old_path
                assert [row["name"] for row in cache.get_functions()] == ["original"]
        with generation_read_scope():
            assert cache.db_path != old_path
            assert [row["name"] for row in cache.get_functions()] == ["replacement"]
    finally:
        cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["mcp", "cli"])
async def test_constraint_persistence_does_not_mutate_published_parent(tmp_path, entry):
    from tests.unit.mcp.tools._constraint_check_support import stage_minimal_constraints
    from tree_sitter_analyzer.cli.commands.constraint_check_command import (
        _evaluate_with_explicit_file,
    )
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    (tmp_path / "a.py").write_text("def original(): return 1\n", encoding="utf-8")
    stage_minimal_constraints(tmp_path)
    root = str(tmp_path)
    assert (await CodeGraphFullIndexTool(root).execute({"mode": "full"}))["published"]
    previous = resolve_index_path(root)
    with sqlite3.connect(previous.as_uri() + "?mode=ro", uri=True) as parent:
        before = tuple(parent.iterdump())
        if entry == "mcp":
            result = await ConstraintCheckTool(root).execute({"persist": True})
        else:
            result = _evaluate_with_explicit_file(
                project_root=root,
                constraint_file=str(tmp_path / "architectural-constraints.yml"),
                severity_min="warn",
                path_filter="",
                output_format="json",
                persist=True,
            )
        assert result["success"] is True
        assert resolve_index_path(root) != previous
        assert tuple(parent.iterdump()) == before
    with sqlite3.connect(resolve_index_path(root)) as current:
        assert current.execute(
            "SELECT count(*) FROM ast_constraint_violations"
        ).fetchone() == (0,)
    with pytest.raises(Superseded):
        mutate_index_path(root, previous, lambda path: pytest.fail("不得写入旧版本"))


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["missing", "malformed"])
async def test_stale_probe_tolerates_unknown_generation(tmp_path, damage):
    from tree_sitter_analyzer.cache.fingerprint import is_ast_index_stale
    from tree_sitter_analyzer.cache.generation_routing import generation_storage_path

    (tmp_path / "a.py").write_text("def original(): return 1\n", encoding="utf-8")
    root = str(tmp_path)
    assert (await CodeGraphFullIndexTool(root).execute({"mode": "full"}))["published"]
    selector = generation_storage_path(root) / "active.json"
    if damage == "missing":
        selector.unlink()
    else:
        selector.write_bytes(b"invalid")
    assert is_ast_index_stale(root) is False
