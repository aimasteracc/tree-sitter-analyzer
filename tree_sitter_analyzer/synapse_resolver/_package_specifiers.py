"""#1764：裸说明符指向项目自己的包（``import * as z from "zod/v4"``）。

monorepo 的测试与子包按包名导入同仓库的包：``packages/zod/package.json`` 的
``"name": "zod"`` 与 ``"exports": {"./v4": {"@zod/source": "./src/v4/index.ts", ...}}``
把 ``zod/v4`` 交给 ``src/v4/index.ts``（TypeScript 的 ``customConditions`` 与包自引用）。

只在能确定时解析：项目里恰有一个同名的 ``package.json``；``exports`` 里该子路径的
全部条件目标中，恰有一个是已索引的文件（其余是未索引的构建产物）。没有 ``exports``、
子路径不在其中、或多个候选都已索引时返回 ``""``——外部包永远不解析到项目文件。
"""

from __future__ import annotations

import json
import os
import posixpath
from collections.abc import Iterable
from typing import Any

_MAX_PACKAGE_JSON_BYTES = 1_000_000


def split_package_specifier(specifier: str) -> tuple[str, str] | None:
    """``"@a/b/c"`` -> ``("@a/b", "./c")``；``"zod"`` -> ``("zod", ".")``。"""
    if not specifier or specifier.startswith((".", "/")) or ":" in specifier:
        return None
    parts = specifier.split("/")
    count = 2 if specifier.startswith("@") else 1
    if len(parts) < count or not all(parts[:count]):
        return None
    name = "/".join(parts[:count])
    rest = "/".join(parts[count:])
    return name, f"./{rest}" if rest else "."


class PackageSpecifiers:
    """按包名找到项目内的 ``package.json``，再按 ``exports`` 找到已索引的源文件。"""

    def __init__(self, project_root: str | None, indexed_files: Iterable[str]) -> None:
        self._root = project_root
        self._indexed = frozenset(indexed_files)
        self._packages: dict[str, list[tuple[str, Any]]] | None = None
        self._resolved: dict[str, str] = {}

    def resolve(self, specifier: str) -> str:
        if specifier not in self._resolved:
            self._resolved[specifier] = self._resolve(specifier)
        return self._resolved[specifier]

    def _resolve(self, specifier: str) -> str:
        split = split_package_specifier(specifier)
        if split is None or not self._root:
            return ""
        name, subpath = split
        found = self._by_name().get(name, [])
        if len(found) != 1:
            return ""
        package_dir, exports = found[0]
        entry = _subpath_entry(exports, subpath)
        if entry is None:
            return ""
        candidates = {
            path
            for leaf in _leaves(entry)
            if (path := _join(package_dir, leaf)) and path in self._indexed
        }
        return next(iter(candidates)) if len(candidates) == 1 else ""

    def _by_name(self) -> dict[str, list[tuple[str, Any]]]:
        if self._packages is None:
            self._packages = {}
            seen: set[str] = set()
            for rel in self._indexed:
                directory = posixpath.dirname(rel.replace("\\", "/"))
                while directory not in seen:
                    seen.add(directory)
                    self._read_package(directory)
                    if not directory:
                        break
                    directory = posixpath.dirname(directory)
        return self._packages

    def _read_package(self, directory: str) -> None:
        if self._packages is None:
            return
        path = os.path.join(str(self._root), directory, "package.json")
        try:
            if os.path.getsize(path) > _MAX_PACKAGE_JSON_BYTES:
                return
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeDecodeError, ValueError):
            return
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            return
        self._packages.setdefault(data["name"], []).append(
            (directory, data.get("exports"))
        )


def _subpath_entry(exports: Any, subpath: str) -> Any:
    """``exports`` 中 ``subpath`` 的条目；不存在或无法判定时为 None。"""
    if exports is None:
        return None
    if isinstance(exports, (str, list)) or (
        isinstance(exports, dict) and not any(k.startswith(".") for k in exports)
    ):
        return exports if subpath == "." else None
    if not isinstance(exports, dict):
        return None
    if subpath in exports:
        return exports[subpath]
    for key, value in exports.items():
        if key.count("*") != 1:
            continue
        head, tail = key.split("*")
        if subpath.startswith(head) and subpath.endswith(tail):
            middle = subpath[len(head) : len(subpath) - len(tail)]
            return _substitute(value, middle)
    return None


def _substitute(value: Any, middle: str) -> Any:
    if isinstance(value, str):
        return value.replace("*", middle)
    if isinstance(value, list):
        return [_substitute(item, middle) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, middle) for key, item in value.items()}
    return value


def _leaves(entry: Any) -> list[str]:
    if isinstance(entry, str):
        return [entry]
    if isinstance(entry, list):
        return [leaf for item in entry for leaf in _leaves(item)]
    if isinstance(entry, dict):
        return [leaf for item in entry.values() for leaf in _leaves(item)]
    return []


def _join(package_dir: str, target: str) -> str:
    if not target.startswith("./"):
        return ""
    joined = posixpath.normpath(posixpath.join(package_dir or ".", target))
    return "" if joined.startswith("..") else joined


__all__ = ["PackageSpecifiers", "split_package_specifier"]
