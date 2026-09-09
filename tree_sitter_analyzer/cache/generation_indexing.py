"""把现有完整索引流程放入私有版本，认证成功后才发布。"""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from ..ast_cache import ASTCache
    from ..mcp.tools.full_index_tool import CodeGraphFullIndexTool

from ..incremental_sync_support import SyncResult
from ..index_source_scope import SourceScopeDescriptor, make_source_scope_descriptor
from ..indexing_candidate_materialization import release_index_candidate_snapshot
from ..indexing_snapshot import IndexCandidateSnapshot
from .generation_routing import (
    generation_storage_path,
    logical_index_path,
    private_index,
)
from .generation_store import (
    GenerationStore,
    PreparedGeneration,
    permanent_rejections_only,
)

_T = TypeVar("_T")


def project_store(root: str, scope: SourceScopeDescriptor) -> GenerationStore:
    storage = generation_storage_path(root)
    for directory in (storage.parent, storage):
        if os.path.lexists(directory):
            info = os.lstat(directory)
            if (
                not stat.S_ISDIR(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("INDEX_GENERATION_PATH_UNSAFE")
    return GenerationStore(
        root,
        str(storage),
        scope=scope,
        logical_path=str(logical_index_path(root)),
    )


def mutate_published_cache(
    cache: Any,
    operation: Callable[[ASTCache], _T],
    *,
    scope: SourceScopeDescriptor | None = None,
    candidate_snapshot: IndexCandidateSnapshot | None = None,
) -> _T:
    """已切换项目的显式单文件、重建和失效操作仍只能写私有副本。"""
    from ..ast_cache import ASTCache
    from .generation_store import Superseded

    store = project_store(cache.project_root, scope or make_source_scope_descriptor())
    with cache._index_lock:
        candidate = store.capture(
            (lambda: candidate_snapshot) if candidate_snapshot is not None else None
        )
        try:
            if candidate_snapshot is not None and (
                not candidate_snapshot.publication_bound
                or candidate_snapshot.publication_parent != candidate.parent
            ):
                raise Superseded("INDEX_GENERATION_SUPERSEDED")
            selector = store.begin(candidate)
            writable = ASTCache(cache.project_root, str(store.database(selector)))
            try:
                result = operation(writable)
            finally:
                writable.close()
            failed = isinstance(result, dict) and (
                result.get("status") == "error"
                or result.get("errors")
                or result.get("backfill_errors")
            )
            if not failed:
                store.seal(selector)
                store.publish(PreparedGeneration(candidate, selector, SyncResult()))
                cache._adopt_published_generation()
            return result

        finally:
            if candidate_snapshot is None:
                release_index_candidate_snapshot(candidate.snapshot)


def run_incremental_sync(
    cache: Any, *, sync_factory: Any = None, **arguments: Any
) -> SyncResult:
    """watcher、CLI 和 MCP 共用隔离同步；已有候选必须保留捕获时的父身份。"""
    from ..ast_cache import ASTCache
    from ..incremental_sync import IncrementalSync
    from .generation_store import Superseded

    scope = arguments["source_scope"]
    store = project_store(cache.project_root, scope)
    supplied = arguments.get("candidate_snapshot")
    candidate = store.capture((lambda: supplied) if supplied is not None else None)
    try:
        if supplied is not None and (
            not supplied.publication_bound
            or supplied.publication_parent != candidate.parent
        ):
            raise Superseded("INDEX_GENERATION_SUPERSEDED")
        selector = store.begin(candidate)
        writable = ASTCache(cache.project_root, str(store.database(selector)))
        try:
            arguments["candidate_snapshot"] = candidate.snapshot
            result = (sync_factory or IncrementalSync)(writable).sync(**arguments)
        finally:
            writable.close()
        permanent_cleanup = permanent_rejections_only(candidate.snapshot)
        if (
            (result.scope_complete or permanent_cleanup)
            and not result.errors
            and not result.backfill_errors
            and not result.manifest_certification_failed
        ):
            store.seal(selector)
            store.publish(
                PreparedGeneration(
                    candidate,
                    selector,
                    result,
                    allow_permanent_rejections=permanent_cleanup,
                )
            )
            cache._adopt_published_generation()
        return result

    finally:
        if supplied is None:
            release_index_candidate_snapshot(candidate.snapshot)


async def run_full_index(
    tool: CodeGraphFullIndexTool, arguments: dict[str, Any]
) -> dict[str, Any]:
    tool.validate_arguments(arguments)
    if not tool.project_root:
        return await tool._execute_in_place(arguments)
    started_at = time.monotonic()
    root = os.path.realpath(os.path.abspath(tool.project_root))
    tool.project_root = root
    scope = make_source_scope_descriptor(
        no_default_excludes=bool(arguments.get("no_default_excludes", False)),
        exclude_patterns=tuple(arguments.get("exclude_patterns") or ()),
        certification_max_files=arguments["max_files"],
    )

    def capture() -> IndexCandidateSnapshot:
        if arguments.get("mode", "incremental") == "full":
            return tool._build_candidate_snapshot(
                scope.certification_max_files,
                scope.effective_excludes,
                materialize=True,
            )
        return tool._build_candidate_snapshot(
            scope.certification_max_files, scope.effective_excludes
        )

    try:
        store = project_store(root, scope)
        candidate = store.capture(capture)
    except Exception as exc:
        return _publication_error(exc, root, "candidate_discovery")
    entered = False
    try:
        try:
            selector = store.begin(candidate)
        except (OSError, ValueError, RuntimeError) as exc:
            return _publication_error(exc, root, "generation_publication")
        with private_index(
            root, store.database(selector), verify=store._verify_directories
        ):
            entered = True
            result = await tool._execute_in_place(
                arguments, candidate.snapshot, started_at=started_at
            )
        if not result.get("success") or not result.get("scope_complete"):
            result["success"] = False
            result["published"] = False
            return result
        try:
            store.seal(selector)
            store.publish(PreparedGeneration(candidate, selector, SyncResult()))
        except (OSError, ValueError, RuntimeError) as exc:
            return _publication_error(exc, root, "generation_publication")
        result["published"] = True
        result["generation_id"] = selector.generation_id
        result["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        return result
    finally:
        if not entered:
            release_index_candidate_snapshot(candidate.snapshot)


def _publication_error(exc: Exception, root: str, phase: str) -> dict[str, Any]:
    from ..mcp.utils.error_sanitizer import bounded_safe_error_message

    error, truncated = bounded_safe_error_message(exc, root)
    if phase == "candidate_discovery":
        error = "Candidate discovery failed: " + error
    return {
        "success": False,
        "verdict": "ERROR",
        "published": False,
        "phase": phase,
        "error": error,
        "error_truncated": truncated,
    }
