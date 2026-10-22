"""#1749：按内容证据复用上一份解析上下文。

每次刷新都在新的索引版本上运行，数据库标识（路径、mtime、大小）总是不同，旧的
标识缓存因此从不命中，解析上下文每次全量重建——开销与改动大小无关。这里按项目
记住最近一份上下文及其输入状态；下一次构建时读取各文件的内容证据
（:func:`read_evidence`），只要文件集合不变、改动文件不多，就在旧状态上只替换改动
文件（:func:`patch_context_state`），结果与全量构建逐项相同。

不复用的情形（回退全量）：没有记住的状态、证据不可读、文件集合变化（新增、删除、
改名）、模块映射变化、改动文件超过上限，或修补时读库失败。``TSA_RESOLVER_CONTEXT_REUSE=0``
关闭复用。旧对象从不修改：修补总是产生新的字典与列表。
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ._context_inputs import ContextState, Evidence, changed_files, read_evidence

if TYPE_CHECKING:
    from ._context import ResolverContext

logger = logging.getLogger(__name__)

#: 改动文件超过 ``max(_MIN_LIMIT, 文件数 × _FRACTION)`` 时全量重建更划算也更简单。
_MIN_LIMIT = 32
_FRACTION = 0.1

_LOCK = threading.Lock()
#: 项目 -> (内容证据, 输入状态, 上下文)；证据不可读的状态不记。
_LAST: dict[str, tuple[Evidence, ContextState, ResolverContext]] = {}


def enabled() -> bool:
    value = os.environ.get("TSA_RESOLVER_CONTEXT_REUSE")
    return value is None or value.strip().lower() not in ("0", "false", "no", "off")


def _project_key(cache: Any) -> str:
    return os.path.normcase(os.path.realpath(str(getattr(cache, "project_root", ""))))


def remember(cache: Any, state: ContextState, ctx: ResolverContext) -> None:
    """记住 ``ctx`` 作为该项目下一次构建的起点（证据不可读的状态不记）。"""
    if not enabled() or state.evidence is None:
        return
    with _LOCK:
        _LAST[_project_key(cache)] = (state.evidence, state, ctx)


def forget_all() -> None:
    with _LOCK:
        _LAST.clear()


def reuse(cache: Any) -> ResolverContext | None:
    """在记住的上下文上修补出 ``cache`` 当前内容的上下文；不能保证相同时返回 None。"""
    if not enabled():
        return None
    with _LOCK:
        last = _LAST.get(_project_key(cache))
    if last is None:
        return None
    old_evidence, old_state, old_ctx = last
    conn = cache.get_conn()
    try:
        evidence, ordered = read_evidence(conn)
    except sqlite3.Error:
        return None
    changed = changed_files(old_evidence, evidence)
    if changed is None or len(changed) > max(
        _MIN_LIMIT, int(len(evidence) * _FRACTION)
    ):
        return None
    try:
        return _rebuilt(cache, conn, old_state, old_ctx, evidence, ordered, changed)
    except sqlite3.Error:
        logger.debug("resolver context patch failed; rebuilding", exc_info=True)
        return None


def _rebuilt(
    cache: Any,
    conn: sqlite3.Connection,
    old_state: ContextState,
    old_ctx: ResolverContext,
    evidence: dict[str, tuple[Any, ...]],
    ordered: list[tuple[str, str]],
    changed: set[str],
) -> ResolverContext | None:
    from ._context import context_from_state, patch_context_state

    if changed:
        state = patch_context_state(conn, old_state, evidence, ordered, changed)
        if state is None:
            return None
    else:
        state = replace(old_state, evidence=evidence)
    ctx = context_from_state(
        cache, conn, state, file_class_methods=_class_methods(cache, old_ctx, changed)
    )
    annotations = _annotations(conn, old_state, old_ctx, changed)
    if annotations is not None:
        ctx._annotation_index = annotations  # type: ignore[attr-defined]  # noqa: SLF001
    remember(cache, state, ctx)
    return ctx


def _class_methods(
    cache: Any, old_ctx: ResolverContext, changed: set[str]
) -> dict[str, dict[str, dict[str, int]]] | None:
    """旧上下文已载入类方法表时只重读改动文件；否则保持惰性（None）。"""
    if not old_ctx._file_class_methods_loaded:  # noqa: SLF001
        return None
    from ._context import _build_file_class_methods_from_cache

    old = old_ctx._file_class_methods  # noqa: SLF001
    kept = {path: value for path, value in old.items() if path not in changed}
    if changed:
        kept.update(_build_file_class_methods_from_cache(cache, changed))
    return kept


def _annotations(
    conn: sqlite3.Connection,
    old_state: ContextState,
    old_ctx: ResolverContext,
    changed: set[str],
) -> Any:
    """旧上下文已建注解索引时只重读改动文件；否则保持惰性（None）。"""
    from ._annotated import AnnotationIndex, _load_index

    old = getattr(old_ctx, "_annotation_index", None)
    if not isinstance(old, AnnotationIndex):
        return None
    stale = {
        sid
        for path in changed
        for _name, _kind, sid in old_state.file_symbols.get(path, ())
    }
    fresh = AnnotationIndex()
    if changed:
        _load_index(conn, fresh, changed)
    return AnnotationIndex(
        classes={p: v for p, v in old.classes.items() if p not in changed}
        | fresh.classes,
        returns={s: v for s, v in old.returns.items() if s not in stale}
        | fresh.returns,
        kinds={s: v for s, v in old.kinds.items() if s not in stale} | fresh.kinds,
        lines={s: v for s, v in old.lines.items() if s not in stale} | fresh.lines,
        module_types={p: v for p, v in old.module_types.items() if p not in changed}
        | fresh.module_types,
    )
