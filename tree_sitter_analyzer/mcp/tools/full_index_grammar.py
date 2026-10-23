"""完整索引遇到未安装的可选语法时的发布说明（#1562）。

缺少可选语法是稳定的单文件失败：重试同一字节只会得到同一失败。按 #1554 的
发布规则，它不应扣下其余文件的索引；结果照常发布，但完整性标为
``incomplete``，并在 ``next_step`` 中写明缺了哪些文件、该装什么。
"""

from __future__ import annotations

from typing import Any

#: next_step 中列出的失败文件上限；总数始终写明。
_LISTED_FILES = 3


def missing_grammar_failures(phases: dict[str, Any]) -> list[tuple[str, str]]:
    """按文件去重的 (文件, 原因)；各阶段可能重复报告同一文件。"""
    seen: dict[str, str] = {}
    for phase in phases.values():
        if not isinstance(phase, dict):
            continue
        for detail in phase.get("error_details") or []:
            file_path = str(detail.get("file") or "")
            if file_path and file_path not in seen:
                seen[file_path] = str(detail.get("reason") or "")
    return sorted(seen.items())


def missing_grammar_next_step(phases: dict[str, Any]) -> str:
    """已发布但缺少可选语法文件时的可执行下一步。"""
    failures = missing_grammar_failures(phases)
    listed = "; ".join(f"{path}: {reason}" for path, reason in failures[:_LISTED_FILES])
    more = (
        f"; and {len(failures) - _LISTED_FILES} more"
        if len(failures) > _LISTED_FILES
        else ""
    )
    return (
        f"Published without {len(failures)} file(s) whose optional grammar is not "
        f"installed ({listed}{more}). Install the extra and re-run index "
        "action=full; graph answers about those files stay incomplete until then."
    )
