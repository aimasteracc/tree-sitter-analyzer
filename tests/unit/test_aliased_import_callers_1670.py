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
_API = (
    "from .core import reexported as public_name\n\n"
    '__all__ = ["public_name"]\n'
)
_MODS = "import pkg.core as cc\n\n\ndef via_module(node):\n    return cc.extract(node)\n"


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
    ) == (41, 41)
