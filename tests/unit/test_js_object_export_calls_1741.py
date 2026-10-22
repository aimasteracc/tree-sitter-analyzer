"""#1741：JavaScript 经导入对象调用的函数（``import utils from '../utils.js'; utils.findKey()``）。

dogfood 第 10 轮 axios：这类调用全部是 ``unknown``，调用点召回 17/53，36 个漏掉的点
没有出现在任何证据字段里，``next_step`` 还指向声明文件中无关的 IIFE。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_UTILS = (
    "const findKey = (obj, key) => {\n"
    "  return Object.keys(obj).find((k) => k === key);\n"
    "};\n"
    "\n"
    "function isSafeIterable(thing) {\n"
    "  return thing != null;\n"
    "}\n"
    "\n"
    "const _global = (() => {\n"
    "  return globalThis;\n"
    "})();\n"
    "\n"
    "export default {\n"
    "  findKey,\n"
    "  isSafeIterable,\n"
    "  global: _global,\n"
    "};\n"
)
_NODE_PLATFORM = (
    "const generateString = (size) => {\n"
    "  return 'x'.repeat(size);\n"
    "};\n"
    "\n"
    "export default {\n"
    "  generateString,\n"
    "};\n"
)
_PLATFORM = (
    "import platform from './node/index.js';\n\nexport default {\n  ...platform,\n};\n"
)
_HEADERS = (
    "import utils from '../utils.js';\n"
    "import platform from '../platform/index.js';\n"
    "\n"
    "export function lookup(self, header) {\n"
    "  return utils.findKey(self, header);\n"
    "}\n"
    "\n"
    "export function boundary() {\n"
    "  return platform.generateString(36);\n"
    "}\n"
    "\n"
    "export function iter(h) {\n"
    "  return utils.isSafeIterable(h);\n"
    "}\n"
)
_HELPERS = "export function helper(x) {\n  return x;\n}\n"
_NAMESPACE = (
    "import * as u from './utils.js';\n"
    "import * as h from './helpers.js';\n"
    "\n"
    "export function viaDefault(o) {\n"
    "  return u.default.findKey(o, 'a');\n"
    "}\n"
    "\n"
    "export function viaNamed(o) {\n"
    "  return h.helper(o);\n"
    "}\n"
    "\n"
    "export function unrelated(map) {\n"
    "  return map.findKey('a');\n"
    "}\n"
)


async def _index(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _names(result: dict) -> set[tuple[str, str]]:
    return {
        (c["file"].replace("\\", "/"), c["name"]) for c in result.get("callers") or []
    }


_AXIOS_SHAPE = {
    "lib/utils.js": _UTILS,
    "lib/platform/node/index.js": _NODE_PLATFORM,
    "lib/platform/index.js": _PLATFORM,
    "lib/core/headers.js": _HEADERS,
    "lib/helpers.js": _HELPERS,
    "lib/other.js": _NAMESPACE,
}


@pytest.mark.asyncio
async def test_default_import_object_member_arrow_function_is_a_caller(
    tmp_path,
) -> None:
    root = await _index(tmp_path, _AXIOS_SHAPE)

    result = await _callers(root, "findKey", "lib/utils.js")

    assert ("lib/core/headers.js", "lookup") in _names(result)
    # 命名空间导入的 ``u.default.findKey`` 同样指向默认导出对象。
    assert ("lib/other.js", "viaDefault") in _names(result)
    # 接收者不是导入的模块对象：不能绑定。
    assert ("lib/other.js", "unrelated") not in _names(result)
    # 默认导出对象里的 ``findKey,`` 是非调用引用：答案不能是 complete。
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_default_import_object_member_function_declaration(tmp_path) -> None:
    root = await _index(tmp_path, _AXIOS_SHAPE)

    result = await _callers(root, "isSafeIterable", "lib/utils.js")

    assert _names(result) == {("lib/core/headers.js", "iter")}


@pytest.mark.asyncio
async def test_spread_reexport_of_another_default_import(tmp_path) -> None:
    root = await _index(tmp_path, _AXIOS_SHAPE)

    result = await _callers(root, "generateString", "lib/platform/node/index.js")

    assert _names(result) == {("lib/core/headers.js", "boundary")}


@pytest.mark.asyncio
async def test_namespace_import_named_export(tmp_path) -> None:
    root = await _index(tmp_path, _AXIOS_SHAPE)

    result = await _callers(root, "helper", "lib/helpers.js")

    assert ("lib/other.js", "viaNamed") in _names(result)


@pytest.mark.asyncio
async def test_iife_in_declaring_file_is_not_named_as_a_possible_site(tmp_path) -> None:
    root = await _index(tmp_path, _AXIOS_SHAPE)

    result = await _callers(root, "findKey", "lib/utils.js")

    lines = {(s["file"], s["line"]) for s in result.get("unresolved_sites") or []}
    assert ("lib/utils.js", 9) not in lines
    assert "globalThis" not in (result.get("next_step") or "")


@pytest.mark.asyncio
async def test_caller_reassigning_the_member_is_not_bound(tmp_path) -> None:
    files = dict(_AXIOS_SHAPE)
    files["lib/patched.js"] = (
        "import utils from './utils.js';\n"
        "\n"
        "utils.findKey = () => null;\n"
        "\n"
        "export function patched(o) {\n"
        "  return utils.findKey(o, 'a');\n"
        "}\n"
    )
    root = await _index(tmp_path, files)

    result = await _callers(root, "findKey", "lib/utils.js")

    assert ("lib/patched.js", "patched") not in _names(result)
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_named_import_of_same_name_is_not_a_default_object(tmp_path) -> None:
    files = {
        "lib/utils.js": _UTILS,
        "lib/named.js": ("export const utils = { findKey: (o) => o };\n"),
        "lib/consumer.js": (
            "import { utils } from './named.js';\n"
            "\n"
            "export function consumer(o) {\n"
            "  return utils.findKey(o);\n"
            "}\n"
        ),
    }
    root = await _index(tmp_path, files)

    result = await _callers(root, "findKey", "lib/utils.js")

    assert ("lib/consumer.js", "consumer") not in _names(result)
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_non_object_default_export_or_computed_key_is_not_bound(tmp_path) -> None:
    files = {
        "lib/cls.js": (
            "function findKey(o) {\n  return o;\n}\n\n"
            "export default class Store {\n  static findKey(o) {\n    return o;\n  }\n}\n"
        ),
        "lib/computed.js": (
            "function pick(o) {\n  return o;\n}\n\n"
            "const name = 'pick';\n\nexport default {\n  [name]: pick,\n  pick,\n};\n"
        ),
        "lib/use.js": (
            "import Store from './cls.js';\n"
            "import comp from './computed.js';\n"
            "\n"
            "export function a(o) {\n  return Store.findKey(o);\n}\n"
            "\n"
            "export function b(o) {\n  return comp.pick(o);\n}\n"
        ),
    }
    root = await _index(tmp_path, files)

    by_class = await _callers(root, "findKey", "lib/cls.js")
    computed = await _callers(root, "pick", "lib/computed.js")

    assert ("lib/use.js", "a") not in _names(by_class)
    assert ("lib/use.js", "b") not in _names(computed)


@pytest.mark.parametrize(
    "text",
    [
        "(() => {\n  return globalThis;\n})",
        "(({ hasOwnProperty }) => (obj, prop) => hasOwnProperty.call(obj, prop))",
        "((cache) => (thing) => cache[thing])",
        "(function () { return 1; })",
        "(async () => { await x(); })",
        "(lambda: 1)",
    ],
)
def test_immediately_invoked_function_literals_cannot_name_a_target(text: str) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_dispatch import (
        could_name_target,
        is_function_literal,
    )

    assert is_function_literal(text) is True
    assert could_name_target(text, "findKey") is False


@pytest.mark.parametrize(
    "text",
    ["(handlers)[name]", "(getHandler())", "(a || b).run", "make()()", "(x)"],
)
def test_parenthesised_non_literals_keep_the_guard(text: str) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_dispatch import is_function_literal

    assert is_function_literal(text) is False


_COMMON = (
    "const hasBrowserEnv = typeof window !== 'undefined';\n"
    "const _navigator = null;\n"
    "\n"
    "export { hasBrowserEnv, _navigator as navigator };\n"
)


@pytest.mark.asyncio
async def test_spread_of_a_namespace_import_beside_a_default_import(tmp_path) -> None:
    # axios lib/platform/index.js: ``export default { ...utils, ...platform }`` where
    # ``utils`` is ``import * as utils``. The namespace spread provably carries only its
    # static named exports, so ``generateString`` comes from ``...platform``.
    files = dict(_AXIOS_SHAPE)
    files["lib/platform/common/utils.js"] = _COMMON
    files["lib/platform/index.js"] = (
        "import platform from './node/index.js';\n"
        "import * as utils from './common/utils.js';\n"
        "\n"
        "export default {\n  ...utils,\n  ...platform,\n};\n"
    )
    root = await _index(tmp_path, files)

    result = await _callers(root, "generateString", "lib/platform/node/index.js")

    assert _names(result) == {("lib/core/headers.js", "boundary")}


@pytest.mark.asyncio
async def test_namespace_spread_with_export_star_is_not_bound(tmp_path) -> None:
    files = dict(_AXIOS_SHAPE)
    files["lib/platform/common/utils.js"] = "export * from './more.js';\n"
    files["lib/platform/common/more.js"] = (
        "export function generateString() {\n  return 1;\n}\n"
    )
    files["lib/platform/index.js"] = (
        "import platform from './node/index.js';\n"
        "import * as utils from './common/utils.js';\n"
        "\n"
        "export default {\n  ...utils,\n  ...platform,\n};\n"
    )
    root = await _index(tmp_path, files)

    result = await _callers(root, "generateString", "lib/platform/node/index.js")

    # ``export *`` makes the spread's members unknowable: either source may win.
    assert ("lib/core/headers.js", "boundary") not in _names(result)
    assert result["completeness"] != "complete"
