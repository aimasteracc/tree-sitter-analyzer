"""#1764：TS 跨文件调用经相对导入绑定到定义，未解析的同名边从不被目标文件过滤掉。

ts1 dogfood：TS 调用边从未被解析为 ``project``——具名导入（``import { verifying } from
'./jws'``）、命名空间导入（``import * as core from '../core/index.js'``）与 ``index.ts``
的再导出都留在 ``unknown``；``jwt.ts`` 里未解析的 ``verifying(...)`` 还被按目标文件过滤，
对 ``jws.ts`` 的 ``verifying`` 既不列出、也不算未解析入边。
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
    "src/core/index.ts": "export * from './errors.js';\n",
    "src/classic/external.ts": (
        "export * as core from '../core/index.js';\n"
        "export { flattenError } from '../core/errors.js';\n"
    ),
    "src/classic/errors.ts": (
        "import * as core from '../core/index.js';\n"
        "export function flat(e: unknown) {\n"
        "  return core.flattenError(e);\n"
        "}\n"
    ),
    "src/classic/chain.ts": (
        "import * as z from './external.js';\n"
        "export function chain(p: string[]) {\n"
        "  return z.core.toDotPath(p);\n"
        "}\n"
    ),
    "src/jwt/jws.ts": (
        "export async function verifying(key: string): Promise<boolean> {\n"
        "  return key.length > 0;\n"
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
        "import makeSig, { verifying, Status } from './jws';\n"
        "import type { Token } from './types';\n"
        "export const verify = async (key: string) => {\n"
        "  const ok = await verifying(key);\n"
        "  return ok ? Status.merge(1) : makeSig(key);\n"
        "};\n"
    ),
    "src/jwt/types.ts": "export type Token = string;\n",
    "src/other/pkg.ts": (
        "import { verifying } from 'some-package';\n"
        "export async function remote(k: string) {\n"
        "  return verifying(k);\n"
        "}\n"
    ),
}


def _caller_sites(answer: dict) -> set[str]:
    return {f"{c.get('file')}:{c.get('name')}" for c in answer.get("callers", [])}


def _evidence(answer: dict) -> set[str]:
    return {
        f"{s.get('file')}:{s.get('line')}"
        for s in answer.get("unresolved_inbound_sites", [])
        + answer.get("name_only_sites", [])
    }


# slow_ok：真实全量索引一次，再做 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "file_path", "caller"),
    [
        ("flattenError", "src/core/errors.ts", "src/classic/errors.ts:flat"),
        ("toDotPath", "src/core/errors.ts", "src/classic/chain.ts:chain"),
        ("Status.merge", "src/jwt/jws.ts", "src/jwt/jwt.ts:<module>"),
        ("verifying", "src/jwt/jws.ts", "src/jwt/jwt.ts:<module>"),
    ],
    ids=[
        "namespace-through-barrel",
        "nested-export-star-as",
        "imported-class-static",
        "named-import",
    ],
)
async def test_a_relative_import_binds_the_cross_file_call(
    tmp_path: Path, name: str, file_path: str, caller: str
) -> None:
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, name, file_path)

    assert caller in _caller_sites(answer), answer.get("callers")


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_an_unresolvable_same_named_call_stays_evidence(tmp_path: Path) -> None:
    """``other/pkg.ts`` 调用的是包里的 ``verifying``：不能绑定，但不能从证据里消失。"""
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, "verifying", "src/jwt/jws.ts")

    assert answer["completeness"] != "complete"
    assert "src/other/pkg.ts:3" in _evidence(answer)
    assert "src/other/pkg.ts:remote" not in _caller_sites(answer)


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_a_default_import_is_not_bound_by_name(tmp_path: Path) -> None:
    """默认导入的本地名与导出名无关：``makeSig(key)`` 不经名字绑定到 ``signer``。"""
    root = await _index(tmp_path, _FILES)

    answer = await _callers(root, "signer", "src/jwt/jws.ts")

    assert "src/jwt/jwt.ts:<module>" not in _caller_sites(answer)
    assert answer["completeness"] != "complete"
