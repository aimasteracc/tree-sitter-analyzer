"""架构约束阶段的路由、快照校验与证据记录。"""

from __future__ import annotations

from typing import Any

from . import _router_wire
from ._router_session import RouteSession, request_hash, with_evidence
from .evidence import SourceSnapshotRecord
from .projection import StepFragment
from .truth_table import FRESH, NOT_APPLICABLE, UNKNOWN, Finding, contribute

_SOURCE_GENERATION_MISMATCH = "SOURCE_GENERATION_MISMATCH"


async def run_constraints_stage(
    *,
    session: RouteSession,
    assessed_scope_paths: tuple[str, ...],
) -> None:
    """执行 edit.constraints，并把全部判断写入会话账本。"""
    snapshot = session.snapshots
    if not snapshot.diff_snapshot_id or not snapshot.route_lease_id:
        return
    if snapshot.index_snapshot_id is None or snapshot.index_source_generation is None:
        session.record_not_called(
            "diff:edit.constraints", "edit", "constraints", kind="constraints"
        )
        session.add_unknown(
            "diff:edit.constraints", "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
        )
        session.stopped = True
        return

    arguments = {
        "diff_snapshot_id": snapshot.diff_snapshot_id,
        "snapshot_id": snapshot.index_snapshot_id,
        "source_generation": snapshot.index_source_generation,
        "scope_paths": list(assessed_scope_paths),
        "persist": False,
        "access_mode": "read_existing",
        "output_format": "json",
    }
    response = await session.call(
        "diff:edit.constraints", "edit", "constraints", arguments
    )
    if response is None:
        session.record_not_called(
            "diff:edit.constraints", "edit", "constraints", kind="constraints"
        )
        session.stopped = True
        return

    access_unavailable = _router_wire.access_unavailable(response)
    if access_unavailable is not None:
        _record_failure(
            session,
            response=response,
            arguments=arguments,
            records=_router_wire.echo_records(response),
            reason=f"ACCESS_UNAVAILABLE:{access_unavailable}",
            success=True,
        )
        return

    records = _router_wire.echo_records(response)
    violations = [
        dict(item)
        for item in response.get("violations") or []
        if isinstance(item, dict)
    ]
    if response.get("success") is not True:
        _record_failure(
            session,
            response=response,
            arguments=arguments,
            records=records,
            reason="PRIMITIVE_FAILURE",
            success=False,
        )
        return

    diff_echo_ok = _diff_echo_matches(session, records)
    state = response.get("state")
    if state == "not_applicable" and response.get("reason") == "NO_CONFIG":
        if not diff_echo_ok:
            _record_failure(
                session,
                response=response,
                arguments=arguments,
                records=records,
                reason=_SOURCE_GENERATION_MISMATCH,
                success=True,
            )
        else:
            _record_no_config(session, response, arguments, records)
        return

    index_echo_ok = _router_wire.echo_matches(
        records,
        snapshot.index_snapshot_id,
        snapshot.index_source_generation,
    )
    if not diff_echo_ok or not index_echo_ok:
        _record_failure(
            session,
            response=response,
            arguments=arguments,
            records=records,
            reason=_SOURCE_GENERATION_MISMATCH,
            success=True,
        )
        return

    _record_success(
        session,
        response=response,
        arguments=arguments,
        records=records,
        violations=violations,
        state=state,
    )


def _diff_echo_matches(
    session: RouteSession, records: list[SourceSnapshotRecord]
) -> bool:
    """检查响应是否回显当前 impact 绑定的差分快照。"""
    snapshot = session.snapshots
    return any(
        record.kind == "diff"
        and record.snapshot_id == snapshot.diff_snapshot_id
        and record.source_generation == snapshot.impact_source_generation
        for record in records
    )


def _record_failure(
    session: RouteSession,
    *,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
    reason: str,
    success: bool,
) -> None:
    """记录约束阶段失败，并阻止依赖快照的后续 fan-out。"""
    contribution = contribute(
        row="diff:edit.constraints",
        state="failed",
        kind="constraints",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action="constraints",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=records,
        success=success,
    )
    session.add_unknown("diff:edit.constraints", reason)
    session.stopped = True


def _record_no_config(
    session: RouteSession,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
) -> None:
    """记录没有约束配置时已完成且不适用的结果。"""
    contribution = contribute(
        row="diff:edit.constraints",
        state="succeeded",
        kind="constraints",
        finding="no_config",
        freshness=NOT_APPLICABLE,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action="constraints",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=records,
        success=True,
    )


def _record_success(
    session: RouteSession,
    *,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
    violations: list[dict[str, Any]],
    state: Any,
) -> None:
    """按响应顺序记录约束违反项、证据和计划片段。"""
    finding: Finding = "violation" if state == "applicable" and violations else "none"
    contribution = contribute(
        row="diff:edit.constraints",
        state="succeeded",
        kind="constraints",
        finding=finding,
        freshness=FRESH if session.snapshots.oracle_fresh else UNKNOWN,
        truncated=False,
        primitive_verdict=_router_wire.primitive_verdict(response.get("verdict")),
        violations=violations,
    )
    evidence_ids: list[str] = []
    for item in violations:
        violation_path = item.get("path")
        if not isinstance(violation_path, str):
            violation_path = item.get("caller_file")
        if not isinstance(violation_path, str):
            continue
        violation_symbol = item.get("symbol")
        if not isinstance(violation_symbol, str):
            violation_symbol = item.get("caller_name")
        evidence_id, evidence_code = session.mint_evidence(
            "diff:edit.constraints",
            "edit",
            "constraints",
            response,
            violation_path,
            fragment=item,
            snapshots=records,
        )
        if evidence_code == "budget_exhausted":
            continue
        if evidence_id is not None:
            evidence_ids.append(evidence_id)
        session.ledger.step_fragments.append(
            StepFragment(
                route="edit.constraints",
                path=violation_path,
                symbol=violation_symbol,
                locator=violation_path,
                evidence_id=evidence_id,
            )
        )
    contribution = with_evidence(
        contribution, evidence_ids[0] if evidence_ids else None
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action="constraints",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=evidence_ids,
        snapshots=records,
        success=True,
    )
