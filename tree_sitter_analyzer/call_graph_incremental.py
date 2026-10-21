"""发布之后按刷新的解析范围增量更新内存调用图（#1723）。

#1708 之后，发布刷新后的第一次 ``nav callers`` 仍要重建整张内存调用图：读行、算摘要、
逐边解析约 19 万条边、写回解析结果，负载下 6–14 s。#1714（#1696）的刷新已经算出
**解析范围**：改动文件、解析到它们的边、解析面变化的名字及其经导入 / 别名 / MRO /
类型化导出的依赖文件；范围之外的边的输入与上一轮相同，库里的行也逐字节不变。

这里沿用同一范围更新上一版本的图：

1. 函数定义：未改动文件沿用上一张图的 ``FunctionRef``，改动文件重新读取，按
   ``ast_index`` 的读取顺序排列（与全量构图同序）；
2. 边：上一张图按边 rowid 保存了每行的解析结果。受影响的行——调用方文件或被调名在
   范围内、或结果指向改动文件中的函数——按新库重新读取并解析，其余沿用；
3. 全部结果按 rowid 排序后用全量构图的同一个应用函数写入图（``_apply_edge_records``），
   因此与在新库上全新构图得到的状态逐项相同。

任一前提不成立就放弃增量（调用方照常全量构图），并给出原因：范围回填退回了全量、
上一张图不是从刷新所基于的那份库构建的、有函数定义的文件集合变了（模块映射随之
变化）、包再导出或子类证据变了、行数对不上。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .cached_reexport_binding import PackageReexportBinder
    from .call_graph import CachedCallGraph, FunctionRef
    from .call_graph_self_dispatch import SubclassIndex

logger = logging.getLogger(__name__)

#: 一次 SQL 的占位符上限（远低于 SQLite 默认上限）。
_CHUNK = 500

_lock = threading.Lock()
#: 项目根 -> 最近一次刷新的解析范围（发布之后由预构图取走）。
_plans: dict[str, RefreshPlan] = {}
#: 项目根 -> 最近一次记下的范围（不取走；供诊断与刷新答复）。
_last: dict[str, RefreshPlan] = {}


@dataclass(frozen=True)
class RefreshPlan:
    """一次刷新的范围回填决定，及其所基于与将发布的版本（generation id）。"""

    base_generation: str | None
    changed: frozenset[str]
    files: frozenset[str]
    names: frozenset[str]
    reason: str
    #: 刷新写入的候选版本（发布后即活动版本）；发布的不是它时范围不适用。
    generation: str = ""


@dataclass(frozen=True)
class Alignment:
    """全量构图读取的每一行：rowid、被调名与调用方文件（与解析结果一一对应）。"""

    ids: list[int]
    callee_names: list[str]
    caller_files: list[str]


def _key(project_root: str) -> str:
    return os.path.normcase(os.path.realpath(project_root))


# ---------------------------------------------------------------------------
# 刷新侧：记下范围回填的决定
# ---------------------------------------------------------------------------


def note_scope(cache: Any, decision: Any) -> None:
    """``backfill_scope.decide`` 之后调用：记下本轮的范围与刷新所基于的已发布库。"""
    root = getattr(cache, "project_root", None)
    if not root:
        return
    scope = getattr(decision, "scope", None)
    reason = str(getattr(decision, "reason", "") or "")
    if scope is None:
        # 范围回填退回了全量：图同样全量重建（记下原因）。
        plan = RefreshPlan(None, frozenset(), frozenset(), frozenset(), reason)
    else:
        plan = RefreshPlan(
            base_generation=_published_generation(str(root)),
            changed=frozenset(getattr(decision, "changed", ()) or ()),
            files=frozenset(scope.files),
            names=frozenset(scope.names),
            reason=reason,
            generation=generation_of(cache) or "",
        )
    with _lock:
        _plans[_key(str(root))] = plan
        _last[_key(str(root))] = plan


def last_plan(project_root: str) -> RefreshPlan | None:
    """`project_root` 最近一次刷新记下的范围（诊断用，不取走）。"""
    with _lock:
        return _last.get(_key(project_root))


def take_plan(project_root: str) -> RefreshPlan | None:
    """取走 ``project_root`` 最近一次刷新的范围（每次发布只用一次）。"""
    with _lock:
        return _plans.pop(_key(project_root), None)


def _real(database: str) -> str:
    return os.path.normcase(os.path.realpath(database)) if database else ""


def _published_generation(project_root: str) -> str | None:
    try:
        from .cache.generation_routing import resolve_index_location

        location = resolve_index_location(project_root)
    except (OSError, ValueError):
        return None
    selector = getattr(location, "selector", None)
    return str(selector.generation_id) if selector is not None else None


# ---------------------------------------------------------------------------
# 构图侧：全量构图时记下对齐依据
# ---------------------------------------------------------------------------


def generation_of(cache: Any) -> str | None:
    """构图所读版本的 generation id；不是已封存的版本（或无法判定）时为 None。

    已发布的版本封存后不再改写，id 即内容身份：已发布库位于
    ``generations/<id>/index.db``；认证快照是某个版本的私有副本，带 ``source_generation``。
    """
    owner = getattr(cache, "_owner", None)
    snapshot = getattr(owner, "snapshot", None)
    if snapshot is not None:
        source = getattr(snapshot, "source_generation", None)
        return str(source) if source else None
    database = getattr(cache, "db_path", None)
    if not database:
        return None
    path = Path(str(database))
    if path.name != "index.db" or path.parent.parent.name != "generations":
        return None
    return path.parent.name


def alignment(edge_source: Any) -> Alignment | None:
    """边输入带 rowid 且按 rowid 递增读取时的对齐依据；否则 None（不支持增量）。"""
    ids = list(getattr(edge_source, "ids", None) or ())
    rows = getattr(edge_source, "rows", None)
    names = getattr(edge_source, "names", None)
    if not ids or rows is None or names is None or len(ids) != len(rows):
        return None
    if any(later <= earlier for earlier, later in zip(ids, ids[1:], strict=False)):
        return None
    callee = names.index("callee_name")
    caller = names.index("caller_file")
    return Alignment(
        ids,
        [str(row[callee] or "") for row in rows],
        [str(row[caller]) for row in rows],
    )


def alignment_from_index(cache: Any) -> Alignment | None:
    """边行未读取时（#1726 的已知摘要）从索引补读对齐依据；只在预构图启用时读取。

    一次性进程不会有下一次刷新后的增量，不为它付这次读取。
    """
    from . import call_graph_warm

    if cache is None or not call_graph_warm.enabled():
        return None
    try:
        rows = (
            cache.get_conn()
            .execute(
                "SELECT id, callee_name, file_path FROM edges "
                "WHERE kind = 'calls' ORDER BY id"
            )
            .fetchall()
        )
    except Exception:  # nosec B110 — 读不到对齐依据：这张图不作增量基础。
        return None
    return Alignment(
        [int(row[0]) for row in rows],
        [str(row[1] or "") for row in rows],
        [str(row[2]) for row in rows],
    )


def remember(
    graph: CachedCallGraph,
    aligned: Alignment | None,
    records: list[Any] | None,
    reexport_binder: PackageReexportBinder,
    subclasses: SubclassIndex,
) -> None:
    """把对齐依据、解析结果与输入证据留在图状态里，供下一次刷新后增量更新。

    只在读的是已封存版本、对齐依据与结果一一对应时保留；否则清除（不增量）。
    """
    generation = generation_of(graph._cache)
    usable = (
        aligned is not None
        and records is not None
        and len(records) == len(aligned.ids)
        and generation is not None
    )
    graph._incremental = (
        {
            "generation": generation,
            "alignment": aligned,
            "records": records,
            "binder": reexport_binder.evidence(),
            "children": children_of(subclasses),
            "function_files": _function_files(graph),
            "hierarchy": _hierarchy_of(graph),
        }
        if usable
        else None
    )


def binder_method_names(
    old: Any, new: Any, old_files: dict[str, Any], new_files: dict[str, Any]
) -> frozenset[str] | None:
    """包再导出绑定证据的变化所影响的方法名；无法界定时为 None（全量构图）。

    绑定把 `T.m()` 沿 `T` 的基类找到 `m`：类集合或某个类的基类变了，只有在
    这些类（及其新旧祖先）里定义的方法名的解析可能变化。模块映射或包再导出本身
    变了则无法界定。
    """
    if old is None or new is None:
        return frozenset() if old is new else None
    if old.module_to_file != new.module_to_file or old.reexports != new.reexports:
        return None
    changed = set(old.classes ^ new.classes)
    changed.update(
        node
        for node in old.bases.keys() | new.bases.keys()
        if old.bases.get(node) != new.bases.get(node)
    )
    if not changed:
        return frozenset()
    closure = set(changed)
    queue = list(changed)
    while queue:
        node = queue.pop()
        for mapping in (old.bases, new.bases):
            for parent in mapping.get(node, ()):
                if parent not in closure:
                    closure.add(parent)
                    queue.append(parent)
    names: set[str] = set()
    for files in (old_files, new_files):
        for path, class_name in closure:
            names.update(
                ref.name for ref in files.get(path, ()) if ref.receiver == class_name
            )
    return frozenset(names)


def children_of(subclasses: SubclassIndex) -> dict[str, frozenset[str]]:
    """子类证据（父类名 -> 直接子类名）的不可变副本。"""
    return {
        parent: frozenset(children)
        for parent, children in subclasses.evidence().items()
        if children
    }


def changed_classes(
    old: dict[str, frozenset[str]], new: dict[str, frozenset[str]]
) -> frozenset[str]:
    """子类关系变化的父类，以及它们在新旧层级中的全部祖先。

    `self.m()` 的子类覆写候选取自调用方类的传递子类：某个类之下的子类关系变了，
    它和它的每个祖先得到的候选都可能变化。
    """
    changed = {
        name for name in old.keys() | new.keys() if old.get(name) != new.get(name)
    }
    parents: dict[str, set[str]] = {}
    for mapping in (old, new):
        for parent, children in mapping.items():
            for child in children:
                parents.setdefault(child, set()).add(parent)
    found = set(changed)
    queue = list(changed)
    while queue:
        for parent in parents.get(queue.pop(), ()):
            if parent not in found:
                found.add(parent)
                queue.append(parent)
    return frozenset(found)


def _hierarchy_of(graph: Any) -> Any:
    """构图中已读取的类层级（未用到时为 None，下一次增量再全量读取）。"""
    loader = getattr(graph, "_hierarchy_loader", None)
    return getattr(loader, "value", None)


def _function_files(graph: Any) -> frozenset[str]:
    return frozenset(path for path, refs in graph._func_by_file.items() if refs)


# ---------------------------------------------------------------------------
# 增量更新
# ---------------------------------------------------------------------------


def update(
    graph: CachedCallGraph, previous: dict[str, Any], plan: RefreshPlan
) -> str | None:
    """在 ``graph``（新库上的空图）里由 ``previous`` 增量构图；成功返回 None，否则原因。"""
    memo = previous.get("_incremental")
    if not plan.files and not plan.names and not plan.changed:
        return "BACKFILL_NOT_SCOPED:" + plan.reason
    if not isinstance(memo, dict):
        return "PREVIOUS_GRAPH_NOT_ALIGNED"
    if plan.base_generation is None or memo.get("generation") != plan.base_generation:
        return "PREVIOUS_GRAPH_OTHER_GENERATION"
    generation = generation_of(graph._cache)
    if not plan.generation or generation != plan.generation:
        return "PLAN_FOR_ANOTHER_GENERATION"
    try:
        reason = _update(graph, previous, memo, plan, generation)
    except Exception:  # nosec B110 — 增量失败一律退回全量构图。
        logger.debug("incremental call-graph update failed", exc_info=True)
        reason = "INCREMENTAL_UPDATE_FAILED"
    if reason is not None:
        # 放弃时不留下半份图状态：调用方随后照常全量构图。
        graph._reset_graph_state()
        graph._incremental = None
    return reason


def _update(
    graph: CachedCallGraph,
    previous: dict[str, Any],
    memo: dict[str, Any],
    plan: RefreshPlan,
    generation: str,
) -> str | None:
    from .cached_reexport_binding import PackageReexportBinder
    from .call_graph import _resolve_edge
    from .call_graph_self_dispatch import SubclassIndex

    clock = _Clock()
    cache: Any = graph._cache
    conn = cache.get_conn()
    graph._reset_graph_state()
    graph._index_function_refs(_ordered_refs(conn, previous, plan.changed))
    clock.mark("functions")
    if _function_files(graph) != memo["function_files"]:
        return "FUNCTION_FILES_CHANGED"
    reexport_binder = PackageReexportBinder(cache)
    subclasses = SubclassIndex(cache)
    clock.mark("start_evidence")
    binder = reexport_binder.evidence()
    methods = binder_method_names(
        memo["binder"], binder, previous.get("_func_by_file", {}), graph._func_by_file
    )
    if methods is None:
        return "REEXPORT_EVIDENCE_CHANGED"
    children = children_of(subclasses)
    classes = changed_classes(memo["children"], children)
    clock.mark("evidence")
    resolver = graph._make_edge_resolver(
        cache.get_imports(),
        reexport_binder,
        subclasses,
        hierarchy_base=memo.get("hierarchy"),
        hierarchy_files=plan.files,
    )

    aligned: Alignment = memo["alignment"]
    old_records: list[Any] = memo["records"]
    clock.mark("resolver")
    affected = _affected(aligned, old_records, plan, previous, classes, methods)
    fresh = _read_rows(conn, plan, [aligned.ids[index] for index in sorted(affected)])
    fresh_ids = set(fresh.ids)
    kept = [
        index
        for index, edge_id in enumerate(aligned.ids)
        if index not in affected and edge_id not in fresh_ids
    ]
    total = int(
        conn.execute("SELECT COUNT(*) FROM edges WHERE kind = 'calls'").fetchone()[0]
    )
    if total != len(kept) + len(fresh.ids):
        return "EDGE_COUNT_MISMATCH"
    clock.mark("affected_and_rows")
    new_rows = fresh.to_dicts()
    computed = [_resolve_edge(graph._func_by_name, resolver, edge) for edge in new_rows]
    clock.mark("resolve")
    merged = _merge(aligned, old_records, kept, fresh.ids, computed, new_rows)
    clock.mark("merge")
    records = merged.records
    graph._apply_edge_records(records)
    clock.mark("apply")
    resolver.release_memos()
    graph._built = True
    graph._input_digest = None
    graph._incremental = {
        "generation": generation,
        "alignment": merged.alignment,
        "records": records,
        "binder": binder,
        "children": children,
        "function_files": memo["function_files"],
        # 上一轮有层级时本轮无论是否用到都更新它（只重读范围内文件），下一轮可继续沿用。
        "hierarchy": (
            graph._hierarchy_loader()
            if memo.get("hierarchy") is not None and graph._hierarchy_loader is not None
            else _hierarchy_of(graph)
        ),
    }
    graph._incremental_stats = {
        "recomputed_edges": len(computed),
        "reused_edges": len(kept),
        "changed_files": len(plan.changed),
        "phase_seconds": clock.phases,
    }
    return None


class _Clock:
    """增量各阶段的耗时（秒），写入 `_incremental_stats`。"""

    def __init__(self) -> None:
        self._last = time.perf_counter()
        self.phases: dict[str, float] = {}

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.phases[name] = round(now - self._last, 3)
        self._last = now


@dataclass(frozen=True)
class _Merged:
    records: list[Any]
    alignment: Alignment


def _merge(
    aligned: Alignment,
    old_records: list[Any],
    kept: list[int],
    fresh_ids: list[int],
    computed: list[Any],
    new_rows: list[dict[str, Any]],
) -> _Merged:
    """沿用的旧结果与新解析的结果按 rowid 归并（两者都已按 rowid 递增）。"""
    ids: list[int] = []
    records: list[Any] = []
    names: list[str] = []
    files: list[str] = []
    old_at, new_at = 0, 0
    while old_at < len(kept) or new_at < len(fresh_ids):
        take_old = new_at >= len(fresh_ids) or (
            old_at < len(kept) and aligned.ids[kept[old_at]] < fresh_ids[new_at]
        )
        if take_old:
            index = kept[old_at]
            old_at += 1
            ids.append(aligned.ids[index])
            records.append(old_records[index])
            names.append(aligned.callee_names[index])
            files.append(aligned.caller_files[index])
        else:
            row = new_rows[new_at]
            ids.append(fresh_ids[new_at])
            records.append(computed[new_at])
            names.append(str(row["callee_name"] or ""))
            files.append(str(row["caller_file"]))
            new_at += 1
    return _Merged(records, Alignment(ids, names, files))


def _ordered_refs(
    conn: Any, previous: dict[str, Any], changed: frozenset[str]
) -> Iterable[FunctionRef]:
    """新库的函数定义，按 ``ast_index`` 的读取顺序；未改动文件沿用上一张图的引用。"""
    from .cache.graph_input_rows import FunctionRows
    from .call_graph import FunctionRef

    order = [
        str(row[0])
        for row in conn.execute("SELECT file_path FROM ast_index ORDER BY rowid")
    ]
    reread: dict[str, list[FunctionRef]] = {}
    changed_list = sorted(changed)
    for start in range(0, len(changed_list), _CHUNK):
        chunk = changed_list[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index "  # nosec B608
            f"WHERE file_path IN ({marks}) ORDER BY rowid",
            chunk,
        ).fetchall()
        for func in FunctionRows([tuple(row) for row in rows]).to_functions():
            reread.setdefault(func["file"], []).append(
                FunctionRef(
                    file_path=func["file"],
                    name=func["name"],
                    start_line=func["line"],
                    language=func["language"],
                    end_line=func.get("end_line", func["line"]),
                    receiver=func.get("class"),
                )
            )
    by_file: dict[str, list[FunctionRef]] = previous.get("_func_by_file", {})
    for path in order:
        if path in changed:
            yield from reread.get(path, [])
        else:
            yield from by_file.get(path, [])


def _affected(
    aligned: Alignment,
    records: list[Any],
    plan: RefreshPlan,
    previous: dict[str, Any],
    classes: frozenset[str] = frozenset(),
    methods: frozenset[str] = frozenset(),
) -> set[int]:
    """须按新库重新解析的行：调用方文件或被调名在范围内，或结果指向改动文件。

    指向改动文件的结果经上一张图的反向索引找出：改动文件中每个函数的（确定与
    可能）调用方，其全部行都重新解析（超集即可）。子类关系变了（``classes``）时，
    调用方属于这些类的行（子类覆写候选）与经注解绑定的行（分派候选）同样重新解析。
    """
    files, names = plan.files, plan.names
    suspects = _callers_into(previous, plan.changed)
    affected: set[int] = set()
    for index, record in enumerate(records):
        name = aligned.callee_names[index]
        if aligned.caller_files[index] in files or name in names or name in methods:
            affected.add(index)
        elif record is not None and (
            record[0] in suspects
            or (classes and (record[0].receiver in classes or record[3] is not None))
        ):
            affected.add(index)
    return affected


def _callers_into(previous: dict[str, Any], changed: frozenset[str]) -> set[Any]:
    """上一张图中调用（确定或可能）改动文件里任一函数的调用方。"""
    by_file = previous.get("_func_by_file", {})
    callers = previous.get("_callers", {})
    possible = previous.get("_possible_callers", {})
    found: set[Any] = set()
    for path in changed:
        for ref in by_file.get(path, ()):
            found.update(callers.get(ref, ()))
            found.update(possible.get(ref, ()))
    return found


def _read_rows(conn: Any, plan: RefreshPlan, extra_ids: list[int]) -> Any:
    """范围内的行与受影响旧行在新库中的当前内容（按 rowid）。"""
    from .cache.graph_input_rows import CallEdgeRows, read_call_edge_rows_where

    collected: dict[int, tuple[Any, ...]] = {}
    names: tuple[str, ...] = ()
    for column, values in (
        ("file_path", sorted(plan.files)),
        ("callee_name", sorted(plan.names)),
        ("id", extra_ids),
    ):
        for start in range(0, len(values), _CHUNK):
            chunk = list(values[start : start + _CHUNK])
            marks = ",".join("?" * len(chunk))
            part = read_call_edge_rows_where(conn, f"{column} IN ({marks})", chunk)
            names = part.names or names
            collected.update(zip(part.ids, part.rows, strict=True))
    if not names:
        names = read_call_edge_rows_where(conn, "0", []).names
    ordered = sorted(collected)
    return CallEdgeRows(names, [collected[edge_id] for edge_id in ordered], ordered)


def finalize(graph: CachedCallGraph, state: dict[str, Any]) -> bool:
    """增量结果补算输入摘要：登记为同一状态的另一个键，并落盘解析结果（#1675）。

    认证快照上的调用与新进程按输入摘要取用图；摘要按全量构图的同一公式由新库的
    全部输入计算。读到的行与增量结果的对齐依据不一致时不登记（宁可之后重建）。
    """
    from . import call_graph_memo, call_graph_store
    from .cache import graph_input_rows
    from .cached_reexport_binding import PackageReexportBinder
    from .call_graph import graph_input_digest
    from .call_graph_self_dispatch import SubclassIndex

    memo = graph._incremental
    cache: Any = graph._cache
    if memo is None or cache is None:
        return False
    try:
        edge_source = graph_input_rows.read_edge_source(cache)
        function_source = graph_input_rows.read_function_source(cache)
        imports_raw = cache.get_imports()
        digest = graph_input_digest(
            edge_source,
            function_source,
            imports_raw,
            PackageReexportBinder(cache),
            SubclassIndex(cache),
        )
    except Exception:  # nosec B110 — 补算失败只是少一个键：之后按摘要的调用照常构图。
        logger.debug("incremental call-graph digest failed", exc_info=True)
        return False
    if digest is None or list(getattr(edge_source, "ids", ())) != memo["alignment"].ids:
        return False
    root = str(graph.project_root)
    state["_input_digest"] = digest
    if not call_graph_memo.add_key(root, state, digest):
        return False
    if graph._persist:
        call_graph_store.save(root, digest, graph._functions, memo["records"])
    return True


def memo_key(identity: tuple[Any, ...]) -> str:
    """增量结果在内存记忆中的键（输入摘要未计算，按库身份区分）。"""
    payload = json.dumps(identity, default=str).encode("utf-8")
    return "incremental:" + hashlib.blake2b(payload, digest_size=16).hexdigest()


__all__ = [
    "Alignment",
    "RefreshPlan",
    "alignment",
    "generation_of",
    "memo_key",
    "note_scope",
    "remember",
    "take_plan",
    "update",
]
