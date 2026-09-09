"""在项目内发现文件并核验符号文本，不启动外部搜索进程。"""

from __future__ import annotations

import fnmatch
import os
import re
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pathspec

_MAX_ENTRIES = 200000
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_MATCHES = 100000

_EXCLUDED = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", "target"}
)


def workspace_files(
    roots: list[str], *, deadline: float | None = None
) -> Iterator[Path]:
    """遵守嵌套忽略规则、隐藏目录和符号链接边界，按路径顺序返回普通文件。"""
    seen: set[str] = set()
    entries = 0
    for value in roots:
        root = Path(value).absolute()
        if root.is_symlink():
            raise OSError("SOURCE_ROOT_SYMLINK")
        if not root.is_dir():
            raise OSError("SOURCE_ROOT_UNAVAILABLE")
        rules: dict[Path, list[tuple[Path, pathspec.GitIgnoreSpec]]] = {}
        for current, directories, names in os.walk(
            root, followlinks=False, onerror=_raise_walk_error
        ):
            entries += len(directories) + len(names)
            if entries > _MAX_ENTRIES or (
                deadline is not None and time.monotonic() >= deadline
            ):
                raise TimeoutError("SOURCE_DISCOVERY_BUDGET_EXCEEDED")
            parent = Path(current)
            inherited = list(rules.get(parent.parent, []))
            for rule_name in (".gitignore", ".ignore", ".rgignore"):
                rule_path = parent / rule_name
                if rule_path.is_file() and not rule_path.is_symlink():
                    inherited.append(
                        (
                            parent,
                            pathspec.GitIgnoreSpec.from_lines(
                                rule_path.read_text(
                                    encoding="utf-8", errors="replace"
                                ).splitlines()
                            ),
                        )
                    )
            rules[parent] = inherited
            directories[:] = sorted(
                d
                for d in directories
                if d not in _EXCLUDED
                and not d.startswith(".")
                and not (parent / d).is_symlink()
                and not _ignored(parent / d, inherited, directory=True)
            )
            for name in sorted(names):
                path = parent / name
                if (
                    name.startswith(".")
                    or path.is_symlink()
                    or _ignored(path, inherited)
                ):
                    continue
                key = str(path)
                if key in seen:
                    continue
                if stat.S_ISREG(path.stat().st_mode):
                    seen.add(key)
                    yield path


def _raise_walk_error(error: OSError) -> None:
    raise error


def _ignored(
    path: Path,
    rules: list[tuple[Path, pathspec.GitIgnoreSpec]],
    *,
    directory: bool = False,
) -> bool:
    ignored = False
    for base, spec in rules:
        result = spec.check_file(
            path.relative_to(base).as_posix() + ("/" if directory else "")
        )
        if result.include is not None:
            ignored = bool(result.include)
    return ignored


def _matches_glob(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or (pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]))
        for pattern in patterns
    )


def scan_symbol_lines(
    symbol: str,
    roots: list[str],
    *,
    case_sensitive: bool,
    word_match: bool,
    include_globs: list[str],
    exclude_globs: list[str],
    timeout: float = 5,
) -> list[dict[str, Any]]:
    """保留全部命中行供计数；预算或读取失败时拒绝返回不完整的成功结果。"""
    deadline = time.monotonic() + timeout
    sensitive = case_sensitive or any(c.isupper() for c in symbol)
    expression = re.escape(symbol)
    if word_match:
        expression = r"(?<!\w)" + expression + r"(?!\w)"
    matcher = re.compile(expression, 0 if sensitive else re.IGNORECASE)
    matches = []
    total_bytes = 0
    bases = [Path(root).absolute() for root in roots]
    for path in workspace_files(roots, deadline=deadline):
        relative = next(
            path.relative_to(base).as_posix()
            for base in bases
            if path.is_relative_to(base)
        )
        if (
            include_globs and not _matches_glob(relative, include_globs)
        ) or _matches_glob(relative, exclude_globs):
            continue
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0)
        )
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise OSError("SOURCE_FILE_CHANGED")
            if info.st_size > _MAX_FILE_BYTES:
                raise TimeoutError("SOURCE_FILE_BUDGET_EXCEEDED")
            raw = stream.read(_MAX_FILE_BYTES + 1)
        total_bytes += len(raw)
        if (
            len(raw) > _MAX_FILE_BYTES
            or total_bytes > _MAX_TOTAL_BYTES
            or time.monotonic() >= deadline
        ):
            raise TimeoutError("SOURCE_SCAN_BUDGET_EXCEEDED")
        if b"\x00" in raw:
            continue
        for number, line in enumerate(
            raw.decode("utf-8", errors="replace").splitlines(), 1
        ):
            if matcher.search(line):
                matches.append({"file": str(path), "line": number, "text": line})
                if len(matches) > _MAX_MATCHES:
                    raise TimeoutError("SOURCE_MATCH_BUDGET_EXCEEDED")
    return matches
