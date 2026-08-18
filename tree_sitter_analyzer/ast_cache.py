#!/usr/bin/env python3
"""Stable facade for the SQLite-backed pre-indexed AST cache."""

from __future__ import annotations

import json  # noqa: F401  # historical monkeypatch surface
import os
import threading
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
_AST_CACHE_EXTRACTOR_VERSION = 37

# Preserve the historical public exception identity after implementation split.
SchemaIntegrityError.__module__ = __name__


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
        if db_path is None:
            db_path = default_db_path
        self.db_path = db_path
        self._local = threading.local()
        self._parser = Parser()
        self._index_lock = threading.Lock()
        self._fts5_available: bool | None = None
        self._cache_dir_fd: int | None = None
        self._cache_dir_identity: tuple[int, int] | None = None
        db_dir = os.path.dirname(db_path) or "."
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
            self._init_db()
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


def _walk_source_files(project_root: str) -> Iterator[str]:
    """Backward-compatible source walker re-export."""
    yield from _indexer._walk_source_files(project_root)
