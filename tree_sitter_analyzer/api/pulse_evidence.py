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


class PulseSourceError(ValueError):
    """源码认证失败；与符号不存在或 SQL 查询失败分开处理。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.freshness = (
            "stale"
            if reason in _STALE_REASONS
            else "missing"
            if reason in _MISSING_REASONS
            else "unknown"
        )

    def to_response(self) -> dict[str, Any]:
        """错误响应不携带候选结果或未经认证的版本身份。"""
        return {
            "success": False,
            "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
            "error": f"Pulse source evidence unavailable: {self.reason}",
            "source_evidence": {
                "freshness": self.freshness,
                "snapshot_id": None,
                "source_generation": None,
                "reason": self.reason,
            },
        }


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
    with ExitStack() as stack:
        try:
            snapshot = stack.enter_context(
                index_snapshot.lease_existing_snapshot(project_root)
            )
            if (
                snapshot.completeness != "complete"
                or not snapshot.snapshot_id
                or not snapshot.source_generation
                or snapshot.source_scope is None
            ):
                raise PulseSourceError(snapshot.reason or "INDEX_SNAPSHOT_UNKNOWN")
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
            index_snapshot.verify_snapshot_source_current(snapshot)
        except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError) as exc:
            raise _source_failure(exc) from exc
    evidence.update(freshness="fresh", reason=None)


def _source_failure(exc: Exception) -> PulseSourceError:
    """沿用既有认证错误分类，不把操作系统异常原文当作稳定协议字段。"""
    code = _stable_consumer_code(exc)
    if code == "INDEX_SNAPSHOT_FAILED":
        code = "INDEX_SNAPSHOT_UNKNOWN"
    return PulseSourceError(code)
