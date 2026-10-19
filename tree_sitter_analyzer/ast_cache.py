#!/usr/bin/env python3
"""Stable facade for the SQLite-backed pre-indexed AST cache."""

from __future__ import annotations

import json  # noqa: F401  # historical monkeypatch surface
import os
import sqlite3
from collections.abc import Callable
import threading
from _thread import LockType
from weakref import WeakValueDictionary
from collections.abc import Iterator

from .cache import indexer as _indexer
from .cache.extraction import (  # noqa: F401
    _content_hash,
    _extract_symbols,
    _has_fts5,
    _node_text,
)
from .cache.helpers import (  # noqa: F401
    _build_function_entry,
    _commit_index_results,
)
from .cache.indexer import _EXT_TO_LANG, _language_from_ext  # noqa: F401
from .cache.maintenance import (  # noqa: F401
    reclaim_storage_after_full_rebuild as _reclaim_storage_after_full_rebuild,
)
from .cache.schema import (
    EXPECTED_SCHEMA_VERSIONS as _EXPECTED_SCHEMA_VERSIONS,  # noqa: F401
)
from .cache.writer_state import WriterFence
from .core.parser import Parser
from ._ast_cache_database_mixin import (
    ASTCacheDatabaseMixin,
    SchemaIntegrityError,
)
from ._ast_cache_graph_mixin import ASTCacheGraphMixin
from ._ast_cache_index_mixin import ASTCacheIndexMixin
from ._ast_cache_query_mixin import ASTCacheQueryMixin

# v3: #610 — Python module-level constants extracted as kind="constant".
# v4: #613 — Go package-level const/var specs extracted as kind="constant".
# v5: #613 — Rust const/static items extracted as kind="constant".
# v6: #614 — docstring/return_type/params serialized into symbols_json.
# v7: #624 — PHP const declarations extracted as kind="constant".
# v8: #626 — JS/TS function-local variables no longer over-captured.
# v9: #626 — Java function-local variables no longer over-captured.
# v10: #628 — C# function-local variables no longer over-captured.
# v11: #638 — call edges retain every same-named definition span.
# v12: #779 — walker depth cap raised from 20 to 100.
# v13: #949 — bash command-prefix environment variables are not declarations.
# v14: #1094 / RFC-0019 — symbols carry canonical extractor complexity.
# v15: #1275 (dogfood F5) — ast_index.imports_json entries carry a line
# field (dict entries instead of bare statement strings).
# v16: P1 causal envelopes project literal CommonJS/dynamic module calls.
# v17: P1 causal envelopes project C/C++ preprocessor includes.
# v18: P1 causal envelopes project static templates and Python dynamic imports.
# v19: retain unresolved JS/TS module calls as fail-closed evidence.
# v20: project JS/TS re-exports and aliased/reflection dynamic loads.
# v21: project TypeScript path references and pre-discover Python aliases.
# v22: project assignment aliases of Python dynamic-import loaders.
# v23: seal ambiguous Python scopes and project static Java/CommonJS loads.
# v24: project CommonJS aliases and C++20 imports for fail-closed reads.
# v33-v37: invalidate computed/header loaders, then retained execution paths.
# v38: loader projection fails closed by default instead of enumerating risks.
# v39：按语言分类驱动提取，修复成员作用域与 C++ 函数名称恢复。
# v40：Python 调用边携带接收者类型线索（RFC-0038 receiver_hint）。
# v41：接收者未被证明的调用不再按项目唯一方法名绑定为 project（#1669）。
# v42：改名导入的调用解析到真实目标，并在 metadata 中记录 import_alias（#1670）。
# v43：继承方法的 self.m() 调用按 MRO 解析到最近的定义（#1677）。
_AST_CACHE_EXTRACTOR_VERSION = 43

# Preserve the historical public exception identity after implementation split.
SchemaIntegrityError.__module__ = __name__


_writer_locks: WeakValueDictionary[str, LockType] = WeakValueDictionary()
_writer_locks_guard = threading.Lock()


def _shared_writer_lock(db_path: str) -> LockType:
    """同进程同数据库路径共用写入锁，最后一个缓存释放后不保留注册项。"""
    key = os.path.normcase(os.path.realpath(os.path.abspath(db_path)))
    with _writer_locks_guard:
        lock = _writer_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _writer_locks[key] = lock
        return lock


