"""隔离构建、完整父身份校验和只读版本会话；不自动迁移旧数据库。"""

from __future__ import annotations

import os
import sqlite3
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..ast_cache import ASTCache
from ..constants import EXCLUDE_DIRS
from ..incremental_sync import IncrementalSync
from ..incremental_sync_support import SyncResult
from ..index_source_scope import SourceScopeDescriptor, make_source_scope_descriptor
from ..indexing_snapshot import (
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
    walk_index_candidate_entries,
)
from ..project_graph import _language_from_ext
from .generation_selector import (
    SELECTOR_BYTE_LIMIT,
    GenerationSelector,
    InvalidGenerationSelector,
    decode_generation_selector,
)


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
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        self.storage = Path(storage).resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        (self.storage / "generations").mkdir(exist_ok=True)
        self.logical_path = str(self.storage / "index.db")
        self.selector_path = self.storage / "active.json"
        self.scope = scope or make_source_scope_descriptor()

    @contextmanager
    def _lease(self) -> Iterator[None]:
        """独立 SQLite 文件只承担跨进程发布锁，不能被活动数据库写锁阻塞。"""
        connection = sqlite3.connect(self.storage / "publication.lock.db", timeout=5)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield
        finally:
            connection.close()

    def active_selector(self) -> GenerationSelector | None:
        """有界读取选择器；格式错误不能作为空索引继续初始化。"""
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(self.selector_path, flags)
        except FileNotFoundError:
            return None
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_INVALID")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                data = handle.read(SELECTOR_BYTE_LIMIT + 1)
        finally:
            os.close(descriptor)
        return decode_generation_selector(
            data, canonical_root=str(self.root), logical_path=self.logical_path
        )

    def database(self, selector: GenerationSelector) -> Path:
        """物理路径只能由已绑定的选择器 ID 构造，不接受任意数据库定位符。"""
        if (
            selector.canonical_root != str(self.root)
            or selector.logical_path != self.logical_path
        ):
            raise Superseded("INDEX_GENERATION_FOREIGN_STORE")
        return self.storage / "generations" / selector.generation_id / "index.db"

    def _snapshot(self) -> IndexCandidateSnapshot:
        return build_index_candidate_snapshot(
            str(self.root),
            max_files=self.scope.certification_max_files,
            exclude_patterns=self.scope.effective_excludes,
            walk_fn=lambda root: walk_index_candidate_entries(
                root, excluded_dir_names=frozenset(EXCLUDE_DIRS)
            ),
            language_fn=_language_from_ext,
        )

    def capture(self) -> GenerationCandidate:
        """先捕获父身份再扫描；并行发布只会使这个候选过期。"""
        with self._lease():
            parent = self.active_selector()
        return GenerationCandidate(
            str(self.root), self.logical_path, parent, self._snapshot()
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

    def prepare(self, candidate: GenerationCandidate) -> PreparedGeneration:
        """复制已发布父数据库，再执行真实 TSA 增量同步，失败不会触碰父版本。"""
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
        with database.open("rb") as handle:
            os.fsync(handle.fileno())
        _flush_directory(database.parent)
        _flush_directory(database.parent.parent)
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
                or current.errors
                or current.discovery_error
            ):
                raise RuntimeError("INDEX_GENERATION_SOURCE_CHANGED")
            database = self.database(prepared.selector)
            if not database.is_file():
                raise FileNotFoundError("INDEX_GENERATION_DATABASE_MISSING")
            data = prepared.selector.encode()
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
