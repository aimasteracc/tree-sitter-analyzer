#!/usr/bin/env python3
"""
AST-aware Rename Symbol — Project-wide symbol renaming engine.

Uses the pre-indexed AST cache + SymbolResolver to locate all definition
and reference sites of a symbol, then performs coordinated text replacement
across all affected files.

Key capabilities:
- Rename functions, classes, methods, and variables
- Import-aware: renames imported names and import statements
- Scope-aware: only renames the target symbol, not unrelated same-name tokens
- Dry-run mode: preview changes without writing
- Rollback on failure: reverts all files if any write fails

CodeGraph parity: equivalent to CodeGraph's "Rename Symbol" refactoring.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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


_WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"  # pragma: allowlist secret
)


def _is_word_boundary(text: str, pos: int) -> bool:
    if pos < 0 or pos >= len(text):
        return True
    return text[pos] not in _WORD_CHARS


def _find_identifier_at_or_near(
    line_text: str, column: int, target_name: str
) -> int | None:
    name_len = len(target_name)
    start = max(0, column - name_len)
    for offset in range(name_len + 5):
        pos = start + offset
        end_pos = pos + name_len
        if pos < 0 or end_pos > len(line_text):
            continue
        candidate = line_text[pos:end_pos]
        if candidate == target_name:
            before_ok = _is_word_boundary(line_text, pos - 1)
            after_ok = _is_word_boundary(line_text, end_pos)
            if before_ok and after_ok:
                return pos
    return None


def _scan_line_for_name(line_text: str, name: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while start < len(line_text):
        idx = line_text.find(name, start)
        if idx == -1:
            break
        if _is_word_boundary(line_text, idx - 1) and _is_word_boundary(
            line_text, idx + len(name)
        ):
            positions.append(idx)
        start = idx + 1
    return positions


def _sites_from_defn(defn: Any, old_name: str, project_root: str) -> list[RenameSite]:
    """Collect rename sites for a single definition entry."""
    fpath = (
        defn.file if os.path.isabs(defn.file) else os.path.join(project_root, defn.file)
    )
    if not os.path.isfile(fpath):
        return []
    try:
        with open(fpath) as f:
            lines = f.readlines()
    except OSError:
        return []
    line_idx = defn.line - 1
    if 0 <= line_idx < len(lines):
        line_text = lines[line_idx]
        positions = _scan_line_for_name(line_text, old_name)
        return [
            RenameSite(
                file=defn.file,
                line=defn.line,
                column=col,
                old_text=old_name,
                site_type="definition",
            )
            for col in positions
        ]
    return []


def _sites_from_ref(ref: Any, old_name: str, project_root: str) -> list[RenameSite]:
    """Collect rename sites for a single reference entry."""
    fpath = (
        ref.file if os.path.isabs(ref.file) else os.path.join(project_root, ref.file)
    )
    if not os.path.isfile(fpath):
        return []
    try:
        with open(fpath) as f:
            lines = f.readlines()
    except OSError:
        return []
    if ref.line <= 0:
        return [
            RenameSite(
                file=ref.file,
                line=0,
                column=0,
                old_text=old_name,
                site_type=ref.reference_type,
            )
        ]
    line_idx = ref.line - 1
    if 0 <= line_idx < len(lines):
        line_text = lines[line_idx]
        positions = _scan_line_for_name(line_text, old_name)
        return [
            RenameSite(
                file=ref.file,
                line=ref.line,
                column=col,
                old_text=old_name,
                site_type=ref.reference_type,
            )
            for col in positions
        ]
    return []


def _collect_rename_sites_from_resolver(
    resolve_result: Any, old_name: str, project_root: str
) -> list[RenameSite]:
    sites: list[RenameSite] = []
    for defn in resolve_result.definitions:
        sites.extend(_sites_from_defn(defn, old_name, project_root))
    for ref in resolve_result.references:
        sites.extend(_sites_from_ref(ref, old_name, project_root))
    return sites


def _deduplicate_sites(sites: list[RenameSite]) -> list[RenameSite]:
    seen: set[tuple[str, int, int]] = set()
    deduped: list[RenameSite] = []
    for s in sites:
        key = (s.file, s.line, s.column)
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


def _group_sites_by_file(
    sites: list[RenameSite],
) -> dict[str, list[RenameSite]]:
    groups: dict[str, list[RenameSite]] = {}
    for s in sites:
        groups.setdefault(s.file, []).append(s)
    return groups


def _has_unknown_cols(line_sites: list[Any]) -> bool:
    """Return True if any site has an unknown column or line position."""
    return any(s.column < 0 or s.line <= 0 for s in line_sites)


def _apply_col_rename(
    line_text: str, col: int, name_len: int, old_name: str, new_name: str
) -> str:
    """Apply a single-column rename to line_text if the candidate matches."""
    if col + name_len > len(line_text):
        return line_text
    before = line_text[:col]
    after = line_text[col + name_len :]
    if line_text[col : col + name_len] == old_name:
        return before + new_name + after
    return line_text


def _apply_rename_to_file(
    file_path: str, sites: list[RenameSite], old_name: str, new_name: str
) -> bool:
    abs_path = file_path if os.path.isabs(file_path) else file_path
    try:
        with open(abs_path) as f:
            content = f.read()
    except OSError:
        return False

    lines = content.split("\n")
    name_len = len(old_name)
    site_by_line: dict[int, list[RenameSite]] = {}
    for s in sites:
        key = 0 if s.line <= 0 else s.line - 1
        site_by_line.setdefault(key, []).append(s)

    for line_idx, line_sites in site_by_line.items():
        if line_idx < 0 or line_idx >= len(lines):
            continue
        line_text = lines[line_idx]
        col_set = {s.column for s in line_sites if s.column >= 0}
        columns = sorted(col_set, reverse=True)
        if not columns and _has_unknown_cols(line_sites):
            raw_positions = _scan_line_for_name(line_text, old_name)
            unique_positions = set(raw_positions)
            columns = sorted(unique_positions, reverse=True)

        for col in columns:
            line_text = _apply_col_rename(line_text, col, name_len, old_name, new_name)
        lines[line_idx] = line_text

    new_content = "\n".join(lines)
    try:
        with open(abs_path, "w") as f:
            f.write(new_content)
        return True
    except OSError:
        return False


def _read_backup(abs_path: str) -> str | None:
    """Read file content for rollback backup; return None on OSError."""
    try:
        with open(abs_path) as f:
            return f.read()
    except OSError:
        return None


def _rollback_file(fpath: str, orig_content: str, root: str) -> None:
    """Restore a single file to its original content during rollback."""
    abs_path = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
    try:
        with open(abs_path, "w") as f:
            f.write(orig_content)
    except OSError:
        pass


def rename_symbol(
    cache: Any,
    old_name: str,
    new_name: str,
    dry_run: bool = True,
    project_root: str | None = None,
) -> RenameResult:
    from .symbol_resolver import SymbolResolver

    root = project_root or cache.project_root
    resolver = SymbolResolver(cache)
    resolve_result = resolver.find_references(old_name)

    raw_sites = _collect_rename_sites_from_resolver(resolve_result, old_name, root)
    sites = _deduplicate_sites(raw_sites)

    result = RenameResult(
        symbol=old_name,
        new_name=new_name,
        dry_run=dry_run,
        sites=sites,
    )

    if not sites:
        return result

    if dry_run:
        return result

    by_file = _group_sites_by_file(sites)
    files_changed = 0
    errors: list[str] = []
    backup: dict[str, str] = {}

    for fpath, file_sites in by_file.items():
        abs_path = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
        content = _read_backup(abs_path)
        if content is None:
            errors.append(f"Cannot read {fpath}")
            continue
        backup[fpath] = content

        ok = _apply_rename_to_file(abs_path, file_sites, old_name, new_name)
        if ok:
            files_changed += 1
        if not ok:
            errors.append(f"Failed to write {fpath}")

    if errors:
        for fpath, orig_content in backup.items():
            _rollback_file(fpath, orig_content, root)

    result.files_changed = files_changed
    result.sites_renamed = sum(len(s) for s in by_file.values())
    result.errors = errors
    return result
