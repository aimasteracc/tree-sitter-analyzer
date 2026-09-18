"""执行任务文本路由，并把结果写入共享路由会话。"""

from __future__ import annotations

from typing import Any, Literal

from ._router_session import RouteSession, degraded_unknown, request_hash, with_evidence
from ._router_wire import (
    access_unavailable,
    echo_matches,
    echo_records,
    finding_from_verdict,
    primitive_verdict,
)
from .evidence import SourceSnapshotRecord
from .projection import StepFragment
from .route_table import SAFE_FANOUT_CAPS
from .truth_table import FRESH, UNKNOWN, Contribution, contribute

SOURCE_GENERATION_MISMATCH = "SOURCE_GENERATION_MISMATCH"


def _record_missing_snapshot(session: RouteSession, operation: str) -> None:
    """记录缺少权威索引快照时未调用的上下文原语。"""
    row = f"{operation}:nav.context"
    contribution = contribute(
        row=row,
        state="not_called",
        kind="generic",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=None,
    )
    session.record_contribution(
        contribution,
        facade="nav",
        action="context",
        response=None,
        request_hash=request_hash({}),
        evidence_ids=[],
        snapshots=[],
        success=True,
    )
    session.add_unknown(row, "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE")


def _nav_arguments(session: RouteSession, task: str) -> dict[str, Any]:
    """用会话快照构造固定的 nav.context 参数。"""
    snapshots = session.snapshots
    return {
        "task": task,
        "max_nodes": 12 if session.budget.profile == "compact" else 30,
        "max_code_blocks": 3 if session.budget.profile == "compact" else 5,
        "include_graph": False,
        "access_mode": "read_existing",
        "snapshot_id": snapshots.index_snapshot_id,
        "source_generation": snapshots.index_source_generation,
        "output_format": "json",
    }


def _record_nav_failure(
    session: RouteSession,
    operation: str,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
    *,
    reason: str,
    success: bool,
) -> None:
    """按固定字段记录 nav.context 失败，并停止后续任务路由。"""
    row = f"{operation}:nav.context"
    contribution = contribute(
        row=row,
        state="failed",
        kind="generic",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="nav",
        action="context",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=records,
        success=success,
    )
    session.add_unknown(row, reason)
    session.stopped = True


def _record_nav_blocks(
    session: RouteSession,
    operation: str,
    response: dict[str, Any],
    records: list[SourceSnapshotRecord],
    contribution: Contribution,
) -> list[str]:
    """把上下文代码块投影为证据、步骤片段和相关符号。"""
    block_paths: list[str] = []
    for block in response.get("code_blocks") or []:
        if not isinstance(block, dict):
            continue
        # CodeGraphContextTool 实际使用 file/name；这里兼容两套字段名。
        path = block.get("path")
        if not isinstance(path, str):
            path = block.get("file")
        symbol = block.get("symbol")
        if not isinstance(symbol, str):
            symbol = block.get("name")
        if isinstance(path, str):
            block_paths.append(path)
            if isinstance(symbol, str) and symbol:
                session.ledger.relevant_symbols.append(symbol)
        block_fragment = {
            "file": path,
            "name": symbol,
            "start_line": block.get("start_line"),
            "end_line": block.get("end_line"),
        }
        evidence_id, evidence_code = session.mint_evidence(
            f"{operation}:nav.context",
            "nav",
            "context",
            response,
            path if isinstance(path, str) else None,
            fragment=block_fragment,
            snapshots=records,
        )
        if evidence_code == "action_version_missing":
            contribution = degraded_unknown(contribution)
        session.ledger.step_fragments.append(
            StepFragment(
                route="nav.context",
                path=path if isinstance(path, str) else None,
                symbol=symbol if isinstance(symbol, str) else None,
                locator=path if isinstance(path, str) else None,
                evidence_id=None
                if evidence_code == "budget_exhausted"
                else evidence_id,
            )
        )
    session.ledger.relevant_paths.extend(block_paths)
    return block_paths


def _record_safe_failure(
    session: RouteSession,
    path: str,
    response: dict[str, Any],
    arguments: dict[str, Any],
    records: list[SourceSnapshotRecord],
    *,
    reason: str,
    success: bool,
) -> None:
    """记录单个 edit.safe 失败，但由调用方决定是否继续扇出。"""
    row = f"plan_change:edit.safe:{path}"
    contribution = contribute(
        row=row,
        state="failed",
        kind="generic",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="edit",
        action="safe",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=records,
        success=success,
    )
    session.add_unknown(row, reason)


