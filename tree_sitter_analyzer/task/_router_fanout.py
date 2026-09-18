"""按文件执行 AST 差异与变更分类的 fan-out 阶段。"""

from __future__ import annotations

from typing import Any

from . import _router_wire
from ._router_session import (
    RouteSession,
    degraded_unknown,
    request_hash,
    with_evidence,
)
from .evidence import SourceSnapshotRecord
from .projection import StepFragment
from .truth_table import FRESH, UNKNOWN, Finding, RowKind, contribute

_SOURCE_GENERATION_MISMATCH = "SOURCE_GENERATION_MISMATCH"
_UNSUPPORTED_RECORD_STATUSES = frozenset(
    {"added", "deleted", "renamed", "A", "D", "R", "C"}
)
_STRUCTURAL_INVALID_VERDICTS = frozenset({"REVIEW", "UNSAFE"})


async def run_fanout_stage(
    *,
    session: RouteSession,
    changed_records: tuple[Any, ...],
) -> None:
    """按稳定路径顺序执行 ast_diff 与 classify，并记录全部结果。"""
    if session.stopped or session.snapshots.diff_snapshot_id is None:
        return
    eligible = _eligible_paths(session, changed_records)
    for path_index, path in enumerate(eligible):
        if not await _run_ast_diff(session, path, eligible[path_index:]):
            break
        if not await _run_classify(session, path, eligible[path_index + 1 :]):
            break


def _eligible_paths(
    session: RouteSession, changed_records: tuple[Any, ...]
) -> list[str]:
    """按输入顺序记录不支持项，并返回去重排序后的可分析路径。"""
    eligible: list[str] = []
    for record in changed_records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if not isinstance(path, str):
            continue
        unsupported = (
            record.get("binary") is True
            or record.get("status") in _UNSUPPORTED_RECORD_STATUSES
            or record.get("unsupported_kind") is not None
            or record.get("old_available") is False
            or record.get("new_available") is False
            or record.get("old_kind") not in (None, "file", "missing")
            or record.get("new_kind") not in (None, "file", "missing")
        )
        if unsupported:
            session.add_unknown(
                f"diff:edit.ast_diff:{path}", "not_run:UNSUPPORTED_DIFF_RECORD"
            )
            session.add_unknown(
                f"diff:edit.classify:{path}", "not_run:UNSUPPORTED_DIFF_RECORD"
            )
            continue
        eligible.append(path)
    return sorted(set(eligible))


async def _run_ast_diff(
    session: RouteSession,
    path: str,
    remaining_paths: list[str],
) -> bool:
    """执行一个 ast_diff；返回是否应继续当前路径的 classify。"""
    row = f"diff:edit.ast_diff:{path}"
    arguments = _arguments(session, path)
    response = await session.call(row, "edit", "ast_diff", arguments)
    if response is None:
        _record_remaining_not_called(session, remaining_paths)
        session.stopped = True
        return False

    access_unavailable = _router_wire.access_unavailable(response)
    if access_unavailable is not None:
        _record_failure(
            session,
            row=row,
            action="ast_diff",
            kind="structural",
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            success=True,
            reason=f"ACCESS_UNAVAILABLE:{access_unavailable}",
        )
        return True
    if response.get("success") is not True:
        _record_failure(
            session,
            row=row,
            action="ast_diff",
            kind="structural",
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            success=False,
            reason="PRIMITIVE_FAILURE",
        )
        return True

    records = _router_wire.echo_records(response)
    if not _diff_echo_matches(session, records):
        _record_failure(
            session,
            row=row,
            action="ast_diff",
            kind="structural",
            response=response,
            arguments=arguments,
            snapshots=records,
            success=True,
            reason=_SOURCE_GENERATION_MISMATCH,
            stop=True,
        )
        return False

    verdict = response.get("verdict")
    finding: Finding = (
        "invalid"
        if verdict in _STRUCTURAL_INVALID_VERDICTS
        else _router_wire.finding_from_verdict(verdict)
    )
    _record_success(
        session,
        row=row,
        action="ast_diff",
        kind="structural",
        path=path,
        response=response,
        arguments=arguments,
        records=records,
        finding=finding,
    )
    return True


