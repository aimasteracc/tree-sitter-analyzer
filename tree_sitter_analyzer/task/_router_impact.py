"""Diff impact 阶段的路由与状态归一化。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import _router_wire
from ._router_session import (
    RouteSession,
    degraded_unknown,
    request_hash,
    with_evidence,
)
from .evidence import SourceSnapshotRecord
from .models import DiffInput
from .projection import StepFragment
from .truth_table import FRESH, UNKNOWN, contribute

_SOURCE_GENERATION_MISMATCH = "SOURCE_GENERATION_MISMATCH"


@dataclass(frozen=True, slots=True)
class ImpactResult:
    """供 constraints、fan-out 与最终 subject 使用的已归一化结果。"""

    diff_source: str
    changed_paths: tuple[str, ...]
    assessed_scope_paths: tuple[str, ...]
    changed_records: tuple[Any, ...]


async def run_impact_stage(*, session: RouteSession, diff: DiffInput) -> ImpactResult:
    """执行 edit.impact，并在任何停止判定前保存可清理的租约。"""
    arguments = {
        "mode": "diff" if diff.source == "workspace" else "staged",
        "scope_paths": list(diff.scope_paths),
        "include_tests": True,
        "resource_profile": "local_low_impact",
        "access_mode": "read_existing",
        "output_format": "json",
    }
    response = await session.call("diff:edit.impact", "edit", "impact", arguments)
    if response is None:
        session.record_not_called("diff:edit.impact", "edit", "impact")
        session.stopped = True
        return ImpactResult(diff.source, (), (), ())

    result, changed_records, assessed_valid = _normalize_response(
        session, diff, response
    )
    failure = _failure_reason(session, response, changed_records, assessed_valid)
    if failure is not None:
        reason, success = failure
        _record_failure(
            session,
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            success=success,
            reason=reason,
        )
    else:
        _record_success(
            session,
            response=response,
            arguments=arguments,
            snapshots=session.current_snapshots(),
            changed_records=changed_records or [],
        )
    return result


def _normalize_response(
    session: RouteSession,
    diff: DiffInput,
    response: dict[str, Any],
) -> tuple[ImpactResult, list[Any] | None, bool]:
    """先保存租约，再归一化供下游消费的 impact 字段。"""
    snapshot_state = session.snapshots
    snapshot_state.diff_snapshot_id = response.get("diff_snapshot_id")
    snapshot_state.route_lease_id = response.get("route_lease_id")
    snapshot_state.impact_source_generation = response.get("source_generation")
    _normalize_snapshot_tokens(session)

    raw_changed_records = response.get("changed_records")
    changed_records = (
        raw_changed_records if isinstance(raw_changed_records, list) else None
    )
    raw_assessed_scope_paths = response.get("assessed_scope_paths")
    assessed_valid = isinstance(raw_assessed_scope_paths, list)
    assessed_items = (
        raw_assessed_scope_paths if isinstance(raw_assessed_scope_paths, list) else []
    )
    assessed_scope_paths = tuple(
        path for path in assessed_items if isinstance(path, str)
    )
    changed_paths = tuple(
        record["path"]
        for record in (changed_records or [])
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    )
    result = ImpactResult(
        diff_source=diff.source,
        changed_paths=changed_paths,
        assessed_scope_paths=assessed_scope_paths,
        changed_records=tuple(changed_records or ()),
    )
    return result, changed_records, assessed_valid


def _failure_reason(
    session: RouteSession,
    response: dict[str, Any],
    changed_records: list[Any] | None,
    assessed_valid: bool,
) -> tuple[str, bool] | None:
    """返回停止原因和 primitive success 标记；成功时返回空。"""
    snapshot_state = session.snapshots
    access_unavailable = _router_wire.access_unavailable(response)
    if access_unavailable is not None:
        return f"ACCESS_UNAVAILABLE:{access_unavailable}", True
    if response.get("success") is not True:
        return "PRIMITIVE_FAILURE", False
    missing_fields = (
        snapshot_state.diff_snapshot_id is None
        or snapshot_state.route_lease_id is None
        or snapshot_state.impact_source_generation is None
        or changed_records is None
        or not assessed_valid
    )
    if missing_fields:
        return "MISSING_SNAPSHOT_FIELDS", True
    if (
        snapshot_state.index_source_generation is not None
        and snapshot_state.impact_source_generation
        != snapshot_state.index_source_generation
    ):
        return _SOURCE_GENERATION_MISMATCH, True
    return None


def _normalize_snapshot_tokens(session: RouteSession) -> None:
    """把空值或非字符串令牌归一化为缺失。"""
    snapshot_state = session.snapshots
    if (
        not isinstance(snapshot_state.diff_snapshot_id, str)
        or not snapshot_state.diff_snapshot_id
    ):
        snapshot_state.diff_snapshot_id = None
    if (
        not isinstance(snapshot_state.route_lease_id, str)
        or not snapshot_state.route_lease_id
    ):
        snapshot_state.route_lease_id = None
    if (
        not isinstance(snapshot_state.impact_source_generation, str)
        or not snapshot_state.impact_source_generation
    ):
        snapshot_state.impact_source_generation = None


def _record_failure(
    session: RouteSession,
    *,
    response: dict[str, Any],
    arguments: dict[str, Any],
    snapshots: list[SourceSnapshotRecord],
    success: bool,
    reason: str,
) -> None:
    """记录失败贡献并关闭后续 diff 路由。"""
    contribution = contribute(
        row="diff:edit.impact",
        state="failed",
        kind="generic",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action="impact",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=snapshots,
        success=success,
    )
    session.add_unknown("diff:edit.impact", reason)
    session.stopped = True


def _record_success(
    session: RouteSession,
    *,
    response: dict[str, Any],
    arguments: dict[str, Any],
    snapshots: list[SourceSnapshotRecord],
    changed_records: list[Any],
) -> None:
    """记录成功贡献、证据与下游计划片段。"""
    freshness = FRESH if session.snapshots.oracle_fresh else UNKNOWN
    impact_verdict = response.get("verdict")
    contribution = contribute(
        row="diff:edit.impact",
        state="succeeded",
        kind="generic",
        finding=_router_wire.finding_from_verdict(impact_verdict),
        freshness=freshness,
        truncated=response.get("truncated") is True,
        primitive_verdict=_router_wire.primitive_verdict(impact_verdict),
    )
    evidence_id, evidence_code = session.mint_evidence(
        "diff:edit.impact", "edit", "impact", response, None
    )
    if evidence_code == "action_version_missing":
        contribution = degraded_unknown(contribution)
    else:
        contribution = with_evidence(contribution, evidence_id)
    session.record_contribution(
        contribution,
        facade="edit",
        action="impact",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[evidence_id] if evidence_id else [],
        snapshots=snapshots,
        success=True,
    )
    for record in changed_records:
        if isinstance(record, dict) and isinstance(record.get("path"), str):
            session.ledger.step_fragments.append(
                StepFragment(
                    route="edit.impact",
                    path=record["path"],
                    symbol=None,
                    locator=record["path"],
                    evidence_id=evidence_id,
                )
            )
