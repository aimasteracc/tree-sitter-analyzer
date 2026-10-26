"""隔离构建、完整父身份校验和只读版本会话；旧库仅在首次写入时被复制采纳。"""

from __future__ import annotations

import logging
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
    IndexCandidateSnapshot,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
    walk_index_candidate_entries,
)
from ..project_graph import _language_from_ext
from ..read_only_files import mark_read_only
from ._win_fileops import IS_WINDOWS, replace_file
from ._win_fileops import IndexWriterBusy as IndexWriterBusy  # 发布失败关闭的类型
from .admission import Superseded as Superseded  # 发布选择器 CAS 的拒绝类型
from .generation_bootstrap import adopt_legacy_database
from .generation_pins import GenerationPin, pin_generation
from .generation_reader_release import release_idle_readers
from .generation_retirement import retire_generations, retire_unpublished
from .generation_routing import read_selector
from .generation_seal import leave_wal
from .generation_selector import (
    GenerationSelector,
    InvalidGenerationSelector,
    decode_generation_selector,
)
from .source_hash_budget import (
    SOURCE_HASH_BYTE_BUDGET,
    SourceHashBudgetExceeded,
    source_hash_budget_seconds,
)
from .source_recheck import (
    SOURCE_CHANGED,
    SourceChanged,
    check_publication_sources,
    recheck_discovery_seconds,
)
from .source_recheck import permanent_rejections_only as permanent_rejections_only
from .source_recheck import source_contents as _source_contents
from .stable_failures import clear_record_at

_PATH_ONLY_SOURCE = os.name != "posix"
# 发布租约的等待上限（秒）；超时报 ``INDEX_WRITER_BUSY``。RFC-0032 规定 30 秒。
# 实测（#1664，Windows，2,865 个文件）：发布临界区要复核全部源码，持有 3.4–6.6 秒，
# 5 秒上限会把普通竞争报成忙。租约一释放等待即结束，30 秒只是上限而非常态延迟。
LEASE_TIMEOUT_S = 30.0
logger = logging.getLogger(__name__)


def _lease_busy(exc: sqlite3.OperationalError) -> bool:
    """SQLITE_BUSY / SQLITE_LOCKED；Python 3.10 没有 ``sqlite_errorcode``。"""
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        return (int(code) & 0xFF) in (5, 6)
    return "locked" in str(exc) or "busy" in str(exc)


def _bind_source_hashes(snapshot: IndexCandidateSnapshot) -> IndexCandidateSnapshot:
    """路径平台也绑定候选内容摘要，禁止同元数据改写逃过发布复核。

    任一文件超出预算即抛 ``SourceHashBudgetExceeded``：不返回部分绑定的快照，
    因此不完整的候选既不能开始构建也不能发布（RFC-0032）。
    """
    if not _PATH_ONLY_SOURCE:
        return snapshot
    selected = [
        entry
        for entry in snapshot.entries
        if entry.decision == "selected" and entry.fingerprint is not None
    ]
    overall_deadline = time.monotonic() + source_hash_budget_seconds(len(selected))
    bound = _bound_source_hashes(selected, overall_deadline)
    entries = []
    for entry in snapshot.entries:
        if entry.decision == "selected" and entry.fingerprint is not None:
            before, digest, clean = bound[entry.rel_path]
            if not clean or entry.fingerprint != type(entry.fingerprint).from_stat(
                before
            ):
                raise SourceChanged(SOURCE_CHANGED, [f"modified: {entry.rel_path}"])
            entry = replace(
                entry, fingerprint=replace(entry.fingerprint, content_hash=digest)
            )
        entries.append(entry)
    return replace(snapshot, entries=tuple(entries))


#: 冷读取的并发线程数（#1673）：Windows 打开文件受 I/O 与实时扫描延迟支配，
#: 本机实测顺序读取约 35 ms/文件、8 线程约 6 ms/文件；命中 ``source_hash_cache``
#: 时根本不读文件。
_HASH_THREADS = 8


