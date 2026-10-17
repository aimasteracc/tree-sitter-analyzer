"""#1635：未解析的目标若定义在被索引排除的文件里，点名该文件与排除规则。

dogfood 第 6、7 轮：``tests/golden/corpus_python.py`` 中确实存在的函数答
``SYMBOL_NOT_DEFINED``，提示却让人刷新索引或改用相近的名字。被排除的文件
（默认规则 ``tests/golden/corpus_*`` 或建索引时传入的 ``exclude_patterns``）
刷新多少次都不会入索引，因此这里给出独立的原因码与正确的下一步。

只在目标未解析时运行：按与全量索引相同的发现规则遍历目录，只读取命中排除
模式的源码文件，用行首定义关键字（``def`` / ``class`` / ``function`` / ``func``
等）匹配名字。遍历超出预算或读取失败时返回 None——答案沿用
``SYMBOL_NOT_DEFINED``，始终是 ``unknown``，从不因此变成 complete。
"""

from __future__ import annotations

import fnmatch
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

#: 目标的定义位于被索引排除的源码文件中。
EXCLUDED_REASON = "SYMBOL_IN_EXCLUDED_FILE"

#: 目录项预算，与 unindexed_sources 的遍历一致。
_ENTRY_BUDGET = 100_000
#: 路径字节预算，与 unindexed_sources 的遍历一致。
_PATH_BYTE_BUDGET = 16 * 1024 * 1024
#: 最多读取的被排除源码文件数；超出即放弃（沿用 SYMBOL_NOT_DEFINED）。
_FILES_CAP = 2_000
#: 单个文件的读取上限（字节）。
_FILE_BYTES_CAP = 4 * 1024 * 1024
#: 行首定义关键字；Go 的接收者 ``func (r *T) name`` 也匹配。
_DEFINITION_KEYWORDS = (
    "def|class|function|func|fn|sub|struct|interface|trait|enum|object|module"
)
#: 会入索引的 MCP / CLI 重建命令（关闭默认排除）。
_INCLUDE_DEFAULTS_COMMAND = (
    "`index action=full no_default_excludes=true` "
    "(CLI: `--full-index --full-index-no-default-excludes`)"
)


@dataclass(frozen=True)
class ExcludedDefinition:
    """被排除文件中的定义位置与排除它的模式。"""

    file: str
    line: int
    exclude_pattern: str
    default_exclude: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "exclude_pattern": self.exclude_pattern,
            "default_exclude": self.default_exclude,
        }


def excluded_definition(
    cache: Any, project_root: str, func_name: str, file_path: str | None
) -> ExcludedDefinition | None:
    """目标在被排除文件中的定义；没有、无法确认或超出预算时为 None。"""
    from ...index_source_scope import default_exclude_patterns
    from .unindexed_sources import effective_excludes

    owner, _sep, bare = func_name.rpartition(".")
    if not bare:
        return None
    try:
        excludes = sorted(effective_excludes(cache.get_conn()))
    except (sqlite3.Error, AttributeError):
        # 读取失败只是不改写原答案（仍为 SYMBOL_NOT_DEFINED）。
        return None
    if not excludes:
        return None
    files = _excluded_sources(project_root, excludes, file_path)
    if files is None:
        return None
    defaults = default_exclude_patterns()
    definition = _definition_pattern(bare)
    owner_pattern = _definition_pattern(owner.rpartition(".")[2]) if owner else None
    for rel_path, pattern in files:
        line = _definition_line(project_root, rel_path, definition, owner_pattern)
        if line is not None:
            return ExcludedDefinition(rel_path, line, pattern, pattern in defaults)
    return None


def _definition_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"^[ \t]*(?:(?:export|default|pub|public|private|protected|static|async)"
        rf"[ \t]+)*(?:{_DEFINITION_KEYWORDS})[ \t]+(?:\([^)\n]*\)[ \t]*)?"
        rf"{re.escape(name)}(?![\w$])",
        re.MULTILINE,
    )


def _matching_pattern(rel_path: str, excludes: list[str]) -> str | None:
    return next((p for p in excludes if fnmatch.fnmatch(rel_path, p)), None)


def _excluded_sources(
    project_root: str, excludes: list[str], file_path: str | None
) -> list[tuple[str, str]] | None:
    """命中排除模式的源码文件 ``(相对路径, 模式)``；遍历失败或超出上限为 None。"""
    from ...project_graph import _language_from_ext

    if file_path:
        # 调用方点名了文件：只看这个文件，不去别处找同名定义。
        rel_path = _relative(project_root, file_path)
        pattern = _matching_pattern(rel_path, excludes)
        if pattern is None or _language_from_ext(rel_path) is None:
            return []
        return [(rel_path, pattern)]
    from ...constants import EXCLUDE_DIRS
    from ...index_candidate_walker import (
        CandidateDiscoveryBudgetExceeded,
        CandidateDiscoveryError,
        walk_candidate_entries,
    )

    found: list[tuple[str, str]] = []
    try:
        for abs_path in walk_candidate_entries(
            project_root,
            excluded_dir_names=frozenset(EXCLUDE_DIRS),
            entry_budget=_ENTRY_BUDGET,
            path_byte_budget=_PATH_BYTE_BUDGET,
            discovery_seconds=None,
            budget_error=EXCLUDED_REASON,
        ):
            if _language_from_ext(abs_path) is None:
                continue
            rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
            pattern = _matching_pattern(rel_path, excludes)
            if pattern is None:
                continue
            found.append((rel_path, pattern))
            if len(found) > _FILES_CAP:
                return None
    except (CandidateDiscoveryBudgetExceeded, CandidateDiscoveryError, OSError):
        return None
    return sorted(found)


def _relative(project_root: str, file_path: str) -> str:
    path = file_path
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, project_root)
        except ValueError:
            pass
    return path.replace("\\", "/")


def _definition_line(
    project_root: str,
    rel_path: str,
    definition: re.Pattern[str],
    owner: re.Pattern[str] | None,
) -> int | None:
    """``rel_path`` 中名字的定义行；限定名还要求文件里定义了所有者。"""
    try:
        with open(os.path.join(project_root, rel_path), "rb") as handle:
            data = handle.read(_FILE_BYTES_CAP)
    except OSError:
        return None
    text = data.decode("utf-8", "replace")
    match = definition.search(text)
    if match is None or (owner is not None and owner.search(text) is None):
        return None
    return text.count("\n", 0, match.start()) + 1


def excluded_hint(func_name: str, found: ExcludedDefinition) -> str:
    """点名文件与规则：刷新不会把它入索引，下一步是直接读或带上它重建。"""
    if found.default_exclude:
        rule = f"built-in default exclude pattern {found.exclude_pattern!r}"
        rebuild = (
            f"rebuild the index without the default excludes: "
            f"{_INCLUDE_DEFAULTS_COMMAND}"
        )
    else:
        rule = f"exclude pattern {found.exclude_pattern!r}"
        rebuild = (
            "rebuild the index without the exclude pattern "
            f"{found.exclude_pattern!r} (`index action=full` with exclude_patterns "
            "that omit it)"
        )
    return (
        f"Symbol {func_name!r} is defined in {found.file}:{found.line}, which the "
        f"index excludes ({rule}), so 0 callers is not evidence of absence and "
        f"refreshing the index will not include it. Read the file directly, or "
        f"{rebuild}."
    )
