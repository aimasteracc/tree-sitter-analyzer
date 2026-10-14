"""Pulse 项目查询的源码认证租约；复用索引所有者，不维护另一份事实源。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from .. import index_snapshot
from ..read_existing_access import _stable_consumer_code

_STALE_REASONS = frozenset({"SOURCE_INDEX_MISMATCH", "SOURCE_GENERATION_MISMATCH"})
_MISSING_REASONS = frozenset({"MISSING_INDEX", "MISSING_PROJECT_ROOT"})
_COORDINATE_FALLBACK_REASONS = frozenset(
    {
        "CALL_GRAPH_INCOMPLETE",
        "INDEX_SNAPSHOT_FAILED",
        "INDEX_SNAPSHOT_INCOMPLETE",
        "INDEX_SNAPSHOT_UNKNOWN",
        "MISSING_INDEX",
        "NO_EXACT_FULL_INDEX_MANIFEST",
        "SOURCE_SCOPE_DESCRIPTOR_MISSING",
    }
)
# #1561：整仓认证在捕获阶段超出期限或资源上限。此时尚未读取任何快照数据，
# 失败不说明源码过期、并发写入或索引损坏，只说明「本次无法证明 fresh」。
_CERTIFICATION_BOUND_REASONS = frozenset(
    {
        "INDEX_BACKUP_BUDGET",
        "INDEX_FINGERPRINT_BUDGET",
        "INDEX_FINGERPRINT_DEADLINE",
        "INDEX_SNAPSHOT_CAPACITY",
        "INDEX_SNAPSHOT_DEADLINE",
        "SOURCE_SCAN_DEADLINE",
        "SOURCE_SCOPE_UNBOUNDED",
    }
)
CERTIFICATION_BOUND_NEXT_STEP = (
    "Whole-index source certification exceeded its per-call bound ({reason}): "
    "every call re-hashes all indexed sources within "
    f"{index_snapshot._CERTIFICATION_DEADLINE_SECONDS:g} s, so nothing here is "
    "certified fresh. Read the target file before editing; search action=symbol "
    "and nav action=resolve still return uncertified coordinates as leads."
)


class PulseSourceError(ValueError):
    """源码认证失败；与符号不存在或 SQL 查询失败分开处理。"""

    def __init__(self, reason: str, *, capture_phase: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        # 仅捕获阶段（尚无任何读取）的预算失败才属于「认证上限」。
        self.certification_bound = (
            capture_phase and reason in _CERTIFICATION_BOUND_REASONS
        )
        self.freshness = (
            "stale"
            if reason in _STALE_REASONS
            else "missing"
            if reason in _MISSING_REASONS
            else "unknown"
        )

    def evidence(self) -> dict[str, Any]:
        """返回不携带未认证版本身份的统一源码证据。"""
        return {
            "freshness": self.freshness,
            "snapshot_id": None,
            "source_generation": None,
            "reason": self.reason,
        }

    def allows_coordinate_fallback(self) -> bool:
        """仅允许旧式、缺失索引或认证上限降级；并发、过期和损坏必须失败。"""
        return self.reason in _COORDINATE_FALLBACK_REASONS or self.certification_bound

    def next_step(self) -> str | None:
        """认证上限给出可执行的下一步；其他失败沿用调用方原有提示。"""
        if not self.certification_bound:
            return None
        return CERTIFICATION_BOUND_NEXT_STEP.format(reason=self.reason)

    def to_response(self, operation: str = "Pulse") -> dict[str, Any]:
        """错误响应不携带候选结果或未经认证的版本身份。"""
        response: dict[str, Any] = {
            "success": False,
            "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
            "error": f"{operation} source evidence unavailable: {self.reason}",
            "source_evidence": self.evidence(),
        }
        next_step = self.next_step()
        if next_step is not None:
            response["next_step"] = next_step
        return response


@contextmanager
def certified_source_read(
    project_root: str | None,
) -> Iterator[tuple[Any, dict[str, Any]]]:
    """为搜索与解析提供同一个认证索引 owner 和 Pulse 证据模型。"""
    if not project_root:
        raise PulseSourceError("MISSING_PROJECT_ROOT")
    try:
        with (
            index_snapshot.certification_budget(
                index_snapshot._CERTIFICATION_DEADLINE_SECONDS
            ),
            index_snapshot.certified_index_read(project_root) as owner,
        ):
            if owner is None:
                raise PulseSourceError(
                    index_snapshot._certified_index_read_reason()
                    or "INDEX_SNAPSHOT_UNKNOWN",
                    capture_phase=True,
                )
            evidence: dict[str, Any] = {
                "freshness": "unknown",
                "snapshot_id": owner.snapshot.snapshot_id,
                "source_generation": owner.snapshot.source_generation,
                "reason": "SOURCE_REVALIDATION_PENDING",
            }
            yield owner, evidence
    except PulseSourceError:
        raise
    except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError) as exc:
        raise _source_failure(exc) from exc
    evidence.update(freshness="fresh", reason=None)


@contextmanager
def certified_pulse_connection(
    project_root: str | None,
) -> Iterator[tuple[sqlite3.Connection, dict[str, Any]]]:
    """在同一认证连接中读取，正常退出后才允许发布结果和 fresh 证据。

    候选证据在上下文内部始终为 unknown；调用者必须在退出后构造响应。
    源码再验证失败会抛出 PulseSourceError，不能发布已读出的部分结果。
    """
    if not project_root:
        raise PulseSourceError("MISSING_PROJECT_ROOT")
    # #1561：捕获、读取与读后复核共用一个绝对期限，整次调用有界。
    deadline = index_snapshot._clock() + index_snapshot._CERTIFICATION_DEADLINE_SECONDS
    with ExitStack() as stack:
        try:
            snapshot = stack.enter_context(
                index_snapshot.lease_existing_snapshot(project_root, deadline=deadline)
            )
            if (
                snapshot.completeness != "complete"
                or not snapshot.snapshot_id
                or not snapshot.source_generation
                or snapshot.source_scope is None
            ):
                raise PulseSourceError(
                    snapshot.reason or "INDEX_SNAPSHOT_UNKNOWN", capture_phase=True
                )
            _owned_snapshot, connection = stack.enter_context(
                index_snapshot.acquire_index_snapshot(
                    snapshot.snapshot_id, project_root, snapshot.source_generation
                )
            )
        except PulseSourceError:
            raise
        except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError) as exc:
            raise _source_failure(exc) from exc
        evidence: dict[str, Any] = {
            "freshness": "unknown",
            "snapshot_id": snapshot.snapshot_id,
            "source_generation": snapshot.source_generation,
            "reason": "SOURCE_REVALIDATION_PENDING",
        }
        yield connection, evidence
        try:
            index_snapshot.verify_snapshot_source_current(snapshot, deadline=deadline)
        except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError) as exc:
            raise _source_failure(exc) from exc
    evidence.update(freshness="fresh", reason=None)


def _source_failure(exc: Exception) -> PulseSourceError:
    """沿用既有认证错误分类，不把操作系统异常原文当作稳定协议字段。"""
    code = _stable_consumer_code(exc)
    if code == "INDEX_SNAPSHOT_FAILED":
        code = (
            "CORRUPT_INDEX"
            if isinstance(exc, sqlite3.DatabaseError)
            else "INDEX_SNAPSHOT_UNKNOWN"
        )
    return PulseSourceError(code)
