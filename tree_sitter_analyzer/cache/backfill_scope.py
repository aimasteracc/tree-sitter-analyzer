"""#1696：按依赖界定的回填范围——只重新解析输入可能改变的调用边。

一次刷新只改动少数文件，但三段回填（cross-file / synapse / 第二遍）原先每次都
重扫全部调用边。解析结果只依赖下面这些输入，所以只有它们涉及的边需要重新解析：

* **改动文件自身的边**（重新提取，从未解析开始）；
* **解析到改动文件的边**：符号行重写后 id 与行号都变了，须重新绑定；
* **解析面差异**：比较改动文件新旧 ``ast_index`` 行的解析面（符号的种类、所属类、
  参数、返回注解、基类，模块单例类型，结构化导入；位置与度量不计）。差异里的名字：
  - 同名候选集变了（#1652 / #1669）：调用名属于它们的边全部重新解析；
  - 导入方（含改名导入、模块别名与星号展开，#1670）沿再导出传播；
  - 变化的类：传递子类所在文件（MRO、``self`` / ``super()``，#1677 / #1699），
    以及导入方的类型化导出（类、带返回注解的函数、模块单例，#1660 / #1699）。
  依赖文件的调用边全部恢复为新提取形态，由回填以完整上下文重新解析。

写入路径只能在写入前按名字保守地重置边；它在重置前把原解析存入 TEMP 表，决定
范围时把名字不在差异里、也不解析到改动文件的边恢复为原解析。只改函数体时解析面
不变，范围只剩改动文件与解析到它的边。

旧 ``ast_index`` 行由 TEMP 触发器在替换或删除前存下。记录都在连接级 TEMP 表里，
不进入索引文件。任何一项无法确认（未武装、上一轮回填未收敛、改动文件没有全部被
记录、范围超过全部调用边的一半、读取失败）都退回全量回填，并在结果中注明原因。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: 导入依赖的最大传递跳数（与再导出追踪一致）。
_IMPORT_HOPS = 4
#: 范围超过全部调用边的这个比例时，全量回填不比范围回填慢，直接退回全量。
_MAX_SCOPE_FRACTION = 0.5
#: 调用边少于这个数时全量回填本就很快，不因比例退回全量（范围回填同样正确）。
_MIN_EDGES_FOR_FRACTION = 2_000
_ARMED = "tsa_backfill_armed"
_EXTENDS = "tsa_backfill_extends"
_SAVED = "tsa_backfill_saved"
_CHANGED = "tsa_backfill_changed"
_OLD = "tsa_backfill_old"
_TRIGGERS = ("tsa_backfill_old_on_insert", "tsa_backfill_old_on_delete")
_TABLES = (
    (_EXTENDS, "path TEXT, source TEXT, target TEXT, PRIMARY KEY (source, target)"),
    (
        _SAVED,
        "id INTEGER PRIMARY KEY, file_path TEXT, callee_name TEXT, "
        "callee_resolution TEXT, callee_resolved_file TEXT, callee_symbol_id INTEGER, "
        "metadata TEXT",
    ),
    (_CHANGED, "path TEXT PRIMARY KEY"),
    (
        _OLD,
        "path TEXT PRIMARY KEY, language TEXT, symbols_json TEXT, imports_json TEXT",
    ),
    (_ARMED, "id INTEGER PRIMARY KEY"),
)
#: 文件旧代际的 ``ast_index`` 行在被替换（INSERT OR REPLACE）或删除之前存入 TEMP 表，
#: 只保留第一次（即本轮刷新前的）内容。
_OLD_ROW_TRIGGERS = (
    f"CREATE TEMP TRIGGER IF NOT EXISTS {_TRIGGERS[0]} BEFORE INSERT ON main.ast_index "
    f"BEGIN INSERT OR IGNORE INTO {_OLD} (path, language, symbols_json, imports_json) "
    "SELECT file_path, language, symbols_json, imports_json FROM main.ast_index "
    "WHERE file_path = NEW.file_path; END",
    f"CREATE TEMP TRIGGER IF NOT EXISTS {_TRIGGERS[1]} BEFORE DELETE ON main.ast_index "
    f"BEGIN INSERT OR IGNORE INTO {_OLD} (path, language, symbols_json, imports_json) "
    "VALUES (OLD.file_path, OLD.language, OLD.symbols_json, OLD.imports_json); END",
)
#: 不参与解析的符号字段（位置与度量）；其余字段都算解析面，未知字段保守地计入。
_POSITION_KEYS = frozenset(
    {"line", "end_line", "complexity", "docstring", "decision_points"}
)
#: 解析面里的文件级标记；它们变化时整份文件按“所有名字都变了”处理。
_FLAGS = "@flags"
#: 连接 -> 当前生效的范围（回填各段在执行时读取）。
_ACTIVE: dict[int, BackfillScope] = {}


@dataclass(frozen=True)
class BackfillScope:
    """回填只处理满足 ``covers`` 的调用边，以及 ``files`` 中文件的 EXTENDS 引用。"""

    files: frozenset[str]
    names: frozenset[str]
    edge_ids: frozenset[int]
    edge_count: int = 0

    def covers(self, file_path: str, callee_name: str, edge_id: int | None) -> bool:
        return (
            file_path in self.files
            or callee_name in self.names
            or (edge_id is not None and edge_id in self.edge_ids)
        )


@dataclass
class ScopeDecision:
    """范围回填或全量回填的决定及其原因（写入刷新结果，供审计）。"""

    scope: BackfillScope | None
    reason: str
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "scoped" if self.scope is not None else "full",
            "reason": self.reason,
            **self.stats,
        }


@dataclass(frozen=True)
class _Surface:
    """一个文件的解析面：名字 -> 该名字全部定义/导入/模块类型的规范化形态。"""

    items: dict[str, frozenset[str]]
    classes: frozenset[str]


def begin(conn: sqlite3.Connection) -> None:
    """刷新开始：武装本连接的记录并清空上一轮的残留。"""
    try:
        for table, columns in _TABLES:
            conn.execute(f"CREATE TEMP TABLE IF NOT EXISTS {table} ({columns})")  # nosec B608
            conn.execute(f"DELETE FROM temp.{table}")  # nosec B608
        # 上一轮回填未收敛（调用图标记不是当前的）时，旧解析不可作为未变部分的基准。
        # #1735：唯一的原因是已记录的稳定失败（标记按设计保持撤销）时照常武装。
        from .stable_failures import consume_parent_converged

        converged = _previous_run_converged(conn)
        consume_parent_converged(conn)
        if not converged:
            disarm(conn)
            return
        for statement in _OLD_ROW_TRIGGERS:
            conn.execute(statement)
        conn.execute(f"INSERT INTO temp.{_ARMED} (id) VALUES (1)")  # nosec B608
    except sqlite3.Error:
        logger.debug("backfill scope collector could not be armed", exc_info=True)
        disarm(conn)


def _previous_run_converged(conn: sqlite3.Connection) -> bool:
    """上一轮的调用边解析可作为基准：标记当前，或只差已记录的稳定失败（#1735）。

    后者与发布、监视器（#1733）的 ``stable_failures_only`` 规则同源：#1671 的收敛记录
    只在全部错误都是稳定失败、回填零错误的完整运行结束时签发；边的一致性仍须成立。
    """
    from .callgraph_state import (
        _WRITER_CHECK_DEADLINE_SECONDS,
        call_graph_edges_are_consistent,
        writer_marker_is_current,
    )
    from .stable_failures import converged_except_stable_failures

    if writer_marker_is_current(conn):
        return True
    if not converged_except_stable_failures(conn):
        return False
    import time

    return call_graph_edges_are_consistent(
        conn, deadline=time.monotonic() + _WRITER_CHECK_DEADLINE_SECONDS
    )


def disarm(conn: sqlite3.Connection) -> None:
    """撤销武装（记录丢弃）；之后的回填为全量。"""
    try:
        for trigger in _TRIGGERS:
            conn.execute(f"DROP TRIGGER IF EXISTS temp.{trigger}")  # nosec B608
        for table, _columns in _TABLES:
            conn.execute(f"DROP TABLE IF EXISTS temp.{table}")  # nosec B608
    except Exception:  # nosec B110 — 撤销失败只影响本轮记录，回填按全量处理。
        logger.debug("backfill scope collector could not be disarmed", exc_info=True)


def _armed(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(f"SELECT 1 FROM temp.{_ARMED} LIMIT 1").fetchone()  # nosec B608
    except Exception:  # nosec B110 — 不是可用的 SQLite 连接：未武装，全量回填。
        logger.debug("backfill scope collector unavailable", exc_info=True)
        return False
    return row is not None


def record_file_write(
    conn: sqlite3.Connection,
    rel_path: str,
    reset_edge_ids: Iterable[int],
    extends_edges: Iterable[tuple[str, str, str]],
) -> None:
    """``write._reset_incoming_edge_resolutions`` 的旁路：在重置之前记下文件与边的原解析。"""
    if not _armed(conn):
        return
    try:
        conn.execute(
            f"INSERT OR IGNORE INTO temp.{_CHANGED} (path) VALUES (?)",  # nosec B608
            (rel_path,),
        )
        # 写入路径随后删除指向本文件类的继承边；记下它们（子类文件、子类与基类节点）。
        conn.executemany(
            f"INSERT OR IGNORE INTO temp.{_EXTENDS} (path, source, target) "  # nosec B608
            "VALUES (?, ?, ?)",
            list(extends_edges),
        )
        # 同一条边在一轮里可能被重置多次；只保留第一次（刷新前）的解析。
        conn.executemany(
            f"INSERT OR IGNORE INTO temp.{_SAVED} "  # nosec B608
            "SELECT id, file_path, callee_name, callee_resolution, callee_resolved_file, "
            "callee_symbol_id, metadata FROM main.edges WHERE id = ?",
            [(int(edge_id),) for edge_id in reset_edge_ids],
        )
    except sqlite3.Error:
        logger.debug("backfill scope record failed; falling back", exc_info=True)
        disarm(conn)


def decide(
    cache: Any, conn: sqlite3.Connection, changed_count: int | None
) -> ScopeDecision:
    """计算本轮刷新的回填范围；无法界定时返回全量决定。

    ``changed_count`` 是本轮新增、更新与删除的文件数；本连接记录到的写入文件少于它，
    说明有写入不经本连接（或未经重置路径），范围不可信，退回全量。
    """
    if changed_count is None:
        return ScopeDecision(None, "CHANGED_FILES_UNKNOWN")
    if not _armed(conn):
        return ScopeDecision(None, "COLLECTOR_NOT_ARMED")
    try:
        changed = set(_column(conn, _CHANGED, "path"))
        if len(changed) < changed_count:
            return ScopeDecision(None, "CHANGED_FILE_NOT_RECORDED")
        deltas, classes, wide = _surface_deltas(conn, changed)
        names = set().union(*deltas.values()) if deltas else set()
        restored = _restore_unaffected(conn, changed, names)
        _reset_named_edges(conn, changed, names)
        dependents = _dependent_files(cache, conn, deltas, classes, wide) - changed
        # 依赖文件的调用边先恢复为新提取形态：无论范围还是全量回填，它们都须以完整
        # 上下文重新解析（全量回填只重新解析未解析的边）。
        _reset_dependent_files(conn, dependents)
        edge_ids = {int(value) for value in _column(conn, _SAVED, "id")} - restored
        extends = set(_column(conn, _EXTENDS, "path"))  # 子类文件须重新解析继承边
        files = changed | dependents | extends | _edge_files(conn, edge_ids)
        scope = BackfillScope(frozenset(files), frozenset(names), frozenset(edge_ids))
        total, in_scope = _edge_counts(conn, scope)
    except Exception:  # nosec B110 — 任何读取失败都退回全量。
        logger.debug("backfill scope computation failed", exc_info=True)
        return ScopeDecision(None, "SCOPE_COMPUTATION_FAILED")
    stats = {
        "changed_files": len(changed),
        "surface_changed_files": len(deltas),
        "wide_files": len(wide),
        "dependent_files": len(dependents),
        "scope_files": len(files),
        "scope_names": len(names),
        "restored_edges": len(restored),
        "scope_edges": in_scope,
        "call_edges": total,
    }
    if total >= _MIN_EDGES_FOR_FRACTION and in_scope > total * _MAX_SCOPE_FRACTION:
        return ScopeDecision(None, "SCOPE_TOO_LARGE", stats)
    sized = BackfillScope(scope.files, scope.names, scope.edge_ids, in_scope)
    return ScopeDecision(sized, "DEPENDENCIES_BOUNDED", stats)


def _column(conn: sqlite3.Connection, table: str, column: str) -> list[Any]:
    sql = f"SELECT {column} FROM temp.{table}"  # nosec B608 — 表名与列名是模块常量
    return [row[0] for row in conn.execute(sql)]


def _surface_deltas(
    conn: sqlite3.Connection, changed: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """每个改动文件解析面变化的名字、其中的类名，以及须按整文件处理的文件。

    旧解析面取自触发器存下的旧 ``ast_index`` 行（没有就是新文件），新解析面取自当前行
    （没有就是已删除）。只改函数体时解析面不变，名字集合为空。
    """
    old_rows = {
        str(row[0]): row[1:]
        for row in conn.execute(
            f"SELECT path, language, symbols_json, imports_json FROM temp.{_OLD}"  # nosec B608
        )
    }
    deltas: dict[str, set[str]] = {}
    classes: dict[str, set[str]] = {}
    wide: set[str] = set()
    for path in sorted(changed):
        new_row = conn.execute(
            "SELECT language, symbols_json, imports_json FROM ast_index WHERE file_path = ?",
            (path,),
        ).fetchone()
        old = _surface(old_rows.get(path))
        new = _surface(tuple(new_row) if new_row is not None else None)
        delta = {
            name
            for name in old.items.keys() | new.items.keys()
            if old.items.get(name) != new.items.get(name)
        }
        if _FLAGS in delta:
            wide.add(path)
            delta = set(old.items) | set(new.items)
        delta.discard(_FLAGS)
        if delta:
            deltas[path] = delta
            classes[path] = delta & (old.classes | new.classes)
    return deltas, classes, wide


def _surface(row: Any) -> _Surface:
    """``(language, symbols_json, imports_json)`` 的解析面；``None`` 为空解析面。"""
    if row is None:
        return _Surface({}, frozenset())
    language, symbols_json, imports_json = (str(row[0] or ""), row[1], row[2])
    items: dict[str, set[str]] = defaultdict(set)
    class_names: set[str] = set()
    payload = json.loads(symbols_json or "{}")
    flags = {
        key: payload.get(key)
        for key in ("syntax_error", "truncated_depth", "import_projection_complete")
    }
    for symbol in payload.get("symbols") or []:
        if symbol.get("kind") == "import":
            continue  # 导入按结构化条目比较（下面）。
        name = str(symbol.get("name") or symbol.get("text") or "")
        shape = {
            key: value for key, value in symbol.items() if key not in _POSITION_KEYS
        }
        items[name].add(_canonical(shape))
        if symbol.get("kind") == "class":
            class_names.add(name)
    for name, hint in (payload.get("module_types") or {}).items():
        items[str(name)].add("module_type:" + _canonical(hint))
    # #1721：函数内 `global` / 模块级 `del` 重新绑定的名字。增删它们会改变经模块属性
    # 的解析（#1705），名字进入差异后，以它为被调名的边与导入方都会重新解析。
    for name in payload.get("module_rebinds") or []:
        items[str(name)].add("module_rebind")
    from ..synapse_resolver._imports import parse_imports

    unparsed: list[str] = []
    for item in json.loads(imports_json or "[]"):
        text = str(item.get("text") or "") if isinstance(item, dict) else str(item)
        entries = parse_imports(text, language)
        if not entries:
            unparsed.append(text)
        for entry in entries:
            import_shape: list[Any] = [
                entry.module_path,
                entry.is_relative,
                entry.is_star,
                entry.alias_of,
            ]
            if entry.is_star:
                # 星号导入改变的名字无法从本文件得知：作为文件级标记，整文件处理。
                flags.setdefault("star", []).append(import_shape)
                continue
            items[entry.local_name or entry.module_path].add(
                "import:" + _canonical(import_shape)
            )
    # 解析器不认识的导入语句（其他语言）同样只能整文件处理。
    flags["unparsed_imports"] = sorted(unparsed)
    items[_FLAGS].add(_canonical(flags))
    frozen = {name: frozenset(shapes) for name, shapes in items.items()}
    return _Surface(frozen, frozenset(class_names))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _restore_unaffected(
    conn: sqlite3.Connection, changed: set[str], names: set[str]
) -> set[int]:
    """写入路径按名字重置、但解析输入没变的边恢复为刷新前的解析。

    写入路径无法预知新解析面，重置了调用名属于该文件符号的全部边；名字不在解析面
    差异里、也不解析到改动文件的边，其候选集、导入与类型都不变，结果与上一轮相同。
    """
    restorable = [
        row
        for row in conn.execute(
            "SELECT id, file_path, callee_name, callee_resolution, callee_resolved_file, "
            f"callee_symbol_id, metadata FROM temp.{_SAVED}"  # nosec B608
        )
        if str(row[1]) not in changed
        and str(row[2] or "") not in names
        and str(row[4] or "") not in changed
    ]
    for (
        edge_id,
        file_path,
        callee_name,
        resolution,
        resolved,
        symbol_id,
        metadata,
    ) in restorable:
        conn.execute(
            "UPDATE edges SET callee_resolution = ?, callee_resolved_file = ?, "
            "callee_symbol_id = ?, metadata = ? "
            "WHERE id = ? AND file_path = ? AND callee_name = ?",
            (
                resolution,
                resolved,
                symbol_id,
                metadata,
                edge_id,
                file_path,
                callee_name,
            ),
        )
    return {int(row[0]) for row in restorable}


def _reset_named_edges(
    conn: sqlite3.Connection, changed: set[str], names: set[str]
) -> None:
    """调用名在解析面差异里的边（同名候选集变了）全部重新解析，与全新重建一致。"""
    from .write import reset_call_edge_rows

    ordered = sorted(names)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start : start + 500]
        marks = ",".join("?" * len(chunk))
        rows = [
            row
            for row in conn.execute(
                "SELECT id, metadata, file_path FROM edges "  # nosec B608
                f"WHERE +kind = 'calls' AND callee_name IN ({marks}) "
                "AND (callee_resolution != 'unknown' OR callee_resolved_file != '')",
                chunk,
            )
            if str(row[2]) not in changed
        ]
        reset_call_edge_rows(conn, rows)


def _reset_dependent_files(conn: sqlite3.Connection, files: set[str]) -> None:
    """依赖文件（导入方、子类所在文件）的调用边恢复为新提取形态，由回填以完整上下文重新解析。

    这些边的解析可能经导入、MRO、注解或别名依赖改动文件，而它们的调用名不一定
    在解析面差异里，写入路径不会重置它们；全新重建中它们同样从未解析开始。
    """
    from .write import reset_call_edge_rows

    for path in sorted(files):
        rows = conn.execute(
            "SELECT id, metadata FROM edges WHERE kind = 'calls' AND file_path = ?",
            (path,),
        ).fetchall()
        reset_call_edge_rows(conn, rows)


def _dependent_files(
    cache: Any,
    conn: sqlite3.Connection,
    deltas: dict[str, set[str]],
    classes: dict[str, set[str]],
    wide: set[str],
) -> set[str]:
    """解析经导入、继承或类型依赖改动名字的文件。

    * 子类：解析面变化的类（基类、增删）的传递子类所在文件，以及基类占位命中者；
    * 导入方：导入了变化名字（含改名、星号展开与模块别名）的文件，沿再导出最多
      ``_IMPORT_HOPS`` 跳；变化的是类时，导入方自己的类型化导出（类、带返回注解的
      函数、模块单例）同样继续传播，因为它们的类型可能经这个类解析。
    """
    if not deltas:
        return set()
    names_by_file: dict[str, set[str]] = {
        path: set(names) for path, names in deltas.items()
    }
    typed_by_file: dict[str, set[str]] = {
        path: set(names) for path, names in classes.items()
    }
    class_names = set().union(*classes.values()) if classes else set()
    subclass_files, subclass_names = _subclass_files(conn, class_names)
    found = set(subclass_files)
    for path, class_name in subclass_names:
        names_by_file.setdefault(path, set()).add(class_name)
        typed_by_file.setdefault(path, set()).add(class_name)
    found |= _importer_closure(cache, conn, names_by_file, typed_by_file, wide)
    return found


def _subclass_files(
    conn: sqlite3.Connection, class_names: set[str]
) -> tuple[set[str], set[tuple[str, str]]]:
    """这些类的传递子类（文件与类名），以及基类占位 ``class:Name`` 命中它们的文件。"""
    if not class_names:
        return set(), set()
    children: dict[str, set[tuple[str, str]]] = defaultdict(set)
    placeholder_files: set[str] = set()
    # 写入路径已删除指向改动文件类的继承边，它们记录在 TEMP 表里，一并参与。
    for source, target in conn.execute(
        "SELECT source_node_id, target_node_id FROM edges "
        "WHERE kind IN ('extends', 'implements') "
        f"UNION SELECT source, target FROM temp.{_EXTENDS}"  # nosec B608
    ):
        child = _node(source)
        if child is None:
            continue
        target_text = str(target)
        if target_text.startswith("class:"):
            base = target_text[len("class:") :]
            if base in class_names or base.rsplit(".", 1)[-1] in class_names:
                placeholder_files.add(child[0])
            continue
        parent = _node(target)
        if parent is not None:
            children[parent[1]].add(child)
    subclasses: set[tuple[str, str]] = set()
    queue = deque(class_names)
    seen = set(class_names)
    while queue:
        for child in children.get(queue.popleft(), ()):
            subclasses.add(child)
            if child[1] not in seen:
                seen.add(child[1])
                queue.append(child[1])
    return placeholder_files | {path for path, _name in subclasses}, subclasses


def _importer_closure(
    cache: Any,
    conn: sqlite3.Connection,
    names_by_file: dict[str, set[str]],
    typed_by_file: dict[str, set[str]],
    wide: set[str],
) -> set[str]:
    """导入了 ``names_by_file`` 中名字的文件，沿再导出传递（最多 ``_IMPORT_HOPS`` 跳）。"""
    from ..synapse_resolver import build_resolver_context

    ctx = build_resolver_context(cache)
    bindings = _import_bindings(ctx)
    found: set[str] = set()
    frontier = {path: set(names) for path, names in names_by_file.items()}
    typed = {path: set(names) for path, names in typed_by_file.items()}
    for _hop in range(_IMPORT_HOPS):
        following: dict[str, set[str]] = defaultdict(set)
        following_typed: dict[str, set[str]] = defaultdict(set)
        for target, changed_names in frontier.items():
            for importer, local, original, is_module in bindings.get(target, ()):
                if importer == target:
                    continue
                hit = is_module or target in wide or original in changed_names
                if not hit:
                    continue
                found.add(importer)
                if not is_module:
                    following[importer].add(local)
                    if original in typed.get(target, ()):
                        following_typed[importer].add(local)
                if (is_module and typed.get(target)) or following_typed.get(importer):
                    exports = _typed_exports(conn, importer)
                    following[importer] |= exports
                    following_typed[importer] |= exports
        frontier = {path: names for path, names in following.items() if names}
        typed = dict(following_typed)
        if not frontier:
            break
    return found


def _import_bindings(ctx: Any) -> dict[str, list[tuple[str, str, str, bool]]]:
    """target 文件 -> [(导入方, 本地名, 原名, 是否模块绑定)]。

    ``import a.b as c`` / ``import a`` 是模块绑定：经它的任何属性调用都可能依赖
    target 的变化名字，所以总是命中；``from m import x as y`` 记原名 ``x``；星号
    展开的名字只出现在 ``name_to_source`` 里，按同名记。
    """
    bindings: dict[str, list[tuple[str, str, str, bool]]] = defaultdict(list)
    for importer in ctx.name_to_source.keys() | ctx.import_alias_target.keys():
        named = ctx.name_to_source.get(importer, {})
        aliased = ctx.import_alias_target.get(importer, {})
        seen: set[str] = set()
        for entry in ctx.imports_by_file.get(importer, []):
            local = entry.local_name
            if entry.is_star or not local:
                continue
            seen.add(local)
            module_like = entry.alias_of == entry.module_path or (
                not entry.alias_of and entry.module_path.split(".")[0] == local
            )
            for target in {named.get(local), aliased.get(local)} - {None}:
                is_module = module_like or named.get(local) != target
                original = local if is_module else (entry.alias_of or local)
                bindings[str(target)].append((importer, local, original, is_module))
        for local, target in named.items():
            if local not in seen:
                bindings[target].append((importer, local, local, False))
    return bindings


def _typed_exports(conn: sqlite3.Connection, path: str) -> set[str]:
    """文件的类型化导出：类、带返回注解的函数与模块单例——它们的类型可能经导入解析。"""
    row = conn.execute(
        "SELECT symbols_json FROM ast_index WHERE file_path = ?", (path,)
    ).fetchone()
    if row is None:
        return set()
    payload = json.loads(row[0] or "{}")
    exports = {str(name) for name in (payload.get("module_types") or {})}
    for symbol in payload.get("symbols") or []:
        if symbol.get("kind") == "class" or (
            symbol.get("kind") == "function" and symbol.get("return_type")
        ):
            exports.add(str(symbol.get("name") or ""))
    exports.discard("")
    return exports


def _edge_files(conn: sqlite3.Connection, edge_ids: set[int]) -> set[str]:
    files: set[str] = set()
    ids = sorted(edge_ids)
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        files.update(
            str(row[0])
            for row in conn.execute(
                f"SELECT DISTINCT file_path FROM edges WHERE id IN ({marks})",  # nosec B608
                chunk,
            )
        )
    return files


def scope_pass_files(conn: sqlite3.Connection, scope: BackfillScope) -> set[str]:
    """第二遍需要处理的文件：范围文件，加上调用名属于受影响名字的边所在文件。"""
    files = set(scope.files)
    names = sorted(scope.names)
    for start in range(0, len(names), 500):
        chunk = names[start : start + 500]
        marks = ",".join("?" * len(chunk))
        files.update(
            str(row[0])
            for row in conn.execute(
                "SELECT DISTINCT file_path FROM edges "  # nosec B608
                f"WHERE kind = 'calls' AND callee_name IN ({marks})",
                chunk,
            )
        )
    return files


def _edge_counts(conn: sqlite3.Connection, scope: BackfillScope) -> tuple[int, int]:
    total = 0
    in_scope = 0
    for edge_id, file_path, callee_name in conn.execute(
        "SELECT id, file_path, callee_name FROM edges WHERE kind = 'calls'"
    ):
        total += 1
        if scope.covers(str(file_path), str(callee_name or ""), int(edge_id)):
            in_scope += 1
    return total, in_scope


def _node(node_id: Any) -> tuple[str, str] | None:
    parts = str(node_id).rsplit(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1] or parts[0] == "class":
        return None
    return parts[0], parts[1]


@contextmanager
def active(conn: sqlite3.Connection, scope: BackfillScope | None) -> Iterator[None]:
    """回填各段执行期间生效的范围；结束后撤销武装（记录只服务这一轮）。"""
    if scope is not None:
        _ACTIVE[id(conn)] = scope
    try:
        yield
    finally:
        _ACTIVE.pop(id(conn), None)
        disarm(conn)


def current(conn: sqlite3.Connection) -> BackfillScope | None:
    """本连接上正在执行的回填范围；``None`` 表示全量。"""
    return _ACTIVE.get(id(conn))


__all__ = [
    "BackfillScope",
    "ScopeDecision",
    "active",
    "begin",
    "current",
    "decide",
    "disarm",
    "record_file_write",
    "scope_pass_files",
]
