"""#1765：类表达式里的 ``this.m()``，以及继承来的 ``this.m()``，不得被丢掉或误绑。

ts1 dogfood（hono ``prepared-router.ts:98-101``）::

    const RegExpRouterWithMatcherExport = class<T> extends RegExpRouter<T> {
      buildAndExportAllMatchers() { return this.buildAllMatchers() }
    }

同一文件还有 ``PreparedRegExpRouter.buildAllMatchers``。Synapse 按“文件里只有一个
类定义了它”把 ``this.buildAllMatchers()`` 绑定为那个方法的调用；真正的目标
``RegExpRouter.buildAllMatchers`` 看不到这个调用点——命名的 ``class Sub extends
RegExpRouter`` 同样如此，只有一个调用点时答 ``complete, 0``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_ROUTER = (
    "export class RegExpRouter<T> {\n"
    "  protected buildAllMatchers(): number { return 1 }\n"
    "  match() { return this.buildAllMatchers() }\n"
    "}\n"
)
_PREPARED = (
    "import { RegExpRouter } from './router'\n"
    "export class PreparedRegExpRouter<T> {\n"
    "  protected buildAllMatchers(): number { return 2 }\n"
    "  own() { return this.buildAllMatchers() }\n"
    "}\n"
    "export const buildInitParams = () => {\n"
    "  const RegExpRouterWithMatcherExport = class<T> extends RegExpRouter<T> {\n"
    "    buildAndExportAllMatchers() {\n"
    "      return this.buildAllMatchers()\n"
    "    }\n"
    "  }\n"
    "  return new RegExpRouterWithMatcherExport()\n"
    "}\n"
)
_NAMED = (
    "import { RegExpRouter } from './router'\n"
    "export class Named<T> extends RegExpRouter<T> {\n"
    "  exportAll() { return this.buildAllMatchers() }\n"
    "}\n"
    "export class Sibling {\n"
    "  buildAllMatchers() { return 3 }\n"
    "}\n"
)


@pytest.fixture
async def router_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for name, text in (
        ("router.ts", _ROUTER),
        ("prepared-router.ts", _PREPARED),
        ("named.ts", _NAMED),
    ):
        (tmp_path / name).write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _sites(result: dict) -> set[tuple[str, int]]:
    return {
        (site["file"], site["line"])
        for site in result.get("name_only_sites") or []
        + (result.get("unresolved_inbound_sites") or [])
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["RegExpRouter.buildAllMatchers", "buildAllMatchers"])
async def test_inherited_this_call_binds_the_base_method(
    router_root: str, name: str
) -> None:
    # hono：类表达式（`prepared-router.ts:8`）与命名子类（`named.ts:3`）的
    # `this.buildAllMatchers()` 沿 `extends RegExpRouter` 绑定到基类方法。
    result = await _callers(router_root, name, "router.ts")

    assert sorted((c["file"], c["name"]) for c in result["callers"]) == [
        ("named.ts", "exportAll"),
        ("prepared-router.ts", "buildAndExportAllMatchers"),
        ("router.ts", "match"),
    ]


@pytest.mark.asyncio
async def test_ambiguous_or_external_base_is_only_possible(tmp_path: Path) -> None:
    # 基类名对应两个项目类，或是外部类（`Error`）：不确定绑定，调用点仍被点名。
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "a.ts").write_text(
        "export class Base { reset() { return 1 } }\n", encoding="utf-8"
    )
    (tmp_path / "b.ts").write_text(
        "export class Base { reset() { return 2 } }\n", encoding="utf-8"
    )
    (tmp_path / "c.ts").write_text(
        "import { Base } from './a'\n"
        "class Sub extends Base {\n"
        "  go() { return this.reset() }\n"
        "}\n"
        "class Failure extends Error {\n"
        "  stop() { return this.reset() }\n"
        "}\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    result = await _callers(str(tmp_path), "Base.reset", "a.ts")

    assert result["callers"] == []
    assert result["completeness"] != "complete"
    assert _sites(result) == {("c.ts", 3)}


@pytest.mark.asyncio
async def test_this_call_is_not_bound_to_another_class_in_the_file(
    router_root: str,
) -> None:
    # `RegExpRouterWithMatcherExport` 与 `Named` 不是 `PreparedRegExpRouter` /
    # `Sibling`：它们的 `this.buildAllMatchers()` 不是确定调用方。
    prepared = await _callers(
        router_root, "PreparedRegExpRouter.buildAllMatchers", "prepared-router.ts"
    )
    sibling = await _callers(router_root, "Sibling.buildAllMatchers", "named.ts")

    assert [(c["file"], c["name"]) for c in prepared["callers"]] == [
        ("prepared-router.ts", "own")
    ]
    assert sibling["callers"] == []
    assert sibling["completeness"] != "complete"


@pytest.mark.asyncio
async def test_own_class_method_still_binds(router_root: str) -> None:
    # 对照：`RegExpRouter.match` 的 `this.buildAllMatchers()` 是确定调用方。
    result = await _callers(router_root, "RegExpRouter.buildAllMatchers", "router.ts")

    assert ("router.ts", "match") in {(c["file"], c["name"]) for c in result["callers"]}


@pytest.mark.asyncio
async def test_class_expression_is_indexed_with_its_base(router_root: str) -> None:
    import json
    import sqlite3

    db = next(Path(router_root).rglob("index.db"))
    with sqlite3.connect(str(db)) as conn:
        (symbols_json,) = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = 'prepared-router.ts'"
        ).fetchone()
    symbols = json.loads(symbols_json)["symbols"]

    classes = {s["name"]: s.get("parents") for s in symbols if s["kind"] == "class"}
    methods = {s["name"]: s.get("class") for s in symbols if s["kind"] == "method"}
    assert classes == {
        "PreparedRegExpRouter": None,
        "RegExpRouterWithMatcherExport": ["RegExpRouter"],
    }
    assert methods["buildAndExportAllMatchers"] == "RegExpRouterWithMatcherExport"
