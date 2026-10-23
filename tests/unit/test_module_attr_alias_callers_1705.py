"""#1705：经模块属性调用再导出的别名（``import pkg.hub as owner; owner._target()``）。

``hub`` 中 ``from .core import target as _target`` 把 ``target`` 改名绑定为模块属性；
别的文件经模块对象调用 ``owner._target()``。经公开的 ``nav callers``
（``CodeGraphCallersTool``）在已索引的夹具上验证：

* 模块属性调用解析到定义模块的真实符号（沿再导出与改名，最多 4 跳），调用方带
  ``resolution_kind: "import_alias"``；原名再导出（``owner.plain()``）同样解析；
* 函数内导入的同名模块别名按调用所在函数的导入区分（``owner`` 在两个函数里指向不同模块）；
* 反例：在 ``hub`` 中被重新绑定的属性、在调用文件里被赋值的属性仍只是“可能”的调用：
  不列为调用方，答复不是 ``complete``，调用点以别名列入证据。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CORE = (
    "def target(x):\n    return x\n\n\n"
    "def plain(x):\n    return x\n\n\n"
    "def rebound(x):\n    return x\n\n\n"
    "def patched(x):\n    return x\n"
)
_HUB = (
    "from .core import target as _target\n"
    "from .core import plain\n"
    "from .core import rebound as _rebound\n"
    "from .core import patched as _patched\n\n\n"
    "def local_use(x):\n"
    "    return _target(x)\n\n\n"
    "def _wrap(fn):\n"
    "    return fn\n\n\n"
    "_rebound = _wrap(_rebound)\n"
)
# 第 6 / 10 / 14 / 18 行是经模块属性的调用。
_USERS = (
    "import pkg.hub as owner\n"
    "import pkg.hub\n\n\n"
    "def via_alias_module(x):\n"
    "    return owner._target(x)\n\n\n"
    "def via_dotted_module(x):\n"
    "    return pkg.hub._target(x)\n\n\n"
    "def via_plain_reexport(x):\n"
    "    return owner.plain(x)\n\n\n"
    "def via_rebound(x):\n"
    "    return owner._rebound(x)\n"
)
_PATCHER = (
    "import pkg.hub as owner\n\n\n"
    "def via_patched(x):\n"
    "    owner._patched = lambda y: y\n"
    "    return owner._patched(x)\n"
)
_OTHER = "def _target(x):\n    return -x\n"
_SCOPED = (
    "def uses_other():\n"
    "    import pkg.other as owner\n"
    "    return owner._target(1)\n\n\n"
    "def uses_hub():\n"
    "    import pkg.hub as owner\n"
    "    return owner._target(2)\n"
)


@pytest.fixture
async def module_attr_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    files = {
        "__init__.py": "",
        "core.py": _CORE,
        "hub.py": _HUB,
        "users.py": _USERS,
        "patcher.py": _PATCHER,
        "other.py": _OTHER,
        "scoped.py": _SCOPED,
    }
    for name, text in files.items():
        (pkg / name).write_text(text, encoding="utf-8")
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


def _sites(result: dict) -> set[tuple[str, int]]:
    return {(s["file"], s["line"]) for s in result["non_call_reference_sites"] or []}


@pytest.mark.asyncio
async def test_module_attribute_alias_calls_resolve_to_the_definition(
    module_attr_root: str,
) -> None:
    result = await _callers(module_attr_root, "target")

    entries = _entries(result)
    assert {name: e["file"] for name, e in entries.items()} == {
        "local_use": "pkg/hub.py",
        "via_alias_module": "pkg/users.py",
        "via_dotted_module": "pkg/users.py",
        "uses_hub": "pkg/scoped.py",
    }
    assert {
        name: (e.get("resolution_kind"), e.get("import_alias"))
        for name, e in entries.items()
        if name != "local_use"
    } == {
        "via_alias_module": ("import_alias", "_target"),
        "via_dotted_module": ("import_alias", "_target"),
        "uses_hub": ("import_alias", "_target"),
    }


@pytest.mark.asyncio
async def test_module_attribute_reexport_keeps_the_answer_open(
    module_attr_root: str,
) -> None:
    result = await _callers(module_attr_root, "target")

    # `hub._target` 被别的模块经属性使用：别名是再导出，导入行仍是引用。
    assert result["completeness"] == "incomplete"
    assert "NON_CALL_REFERENCES" in result["completeness_reasons"]
    assert ("pkg/hub.py", 1) in _sites(result)


@pytest.mark.asyncio
async def test_plain_reexport_through_a_module_attribute(
    module_attr_root: str,
) -> None:
    result = await _callers(module_attr_root, "plain")

    assert {name: e["file"] for name, e in _entries(result).items()} == {
        "via_plain_reexport": "pkg/users.py"
    }


@pytest.mark.asyncio
async def test_rebound_module_attribute_stays_possible(module_attr_root: str) -> None:
    result = await _callers(module_attr_root, "rebound")

    # `hub` 重新绑定了 `_rebound`：`owner._rebound()` 不一定调用 `rebound`。
    assert "via_rebound" not in _entries(result)
    assert result["completeness"] != "complete"
    assert ("pkg/users.py", 18) in _sites(result)


@pytest.mark.asyncio
async def test_attribute_assigned_in_the_calling_file_stays_possible(
    module_attr_root: str,
) -> None:
    result = await _callers(module_attr_root, "patched")

    assert "via_patched" not in _entries(result)
    assert result["completeness"] != "complete"
    assert ("pkg/patcher.py", 6) in _sites(result)


@pytest.mark.asyncio
async def test_graph_consumers_see_module_attribute_alias_callers(
    module_attr_root: str,
) -> None:
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = CodeGraphCallersTool(module_attr_root)._try_get_cache()
    graph = CachedCallGraph(module_attr_root, cache=cache, fallback=False)

    callers = graph.callers_of("target", "pkg/core.py")

    assert sorted(c["name"] for c in callers) == [
        "local_use",
        "uses_hub",
        "via_alias_module",
        "via_dotted_module",
    ]


def test_extractor_version_is_bumped_for_module_attribute_aliases() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (51, 51)


def _context(tmp_path: Path, imports: list, files: dict[str, str]):
    from tree_sitter_analyzer.synapse_resolver._context import ResolverContext

    for rel_path, text in files.items():
        (tmp_path / rel_path).write_text(text, encoding="utf-8")
    by_file: dict[str, list] = {}
    for entry in imports:
        by_file.setdefault(entry.file_path, []).append(entry)
    return ResolverContext(
        str(tmp_path),
        None,
        imports_by_file=by_file,
        name_to_source={"hub.py": {"_f": "core.py"}},
        file_symbols={"core.py": [("f", "function", 7)]},
        module_to_file={"hub": "hub.py", "other": "other.py", "core": "core.py"},
    )


def test_module_attribute_resolution_declines_when_unsure(tmp_path: Path) -> None:
    from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry
    from tree_sitter_analyzer.synapse_resolver._module_attrs import (
        resolve_module_attribute,
    )

    hub_alias = ImportEntry("hub.py", "python", ".core", "_f", True, False, "f", 1)
    as_owner = ImportEntry("u.py", "python", "hub", "owner", False, False, "hub", 1)
    other = ImportEntry("u.py", "python", "other", "owner", False, False, "other", 9)
    ctx = _context(
        tmp_path, [hub_alias, as_owner], {"hub.py": "", "u.py": "owner._f(1)\n"}
    )

    assert resolve_module_attribute("owner._f", "u.py", 3, 4, ctx) == (
        7,
        "core.py",
        {"local": "_f", "name": "f", "line": 1, "module": "hub.py"},
    )
    # 接收者不是点分名、是实例，或名字不是标识符：不解析。
    for callee in ("_f", "self._f", "x()._f", "owner.1"):
        assert resolve_module_attribute(callee, "u.py", 3, 4, ctx) is None
    # 模块里没有这个名字的导入绑定。
    assert resolve_module_attribute("owner._g", "u.py", 3, 4, ctx) is None
    # 同一别名绑定到两个模块、调用所在函数内也没有导入：不解析。
    ambiguous = _context(
        tmp_path, [hub_alias, as_owner, other], {"hub.py": "", "u.py": ""}
    )
    assert resolve_module_attribute("owner._f", "u.py", 3, 4, ambiguous) is None
    assert resolve_module_attribute("owner._f", "u.py", 8, 10, ambiguous) is None
    # 读不到模块源码按“已重新绑定”处理。
    missing = _context(tmp_path, [hub_alias, as_owner], {})
    (tmp_path / "hub.py").unlink()
    assert resolve_module_attribute("owner._f", "u.py", 3, 4, missing) is None


def test_rebinding_patterns() -> None:
    from tree_sitter_analyzer.synapse_resolver import _module_attrs as attrs

    class _Ctx:
        def __init__(self, text: str) -> None:
            self.text_memo = {"m.py": text}

    def rebound(text: str) -> bool:
        return attrs._rebound_in_module(_Ctx(text), "m.py", "_f")  # type: ignore[arg-type]

    def assigned(text: str) -> bool:
        return attrs._assigned_in_caller(_Ctx(text), "m.py", "_f")  # type: ignore[arg-type]

    assert rebound("_f = wrap(_f)\n")
    assert rebound("_f: Callable = other\n")
    assert rebound("a, _f = pair\n")
    assert rebound("def g():\n    global _f\n")
    assert rebound("del _f\n")
    assert not rebound("x = _f(1)\nif _f == y:\n    pass\n")
    assert assigned("owner._f = fake\n")
    assert assigned('monkeypatch.setattr(owner, "_f", fake)\n')
    assert assigned("del owner._f\n")
    assert not assigned("owner._f(1)\nowner._f == x\n")
