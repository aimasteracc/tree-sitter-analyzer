"""零变化刷新的建库前判定：不复制父版本即可证明本次运行不会改变索引（#1671）。

#1631 的零变化判定在私有副本上跑完整索引流程之后才成立：先整份复制父版本
（本仓库 343 MB），再跑一遍索引；父版本带稳定失败（缺少可选语法）时调用图标记
从未建立，每次还要完整回填（约 70 秒），最后又因为 ``errors`` 非零而照常发布。

本模块在 ``GenerationStore.begin`` 之前、只读地比较本次捕获的候选与父版本：

* 候选完整（无发现错误、无截断、计数对账、无不可读标记）；
* 父版本 schema 为当前版本，每一行的提取器版本不低于当前版本、已逐文件认证；
* 每个选中文件都有一行，**内容摘要**、``mtime_ns``、``file_size`` 与捕获时完全
  相同（摘要来自本次读取的字节，RFC-0030：绝不只看路径或元数据），父版本
  没有多余的行（无需清除已删除文件）；
* 父版本带收敛刷新记录（``stable_failures``）：它是一次收敛的完整刷新运行的
  直接结果，记录绑定的根目录、范围、提取器与流水线版本均未变化；并且
* 记录无失败时，父版本已认证：清单与本次范围、根目录、文件数一致，调用图标记
  当前；或者记录有稳定失败时，缺行的文件恰好是记录中的文件，各自的摘要与记录
  相同，且现在重新解析这份字节仍以**同一原因**失败。

任一条件不满足即返回 ``None``，调用方照常建库（判定只会让刷新退回原路径，不会
放宽发布）。全部满足时，真实运行在私有副本上只会得到与父版本相同的内容：全部
文件命中缓存，稳定失败照旧，回填输入未变。活动版本及其认证因此保持不变。
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..indexing_snapshot import IndexCandidateSnapshot, IndexSnapshotEntry
from .stable_failures import (
    StableFailure,
    StableFailureRecord,
    candidate_is_exact,
    current_extractor_version,
    read_record,
)

#: 未发布原因码，与 #1631 相同。
UNCHANGED_REASON = "INDEX_UNCHANGED"


@dataclass(frozen=True, slots=True)
class UnchangedEvidence:
    """父版本与本次候选相同的证据。"""

    cached: int
    failures: tuple[StableFailure, ...]
    certified: bool

    def index_result(self, snapshot: IndexCandidateSnapshot) -> dict[str, Any]:
        """``index_project`` 形状的结果：与真实零变化运行报告的计数一致。"""
        from .publication_policy import stable_failure

        files: list[dict[str, Any]] = [
            stable_failure(failure.file, failure.reason, failure.content_hash)
            for failure in self.failures
        ]
        failed = {failure.file for failure in self.failures}
        files.extend(
            {"file": entry.rel_path, "status": "cached", "reason": "unchanged"}
            for entry in snapshot.selected_entries
            if entry.rel_path not in failed
        )
        result: dict[str, Any] = {
            "mode_used": "incremental",
            "indexed": 0,
            "cached": self.cached,
            "errors": len(self.failures),
            "skipped": snapshot.excluded + snapshot.skipped,
            "incomplete_skips": 0,
            "processed": self.cached + len(self.failures),
            "changed_during_run": 0,
            "changed_during_run_files": [],
            "files": files,
            "activation_enabled": False,
            "truncated_by_max_files": False,
            "total_files": len(snapshot.entries),
            "removed_files": [],
            "pruned": 0,
            "backfill_errors": 0,
            "published": False,
            "publication_reason": UNCHANGED_REASON,
            "unchanged_evidence": "content_hash",
        }
        if self.failures:
            # 与真实运行一致：稳定失败使本次运行不完整，清单不认证。
            result["verdict"] = "WARN"
            result["manifest_warning"] = "INDEX_RUN_INCOMPLETE"
        return result

    def sync_result(self) -> Any:
        """``IncrementalSync.sync`` 形状的结果。"""
        from ..incremental_sync_support import SyncResult
        from .publication_policy import stable_failure

        details = []
        for failure in self.failures:
            detail = stable_failure(failure.file, failure.reason, failure.content_hash)
            details.append({**detail, "considered": "indexed", "action": "indexed"})
        return SyncResult(
            scanned=self.cached + len(self.failures),
            processed=self.cached + len(self.failures),
            unchanged_files=self.cached,
            errors=len(self.failures),
            scope_complete=self.certified,
            details=details,
            published=False,
            publication_reason=UNCHANGED_REASON,
        )


def _normalize(path: str) -> str:
    return path.replace("\\", "/") if os.name == "nt" else path


def _schema_is_current(conn: sqlite3.Connection) -> bool:
    from .schema_extensions import CURRENT_SCHEMA_VERSION

    versions = {
        row[0] for row in conn.execute("SELECT version FROM ast_schema_version")
    }
    return CURRENT_SCHEMA_VERSION in versions and all(
        type(version) is int and version <= CURRENT_SCHEMA_VERSION
        for version in versions
    )


def _indexed_rows(
    conn: sqlite3.Connection, extractor_version: int
) -> dict[str, tuple[str, int, int]] | None:
    rows: dict[str, tuple[str, int, int]] = {}
    for path, digest, mtime_ns, size, version, certified in conn.execute(
        "SELECT file_path, content_hash, mtime_ns, file_size, extractor_version, "
        "certified_at FROM ast_index"
    ):
        if (
            type(version) is not int
            or version < extractor_version
            or certified is None
            or not isinstance(digest, str)
        ):
            return None
        rows[_normalize(str(path))] = (digest, int(mtime_ns), int(size))
    return rows


def _read_bound_source(entry: IndexSnapshotEntry) -> str | None:
    """读取与捕获元数据相同的字节并解码；读取前后元数据变化即为 ``None``。"""
    from .._bounded_read import read_at_most
    from ..indexing_snapshot import _INDEX_SOURCE_BYTE_LIMIT, decode_index_source

    fingerprint = entry.fingerprint
    if fingerprint is None:
        return None

    def same(info: os.stat_result) -> bool:
        return (int(info.st_mtime_ns), int(info.st_size)) == (
            fingerprint.mtime_ns,
            fingerprint.file_size,
        )

    try:
        if not same(os.stat(entry.abs_path)):
            return None
        with open(entry.abs_path, "rb") as handle:
            data = read_at_most(handle, _INDEX_SOURCE_BYTE_LIMIT)
        if len(data) > _INDEX_SOURCE_BYTE_LIMIT or not same(os.stat(entry.abs_path)):
            return None
    except OSError:
        return None
    return decode_index_source(data)


def bound_digests(candidate: Any) -> dict[str, str]:
    """捕获时绑定的内容摘要（``GenerationCandidate.source_contents``）。

    路径平台在捕获时逐文件读取并摘要，摘要保存在 ``source_contents`` 中（候选
    快照本身只带不可读标记）；这里复用它们，不再为比较重读每个文件。
    """
    digests: dict[str, str] = {}
    for item in getattr(candidate, "source_contents", None) or ():
        try:
            rel_path, evidence = item
            digest = evidence[0] if evidence is not None else ""
        except (TypeError, ValueError, IndexError):
            continue
        if isinstance(rel_path, str) and isinstance(digest, str) and digest:
            digests[rel_path] = digest
    return digests


def _content_hash(
    entry: IndexSnapshotEntry, bound: dict[str, str] | None = None
) -> str | None:
    """捕获时绑定的摘要（路径平台逐文件读取所得）；没有时现在读取并计算。"""
    from ..index_source_stream import unreadable_source_reason
    from ..indexing_snapshot import index_source_content_hash

    fingerprint = entry.fingerprint
    if fingerprint is None:
        return None
    digest = (bound or {}).get(entry.rel_path) or fingerprint.content_hash
    if digest:
        if unreadable_source_reason(digest) is not None or digest == "<unsafe>":
            return None
        return digest
    source = _read_bound_source(entry)
    return None if source is None else index_source_content_hash(source)


def _same_failure(entry: IndexSnapshotEntry, failure: StableFailure) -> bool:
    """现在重新解析同一份字节，仍以同一原因失败（环境未变，如语法仍未安装）。"""
    from ..core.parser import Parser
    from ..indexing_snapshot import index_source_content_hash

    source = _read_bound_source(entry)
    if source is None or index_source_content_hash(source) != failure.content_hash:
        return False
    if entry.language is None:
        return False
    result = Parser().parse_code(source, entry.language, filename=entry.abs_path)
    reason = result.error_message or "parse failed"
    return not result.success and reason == failure.reason


def _certified_parent(
    conn: sqlite3.Connection, root: str, scope: str, file_count: int
) -> bool:
    from .callgraph_state import call_graph_marker_is_current

    manifests = conn.execute(
        "SELECT canonical_root, source_scope_descriptor, file_count, "
        "manifest_version FROM ast_index_snapshot_manifest"
    ).fetchall()
    return (
        len(manifests) == 1
        and tuple(manifests[0]) == (root, scope, file_count, 2)
        and call_graph_marker_is_current(conn)
    )


def _record_binds(
    record: StableFailureRecord | None, *, root: str, scope: str, version: int
) -> bool:
    """记录存在，且绑定的根目录、范围、提取器与流水线版本与本次刷新相同。"""
    from .callgraph_state import CALL_GRAPH_PIPELINE_VERSION

    return bool(
        record is not None
        and record.root == root
        and record.scope == scope
        and record.extractor_version == version
        and record.pipeline_version == CALL_GRAPH_PIPELINE_VERSION
    )


def _recorded_failures_hold(
    conn: sqlite3.Connection,
    record: StableFailureRecord,
    missing: Iterable[tuple[IndexSnapshotEntry, str]],
) -> tuple[StableFailure, ...] | None:
    if conn.execute("SELECT 1 FROM ast_index_snapshot_manifest LIMIT 1").fetchone():
        return None
    recorded = record.by_file()
    pending = list(missing)
    if {entry.rel_path for entry, _digest in pending} != set(recorded):
        return None
    for entry, digest in pending:
        failure = recorded[entry.rel_path]
        if failure.content_hash != digest or not _same_failure(entry, failure):
            return None
    return record.failures


def _evidence(
    conn: sqlite3.Connection,
    snapshot: IndexCandidateSnapshot,
    *,
    root: str,
    scope: str,
    bound: dict[str, str] | None = None,
) -> UnchangedEvidence | None:
    if not _schema_is_current(conn):
        return None
    extractor_version = current_extractor_version()
    rows = _indexed_rows(conn, extractor_version)
    if rows is None:
        return None
    missing: list[tuple[IndexSnapshotEntry, str]] = []
    cached = 0
    for entry in snapshot.selected_entries:
        fingerprint = entry.fingerprint
        digest = _content_hash(entry, bound)
        if fingerprint is None or digest is None:
            return None
        row = rows.pop(entry.rel_path, None)
        if row is None:
            missing.append((entry, digest))
            continue
        if row != (digest, fingerprint.mtime_ns, fingerprint.file_size):
            return None
        cached += 1
    if rows:
        return None  # 父版本有已不在范围内的行：真实运行会清除它们。
    # 记录证明父版本是一次收敛的完整刷新运行的直接结果：没有失败时清单由该运行
    # 本身盖出。单文件写入、失效、派生数据持久化等路由产生的版本不带记录，其
    # 清单或调用图可能已不代表内容，必须照常运行。
    record = read_record(conn)
    if record is None or not _record_binds(
        record, root=root, scope=scope, version=extractor_version
    ):
        return None
    if not missing:
        if record.failures or not _certified_parent(conn, root, scope, cached):
            return None
        return UnchangedEvidence(cached, (), True)
    failures = _recorded_failures_hold(conn, record, missing)
    if failures is None:
        return None
    return UnchangedEvidence(cached, failures, False)


def unchanged_before_build(store: Any, candidate: Any) -> UnchangedEvidence | None:
    """父版本与候选相同时返回证据；任何不确定都返回 ``None``（照常建库）。"""
    from ..index_source_snapshot import canonical_source_scope_descriptor
    from .generation_pins import pin_generation

    snapshot = candidate.snapshot
    if candidate.parent is None or not candidate_is_exact(snapshot):
        return None
    try:
        pin = pin_generation(store.storage, candidate.parent.generation_id)
    except (OSError, ValueError):
        return None
    if pin is None:
        return None
    try:
        database = store.database(candidate.parent)
        connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            evidence = _evidence(
                connection,
                snapshot,
                root=os.path.realpath(str(store.root)),
                scope=canonical_source_scope_descriptor(store.scope),
                bound=bound_digests(candidate),
            )
        finally:
            connection.close()
        if evidence is None or not _parent_still_active(store, candidate):
            return None
        return evidence
    except (sqlite3.Error, OSError, ValueError, RuntimeError):
        return None
    finally:
        pin.release()


def _parent_still_active(store: Any, candidate: Any) -> bool:
    """比较的父版本仍是活动版本（在发布租约内读取）；被更新的发布取代时照常
    进入建库路径，由 ``begin`` 的准入如实报告 ``INDEX_CANDIDATE_SUPERSEDED``。"""
    with store._lease():
        return bool(store._publication_parent() == candidate.parent)
