"""发布前源码复核：只在文件集合或内容真正不同时拒绝发布，并给出有界差异（#1595）。

复核快照曾与首次捕获共用 5 s 墙钟发现预算。实测 2,798 个目录项的 Windows
工作树空闲时就要 2.6–3.0 s（``realpath`` 逐文件打开句柄占大头），244 s 的构建
之后机器负载升高即可越界；越界产生的 ``discovery_error`` 被当作“源码已变化”，
在未改动的树上误报 ``INDEX_GENERATION_SOURCE_CHANGED``。

复核的发现预算因此按首次捕获的目录项数线性放宽（实测成本约 1 ms/项，取 10 ms/项）；
仍越界时报告“复核未完成”，而不是“源码已变化”。两者都失败关闭、绝不发布（RFC-0032）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from ..discovery_budget import discovery_budget_seconds
from ..indexing_snapshot import (
    _PERMANENT_SOURCE_REJECTIONS,
    IndexCandidateSnapshot,
    IndexSnapshotEntry,
)
from .admission import ADMISSION_CODES, INDEX_CANDIDATE_SUPERSEDED, RETRY_AFTER_MS

SOURCE_CHANGED = "INDEX_GENERATION_SOURCE_CHANGED"
SOURCE_RECHECK_INCOMPLETE = "INDEX_GENERATION_SOURCE_RECHECK_INCOMPLETE"
MAX_REPORTED_CHANGES = 20
_Pairs = tuple[tuple[str, object], ...]


class SourceChanged(RuntimeError):
    """候选不能发布：源码确实变化，或复核无法给出权威结论；两者都可直接重试。"""

    def __init__(self, code: str, changes: list[str]) -> None:
        super().__init__(code)
        self.code = code
        self.total = len(changes)
        self.changes = tuple(changes[:MAX_REPORTED_CHANGES])


def permanent_rejections_only(snapshot: IndexCandidateSnapshot) -> bool:
    """只有已明确永久拒绝的路径允许发布清理结果，不能包含临时发现失败。"""
    errors = [entry for entry in snapshot.entries if entry.decision == "error"]
    return (
        bool(errors)
        and not snapshot.discovery_error
        and snapshot.errors == len(errors)
        and all(entry.reason in _PERMANENT_SOURCE_REJECTIONS for entry in errors)
    )


def source_contents(snapshot: IndexCandidateSnapshot) -> tuple[object, ...]:
    """通用 DTO 比较忽略摘要和描述符链，发布边界必须显式纳入二者。"""
    return tuple(
        (
            entry.rel_path,
            (entry.fingerprint.content_hash, entry.fingerprint.descriptor_chain)
            if entry.fingerprint is not None
            else None,
        )
        for entry in snapshot.selected_entries
    )


def recheck_discovery_seconds(previous: IndexCandidateSnapshot) -> float:
    """复核快照的发现预算（秒），随首次捕获的目录项数增长。"""
    return discovery_budget_seconds(previous.discovered)


def _entry_state(entry: IndexSnapshotEntry) -> tuple[object, ...]:
    return (entry.decision, entry.reason, entry.language, entry.fingerprint)


def _entry_changes(
    previous: IndexCandidateSnapshot, current: IndexCandidateSnapshot
) -> list[str]:
    before = {entry.rel_path: _entry_state(entry) for entry in previous.entries}
    after = {entry.rel_path: _entry_state(entry) for entry in current.entries}
    changes = [f"added: {path}" for path in sorted(after.keys() - before.keys())]
    changes += [f"removed: {path}" for path in sorted(before.keys() - after.keys())]
    for path in sorted(before.keys() & after.keys()):
        if before[path] != after[path]:
            old, new = before[path][0], after[path][0]
            changes.append(
                f"modified: {path}" if old == new else f"{old} -> {new}: {path}"
            )
    if not changes and current != previous:
        # 条目一致而计数器不同（如选择窗口截断），同样不是同一候选。
        changes.append(
            f"scope: discovered {previous.discovered} -> {current.discovered}, "
            f"limited {previous.limited} -> {current.limited}"
        )
    return changes


def _content_changes(
    expected: tuple[object, ...], actual: tuple[object, ...]
) -> list[str]:
    before: dict[str, object] = dict(cast(_Pairs, expected))
    after: dict[str, object] = dict(cast(_Pairs, actual))
    return [
        f"content: {path}"
        for path in sorted(before.keys() | after.keys())
        if before.get(path) != after.get(path)
    ]


def check_publication_sources(
    previous: IndexCandidateSnapshot,
    current: IndexCandidateSnapshot,
    expected_contents: tuple[object, ...],
    bind_contents: Callable[[], tuple[object, ...]],
    *,
    allow_permanent_rejections: bool,
) -> None:
    """复核快照与候选的文件集合、元数据和内容摘要必须完全一致，否则抛出。"""
    if current.discovery_error:
        raise SourceChanged(
            SOURCE_RECHECK_INCOMPLETE, [f"discovery: {current.discovery_error}"]
        )
    changes = _entry_changes(previous, current)
    if current.root_identity != previous.root_identity:
        changes.append("root: project root identity changed")
    if not changes:
        changes = _content_changes(expected_contents, bind_contents())
    if (
        not changes
        and current.errors
        and not (allow_permanent_rejections and permanent_rejections_only(current))
    ):
        changes = [
            f"rejected: {entry.rel_path}"
            for entry in current.entries
            if entry.decision == "error"
        ]
    if changes:
        raise SourceChanged(SOURCE_CHANGED, changes)


def source_changed_next_step(exc: SourceChanged) -> str:
    """给调用方的可执行下一步：父版本不变，直接重试同一索引调用。"""
    if exc.code == SOURCE_RECHECK_INCOMPLETE:
        reason = "the pre-publish source recheck could not finish"
    else:
        reason = f"{exc.total} source path(s) changed while the index was built"
    return (
        f"Nothing was published and the previous index is still active: {reason}. "
        "Retry the same index call; if it keeps failing, stop the process that "
        "is modifying the listed files or exclude them with exclude_patterns."
    )


def source_changed_failure(exc: SourceChanged) -> dict[str, Any]:
    """``index action=cache`` 等直接写入口的类型化可重试失败（#1595）。

    源码确实变化时候选已过时：``error_code`` 为 RFC-0032 准入码
    ``INDEX_CANDIDATE_SUPERSEDED``，原因码保留在 ``error`` 与 ``cause_code``。
    复核未完成不是准入失败，仍以自身代码报告。
    """
    next_step = source_changed_next_step(exc)
    summary_line = f"index not published: {exc.code} ({exc.total} change(s))"
    typed: dict[str, Any] = {"error_code": exc.code, "retryable": True}
    if exc.code == SOURCE_CHANGED:
        typed = {
            "error_code": INDEX_CANDIDATE_SUPERSEDED,
            "cause_code": exc.code,
            "retryable": True,
            "retry_after_ms": RETRY_AFTER_MS,
            "next_action": ADMISSION_CODES[INDEX_CANDIDATE_SUPERSEDED].next_action,
        }
    return {
        "success": False,
        "verdict": "ERROR",
        "published": False,
        "error": exc.code,
        **typed,
        "changes": list(exc.changes),
        "changes_total": exc.total,
        "changes_truncated": exc.total > len(exc.changes),
        "next_step": next_step,
        "summary_line": summary_line,
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": next_step,
        },
    }