def _bound_source_hashes(
    selected: list[IndexSnapshotEntry], overall_deadline: float
) -> dict[str, tuple[os.stat_result, str, bool]]:
    """为每个选中条目取 ``(lstat, 摘要, 干净)``；时间与字节预算对整批生效。

    任一文件超出预算即抛 ``SourceHashBudgetExceeded``，不返回部分结果。
    """
    from concurrent.futures import ThreadPoolExecutor

    from ..index_source_stream import SourceUnreadable, hash_source_at
    from ..portable_source_snapshot import _marker, _same

    def bind(entry: IndexSnapshotEntry) -> tuple[os.stat_result, str, bool, int]:
        before = os.lstat(entry.abs_path)
        # 并发读取时单个慢文件只占一个线程；整批期限即上界（逐文件期限在线程
        # 交错下会随调度而变，不再使用）。
        deadline = overall_deadline
        counters = {"input": 0, "output": 0}
        try:
            _, digest, clean = hash_source_at(
                None,
                entry.abs_path,
                before,
                deadline,
                counters,
                SOURCE_HASH_BYTE_BUDGET,
                _marker,
                _same,
            )
        except SourceUnreadable as exc:
            # #1654：被锁定等不可读文件记为标记而非摘要，其余文件照常绑定；
            # 索引器据此按文件报告失败，标记永不等于任何已索引行的摘要。
            digest, clean = exc.marker, True
        return before, digest, clean, counters["input"]

    results: dict[str, tuple[os.stat_result, str, bool]] = {}
    total_bytes = 0
    exhausted: BaseException | None = None
    with ThreadPoolExecutor(max_workers=_HASH_THREADS) as pool:
        futures = [(entry, pool.submit(bind, entry)) for entry in selected]
        try:
            for entry, future in futures:
                before, digest, clean, read = future.result()
                total_bytes += read
                if total_bytes > SOURCE_HASH_BYTE_BUDGET:
                    raise OverflowError
                results[entry.rel_path] = (before, digest, clean)
        except (TimeoutError, OverflowError) as exc:
            exhausted = exc
            for _entry, pending in futures:
                pending.cancel()
        except BaseException:
            for _entry, pending in futures:
                pending.cancel()
            raise
    if exhausted is not None:
        # 线程池退出时已等待运行中的任务；如实报告整批中实际绑定成功的文件数。
        bound = sum(
            1
            for _entry, future in futures
            if future.done() and not future.cancelled() and future.exception() is None
        )
        raise SourceHashBudgetExceeded(len(selected), bound) from exhausted
    return results


def _with_unreadable_marks(
    snapshot: IndexCandidateSnapshot, bound: IndexCandidateSnapshot
) -> IndexCandidateSnapshot:
    """把绑定时不可读的条目带回候选，使索引器不能复用旧行声称其最新（#1654）。

    其余条目保持原样：候选比较忽略摘要，只有不可读标记需要索引器看到。
    """
    from ..index_source_stream import unreadable_source_reason

    marked = {
        entry.rel_path: entry
        for entry in bound.entries
        if entry.fingerprint is not None
        and unreadable_source_reason(entry.fingerprint.content_hash) is not None
    }
    if not marked:
        return snapshot
    entries = tuple(marked.get(entry.rel_path, entry) for entry in snapshot.entries)
    return replace(snapshot, entries=entries)


_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
_COPY_CHUNK = 8 * 1024 * 1024


