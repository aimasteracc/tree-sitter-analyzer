"""#1765：JS/TS 文件中按名字导入的绑定指向哪个项目文件（只处理相对路径导入）。

读取端沿 ``extends`` 链找 ``this.m()`` 的继承定义时，需要知道
``import { ZodType } from './types'`` 里的 ``ZodType`` 是哪个文件的类——zod 的
v3 / v4 各有一个 ``ZodType``。这里只做确定的映射：相对路径解析到索引中恰好存在
的文件，否则不给出映射（调用方随之放弃确定绑定）。说明符解析复用 #1764 的
`resolve_typescript_specifier`（与 Synapse 的 ES 模块绑定一致）。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .synapse_resolver._typescript_imports import resolve_typescript_specifier

_IMPORT = re.compile(
    r"^\s*import\s+(?:type\s+)?(?P<clause>[\s\S]+?)\s+from\s+['\"](?P<spec>[^'\"]+)['\"]"
)
_NAMED = re.compile(r"\{([^}]*)\}")
_JSTS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")


def jsts_import_map(
    imports_raw: Mapping[str, Iterable[Any]], known_files: Iterable[str]
) -> dict[str, dict[str, str]]:
    """``{文件: {本地名: 目标文件}}``，只含 JS/TS 文件与能解析到已知文件的相对导入。"""
    files = set(known_files)
    result: dict[str, dict[str, str]] = {}
    for file_path, imports in imports_raw.items():
        if not file_path.endswith(_JSTS_SUFFIXES):
            continue
        names: dict[str, str] = {}
        for item in imports:
            text = item["text"] if isinstance(item, dict) else str(item)
            match = _IMPORT.match(text)
            if match is None:
                continue
            # #1764 的说明符解析（相对路径、扩展名、./x.js -> x.ts、index）。
            target = resolve_typescript_specifier(match.group("spec"), file_path, files)
            if not target:
                continue
            for local in _local_names(match.group("clause")):
                names[local] = target
        if names:
            result[file_path] = names
    return result


def _local_names(clause: str) -> list[str]:
    """``A, { B, C as D }`` -> ``[A, B, D]``；``* as ns`` 不是按名字的绑定。"""
    names: list[str] = []
    named = _NAMED.search(clause)
    if named is not None:
        for part in named.group(1).split(","):
            part = part.strip()
            if part.startswith("type "):
                part = part[len("type ") :].strip()
            if part:
                names.append(part.split(" as ")[-1].strip())
    head = _NAMED.sub("", clause).strip().strip(",").strip()
    if head and not head.startswith("*") and head.isidentifier():
        names.append(head)
    return names


__all__ = ["jsts_import_map"]
