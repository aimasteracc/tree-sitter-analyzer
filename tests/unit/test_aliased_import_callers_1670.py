"""#1670：经改名导入调用的函数（``from m import f as _f; _f()``）必须列出其调用方。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证：
改名导入的调用解析到真实目标并带上来源；被调用的别名的导入行不再单独让答复停在
``unknown``；但再导出的别名、也被当作回调传递的别名仍是引用，答复不得是 ``complete``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CORE = (
    "def extract(node):\n"
    "    return node\n\n\n"
    "def reexported(node):\n"
    "    return node\n\n\n"
    "def callback_target(node):\n"
    "    return node\n\n\n"
    "def direct(node):\n"
    "    return node\n\n\n"
    "def chained(node):\n"
    "    return node\n"
)
_USER = (
    "from .core import extract as _extract\n"
    "from .core import callback_target as _cb\n"
    "from pkg.core import direct\n\n\n"
    "def use(node):\n"
    "    return _extract(node)\n\n\n"
    "def use_twice(node):\n"
    "    return _extract(_extract(node))\n\n\n"
    "def register(hooks):\n"
    "    hooks.append(_cb)\n"
    "    return _cb(1)\n\n\n"
    "def plain(node):\n"
    "    return direct(node)\n"
)
_API = 'from .core import reexported as public_name\n\n__all__ = ["public_name"]\n'
_MODS = (
    "import pkg.core as cc\n\n\ndef via_module(node):\n    return cc.extract(node)\n"
)
# 改名后再以原样导入：`hub` 把 `chained` 改名为 `_chained`，`hub_user` 导入 `_chained`。
_HUB = "from .core import chained as _chained\n"
_HUB_USER = (
    "from .hub import _chained\n\n\ndef via_hub(node):\n    return _chained(node)\n"
)


@pytest.fixture
async def alias_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text(_CORE, encoding="utf-8")
    (pkg / "user.py").write_text(_USER, encoding="utf-8")
    (pkg / "api.py").write_text(_API, encoding="utf-8")
    (pkg / "mods.py").write_text(_MODS, encoding="utf-8")
    (pkg / "hub.py").write_text(_HUB, encoding="utf-8")
    (pkg / "hub_user.py").write_text(_HUB_USER, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": "pkg/core.py", "include_bodies": False}
    )


def _entries(result: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in result["callers"]}


@pytest.mark.asyncio
async def test_alias_calls_resolve_to_the_real_target(alias_root: str) -> None:
    result = await _callers(alias_root, "extract")

    entries = _entries(result)
    assert {name: (e["file"], e["line"]) for name, e in entries.items()} == {
        "use": ("pkg/user.py", 6),
        "use_twice": ("pkg/user.py", 10),
        "via_module": ("pkg/mods.py", 4),
    }
    assert {name: e.get("import_alias") for name, e in entries.items()} == {
        "use": "_extract",
        "use_twice": "_extract",
        "via_module": None,
    }
    assert entries["use"]["resolution_kind"] == "import_alias"


@pytest.mark.asyncio
async def test_called_alias_import_line_does_not_block_complete(
    alias_root: str,
) -> None:
    result = await _callers(alias_root, "extract")

    assert (result["completeness"], result["completeness_reasons"]) == (
        "complete",
        [],
    )


@pytest.mark.asyncio
async def test_reexported_alias_stays_a_reference(alias_root: str) -> None:
    result = await _callers(alias_root, "reexported")

    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert {(s["file"], s["line"]) for s in result["non_call_reference_sites"]} == {
        ("pkg/api.py", 1),
    }


@pytest.mark.asyncio
async def test_alias_also_passed_as_callback_stays_incomplete(
    alias_root: str,
) -> None:
    result = await _callers(alias_root, "callback_target")

    assert set(_entries(result)) == {"register"}
    assert result["completeness"] == "incomplete"
    assert "NON_CALL_REFERENCES" in result["completeness_reasons"]
    # 回调传递的位置以别名点名，而不只是导入行。
    assert ("pkg/user.py", 15) in {
        (s["file"], s["line"]) for s in result["non_call_reference_sites"]
    }


@pytest.mark.asyncio
async def test_graph_consumers_see_alias_callers(alias_root: str) -> None:
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = CodeGraphCallersTool(alias_root)._try_get_cache()
    graph = CachedCallGraph(alias_root, cache=cache, fallback=False)

    callers = graph.callers_of("extract", "pkg/core.py")

    assert sorted(c["name"] for c in callers) == ["use", "use_twice", "via_module"]


@pytest.mark.asyncio
async def test_renamed_reexport_imported_under_its_alias(alias_root: str) -> None:
    result = await _callers(alias_root, "chained")

    entries = _entries(result)
    assert {
        name: (e["file"], e.get("import_alias")) for name, e in entries.items()
    } == {"via_hub": ("pkg/hub_user.py", "_chained")}
    # `hub` 的 `_chained` 被别的模块导入（再导出）：导入行仍是引用。
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_plain_import_control_is_unchanged(alias_root: str) -> None:
    result = await _callers(alias_root, "direct")

    assert set(_entries(result)) == {"plain"}
    assert "import_alias" not in _entries(result)["plain"]
    assert result["completeness"] == "complete"


def test_extractor_version_is_bumped_for_alias_resolution() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (50, 50)


def test_import_binding_masks_only_accounted_aliases() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_import_bindings import (
        alias_bindings,
        mask_import_bindings,
    )

    text = (
        "from m import f as _f, g\n"
        "from m import f as f\n"
        "from n import (\n    f as _other,\n)\n"
    )

    assert [alias for alias, _start, _end in alias_bindings(text, "f")] == [
        "_f",
        "_other",
    ]
    masked = mask_import_bindings(text, "f", frozenset({"_f"}))
    assert masked.splitlines()[0] == "from m import   as _f, g"
    # `f as f` 是显式再导出，未列入的别名也保留。
    assert masked.splitlines()[1:] == text.splitlines()[1:]
    assert mask_import_bindings(text, "absent") == text


def test_alias_provenance_helpers() -> None:
    import sqlite3

    from tree_sitter_analyzer.graph.alias_edges import alias_call_rows, import_alias_of
    from tree_sitter_analyzer.mcp.tools.callers_alias_refs import _alias_name
    from tree_sitter_analyzer.mcp.tools.callers_annotated import alias_provenance

    class _Edge:
        metadata = {"import_alias": {"local": "_f", "name": "f", "line": 1}}

    assert alias_provenance("_f") == {
        "resolution_kind": "import_alias",
        "import_alias": "_f",
    }
    assert alias_provenance(None) == {}
    assert import_alias_of(_Edge()) == "_f"
    assert import_alias_of(object()) is None
    conn = sqlite3.connect(":memory:")
    assert alias_call_rows(conn, "f") == []
    assert alias_call_rows(conn, "a.f") == []
    assert _alias_name('{"import_alias": {"name": "f"}}') == "f"
    assert _alias_name("import_alias not json") is None
    assert _alias_name(None) is None


def _alias_store():
    import sqlite3

    from tree_sitter_analyzer.graph.edge_store import Edge, EdgeKind, EdgeStore

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_imports (file_path TEXT, language TEXT, module_path TEXT, "
        "local_name TEXT, is_relative INTEGER, is_star INTEGER, alias_of TEXT, "
        "line INTEGER)"
    )
    conn.execute(
        "INSERT INTO ast_imports VALUES ('u.py', 'python', '.core', '_f', 1, 0, 'f', 1)"
    )
    store = EdgeStore(conn)

    def call(caller_line: int, alias: dict | None, full: str = "_f") -> Edge:
        meta = {
            "callee_full": full,
            "callee_resolution": "project",
            "callee_resolved_file": "core.py",
        }
        if alias is not None:
            meta["import_alias"] = alias
        return Edge(
            f"u.py:use{caller_line}:{caller_line}",
            f"u.py:_f:{caller_line + 1}",
            EdgeKind.CALLS,
            caller_line + 1,
            metadata=meta,
        )

    store.upsert_edges(
        [
            call(1, {"local": "_f", "name": "f", "line": 1}),
            call(3, {"local": "_f", "name": "other", "line": 1}),
            call(5, None),
        ]
    )
    return conn, store


def test_alias_rows_need_persisted_provenance_for_the_target() -> None:
    from tree_sitter_analyzer.graph.alias_edges import _row_alias, alias_call_rows
    from tree_sitter_analyzer.graph.edge_store import Edge, EdgeKind

    conn, store = _alias_store()

    rows = alias_call_rows(conn, "f")
    assert [row["caller_line"] for row in rows] == [1]
    callers = store.query_callers("f", "core.py")
    assert [(c["caller_name"], c.get("import_alias")) for c in callers] == [
        ("use1", "_f")
    ]
    # 限定名查询：同名而接收者不同的边被跳过，改名导入的边只按目标真实名字匹配。
    store.upsert_edges(
        [
            Edge(
                "u.py:other:9",
                "u.py:f:10",
                EdgeKind.CALLS,
                10,
                metadata={"callee_full": "b.f", "callee_resolution": "unknown"},
            )
        ]
    )
    assert store.query_callers("a.f") == []
    assert _row_alias({}) is None
    assert _row_alias({"metadata": "import_alias but not json"}) is None
    assert _row_alias({"metadata": '{"import_alias": "flat"}'}) is None


def test_alias_reference_check_is_conservative_on_failures() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_alias_refs import (
        _binds_own,
        _bound_alias_call_lines,
        _reexport_sites,
    )
    from tree_sitter_analyzer.mcp.tools.callers_import_bindings import alias_bindings

    class _Broken:
        def get_conn(self):
            raise AttributeError("no index")

    class _Cache:
        def __init__(self, conn):
            self._conn = conn

        def get_conn(self):
            return self._conn

    conn, _store = _alias_store()
    assert _bound_alias_call_lines(_Broken(), "u.py", "_f", "f", {"core.py"}) is None
    # 读不到再导出证据即不跳过导入行（#1709 起返回 None）。
    assert _reexport_sites(_Broken(), "u.py", "_f", "f") is None
    assert _binds_own(_Broken(), "u.py", "_f") is None
    # 解析到别的文件、或来源指向别的名字的别名调用不算核对过的使用。
    assert _bound_alias_call_lines(_Cache(conn), "u.py", "_f", "f", {"x.py"}) == (
        frozenset()
    )
    assert _bound_alias_call_lines(_Cache(conn), "u.py", "_f", "f", {"core.py"}) == (
        frozenset({2})
    )
    assert alias_bindings("import os\n", "f") == []


def test_alias_and_binding_metadata_are_written_independently() -> None:
    import json

    from tree_sitter_analyzer.cache.synapse import _update_params
    from tree_sitter_analyzer.synapse_resolver import ResolvedCallee

    row = {"id": 9, "metadata": '{"callee_full": "_f"}'}
    aliased = _update_params(
        ResolvedCallee(3, "project", "core.py", alias={"local": "_f", "name": "f"}),
        row,
    )
    bound = _update_params(
        ResolvedCallee(4, "annotated_receiver", "s.py", binding={"line": 2}), row
    )

    assert json.loads(aliased[3])["import_alias"] == {"local": "_f", "name": "f"}
    assert "receiver_binding" not in json.loads(aliased[3])
    assert "import_alias" not in json.loads(bound[3])


def test_alias_resolution_falls_back_without_a_definition() -> None:
    from tree_sitter_analyzer.synapse_resolver import _reexported_or
    from tree_sitter_analyzer.synapse_resolver._aliases import resolve_import_alias
    from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
    from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

    entry = ImportEntry("u.py", "python", ".core", "_f", True, False, "f", 1)
    no_target = ResolverContext(
        "/repo", None, imports_by_file={"u.py": [entry]}, name_to_source={}
    )
    no_definition = ResolverContext(
        "/repo",
        None,
        imports_by_file={"u.py": [entry]},
        name_to_source={"u.py": {"_f": "core.py"}},
        file_symbols={"core.py": []},
    )

    assert resolve_import_alias("_f", "u.py", no_target) is None
    # 名字来自星号导入的展开（没有导入行）：不当作改名。
    starred = ResolverContext(
        "/repo", None, imports_by_file={}, name_to_source={"u.py": {"g": "core.py"}}
    )
    assert resolve_import_alias("g", "u.py", starred) is None
    assert resolve_import_alias("_f", "u.py", no_definition) is None
    kept = _reexported_or("f", "", "u.py", no_definition, None, "core.py")
    assert (kept.resolved_file, kept.callee_symbol_id) == ("core.py", None)