def _copy_sealed_database(source: Path, destination: Path) -> bool:
    """把已封存的父版本按字节复制进已建好的私有库文件；不适用时返回 ``False``。

    #1673：``sqlite3`` 的 backup 按页复制，本仓库 343 MB 实测 5.7–7 秒。已封存
    版本是只读、回滚日志模式、无任何旁路文件的单个主库（``seal``），其字节即是
    完整一致的数据库，大块顺序复制即可得到同一个库。父版本带旁路文件（不应
    出现）时退回 backup。目标文件就地截断写入，保持 ``begin`` 记录的文件身份；
    复制前后父版本的 stat 必须一致，否则退回 backup。
    """
    if any(os.path.lexists(f"{source}{suffix}") for suffix in _SQLITE_SIDECARS):
        return False
    before = os.stat(source)
    with open(source, "rb") as reader, open(destination, "r+b") as writer:
        writer.truncate(0)
        while chunk := reader.read(_COPY_CHUNK):
            writer.write(chunk)
    after = os.stat(source)
    copied = (
        (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        and not any(os.path.lexists(f"{source}{suffix}") for suffix in _SQLITE_SIDECARS)
        and os.path.getsize(destination) == before.st_size
    )
    if not copied:
        with open(destination, "r+b") as writer:
            writer.truncate(0)  # 退回 backup 前恢复为空库文件
    return copied


@dataclass(frozen=True)
class GenerationCandidate:
    """把源码候选与完整父版本身份绑定，首次发布也绑定目标项目。"""

    canonical_root: str
    logical_path: str
    parent: GenerationSelector | None
    snapshot: IndexCandidateSnapshot
    source_contents: tuple[object, ...] | None = None


@dataclass(frozen=True)
class PreparedGeneration:
    """已关闭全部构建连接、尚未对读者可见的版本。"""

    candidate: GenerationCandidate
    selector: GenerationSelector
    result: SyncResult
    allow_permanent_rejections: bool = False


def _flush_directory(path: Path) -> None:
    """POSIX 同步目录项；Windows 不宣称具备目录掉电持久性。"""
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace(source: Path, target: Path) -> None:
    """POSIX rename(2) 本身原子；Windows 需 POSIX 语义改名才能越过持有句柄的读者。"""
    if IS_WINDOWS:  # pragma: no cover - Windows 原生改名 (E4, 2026-10-13)
        replace_file(source, target)
        return
    os.replace(source, target)


def _write_atomic(path: Path, data: bytes) -> None:
    """先刷盘临时文件，再原子替换入口并同步父目录；Windows 只保证原子、不保证掉电持久。"""
    temporary = path.parent / f"selector-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(temporary, path)
        _flush_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


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
        self._database_identities: dict[str, tuple[int, int]] = {}
        # 构建中的私有版本由本对象钉住；进程被杀即释放，孤儿可被回收（slice 6）。
        self._build_pins: dict[str, GenerationPin] = {}
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
        connection = sqlite3.connect(lock_path, timeout=LEASE_TIMEOUT_S)
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                # 租约超时是可重试的忙错误，而非裸 ``database is locked``（E3/E5）。
                if _lease_busy(exc):
                    raise IndexWriterBusy() from exc
                raise
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

    def _snapshot(
        self, discovery_seconds: float | None = None
    ) -> IndexCandidateSnapshot:
        return build_index_candidate_snapshot(
            str(self.root),
            max_files=self.scope.certification_max_files,
            exclude_patterns=self.scope.effective_excludes,
            walk_fn=lambda root: walk_index_candidate_entries(
                root,
                excluded_dir_names=frozenset(EXCLUDE_DIRS),
                discovery_seconds=discovery_seconds,
            ),
            language_fn=_language_from_ext,
            discovery_seconds=discovery_seconds,
        )

    def _publication_parent(self) -> GenerationSelector | None:
        """仅写入租约内允许恢复未完成的首次激活；普通读者始终拒绝缺失选择器。"""
        marker = Path(self.logical_path).with_suffix(".generation")
        try:
            parent = self.active_selector()
        except InvalidGenerationSelector as exc:
            if str(exc) != "INDEX_GENERATION_SELECTOR_MISSING":
                raise
            with marker.open("rb") as handle:
                pending = handle.read(4105)
            if not pending.startswith(b"pending\n"):
                raise
            decode_generation_selector(
                pending[8:],
                canonical_root=str(self.root),
                logical_path=self.logical_path,
            )
            return None
        if parent is not None:
            # 选择器提交后发生故障时，在下一次写租约内补齐完成标记。
            with marker.open("rb") as handle:
                complete = handle.read(3) == b"1\n"
            if not complete:
                _write_atomic(marker, b"1\n")
        return parent

    def capture(
        self, snapshot_factory: Callable[[], IndexCandidateSnapshot] | None = None
    ) -> GenerationCandidate:
        """先捕获父身份再扫描；内容证据独立于旧索引器候选 DTO。"""
        with self._lease():
            parent = self._publication_parent()
        snapshot = (snapshot_factory or self._snapshot)()
        bound = _bind_source_hashes(snapshot)
        return GenerationCandidate(
            str(self.root),
            self.logical_path,
            parent,
            _with_unreadable_marks(snapshot, bound),
            _source_contents(bound),
        )

    def _admit(self, candidate: GenerationCandidate) -> None:
        if (
            candidate.canonical_root != str(self.root)
            or candidate.logical_path != self.logical_path
            or self._publication_parent() != candidate.parent
        ):
            raise Superseded("INDEX_GENERATION_SUPERSEDED")

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """固定一个不可变版本；后续发布不改变当前会话，缺失时不创建数据库。"""
        selector = self.active_selector()
        if selector is None:
            raise FileNotFoundError("INDEX_GENERATION_MISSING")
        pin = pin_generation(self.storage, selector.generation_id)
        connection = sqlite3.connect(
            self.database(selector).as_uri() + "?mode=ro", uri=True
        )
        try:
            connection.row_factory = sqlite3.Row
            yield connection
        finally:
            connection.close()
            if pin is not None:
                pin.release()

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
        pin = pin_generation(self.storage, selector.generation_id)
        if pin is None:
            raise Superseded("INDEX_GENERATION_RETIRING")
        self._build_pins[selector.generation_id] = pin
        database.parent.mkdir(exist_ok=False)
        database.touch(exist_ok=False)
        info = database.stat()
        self._database_identities[selector.generation_id] = (info.st_dev, info.st_ino)
        if candidate.parent is None:
            # 首次发布采纳遗留旧库（#1554）；发布 CAS 照常拒绝过时候选。
            adopt_legacy_database(Path(self.logical_path), database)
        else:
            parent = self.database(candidate.parent)
            if not _copy_sealed_database(parent, database):
                source = sqlite3.connect(parent.as_uri() + "?mode=ro", uri=True)
                try:
                    destination = sqlite3.connect(database)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                finally:
                    source.close()
        # #1671：私有副本不继承父版本的稳定失败记录；只有收敛的运行重新签发。
        clear_record_at(database)
        return selector

    def seal(self, selector: GenerationSelector) -> None:
        """构建连接释放后合并 WAL、刷盘并标记文件级只读；完成之前不能发布。

        公共只读连接可 ``ATTACH ... mode=rw`` 同一文件绕过 ``mode=ro``
        （rfcs/evidence/0032-feasibility E5），因此发布前由操作系统只读位兜底。
        """
        database = self.database(selector)
        self._verify_database(selector)
        connection = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True)
        try:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if checkpoint.fetchone()[0] != 0:
                raise RuntimeError("INDEX_GENERATION_CHECKPOINT_BUSY")
            # 只读 WAL 库的读者会另建可写 -wal/-shm；切回回滚日志使版本只剩主库。
            # #1821：这一步 SQLite 不调用忙处理器，由 leave_wal 按忙等待期限重试。
            journal = leave_wal(connection)
        finally:
            connection.close()
        if journal != "delete" or any(
            os.path.lexists(f"{database}{suffix}")
            for suffix in ("-wal", "-shm", "-journal")
        ):
            raise RuntimeError("INDEX_GENERATION_SIDECAR_PRESENT")
        self._verify_database(selector)
        with database.open("r+b") as handle:
            os.fsync(handle.fileno())
        # 只读位丢失（如掉电前未落盘）只会退回可写文件，不会损坏已刷盘内容。
        mark_read_only(database)
        _flush_directory(database.parent)
        _flush_directory(database.parent.parent)

    def _verify_database(self, selector: GenerationSelector) -> None:
        info = self.database(selector).lstat()
        if not stat.S_ISREG(info.st_mode) or (
            info.st_dev,
            info.st_ino,
        ) != self._database_identities.get(selector.generation_id):
            raise RuntimeError("INDEX_GENERATION_DATABASE_CHANGED")

    def prepare(self, candidate: GenerationCandidate) -> PreparedGeneration:
        """复制已发布父数据库，再执行真实 TSA 增量同步，失败不会触碰父版本。"""
        selector = self.begin(candidate)
        try:
            cache = ASTCache(str(self.root), str(self.database(selector)))
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
        except BaseException:
            self.abandon(selector)  # #1595：失败构建立即回收
            raise
        return PreparedGeneration(candidate, selector, result)

    def publish(self, prepared: PreparedGeneration) -> GenerationSelector:
        """发布前重新校验完整父身份及源码，原子替换唯一活动选择器。"""
        with self._lease(), self.abandoning(prepared.selector):
            self._admit(prepared.candidate)
            previous = prepared.candidate.snapshot
            current = self._snapshot(recheck_discovery_seconds(previous))
            check_publication_sources(
                previous,
                current,
                prepared.candidate.source_contents
                if prepared.candidate.source_contents is not None
                else _source_contents(previous),
                lambda: _source_contents(_bind_source_hashes(current)),
                allow_permanent_rejections=prepared.allow_permanent_rejections,
            )
            database = self.database(prepared.selector)
            if not database.is_file():
                raise FileNotFoundError("INDEX_GENERATION_DATABASE_MISSING")
            self._verify_database(prepared.selector)
            data = prepared.selector.encode()
            activated = Path(self.logical_path).with_suffix(".generation")
            first = prepared.candidate.parent is None
            if first:
                _write_atomic(activated, b"pending\n" + data)
            _write_atomic(self.selector_path, data)
            if first:
                _write_atomic(activated, b"1\n")
            self._retire(prepared.selector)
            return prepared.selector

    @contextmanager
    def abandoning(self, selector: GenerationSelector) -> Iterator[None]:
        """离开时回收未发布的私有构建（异常或结果不可发布）；已发布时为空操作。"""
        try:
            yield
        finally:
            self.abandon(selector)

    def abandon(self, selector: GenerationSelector) -> None:
        """失败或放弃发布的构建立即释放构建钉并回收，绝不触碰活动版本（#1595）。

        成功发布时 ``_retire`` 已取走构建钉，因此本方法对已发布版本是空操作。
        """
        if selector.generation_id not in self._build_pins:
            return
        try:
            if self.active_selector() == selector:
                return
        except (OSError, InvalidGenerationSelector):
            return  # 无法确认活动版本时宁可留给常规回收
        self._build_pins.pop(selector.generation_id).release()
        try:
            retire_unpublished(self.storage, selector.generation_id)
        except OSError:
            logger.warning("abandoned generation retirement failed", exc_info=True)

    def _retire(self, active: GenerationSelector) -> None:
        """发布后在租约内有界回收；失败只记录，已完成的发布不回滚。"""
        pin = self._build_pins.pop(active.generation_id, None)
        if pin is not None:
            pin.release()
        try:
            release_idle_readers()  # #1631：本线程空闲读者不再钉住旧版本
            retire_generations(self.storage, active.generation_id)
        except Exception:
            logger.warning("index generation retirement failed", exc_info=True)

    def sync(self) -> GenerationSelector:
        """捕获、隔离构建、发布一次完整默认范围索引。"""
        return self.publish(self.prepare(self.capture()))
