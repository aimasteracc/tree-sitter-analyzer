"""隔离构建、完整父身份校验和只读版本会话；不自动迁移旧数据库。"""

from __future__ import annotations

import os
import sqlite3
import stat
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from ..ast_cache import ASTCache
from ..constants import EXCLUDE_DIRS
from ..incremental_sync import IncrementalSync
from ..incremental_sync_support import SyncResult
from ..index_source_scope import SourceScopeDescriptor, make_source_scope_descriptor
from ..indexing_snapshot import (
    _PERMANENT_SOURCE_REJECTIONS,
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
    walk_index_candidate_entries,
)
from ..project_graph import _language_from_ext
from .generation_routing import read_selector
from .generation_selector import (
    GenerationSelector,
)

_PATH_ONLY_SOURCE = os.name != "posix"


def _bind_source_hashes(snapshot: IndexCandidateSnapshot) -> IndexCandidateSnapshot:
    """路径平台也绑定候选内容摘要，禁止同元数据改写逃过发布复核。"""
    if not _PATH_ONLY_SOURCE:
        return snapshot
    from ..index_source_stream import hash_source_at
    from ..portable_source_snapshot import _marker, _same

    entries = []
    counters = {"input": 0, "output": 0}
    deadline = time.monotonic() + 30
    for entry in snapshot.entries:
        if entry.decision == "selected" and entry.fingerprint is not None:
            before = os.lstat(entry.abs_path)
            _, digest, clean = hash_source_at(
                None,
                entry.abs_path,
                before,
                deadline,
                counters,
                512 * 1024 * 1024,
                _marker,
                _same,
            )
            if not clean or entry.fingerprint != type(entry.fingerprint).from_stat(
                before
            ):
                raise RuntimeError("INDEX_GENERATION_SOURCE_CHANGED")
            entry = replace(
                entry, fingerprint=replace(entry.fingerprint, content_hash=digest)
            )
        entries.append(entry)
    return replace(snapshot, entries=tuple(entries))


class Superseded(RuntimeError):
    """候选所属的父版本已被替换，不能借用新版本的发布权限。"""


@dataclass(frozen=True)
class GenerationCandidate:
    """把源码候选与完整父版本身份绑定，首次发布也绑定目标项目。"""

    canonical_root: str
    logical_path: str
    parent: GenerationSelector | None
    snapshot: IndexCandidateSnapshot


@dataclass(frozen=True)
class PreparedGeneration:
    """已关闭全部构建连接、尚未对读者可见的版本。"""

    candidate: GenerationCandidate
    selector: GenerationSelector
    result: SyncResult
    allow_permanent_rejections: bool = False


def permanent_rejections_only(snapshot: IndexCandidateSnapshot) -> bool:
    """只有已明确永久拒绝的路径允许发布清理结果，不能包含临时发现失败。"""
    errors = [entry for entry in snapshot.entries if entry.decision == "error"]
    return (
        bool(errors)
        and not snapshot.discovery_error
        and snapshot.errors == len(errors)
        and all(entry.reason in _PERMANENT_SOURCE_REJECTIONS for entry in errors)
    )


def _flush_directory(path: Path) -> None:
    """POSIX 同步目录项；Windows 不宣称具备目录掉电持久性。"""
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _source_contents(snapshot: IndexCandidateSnapshot) -> tuple[object, ...]:
    """通用 DTO 比较忽略摘要和描述符链，发布边界必须显式纳入二者。"""
    return tuple(
        (
            entry.rel_path,
            (entry.fingerprint.content_hash, entry.fingerprint.descriptor_chain)
            if entry.fingerprint is not None
            else None,
        )
        for entry in snapshot.selected_entries
    )


