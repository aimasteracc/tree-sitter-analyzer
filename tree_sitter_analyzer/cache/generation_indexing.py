"""把现有完整索引流程放入私有版本，认证成功后才发布。"""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
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
from .publication_policy import publishable_result, publishable_sync

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


def _first_publication(candidate: Any) -> bool:
    """首次发布前旧路由原地保留部分结果（如缺少可选语法时的其余文件）。

    无父版本可保护时，带单文件失败的结果照常发布，否则这类项目的自动索引
    永远为空（#1554）；已发布项目只接受稳定单文件失败（见 publication_policy）。
    """
    return candidate.parent is None


def mutate_published_cache(
    cache: Any,
    operation: Callable[[ASTCache], _T],
    *,
    scope: SourceScopeDescriptor | None = None,
    candidate_snapshot: IndexCandidateSnapshot | None = None,
    expected_path: Path | None = None,
) -> _T:
    """默认库的显式单文件、重建和失效操作只写私有副本，首次发布前亦然（#1554）。"""
    from ..ast_cache import ASTCache
    from .generation_store import Superseded

    store = project_store(cache.project_root, scope or make_source_scope_descriptor())
    with cache._index_lock:
        candidate = store.capture(
            (lambda: candidate_snapshot) if candidate_snapshot is not None else None
        )
        try:
            # 调用方读到的库必须仍是父版本；首次发布前即旧定位符本身（#1554）。
            if expected_path is not None and expected_path != (
                store.database(candidate.parent)
                if candidate.parent is not None
                else logical_index_path(cache.project_root)
            ):
                raise Superseded("INDEX_GENERATION_SUPERSEDED")
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
            if publishable_result(result) or _first_publication(candidate):
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
        writable._publishes_project_index = True
        try:
            arguments["candidate_snapshot"] = candidate.snapshot
            result = (sync_factory or IncrementalSync)(writable).sync(**arguments)
        finally:
            writable.close()
        permanent_cleanup = permanent_rejections_only(candidate.snapshot)
        if _first_publication(candidate) or publishable_sync(
            result, permanent_cleanup=permanent_cleanup
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
        # #1562：只有稳定单文件失败（如缺少可选语法）时照常发布，完整性如实标为
        # incomplete；与 publication_policy 对 index_project/sync 的规则一致。
        stable_only = result.get("stable_failures_only") is True
        if not stable_only and (
            not result.get("success") or not result.get("scope_complete")
        ):
            result["success"] = False
            result["published"] = False
            return result
        try:
            store.seal(selector)
            store.publish(PreparedGeneration(candidate, selector, SyncResult()))
        except (OSError, ValueError, RuntimeError) as exc:
            failure = _publication_error(exc, root, "generation_publication")
            try:
                failure["published"] = store.active_selector() == selector
            except (OSError, ValueError):
                failure["published"] = None
            return failure
        result["published"] = True
        if stable_only and not result.get("scope_complete"):
            # 已发布但未认证：success 保持 False（PR #1350），完整性如实为 incomplete。
            result["completeness"] = "incomplete"
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


def mutate_index_path(root: str, path: Path, operation: Callable[[Path], _T]) -> _T:
    """派生数据持久化也只能修改私有副本；首次发布前的旧库先被采纳再写（#1554）。"""
    from ..ast_cache import ASTCache
    from .generation_routing import resolve_index_location

    location = resolve_index_location(root)
    if not location.published:
        if location.path != path:
            raise ValueError("INDEX_GENERATION_PATH_MISMATCH")
        if path != logical_index_path(root):
            # 索引操作内绑定的私有构建库，由外层操作负责发布。
            return operation(path)
    cache = ASTCache(root)
    try:
        return mutate_published_cache(
            cache,
            lambda writable: operation(Path(writable.db_path)),
            expected_path=path,
        )
    finally:
        cache.close()
