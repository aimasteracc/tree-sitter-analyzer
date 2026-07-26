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
_AST_CACHE_EXTRACTOR_VERSION = 14

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
        self.project_root = os.path.abspath(project_root)
        if db_path is None:
            db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        self.db_path = db_path
        self._local = threading.local()
        self._parser = Parser()
        self._index_lock = threading.Lock()
        self._fts5_available: bool | None = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()


def _walk_source_files(project_root: str) -> Iterator[str]:
    """Backward-compatible source walker re-export."""
    yield from _indexer._walk_source_files(project_root)
