"""执行所有任务路由共享的权威索引快照阶段。"""

from __future__ import annotations

from ._router_session import RouteSession, request_hash
from .truth_table import FRESH, MISSING, UNKNOWN, contribute

_INDEX_ARGUMENTS = {"access_mode": "read_existing", "output_format": "json"}
_SNAPSHOT_UNAVAILABLE = "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"


async def run_index_oracle(session: RouteSession) -> None:
    """读取 index.status，并把快照、新鲜度和贡献写入会话。"""
    response = await session.call(
        "all:index.status", "index", "status", dict(_INDEX_ARGUMENTS)
    )
    if response is None:  # pragma: no cover - 第一个调用始终会被预算准入
        session.record_freshness(UNKNOWN, "BUDGET_EXHAUSTED", [])
        session.record_not_called("all:index.status", "index", "status")
        return

    snapshots = session.snapshots
    success = response.get("success") is True
    snapshots.index_snapshot_id = response.get("snapshot_id")
    snapshots.index_source_generation = response.get("source_generation")
    completeness = response.get("completeness")
    if (
        not isinstance(snapshots.index_snapshot_id, str)
        or not snapshots.index_snapshot_id
    ):
        snapshots.index_snapshot_id = None
    if (
        not isinstance(snapshots.index_source_generation, str)
        or not snapshots.index_source_generation
    ):
        snapshots.index_source_generation = None
    snapshots.index_complete = completeness == "complete"
    snapshots.oracle_fresh = (
        success
        and snapshots.index_snapshot_id is not None
        and snapshots.index_source_generation is not None
        and snapshots.index_complete
    )

    if not success:
        _record_failure(session, response)
        return
    if snapshots.index_snapshot_id is None or snapshots.index_source_generation is None:
        _record_missing_snapshot(session, response)
        return
    _record_success(session, response, completeness)


def _record_failure(session: RouteSession, response: dict[str, object]) -> None:
    """记录 index.status 原语失败。"""
    reason = str(response.get("access_reason") or _SNAPSHOT_UNAVAILABLE)
    session.record_freshness(UNKNOWN, reason, [])
    contribution = contribute(
        row="all:index.status",
        state="failed",
        kind="generic",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="index",
        action="status",
        response=response,
        request_hash=request_hash({"access_mode": "read_existing"}),
        evidence_ids=[],
        snapshots=[],
        success=False,
    )
    session.add_unknown("all:index.status", "PRIMITIVE_FAILURE")


def _record_missing_snapshot(
    session: RouteSession, response: dict[str, object]
) -> None:
    """记录成功响应缺少权威快照令牌。"""
    session.record_freshness(MISSING, _SNAPSHOT_UNAVAILABLE, [])
    contribution = contribute(
        row="all:index.status",
        state="succeeded",
        kind="generic",
        finding="malformed",
        freshness=MISSING,
        truncated=False,
    )
    session.record_contribution(
        contribution,
        facade="index",
        action="status",
        response=response,
        request_hash=request_hash({"access_mode": "read_existing"}),
        evidence_ids=[],
        snapshots=[],
        success=True,
    )
    session.add_unknown("all:index.status", _SNAPSHOT_UNAVAILABLE)


def _record_success(
    session: RouteSession, response: dict[str, object], completeness: object
) -> None:
    """记录可用索引快照及其完整性。"""
    snapshots = session.snapshots
    freshness = FRESH if snapshots.index_complete else UNKNOWN
    session.record_freshness(
        freshness,
        None if snapshots.index_complete else f"INCOMPLETE_ORACLE:{completeness}",
        [snapshots.index_snapshot_id or ""],
    )
    contribution = contribute(
        row="all:index.status",
        state="succeeded",
        kind="generic",
        finding="none",
        freshness=freshness,
        truncated=False,
        primitive_verdict="INFO",
    )
    session.record_contribution(
        contribution,
        facade="index",
        action="status",
        response=response,
        request_hash=request_hash({"access_mode": "read_existing"}),
        evidence_ids=[],
        snapshots=session.current_snapshots(),
        success=True,
    )
