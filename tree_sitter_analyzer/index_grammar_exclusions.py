"""#1581：因缺少可选语法而无法入索引的文件，及其如实的下一步。

缺少可选语法（swift、lua 等）是环境决定的稳定单文件失败（#1565
``failure_kind: stable``）：同一环境里重跑索引只会得到同一失败。#1576 让其余
文件照常发布，但清单认证要求源码清单与索引行逐一相等，这些文件不入行，
索引因而停在 ``partial``。此前状态答复建议"重新运行全量索引"，重跑后依旧
partial，智能体陷入循环，依赖完整认证的 Pulse 也永远不可用。

本模块只做读侧说明，不改变认证语义：被排除的文件仍使完整性保持非
``complete``——从不对未入索引的文件宣称完整。它找出这些文件与需安装的
extra，供状态与 Pulse 把下一步写成"安装 X"，而不是"重跑全量"。

判定使用解析器自身拒绝该文件时的同一谓词（``core.parser`` 的
``is_grammar_installed``），所以说明与真实失败一致；只有存在缺失语法时才遍历
目录（仅文件名、有时间上界），完整索引或语法齐全时零额外开销。
"""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass
from typing import Any

from .cache.indexer import (
    _DEFAULT_EXCLUDE_PATTERNS,
    _EXT_TO_LANG,
    _language_from_ext,
    _normalize_relative_path,
    _walk_source_files,
)
from .core import parser as _core_parser
from .language_loader import grammar_install_hint

#: 答复中逐一列出的文件上限；总数始终写明。
_LISTED_FILES = 5
#: 仅文件名遍历的时间上界；超出时如实返回"未知"，不猜测。
_WALK_DEADLINE_SECONDS = 3.0

#: 完整性未认证时可能由排除文件造成的原因；并发写入、过期等不在此列。
INCOMPLETE_REASONS = frozenset(
    {
        "CALL_GRAPH_INCOMPLETE",
        "INDEX_SNAPSHOT_INCOMPLETE",
        "NO_EXACT_FULL_INDEX_MANIFEST",
        "SOURCE_SCOPE_DESCRIPTOR_MISSING",
    }
)


@dataclass(frozen=True, slots=True)
class GrammarExclusions:
    """需要未安装可选语法的文件（已排序）及各语言对应的安装提示。"""

    files: tuple[tuple[str, str], ...]
    hints: tuple[tuple[str, str], ...]

    def payload(self) -> list[dict[str, str]]:
        """答复字段：前若干个文件及其原因；总数另由 ``excluded_file_count`` 给出。"""
        by_language = dict(self.hints)
        return [
            {"file": path, "language": language, "reason": by_language[language]}
            for path, language in self.files[:_LISTED_FILES]
        ]

    def next_step(self) -> str:
        """可执行的下一步：安装 extra；明确说明重跑索引不会改变结果。"""
        listed = ", ".join(path for path, _ in self.files[:_LISTED_FILES])
        more = (
            f", and {len(self.files) - _LISTED_FILES} more"
            if len(self.files) > _LISTED_FILES
            else ""
        )
        # 提示形如 "Swift grammar not installed — pip install ..."，只取安装命令。
        installs = "; ".join(hint.rpartition(" — ")[2] for _, hint in self.hints)
        return (
            f"The index stays partial because {len(self.files)} file(s) need an "
            f"optional grammar that is not installed ({listed}{more}). Re-running "
            "indexing without it reproduces the same partial index. To certify "
            f"the index: {installs}, then run index action=full. Until then "
            "certified reads (pulse, project-wide graph queries) refuse, and "
            "answers about the excluded files stay unknown; search action=symbol "
            "and nav action=resolve still return uncertified coordinates."
        )


def missing_grammar_languages() -> tuple[str, ...]:
    """可选语法未安装、且有安装提示的语言（已排序）。"""
    languages = {language for language in _EXT_TO_LANG.values() if language}
    return tuple(
        sorted(
            language
            for language in languages
            if grammar_install_hint(language) is not None
            and not _core_parser.is_grammar_installed(language)
        )
    )


def find_grammar_exclusions(project_root: str) -> GrammarExclusions | None:
    """返回需要缺失语法的源文件；没有则为空集合，遍历超时或失败返回 None。"""
    missing = frozenset(missing_grammar_languages())
    if not missing:
        return GrammarExclusions((), ())
    deadline = time.monotonic() + _WALK_DEADLINE_SECONDS
    files: list[tuple[str, str]] = []
    try:
        for abs_path in _walk_source_files(project_root):
            if time.monotonic() > deadline:
                return None
            language = _language_from_ext(abs_path)
            if language not in missing:
                continue
            rel_path = _normalize_relative_path(os.path.relpath(abs_path, project_root))
            if any(
                fnmatch.fnmatch(rel_path, pattern)
                for pattern in _DEFAULT_EXCLUDE_PATTERNS
            ):
                continue
            files.append((rel_path, str(language)))
    except OSError:
        return None
    used = sorted({language for _, language in files})
    hints = tuple((language, str(grammar_install_hint(language))) for language in used)
    return GrammarExclusions(tuple(sorted(files)), hints)


def explain_incomplete(
    project_root: str | None, reason: str | None
) -> GrammarExclusions | None:
    """完整性因上述原因未认证、且确有缺失语法文件时返回说明，否则返回 None。"""
    if not project_root or reason not in INCOMPLETE_REASONS:
        return None
    exclusions = find_grammar_exclusions(project_root)
    if exclusions is None or not exclusions.files:
        return None
    return exclusions


def with_exclusions(
    response: dict[str, Any], project_root: str | None
) -> dict[str, Any]:
    """返回补上排除文件与"安装 X"下一步的认证拒绝答复；无关时原样返回。"""
    evidence = response.get("source_evidence")
    reason = evidence.get("reason") if isinstance(evidence, dict) else None
    exclusions = explain_incomplete(project_root, reason)
    if exclusions is None:
        return response
    return {
        **response,
        "excluded_files": exclusions.payload(),
        "excluded_file_count": len(exclusions.files),
        "next_step": exclusions.next_step(),
    }