class ASTCache(
    ASTCacheDatabaseMixin,
    ASTCacheIndexMixin,
    ASTCacheQueryMixin,
    ASTCacheGraphMixin,
):
    """SQLite-backed persistent AST cache with a stable public API."""

    _extractor_version = _AST_CACHE_EXTRACTOR_VERSION

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        # Bind every entry path to one canonical root.  In particular, direct
        # force rebuilds use an O_NOFOLLOW walker and cannot safely rediscover a
        # project through a symlink spelling.
        self.project_root = os.path.realpath(os.path.abspath(project_root))
        default_db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        self._default_locator = (
            db_path is None or os.path.abspath(db_path) == default_db_path
        )
        self._read_only = False
        self._generation_managed = False
        self._generation_guard: Callable[[], None] | None = None
        self._publishes_project_index = False
        # #1673：私有构建由发布侧捕获时绑定的内容摘要（相对路径 -> 摘要）。
        self._bound_source_digests: dict[str, str] = {}
        self._unindexed_uri: str | None = None
        self._unindexed_anchor: sqlite3.Connection | None = None
        self._unindexed_sealed = False
        unindexed = False
        if db_path is None or os.path.abspath(db_path) == default_db_path:
            from .cache.generation_routing import resolve_index_location

            location = resolve_index_location(self.project_root)
            db_path = str(location.path)
            self._read_only = location.published
            # 首次发布前的默认库同样只能经版本存储写入（#1554 / E1，2026-10-13）；
            # 仅索引操作内绑定的私有构建库原地写。
            self._generation_managed = location.published or db_path == default_db_path
            self._generation_guard = location.verify
            if not location.published and db_path == default_db_path:
                unindexed = self._open_unindexed_reader(db_path)
        self.db_path = db_path
        self._local = threading.local()
        # RFC-0032 slice 5：原地写入的修订号围栏，schema 初始化完成后启用。
        self._writer_fence = WriterFence()
        self._parser = Parser()
        self._index_lock = _shared_writer_lock(
            default_db_path if self._read_only else db_path
        )
        self._fts5_available: bool | None = None
        self._cache_dir_fd: int | None = None
        self._cache_dir_identity: tuple[int, int] | None = None
        db_dir = os.path.dirname(db_path) or "."
        if not self._read_only:
            os.makedirs(db_dir, exist_ok=True)
        cache_dir = os.path.join(self.project_root, ".ast-cache")
        uses_project_mirror = os.path.abspath(db_path) == os.path.abspath(
            default_db_path
        )
        self._uses_project_mirror = uses_project_mirror
        if uses_project_mirror:
            os.makedirs(cache_dir, exist_ok=True)
        if os.name == "posix" and uses_project_mirror:
            # The default mirror is mutation-sensitive, so keep its directory
            # identity pinned for the cache lifetime.  A custom database has no
            # authority to create state inside a possibly read-only project.
            flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            cache_dir_fd = os.open(cache_dir, flags)
            try:
                info = os.fstat(cache_dir_fd)
            except BaseException:
                os.close(cache_dir_fd)
                raise
            self._cache_dir_fd = cache_dir_fd
            self._cache_dir_identity = (info.st_dev, info.st_ino)
        try:
            if self._read_only:
                self._fts5_available = bool(
                    self._get_conn()
                    .execute("SELECT 1 FROM sqlite_master WHERE name='ast_symbols_fts'")
                    .fetchone()
                )
            else:
                self._init_db()
                if unindexed:
                    # 空库只读：原始连接写入会静默丢失，须与已发布版本一样拒绝。
                    self._unindexed_sealed = True
                    self._get_conn().execute("PRAGMA query_only=ON")
            if self._cache_dir_fd is not None:  # pragma: no branch - POSIX owner
                info = os.stat(cache_dir, follow_symlinks=False)
                if (info.st_dev, info.st_ino) != self._cache_dir_identity:
                    raise RuntimeError(
                        "AST cache directory changed while opening database"
                    )
        except BaseException:
            self.close()
            raise

    def __del__(self) -> None:
        """Release pinned cache resources when callers omit explicit cleanup."""
        try:
            self.close()
        except Exception:
            return

    @property
    def db_path(self) -> str:
        if self._default_locator:
            from .cache.generation_reads import current_read_location

            location = current_read_location(self.project_root)
            if location is not None:
                return str(location.path)
        return self._db_path

    @db_path.setter
    def db_path(self, path: str) -> None:
        self._db_path = path

    @property
    def _owns_project_mirror(self) -> bool:
        """原地默认库或待发布的版本构建库：删除后派生镜像不得继续存活（#1554）。"""
        return self._uses_project_mirror or self._publishes_project_index

    def _open_unindexed_reader(self, legacy_path: str) -> bool:
        """既无旧库也无版本时读者用进程内空库，只读调用不在项目内建库（#1554）。

        锚连接随缓存对象存活（``close()`` 后仍可重新取连接），发布后才释放。
        """
        if os.path.lexists(legacy_path):
            return False
        from .cache.generation_bootstrap import (
            open_unindexed_anchor,
            unindexed_database_uri,
        )

        uri = unindexed_database_uri()
        self._unindexed_anchor = open_unindexed_anchor(uri)
        self._unindexed_uri = uri
        return True

    def _adopt_published_generation(self) -> None:
        """写入成功后换绑只读连接，保留调用方缓存对象和解析器配置。"""
        from .cache.generation_reads import adopt_read_location
        from .cache.generation_routing import resolve_index_location

        location = resolve_index_location(self.project_root)
        adopt_read_location(self.project_root, location)
        ASTCacheDatabaseMixin.close(self)
        self._unindexed_uri = None
        if self._unindexed_anchor is not None:
            self._unindexed_anchor.close()
            self._unindexed_anchor = None
        self._read_only = location.published
        self.db_path = str(location.path)
        self._generation_managed = location.published
        self._uses_project_mirror = False


def _walk_source_files(project_root: str) -> Iterator[str]:
    """Backward-compatible source walker re-export."""
    yield from _indexer._walk_source_files(project_root)
