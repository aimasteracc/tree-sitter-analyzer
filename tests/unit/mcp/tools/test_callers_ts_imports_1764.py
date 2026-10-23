"""#1764 / #1768：TS 跨文件调用经 ES 模块导入、再导出绑定；绑不上的同名调用点始终可见。

ts1 dogfood（hono、zod）：没有一条 TS 调用边被持久化为 ``project``。具名导入
（``import { verifying } from './jws'``）、命名空间导入（``import * as core``）、经
``index.ts`` / ``external.ts`` 的再导出都停在 ``unknown``；``jwt.ts`` 里未解析的
``verifying(...)`` 还被目标文件筛选丢掉，答复只因导入行算作非调用引用才不是错误的
``complete``。#1768：改名的默认导入（``import makeSig from './jws'; makeSig()``）让
``signer`` 答出 ``complete, 0``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.test_callers_bare_name_gates_1740 import _callers, _index

_FILES = {
    "src/core/errors.ts": (
        "export function flattenError(e: unknown): string {\n"
        "  return String(e);\n"
        "}\n"
        "export function toDotPath(p: string[]): string {\n"
        "  return p.join('.');\n"
        "}\n"
    ),
    "src/core/index.ts": "export * from './errors.js';\nexport * from './util.js';\n",
    "src/core/util.ts": "export function joinValues(v: string[]) {\n  return v.join();\n}\n",
    "src/classic/external.ts": (
        "export * as core from '../core/index.js';\n"
        "export { flattenError } from '../core/index.js';\n"
    ),
    "src/index.ts": "export * from './classic/external.js';\n",
    "src/classic/errors.ts": (
        "import * as core from '../core/index.js';\n"
        "export function flat(e: unknown) {\n"
        "  return core.flattenError(e);\n"
        "}\n"
    ),
    "src/classic/chain.ts": (
        "import * as z from '../index.js';\n"
        "export function chain(p: string[]) {\n"
        "  return z.core.toDotPath(p);\n"
        "}\n"
        "export function top(e: unknown) {\n"
        "  return z.flattenError(e);\n"
        "}\n"
    ),
    "src/jwt/jws.ts": (
        "export async function verifying(key: string): Promise<boolean> {\n"
        "  return key.length > 0;\n"
        "}\n"
        "export function signing(key: string) {\n"
        "  return key;\n"
        "}\n"
        "export class Status {\n"
        "  static merge(a: number): number {\n"
        "    return a;\n"
        "  }\n"
        "}\n"
        "export default function signer(k: string) {\n"
        "  return k;\n"
        "}\n"
    ),
    "src/jwt/jwt.ts": (
        "import makeSig, { verifying, Status, signing as sg } from './jws';\n"
        "import type { Token } from './types';\n"
        "export const verify = async (key: string) => {\n"
        "  const ok = await verifying(key);\n"
        "  return ok ? Status.merge(1) : makeSig(key);\n"
        "};\n"
        "export function sign(key: string) {\n"
        "  return sg(key);\n"
        "}\n"
    ),
    "src/jwt/types.ts": "export type Token = string;\n",
    "src/other/pkg.ts": (
        "import { verifying } from 'some-package';\n"
        "export async function remote(k: string) {\n"
        "  return verifying(k);\n"
        "}\n"
    ),
}

# 两个 `export *` 来源导出同名函数：按 ES 语义该名字不被导出，不能绑定到任何一个。
_AMBIGUOUS = {
    "lib/a.ts": "export function dup() {\n  return 1;\n}\n",
    "lib/b.ts": "export function dup() {\n  return 2;\n}\n",
    "lib/index.ts": "export * from './a';\nexport * from './b';\n",
    "lib/use.ts": (
        "import { dup } from './index';\nexport function run() {\n  return dup();\n}\n"
    ),
}

# `export *` 的来源之一是外部包：它可能就导出这个名字。
_EXTERNAL_STAR = {
    "ext/c.ts": "export function cfun() {\n  return 1;\n}\n",
    "ext/index.ts": "export * from 'some-package';\nexport * from './c';\n",
    "ext/use.ts": (
        "import { cfun } from './index';\nexport function run() {\n  return cfun();\n}\n"
    ),
}

# 项目自己的包：测试按包名导入（zod 的 `import * as z from "zod/v4"`）。
_PACKAGE = {
    "packages/pkg/package.json": (
        '{"name": "mypkg", "exports": {"./sub": '
        '{"source": "./src/sub.ts", "import": "./dist/sub.js"}}}\n'
    ),
    "packages/pkg/src/sub.ts": "export function subFn() {\n  return 1;\n}\n",
    "packages/pkg/test/sub.test.ts": (
        "import * as m from 'mypkg/sub';\n"
        "import { subFn } from 'mypkg/sub';\n"
        "export function a() {\n  return m.subFn();\n}\n"
        "export function b() {\n  return subFn();\n}\n"
    ),
}


def _caller_sites(answer: dict) -> set[str]:
    return {f"{c.get('file')}:{c.get('name')}" for c in answer.get("callers") or []}


def _evidence(answer: dict) -> set[str]:
    return {
        f"{s.get('file')}:{s.get('line')}"
        for s in (answer.get("unresolved_inbound_sites") or [])
        + (answer.get("name_only_sites") or [])
    }


# slow_ok：每个用例做一次真实全量索引，再做 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "file_path", "caller"),
    [
        ("flattenError", "src/core/errors.ts", "src/classic/errors.ts:flat"),
        ("toDotPath", "src/core/errors.ts", "src/classic/chain.ts:chain"),
        ("flattenError", "src/core/errors.ts", "src/classic/chain.ts:top"),
        ("Status.merge", "src/jwt/jws.ts", "src/jwt/jwt.ts:<module>"),
        ("signing", "src/jwt/jws.ts", "src/jwt/jwt.ts:sign"),
    ],
    ids=[
        "namespace-through-barrel",
        "nested-export-star-as",
        "explicit-reexport-beside-star",
        "imported-class-static",
        "aliased-named-import",
    ],
)
async def test_an_es_import_binds_the_cross_file_call(
    tmp_path: Path, name: str, file_path: str, caller: str
) -> None:
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, name, file_path)

    assert caller in _caller_sites(answer), answer


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "site"),
    [("verifying", "src/jwt/jwt.ts:4"), ("signer", "src/jwt/jwt.ts:5")],
    ids=["named-import-in-module-level-arrow", "renamed-default-import-1768"],
)
async def test_a_module_level_call_is_never_lost(
    tmp_path: Path, name: str, site: str
) -> None:
    """模块级箭头函数里的调用没有调用方名字：它要么被列出，要么作为证据出现。

    #1768：改名的默认导入曾让 ``signer`` 答出 ``complete, 0``。
    """
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, name, "src/jwt/jws.ts")

    listed = "src/jwt/jwt.ts:<module>" in _caller_sites(answer)
    assert listed or site in _evidence(answer), answer
    if answer["completeness"] == "complete":
        assert listed, answer


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_a_package_import_of_the_same_name_stays_evidence(tmp_path: Path) -> None:
    """``other/pkg.ts`` 调用的是包里的 ``verifying``：不绑定，也不从证据里消失。"""
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, "verifying", "src/jwt/jws.ts")

    assert answer["completeness"] != "complete"
    assert "src/other/pkg.ts:remote" not in _caller_sites(answer)
    assert "src/other/pkg.ts:3" in _evidence(answer), answer


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize("files", [_AMBIGUOUS, _EXTERNAL_STAR], ids=["two", "pkg"])
async def test_an_unprovable_export_star_source_is_not_bound(
    tmp_path: Path, files: dict[str, str]
) -> None:
    root = await _index(tmp_path, files)
    name, file_path = (
        ("dup", "lib/a.ts") if files is _AMBIGUOUS else ("cfun", "ext/c.ts")
    )

    answer = await _callers(root, name, file_path)

    use = file_path.rsplit("/", 1)[0] + "/use.ts"
    listed = f"{use}:run" in _caller_sites(answer)
    if files is _AMBIGUOUS:
        # Two definitions: ES drops the name, so neither is the target of `dup()`.
        assert not listed, answer
    assert listed or f"{use}:3" in _evidence(answer), answer
    if answer["completeness"] == "complete":
        assert listed, answer


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_a_project_package_specifier_binds(tmp_path: Path) -> None:
    root = await _index(tmp_path, _PACKAGE)

    answer = await _callers(root, "subFn", "packages/pkg/src/sub.ts")

    assert _caller_sites(answer) >= {
        "packages/pkg/test/sub.test.ts:a",
        "packages/pkg/test/sub.test.ts:b",
    }, answer


# zod locales: the default export is an anonymous function; `en()` cannot reach `getTypeName`.
_LOCALE = {
    "locales/en.ts": (
        "function getTypeName(t: string) {\n  return t;\n}\n"
        "export default function () {\n  return getTypeName('x');\n}\n"
    ),
    "classic/schemas.ts": (
        "import en from '../locales/en';\nexport function setup() {\n  return en();\n}\n"
    ),
}


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_an_anonymous_default_import_call_is_not_evidence_for_other_functions(
    tmp_path: Path,
) -> None:
    root = await _index(tmp_path, _LOCALE)

    answer = await _callers(root, "getTypeName", "locales/en.ts")

    assert "classic/schemas.ts:3" not in _evidence(answer), answer
    assert answer["completeness"] == "complete", answer