async def _run_safe_path(
    session: RouteSession, path: str
) -> Literal["continue", "stop", "not_called"]:
    """执行一个 edit.safe 单元，并返回扇出控制信号。"""
    snapshots = session.snapshots
    arguments = {
        "file_path": path,
        "edit_type": "refactor",
        "snapshot_id": snapshots.index_snapshot_id,
        "source_generation": snapshots.index_source_generation,
        "access_mode": "read_existing",
        "output_format": "json",
    }
    response = await session.call(
        f"plan_change:edit.safe:{path}", "edit", "safe", arguments
    )
    if response is None:
        return "not_called"
    records = echo_records(response)
    unavailable = access_unavailable(response)
    if unavailable is not None:
        _record_safe_failure(
            session,
            path,
            response,
            arguments,
            records,
            reason=f"ACCESS_UNAVAILABLE:{unavailable}",
            success=True,
        )
        return "continue"
    if response.get("success") is not True:
        _record_safe_failure(
            session,
            path,
            response,
            arguments,
            records,
            reason="PRIMITIVE_FAILURE",
            success=False,
        )
        return "continue"
    if not echo_matches(
        records,
        snapshots.index_snapshot_id or "",
        snapshots.index_source_generation or "",
    ):
        _record_safe_failure(
            session,
            path,
            response,
            arguments,
            records,
            reason=SOURCE_GENERATION_MISMATCH,
            success=True,
        )
        session.stopped = True
        return "stop"

    verdict = response.get("verdict")
    contribution = contribute(
        row=f"plan_change:edit.safe:{path}",
        state="succeeded",
        kind="generic",
        finding=finding_from_verdict(verdict),
        freshness=FRESH if snapshots.oracle_fresh else UNKNOWN,
        truncated=response.get("truncated") is True,
        primitive_verdict=primitive_verdict(verdict),
    )
    evidence_id, evidence_code = session.mint_evidence(
        f"plan_change:edit.safe:{path}",
        "edit",
        "safe",
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
        action="safe",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[evidence_id] if evidence_id else [],
        snapshots=records,
        success=True,
    )
    session.ledger.relevant_paths.append(path)
    session.ledger.step_fragments.append(
        StepFragment(
            route="edit.safe",
            path=path,
            symbol=None,
            locator=path,
            evidence_id=evidence_id,
        )
    )
    return "continue"


async def _run_safe_fanout(session: RouteSession, block_paths: list[str]) -> None:
    """按路径排序与预算上限执行 edit.safe 扇出。"""
    safe_paths = sorted(set(block_paths))
    cap = SAFE_FANOUT_CAPS[session.budget.profile]
    for index, path in enumerate(safe_paths[:cap]):
        result = await _run_safe_path(session, path)
        if result == "continue":
            continue
        if result == "not_called":
            for remaining in safe_paths[index:]:
                session.record_not_called(
                    f"plan_change:edit.safe:{remaining}", "edit", "safe"
                )
            session.stopped = True
        break


async def run_task_route(*, session: RouteSession, operation: str, task: str) -> None:
    """运行 nav.context，并在规划任务中按稳定顺序执行 edit.safe。"""
    snapshots = session.snapshots
    if snapshots.index_snapshot_id is None or snapshots.index_source_generation is None:
        _record_missing_snapshot(session, operation)
        return

    arguments = _nav_arguments(session, task)
    response = await session.call(
        f"{operation}:nav.context", "nav", "context", arguments
    )
    if response is None:
        session.record_not_called(f"{operation}:nav.context", "nav", "context")
        session.stopped = True
        return

    records = echo_records(response)
    unavailable = access_unavailable(response)
    if unavailable is not None:
        _record_nav_failure(
            session,
            operation,
            response,
            arguments,
            records,
            reason=f"ACCESS_UNAVAILABLE:{unavailable}",
            success=True,
        )
        return
    if response.get("success") is not True:
        _record_nav_failure(
            session,
            operation,
            response,
            arguments,
            records,
            reason="PRIMITIVE_FAILURE",
            success=False,
        )
        return
    if not echo_matches(
        records,
        snapshots.index_snapshot_id,
        snapshots.index_source_generation,
    ):
        _record_nav_failure(
            session,
            operation,
            response,
            arguments,
            records,
            reason=SOURCE_GENERATION_MISMATCH,
            success=True,
        )
        return

    verdict = response.get("verdict")
    contribution = contribute(
        row=f"{operation}:nav.context",
        state="succeeded",
        kind="generic",
        finding=finding_from_verdict(verdict),
        freshness=FRESH if snapshots.oracle_fresh else UNKNOWN,
        truncated=response.get("truncated") is True,
        primitive_verdict=primitive_verdict(verdict),
    )
    session.record_contribution(
        contribution,
        facade="nav",
        action="context",
        response=response,
        request_hash=request_hash(arguments),
        evidence_ids=[],
        snapshots=records,
        success=True,
    )
    block_paths = _record_nav_blocks(
        session, operation, response, records, contribution
    )
    if operation == "plan_change":
        await _run_safe_fanout(session, block_paths)
