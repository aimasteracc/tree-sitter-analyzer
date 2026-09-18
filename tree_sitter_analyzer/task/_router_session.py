"""路由会话状态与原语调用准入边界。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .evidence import (
    EvidenceInput,
    SourceSnapshotRecord,
    evidence_identity,
    normalized_result_hash,
)
from .models import TASK_TEXT_OMITTED, Budget, TaskRequest
from .projection import StepFragment
from .truth_table import UNKNOWN, Contribution, contribute


class PrimitiveExecutorLike(Protocol):
    """路由会话可调用的最小原语执行器协议。"""

    async def call(
        self, facade: str, action: str, arguments: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class SnapshotState:
    """一次路由持有的索引与差分快照身份。"""

    index_snapshot_id: str | None = None
    index_source_generation: str | None = None
    index_complete: bool = False
    oracle_fresh: bool = False
    diff_snapshot_id: str | None = None
    route_lease_id: str | None = None
    impact_source_generation: str | None = None


@dataclass(slots=True)
class OutcomeLedger:
    """最终结果所需的可追加记录。"""

    contributions: list[Contribution] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    freshness_records: list[dict[str, Any]] = field(default_factory=list)
    unknowns: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    step_fragments: list[StepFragment] = field(default_factory=list)
    relevant_symbols: list[str] = field(default_factory=list)
    relevant_paths: list[str] = field(default_factory=list)
    verification: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    truncated_rows: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CleanupState:
    """独立于路由预算核算的快照清理结果。"""

    calls: int = 0
    wall_ms: int = 0
    status: str = "not_required"
    error_code: str | None = None


def snapshot_wire(records: list[SourceSnapshotRecord]) -> list[dict[str, Any]]:
    """把快照值对象投影为固定线协议。"""
    return [
        {
            "kind": record.kind,
            "snapshot_id": record.snapshot_id,
            "source_generation": record.source_generation,
        }
        for record in records
    ]


def request_hash(arguments: dict[str, Any]) -> str:
    """计算规范请求摘要，并在摘要前移除原始任务文本。"""
    canonical = dict(arguments)
    if "task" in canonical:
        canonical["task"] = TASK_TEXT_OMITTED
    return normalized_result_hash(canonical)


def degraded_unknown(contribution: Contribution) -> Contribution:
    """所有权缺失或不一致时把贡献降级为未知。"""
    return Contribution(
        row=contribution.row,
        kind=contribution.kind,
        state="succeeded",
        finding="malformed",
        freshness=UNKNOWN,
        truncated=None,
        status_contribution="unknown",
        verdict_contribution=None,
        locator=contribution.locator,
        evidence_id=None,
        primitive_verdict=contribution.primitive_verdict,
    )


def with_evidence(
    contribution: Contribution,
    evidence_id: str | None,
    locator: str | None = None,
) -> Contribution:
    """返回绑定证据身份的等价贡献。"""
    return Contribution(
        row=contribution.row,
        kind=contribution.kind,
        state=contribution.state,
        finding=contribution.finding,
        freshness=contribution.freshness,
        truncated=contribution.truncated,
        status_contribution=contribution.status_contribution,
        verdict_contribution=contribution.verdict_contribution,
        locator=(locator if locator is not None else contribution.locator),
        evidence_id=evidence_id,
        primitive_verdict=contribution.primitive_verdict,
    )


@dataclass(slots=True)
class RouteSession:
    """持有一次路由的预算、时钟、快照和结果账本。"""

    request: TaskRequest
    executor: PrimitiveExecutorLike
    clock: Callable[[], int]
    budget: Budget
    start_ms: int
    deadline_ms: int
    consumed_calls: int = 0
    stopped: bool = False
    routed_end_ms: int = 0
    snapshots: SnapshotState = field(default_factory=SnapshotState)
    ledger: OutcomeLedger = field(default_factory=OutcomeLedger)
    cleanup: CleanupState = field(default_factory=CleanupState)

    @classmethod
    def from_request(
        cls,
        request: TaskRequest,
        executor: PrimitiveExecutorLike,
        clock: Callable[[], int],
    ) -> RouteSession:
        """从已验证请求创建预算已固定的会话。"""
        start_ms = clock()
        return cls(
            request=request,
            executor=executor,
            clock=clock,
            budget=request.budget,
            start_ms=start_ms,
            deadline_ms=start_ms + request.budget.effective_deadline_ms,
            routed_end_ms=start_ms,
        )

    def record_freshness(
        self, freshness: str, reason: str | None, tokens: list[str]
    ) -> None:
        """记录当前权威快照对应的新鲜度判断。"""
        snapshot = self.snapshots
        self.ledger.freshness_records.append(
            {
                "freshness": freshness,
                "reason": reason,
                "oracle_complete": snapshot.index_complete,
                "snapshot_id": snapshot.index_snapshot_id,
                "source_generation": snapshot.index_source_generation,
                "graph_tokens": tokens,
            }
        )

    def add_unknown(self, row: str, reason: str) -> None:
        """追加一个失败关闭的未知原因。"""
        self.ledger.unknowns.append({"row": row, "reason": reason})

    def current_snapshots(self) -> list[SourceSnapshotRecord]:
        """返回当前路由已经绑定的快照身份。"""
        state = self.snapshots
        snapshots: list[SourceSnapshotRecord] = []
        if state.index_snapshot_id and state.index_source_generation:
            snapshots.append(
                SourceSnapshotRecord(
                    kind="index",
                    snapshot_id=state.index_snapshot_id,
                    source_generation=state.index_source_generation,
                )
            )
        if state.diff_snapshot_id and state.impact_source_generation:
            snapshots.append(
                SourceSnapshotRecord(
                    kind="diff",
                    snapshot_id=state.diff_snapshot_id,
                    source_generation=state.impact_source_generation,
                )
            )
        return snapshots

    def mint_evidence(
        self,
        row: str,
        facade: str,
        action: str,
        response: dict[str, Any],
        locator: str | None,
        fragment: dict[str, Any] | None = None,
        snapshots: list[SourceSnapshotRecord] | None = None,
    ) -> tuple[str | None, str]:
        """从精确结果片段铸造一个受预算约束的证据身份。"""
        ledger = self.ledger
        if len(ledger.evidence) >= self.budget.effective_evidence:
            ledger.truncated_rows.append(row)
            return None, "budget_exhausted"
        action_version = response.get("action_version")
        if not isinstance(action_version, str) or not action_version:
            self.add_unknown(row, "ACTION_VERSION_MISSING")
            return None, "action_version_missing"
        bound_snapshots = (
            snapshots if snapshots is not None else self.current_snapshots()
        )
        canonical_fragment = dict(sorted((fragment or response).items()))
        result_hash = normalized_result_hash(canonical_fragment)
        identity = evidence_identity(
            EvidenceInput(
                primitive_facade=facade,
                action=action,
                action_version=action_version,
                normalized_result_sha256=result_hash,
                source_snapshots=tuple(bound_snapshots),
                locator=locator or "",
            )
        )
        ledger.evidence.append(
            {
                "evidence_id": identity,
                "primitive_facade": facade,
                "action": action,
                "action_version": action_version,
                "normalized_result_sha256": result_hash,
                "source_snapshots": snapshot_wire(bound_snapshots),
                "locator": locator,
            }
        )
        return identity, "minted"

    def record_contribution(
        self,
        contribution: Contribution,
        *,
        facade: str,
        action: str,
        response: dict[str, Any] | None,
        request_hash: str,
        evidence_ids: list[str],
        snapshots: list[SourceSnapshotRecord],
        success: bool,
    ) -> None:
        """把同一行贡献同步写入验证与来源账本。"""
        ledger = self.ledger
        ledger.contributions.append(contribution)
        ledger.verification.append(
            {
                "row": contribution.row,
                "facade": facade,
                "action": action,
                "finding": contribution.finding,
                "freshness": contribution.freshness,
                "truncated": contribution.truncated,
                "status_contribution": contribution.status_contribution,
                "verdict_contribution": contribution.verdict_contribution,
                "evidence_id": contribution.evidence_id,
                "locator": contribution.locator,
            }
        )
        ledger.provenance.append(
            {
                "row": contribution.row,
                "primitive_facade": facade,
                "action": action,
                "action_version": (
                    response.get("action_version") if response else None
                ),
                "request_hash": request_hash,
                "result_hash": (
                    normalized_result_hash(dict(sorted(response.items())))
                    if response
                    else None
                ),
                "source_snapshots": snapshot_wire(snapshots),
                "success": success,
                "verdict": response.get("verdict") if response else None,
                "truncated": contribution.truncated,
                "evidence_ids": list(evidence_ids),
            }
        )

    def record_not_called(
        self, row: str, facade: str, action: str, kind: str = "generic"
    ) -> None:
        """把因预算或截止时间省略的必需行记录为未调用。"""
        contribution = contribute(
            row=row,
            state="not_called",
            kind=kind,  # type: ignore[arg-type]
            finding="malformed",
            freshness=UNKNOWN,
            truncated=None,
        )
        self.record_contribution(
            contribution,
            facade=facade,
            action=action,
            response=None,
            request_hash=request_hash({}),
            evidence_ids=[],
            snapshots=[],
            success=True,
        )

    async def call(
        self,
        row: str,
        facade: str,
        action: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """在预算和截止时间允许时顺序执行一个原语调用。"""
        if self.consumed_calls >= self.budget.effective_calls:
            self.ledger.truncated_rows.append(row)
            return None
        if self.clock() > self.deadline_ms:
            self.ledger.truncated_rows.append(row)
            return None
        self.consumed_calls += 1
        try:
            return await self.executor.call(facade, action, arguments)
        except Exception:
            return {"success": False, "verdict": "ERROR"}