class GenerationStore:
    """每次同步只修改专属副本；已发布版本保留至全部读会话结束之后。"""

    def __init__(
        self,
        root: str,
        storage: str,
        *,
        scope: SourceScopeDescriptor | None = None,
        logical_path: str | None = None,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        self.storage = Path(storage).resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        (self.storage / "generations").mkdir(exist_ok=True)
        self.logical_path = logical_path or str(self.storage / "index.db")
        self.selector_path = self.storage / "active.json"
        self.scope = scope or make_source_scope_descriptor()
        self._directory_identities = {
            path: (info.st_dev, info.st_ino)
            for path in (
                self.root,
                self.storage.parent,
                self.storage,
                self.storage / "generations",
            )
            for info in (os.lstat(path),)
        }

    def _verify_directories(self) -> None:
        """存储目录被替换后，旧对象不能在同名新目录重新取得写入权限。"""
        for path, expected in self._directory_identities.items():
            info = os.lstat(path)
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != expected:
                raise Superseded("INDEX_GENERATION_DIRECTORY_CHANGED")

    @contextmanager
    def _lease(self) -> Iterator[None]:
        """独立 SQLite 文件只承担跨进程发布锁，不能被活动数据库写锁阻塞。"""
        self._verify_directories()
        lock_path = self.storage / "publication.lock.db"
        if os.path.lexists(lock_path):
            info = os.lstat(lock_path)
            if (
                not stat.S_ISREG(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
            ):
                raise Superseded("INDEX_GENERATION_LOCK_UNSAFE")
        connection = sqlite3.connect(lock_path, timeout=5)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_directories()
            yield
        finally:
            connection.close()

    def active_selector(self) -> GenerationSelector | None:
        """有界读取选择器；格式错误不能作为空索引继续初始化。"""
        return read_selector(str(self.root), self.storage, self.logical_path)

    def database(self, selector: GenerationSelector) -> Path:
        """物理路径只能由已绑定的选择器 ID 构造，不接受任意数据库定位符。"""
        if (
            selector.canonical_root != str(self.root)
            or selector.logical_path != self.logical_path
        ):
            raise Superseded("INDEX_GENERATION_FOREIGN_STORE")
        return self.storage / "generations" / selector.generation_id / "index.db"

    def _snapshot(self) -> IndexCandidateSnapshot:
        return _bind_source_hashes(
            build_index_candidate_snapshot(
                str(self.root),
                max_files=self.scope.certification_max_files,
                exclude_patterns=self.scope.effective_excludes,
                walk_fn=lambda root: walk_index_candidate_entries(
                    root, excluded_dir_names=frozenset(EXCLUDE_DIRS)
                ),
                language_fn=_language_from_ext,
            )
        )

    def capture(
        self, snapshot_factory: Callable[[], IndexCandidateSnapshot] | None = None
    ) -> GenerationCandidate:
        """先捕获父身份再扫描；并行发布只会使这个候选过期。"""
        with self._lease():
            parent = self.active_selector()
        return GenerationCandidate(
            str(self.root),
            self.logical_path,
            parent,
            _bind_source_hashes(snapshot_factory())
            if snapshot_factory is not None
            else self._snapshot(),
        )

    def _admit(self, candidate: GenerationCandidate) -> None:
        if (
            candidate.canonical_root != str(self.root)
            or candidate.logical_path != self.logical_path
            or self.active_selector() != candidate.parent
        ):
            raise Superseded("INDEX_GENERATION_SUPERSEDED")

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """固定一个不可变版本；后续发布不改变当前会话，缺失时不创建数据库。"""
        selector = self.active_selector()
        if selector is None:
            raise FileNotFoundError("INDEX_GENERATION_MISSING")
        connection = sqlite3.connect(
            self.database(selector).as_uri() + "?mode=ro", uri=True
        )
        try:
            connection.row_factory = sqlite3.Row
            yield connection
        finally:
            connection.close()

    def begin(self, candidate: GenerationCandidate) -> GenerationSelector:
        """为一次已有索引流程分配私有库，不能写入父版本。"""
        with self._lease():
            self._admit(candidate)
        selector = GenerationSelector(
            str(self.root),
            self.logical_path,
            candidate.parent.storage_epoch if candidate.parent else uuid.uuid4().hex,
            uuid.uuid4().hex,
        )
        database = self.database(selector)
        database.parent.mkdir(exist_ok=False)
        if candidate.parent is not None:
            source = sqlite3.connect(
                self.database(candidate.parent).as_uri() + "?mode=ro", uri=True
            )
            try:
                destination = sqlite3.connect(database)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
            finally:
                source.close()
        return selector

    def seal(self, selector: GenerationSelector) -> None:
        """构建连接释放后截断 WAL 并刷盘；完成之前不能发布。"""
        database = self.database(selector)
        connection = sqlite3.connect(database)
        try:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if checkpoint.fetchone()[0] != 0:
                raise RuntimeError("INDEX_GENERATION_CHECKPOINT_BUSY")
        finally:
            connection.close()
        with database.open("rb") as handle:
            os.fsync(handle.fileno())
        _flush_directory(database.parent)
        _flush_directory(database.parent.parent)

    def prepare(self, candidate: GenerationCandidate) -> PreparedGeneration:
        """复制已发布父数据库，再执行真实 TSA 增量同步，失败不会触碰父版本。"""
        selector = self.begin(candidate)
        database = self.database(selector)
        cache = ASTCache(str(self.root), str(database))
        try:
            result = IncrementalSync(cache).sync(
                max_files=self.scope.certification_max_files,
                exclude_patterns=self.scope.effective_excludes,
                candidate_snapshot=candidate.snapshot,
                source_scope=self.scope,
            )
            if (
                not result.scope_complete
                or result.errors
                or result.backfill_errors
                or result.manifest_certification_failed
            ):
                raise RuntimeError("INDEX_GENERATION_INCOMPLETE")
            checkpoint = cache.get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if checkpoint.fetchone()[0] != 0:
                raise RuntimeError("INDEX_GENERATION_CHECKPOINT_BUSY")
        finally:
            cache.close()
        self.seal(selector)
        return PreparedGeneration(candidate, selector, result)

    def publish(self, prepared: PreparedGeneration) -> GenerationSelector:
        """发布前重新校验完整父身份及源码，原子替换唯一活动选择器。"""
        with self._lease():
            self._admit(prepared.candidate)
            current = self._snapshot()
            previous = prepared.candidate.snapshot
            if (
                current != previous
                or _source_contents(current) != _source_contents(previous)
                or current.root_identity != previous.root_identity
                or (
                    current.errors
                    and not (
                        prepared.allow_permanent_rejections
                        and permanent_rejections_only(current)
                    )
                )
                or current.discovery_error
            ):
                raise RuntimeError("INDEX_GENERATION_SOURCE_CHANGED")
            database = self.database(prepared.selector)
            if not database.is_file():
                raise FileNotFoundError("INDEX_GENERATION_DATABASE_MISSING")
            data = prepared.selector.encode()
            activated = Path(self.logical_path).with_suffix(".generation")
            if not activated.exists():
                with activated.open("xb") as handle:
                    handle.write(b"1\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                _flush_directory(activated.parent)
            temporary = self.storage / f"selector-{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.selector_path)
                _flush_directory(self.storage)
            finally:
                temporary.unlink(missing_ok=True)
            return prepared.selector

    def sync(self) -> GenerationSelector:
        """捕获、隔离构建、发布一次完整默认范围索引。"""
        return self.publish(self.prepare(self.capture()))
