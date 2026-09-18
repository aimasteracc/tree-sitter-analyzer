"""路由原语响应的稳定归一化工具。"""

from __future__ import annotations

from typing import Any

from .evidence import SourceSnapshotRecord
from .models import Verdict
from .truth_table import Finding

_RISK_VERDICTS = frozenset({"UNSAFE", "WARN", "REVIEW", "CAUTION"})
_NON_RISK_VERDICTS = frozenset({"SAFE", "INFO", "NOT_FOUND"})


def finding_from_verdict(verdict: object) -> Finding:
    """把原语裁决归一化为真值表所需的 finding。"""
    if isinstance(verdict, str) and verdict in _RISK_VERDICTS:
        return "risk"
    if isinstance(verdict, str) and verdict in _NON_RISK_VERDICTS:
        return "none"
    return "malformed"


def primitive_verdict(verdict: object) -> Verdict | None:
    """只保留固定词表中的原语裁决。"""
    if isinstance(verdict, str) and (
        verdict in _RISK_VERDICTS or verdict in _NON_RISK_VERDICTS
    ):
        return verdict  # type: ignore[return-value]  # 已由成员检查收窄
    return None


def access_unavailable(response: dict[str, Any]) -> str | None:
    """返回 P0.4 访问不可用原因；能力可用时返回 ``None``。"""
    state = response.get("access_state")
    if state is not None and state != "available":
        reason = response.get("access_reason")
        if isinstance(reason, str) and reason:
            return reason
        return "READ_EXISTING_UNAVAILABLE"
    return None


def echo_records(response: dict[str, Any]) -> list[SourceSnapshotRecord]:
    """从原语响应中提取稳定的 P0.4 快照记录。"""
    records: list[SourceSnapshotRecord] = []
    for raw in response.get("source_snapshots") or []:
        if type(raw) is not dict:
            continue
        kind = raw.get("kind")
        snapshot_id = raw.get("snapshot_id")
        source_generation = raw.get("source_generation")
        if (
            kind in {"index", "diff"}
            and isinstance(snapshot_id, str)
            and isinstance(source_generation, str)
        ):
            records.append(
                SourceSnapshotRecord(
                    kind=kind,
                    snapshot_id=snapshot_id,
                    source_generation=source_generation,
                )
            )
    if records:
        return records
    # 部分适配器把快照回显放在顶层，而不是访问证据列表中。
    snapshot_id = response.get("snapshot_id")
    source_generation = response.get("source_generation")
    if isinstance(snapshot_id, str) and isinstance(source_generation, str):
        records.append(
            SourceSnapshotRecord(
                kind="index",
                snapshot_id=snapshot_id,
                source_generation=source_generation,
            )
        )
    return records


def echo_matches(
    records: list[SourceSnapshotRecord], snapshot_id: str, source_generation: str
) -> bool:
    """判断响应是否回显了指定索引快照与源码代次。"""
    return any(
        record.kind == "index"
        and record.snapshot_id == snapshot_id
        and record.source_generation == source_generation
        for record in records
    )
