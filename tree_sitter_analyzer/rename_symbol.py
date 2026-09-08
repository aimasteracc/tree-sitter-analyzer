#!/usr/bin/env python3
"""使用精确 Python 标识符位置重命名，保留原始字节并在失败时回滚。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RenameSite:
    file: str
    line: int
    column: int
    old_text: str
    site_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "old_text": self.old_text,
            "site_type": self.site_type,
        }


@dataclass
class RenameResult:
    symbol: str
    new_name: str
    dry_run: bool
    files_changed: int = 0
    sites_renamed: int = 0
    sites: list[RenameSite] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "new_name": self.new_name,
            "dry_run": self.dry_run,
            "files_changed": self.files_changed,
            "sites_renamed": self.sites_renamed,
            "sites": [s.to_dict() for s in self.sites],
            "errors": self.errors,
        }


def _group_sites_by_file(
    sites: list[RenameSite],
) -> dict[str, list[RenameSite]]:
    groups: dict[str, list[RenameSite]] = {}
    for s in sites:
        groups.setdefault(s.file, []).append(s)
    return groups


def _render_rename(
    file_path: str, sites: list[RenameSite], old_name: str, new_name: str
) -> bytes:
    """在内存中校验坐标和语法，生成保留编码的完整字节。"""
    from pathlib import Path

    from .rename_python import read_source

    _, content, encoding = read_source(Path(file_path))
    lines = content.split("\n")
    for site in sorted(sites, key=lambda s: (s.line, s.column), reverse=True):
        if site.line <= 0 or site.line > len(lines) or site.column < 0:
            raise ValueError("Unknown identifier location")
        line = lines[site.line - 1]
        col = site.column
        if line[col : col + len(old_name)] != old_name:
            raise ValueError("Identifier location mismatch")
        lines[site.line - 1] = line[:col] + new_name + line[col + len(old_name) :]
    output = "\n".join(lines).encode(encoding)
    compile(output, file_path, "exec")
    return output


def _apply_rename_to_file(
    file_path: str, sites: list[RenameSite], old_name: str, new_name: str
) -> bool:
    """校验精确位置并保留编码和换行。"""
    from pathlib import Path

    try:
        Path(file_path).write_bytes(
            _render_rename(file_path, sites, old_name, new_name)
        )
        return True
    except (OSError, ValueError, UnicodeError, SyntaxError):
        return False


def rename_symbol(
    cache: Any,
    old_name: str,
    new_name: str,
    dry_run: bool = True,
    project_root: str | None = None,
) -> RenameResult:
    from pathlib import Path

    from .rename_python import plan_python

    result = RenameResult(symbol=old_name, new_name=new_name, dry_run=dry_run)
    root = project_root or cache.project_root
    try:
        sites, backup = plan_python(root, old_name, new_name)
        for filename, file_sites in _group_sites_by_file(sites).items():
            _render_rename(
                str(Path(root).resolve() / filename), file_sites, old_name, new_name
            )
    except (ValueError, OSError, SyntaxError, UnicodeError) as exc:
        result.errors.append(str(exc))
        return result
    result.sites = sites
    if dry_run or not sites:
        return result
    by_file = _group_sites_by_file(sites)
    written: list[str] = []
    try:
        for fpath, file_sites in by_file.items():
            abs_path = str(Path(root).resolve() / fpath)
            if Path(abs_path).read_bytes() != backup[abs_path]:
                raise OSError(f"Source changed during rename: {fpath}")
            written.append(abs_path)
            if not _apply_rename_to_file(abs_path, file_sites, old_name, new_name):
                raise OSError(f"Failed to write {fpath}")
    except OSError as exc:
        result.errors.append(str(exc))
        for filename in written:
            try:
                Path(filename).write_bytes(backup[filename])
            except OSError as rollback_error:
                result.errors.append(
                    f"Rollback failed for {filename}: {rollback_error}"
                )
        return result
    result.files_changed = len(by_file)
    result.sites_renamed = len(sites)
    for filename in written:
        cache.invalidate(filename)
    return result