async def _run_classify(
    session: RouteSession,
    path: str,
    remaining_paths: list[str],
) -> bool:
    """执行一个 classify；返回是否应继续后续路径。"""
    row = f"diff:edit.classify:{path}"
    arguments = _arguments(session, path)
    response = await session.call(row, "edit", "classify", arguments)
    if response is None:
        session.record_not_called(row, "edit", "classify")
        _record_remaining_not_called(session, remaining_paths)
        session.stopped = True
        return False

    access_unavailable = _router_wire.access_unavailable(response)
    if access_unavailable is not None:
        _record_failure(
            session,
            row=row,
            action="classify",
            kind="generic",
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            success=True,
            reason=f"ACCESS_UNAVAILABLE:{access_unavailable}",
        )
        return True
    if response.get("success") is not True:
        _record_failure(
            session,
            row=row,
            action="classify",
            kind="generic",
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            success=False,
            reason="PRIMITIVE_FAILURE",
        )
        return True

    records = _router_wire.echo_records(response)
    if not _diff_echo_matches(session, records):
        _record_failure(
            session,
            row=row,
            action="classify",
            kind="generic",
            response=response,
            arguments=arguments,
            snapshots=records,
            success=True,
            reason=_SOURCE_GENERATION_MISMATCH,
            stop=True,
        )
        return False

    _record_success(
        session,
        row=row,
        action="classify",
        kind="generic",
        path=path,
        response=response,
        arguments=arguments,
        records=records,
        finding=_router_wire.finding_from_verdict(response.get("verdict")),
    )
    return True


def _arguments(session: RouteSession, path: str) -> dict[str, Any]:
    """构造两个 fan-out 动作共享的固定请求参数。"""
    return {
        "diff_snapshot_id": session.snapshots.diff_snapshot_id,
        "file_path": path,
        "access_mode": "read_existing",
        "output_format": "json",
    }


def _diff_echo_matches(
    session: RouteSession, records: list[SourceSnapshotRecord]
) -> bool:
    """检查响应是否回显当前差分快照及其源代次。"""
    snapshot = session.snapshots
    return any(
        record.kind == "diff"
        and record.snapshot_id == snapshot.diff_snapshot_id
        and record.source_generation == snapshot.impact_source_generation
        for record in records
    )


def _record_remaining_not_called(
    session: RouteSession, remaining_paths: list[str]
) -> None:
    """按路径顺序记录尚未准入的 ast_diff 与 classify 行。"""
    for remaining in remaining_paths:
        session.record_not_called(
            f"diff:edit.ast_diff:{remaining}",
            "edit",
            "ast_diff",
            kind="structural",
        )
        session.record_not_called(f"diff:edit.classify:{remaining}", "edit", "classify")


def _record_failure(
    session: RouteSession,
    *,
    row: str,
    action: str,
    kind: RowKind,
    response: dict[str, Any],
    arguments: dict[str, Any],
    snapshots: list[SourceSnapshotRecord],
    success: bool,
    reason: str,
    stop: bool = False,
) -> None:
    """记录一个 fan-out 动作失败及其未知原因。"""
    contribution = contribute(
        row=row,
        state="failed",
        kind=kind,
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action=action,
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=snapshots,
        success=success,
    )
    session.add_unknown(row, reason)
    if stop:
        session.stopped = True


def _record_success(
    session: RouteSession,
    *,
    row: str,
    action: str,
    kind: RowKind,
    path: str,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
    finding: Finding,
) -> None:
    """记录成功贡献、证据与计划片段。"""
    contribution = contribute(
        row=row,
        state="succeeded",
        kind=kind,
        finding=finding,
        freshness=FRESH,
        truncated=response.get("truncated") is True,
        primitive_verdict=_router_wire.primitive_verdict(response.get("verdict")),
    )
    evidence_id, evidence_code = session.mint_evidence(
        row,
        "edit",
        action,
        response,
        path,
        snapshots=records,
    )
    if evidence_code == "action_version_missing":
        contribution = degraded_unknown(contribution)
    else:
        contribution = with_evidence(contribution, evidence_id, locator=path)
    session.record_contribution(
        contribution,
        facade="edit",
        action=action,
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[evidence_id] if evidence_id else [],
        snapshots=session.current_snapshots(),
        success=True,
    )
    session.ledger.step_fragments.append(
        StepFragment(
            route=f"edit.{action}",
            path=path,
            symbol=None,
            locator=path,
            evidence_id=evidence_id,
        )
    )
