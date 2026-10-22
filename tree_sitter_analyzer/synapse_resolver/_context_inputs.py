"""#1749：解析上下文的输入表——逐文件可替换，并带内容证据。

``_build_resolver_context_uncached`` 每次刷新都要把整个项目的符号行、导入行与
导入映射重新读一遍、建一遍，开销与改动大小无关。这里把这些输入拆成按文件的部分：
全量读取（:func:`read_state`）与"在上一份状态上只替换改动文件"（:func:`patch_state`）
得到的结果逐项相同，后者只读取改动文件的行。

顺序约定（与全量读取一致，修补时保持）：

* 符号行按 ``(file_path, name, kind, line, id)`` 读取（覆盖索引顺序，不额外排序）；
  ``file_symbols`` 的键按文件路径排序，``global_name_table`` 每个名字下的条目按
  文件路径排序、同一文件内保持读取顺序。
* 导入行按 ``id`` 读取（AUTOINCREMENT，不复用）；``imports_by_file`` 的键按各文件
  第一条导入行的 ``id`` 排序。
* ``file_paths`` 取 ``ast_index`` 的扫描顺序；``module_to_file`` 由它推出。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from typing import Any

from ._imports import ImportEntry

#: 每个文件的内容证据：``ast_index`` 行（rowid、语言、内容摘要、提取器版本）与该文件
#: 符号行、导入行的 (条数, 最小 id, 最大 id)。重新索引会删除并重写这些行，id 随之改变，
#: 所以内容相同的重写也会被视为改动（安全方向）。
Evidence = dict[str, tuple[Any, ...]]

_SYMBOL_SQL = (
    "SELECT id, name, kind, file_path, line FROM ast_symbol_rows "
    "WHERE kind IN ('function', 'method', 'class')"
)
_SYMBOL_ORDER = " ORDER BY file_path, name, kind, line, id"
_IMPORT_SQL = (
    "SELECT id, file_path, language, module_path, local_name, "
    "is_relative, is_star, alias_of, line FROM ast_imports"
)
_INDEX_SQL = (
    "SELECT rowid, file_path, language, content_hash, extractor_version FROM ast_index"
)
_SYMBOL_EVIDENCE_SQL = "SELECT file_path, count(*), min(id), max(id) FROM ast_symbol_rows GROUP BY file_path"
_IMPORT_EVIDENCE_SQL = (
    "SELECT file_path, count(*), min(id), max(id) FROM ast_imports GROUP BY file_path"
)
_CHUNK = 500

ImportMapBuilder = Callable[
    [
        dict[str, list[ImportEntry]],
        dict[str, str],
        dict[str, list[tuple[str, str, int]]],
    ],
    tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]],
]
ModuleMapBuilder = Callable[[list[str]], dict[str, str]]
StarTarget = Callable[[ImportEntry, str, dict[str, str]], str]


@dataclass(frozen=True)
class ContextState:
    """解析上下文的全部输入与派生映射（只读；修补总是产生新对象）。"""

    #: None：证据不可读（旧表结构），这份状态不参与复用。
    evidence: Evidence | None
    file_paths: list[str]
    file_languages: dict[str, str]
    file_symbols: dict[str, list[tuple[str, str, int]]]
    global_name_table: dict[str, list[tuple[str, int]]]
    line_idx: dict[tuple[str, str, int], int]
    #: 文件 -> 该文件在 ``line_idx`` 中的键（修补时据此删除旧键）。
    line_keys: dict[str, list[tuple[str, str, int]]]
    imports_by_file: dict[str, list[ImportEntry]]
    #: 文件 -> 第一条导入行的 id（决定 ``imports_by_file`` 的键顺序）。
    import_first_id: dict[str, int]
    module_to_file: dict[str, str]
    name_to_source: dict[str, dict[str, str]]
    alias_target: dict[str, dict[str, str]]
    functions_by_name: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    functions_by_file: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    combined_sources: dict[str, dict[str, str]] = field(default_factory=dict)


def read_evidence(conn: sqlite3.Connection) -> tuple[Evidence, list[tuple[str, str]]]:
    """全部文件的内容证据，以及 ``ast_index`` 扫描顺序的 (文件, 语言) 列表。"""
    index_rows = conn.execute(_INDEX_SQL).fetchall()
    symbols = {str(r[0]): tuple(r[1:]) for r in conn.execute(_SYMBOL_EVIDENCE_SQL)}
    imports = {str(r[0]): tuple(r[1:]) for r in conn.execute(_IMPORT_EVIDENCE_SQL)}
    evidence: Evidence = {}
    ordered: list[tuple[str, str]] = []
    for rowid, file_path, language, content_hash, extractor_version in index_rows:
        path = str(file_path)
        ordered.append((path, str(language)))
        evidence[path] = (
            rowid,
            language,
            content_hash,
            extractor_version,
            symbols.get(path),
            imports.get(path),
        )
    # 没有 ast_index 行的符号/导入行（不应出现）同样进入证据，使其变化可见。
    for path in (set(symbols) | set(imports)) - set(evidence):
        evidence[path] = (None, None, None, None, symbols.get(path), imports.get(path))
    return evidence, ordered


def changed_files(old: Evidence, new: Evidence) -> set[str] | None:
    """证据不同的文件；文件集合变化（新增、删除、改名）时返回 None。"""
    if old.keys() != new.keys():
        return None
    return {path for path, value in new.items() if old[path] != value}


def _import_entry(row: Any) -> ImportEntry:
    return ImportEntry(
        file_path=row[1],
        language=row[2],
        module_path=row[3],
        local_name=row[4],
        is_relative=bool(row[5]),
        is_star=bool(row[6]),
        alias_of=row[7],
        line=row[8],
    )


def scoped_rows(
    conn: sqlite3.Connection, sql: str, files: Collection[str], order: str
) -> list[Any]:
    rows: list[Any] = []
    wanted = sorted(files)
    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        joiner = " AND " if " WHERE " in sql else " WHERE "
        rows += conn.execute(  # nosec B608 — 只拼接占位符
            f"{sql}{joiner}file_path IN ({marks}){order}", chunk
        ).fetchall()
    return rows


def read_state(
    conn: sqlite3.Connection,
    *,
    module_map: ModuleMapBuilder,
    import_maps: ImportMapBuilder,
) -> ContextState:
    """全量读取（任何一张表缺失时按空表处理，与旧实现一致）。"""
    evidence: Evidence | None
    try:
        evidence, ordered = read_evidence(conn)
    except sqlite3.Error:
        evidence = None
        try:
            ordered = [
                (str(r[0]), str(r[1]))
                for r in conn.execute("SELECT file_path, language FROM ast_index")
            ]
        except sqlite3.Error:
            ordered = []
    try:
        symbol_rows = conn.execute(_SYMBOL_SQL + _SYMBOL_ORDER).fetchall()
    except sqlite3.Error:
        symbol_rows = []
    try:
        import_rows = conn.execute(_IMPORT_SQL + " ORDER BY id").fetchall()
    except sqlite3.Error:
        import_rows = []
    file_symbols: dict[str, list[tuple[str, str, int]]] = {}
    global_name_table: dict[str, list[tuple[str, int]]] = {}
    line_idx: dict[tuple[str, str, int], int] = {}
    line_keys: dict[str, list[tuple[str, str, int]]] = {}
    _add_symbols(symbol_rows, file_symbols, global_name_table, line_idx, line_keys)
    imports_by_file: dict[str, list[ImportEntry]] = {}
    import_first_id: dict[str, int] = {}
    for row in import_rows:
        entry = _import_entry(row)
        import_first_id.setdefault(entry.file_path, int(row[0]))
        imports_by_file.setdefault(entry.file_path, []).append(entry)
    file_paths = [path for path, _language in ordered]
    module_to_file = module_map(file_paths)
    name_to_source, alias_target = import_maps(
        imports_by_file, module_to_file, file_symbols
    )
    return _with_callee_parts(
        ContextState(
            evidence=evidence,
            file_paths=file_paths,
            file_languages=dict(ordered),
            file_symbols=file_symbols,
            global_name_table=global_name_table,
            line_idx=line_idx,
            line_keys=line_keys,
            imports_by_file=imports_by_file,
            import_first_id=import_first_id,
            module_to_file=module_to_file,
            name_to_source=name_to_source,
            alias_target=alias_target,
        )
    )


def _add_symbols(
    rows: Iterable[Any],
    file_symbols: dict[str, list[tuple[str, str, int]]],
    global_name_table: dict[str, list[tuple[str, int]]],
    line_idx: dict[tuple[str, str, int], int],
    line_keys: dict[str, list[tuple[str, str, int]]],
) -> None:
    for sid, name, kind, file_path, line in rows:
        file_symbols.setdefault(file_path, []).append((name, kind, sid))
        global_name_table.setdefault(name, []).append((file_path, sid))
        key = (file_path, name, line)
        line_idx[key] = sid
        line_keys.setdefault(file_path, []).append(key)


def patch_state(
    conn: sqlite3.Connection,
    old: ContextState,
    evidence: Evidence,
    ordered: list[tuple[str, str]],
    changed: set[str],
    *,
    module_map: ModuleMapBuilder,
    import_maps: ImportMapBuilder,
    star_target: StarTarget,
) -> ContextState | None:
    """在 ``old`` 上只替换 ``changed`` 文件的输入；无法保证与全量相同时返回 None。"""
    file_paths = [path for path, _language in ordered]
    module_to_file = module_map(file_paths)
    if module_to_file != old.module_to_file:
        return None  # 模块映射变化会影响所有导入方：全量重建
    symbol_rows = scoped_rows(conn, _SYMBOL_SQL, changed, _SYMBOL_ORDER)
    import_rows = scoped_rows(conn, _IMPORT_SQL, changed, " ORDER BY id")

    new_symbols: dict[str, list[tuple[str, str, int]]] = {}
    new_names: dict[str, list[tuple[str, int]]] = {}
    new_line_idx: dict[tuple[str, str, int], int] = {}
    new_line_keys: dict[str, list[tuple[str, str, int]]] = {}
    _add_symbols(symbol_rows, new_symbols, new_names, new_line_idx, new_line_keys)

    file_symbols = _replace_files(
        old.file_symbols, changed, new_symbols, sort_keys=True
    )
    line_keys = _replace_files(old.line_keys, changed, new_line_keys, sort_keys=False)
    line_idx = dict(old.line_idx)
    for path in changed:
        for key in old.line_keys.get(path, ()):
            line_idx.pop(key, None)
    line_idx.update(new_line_idx)

    touched = set(new_names)
    for path in changed:
        touched.update(name for name, _kind, _sid in old.file_symbols.get(path, ()))
    global_name_table = dict(old.global_name_table)
    for name in touched:
        kept = [e for e in old.global_name_table.get(name, ()) if e[0] not in changed]
        merged = sorted(kept + new_names.get(name, []), key=lambda e: e[0])  # 稳定排序
        if merged:
            global_name_table[name] = merged
        else:
            global_name_table.pop(name, None)

    imports_by_file, import_first_id = _patch_imports(old, changed, import_rows)
    callers = set(changed) | _star_importers(
        old.imports_by_file, changed, module_to_file, star_target
    )
    partial_sources, partial_aliases = import_maps(
        {path: imports_by_file[path] for path in callers if path in imports_by_file},
        module_to_file,
        file_symbols,
    )
    name_to_source = _replace_files(
        old.name_to_source, callers, partial_sources, sort_keys=False
    )
    alias_target = _replace_files(
        old.alias_target, callers, partial_aliases, sort_keys=False
    )
    state = ContextState(
        evidence=evidence,
        file_paths=file_paths,
        file_languages=dict(ordered),
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        line_idx=line_idx,
        line_keys=line_keys,
        imports_by_file=imports_by_file,
        import_first_id=import_first_id,
        module_to_file=module_to_file,
        name_to_source=name_to_source,
        alias_target=alias_target,
    )
    return _patch_callee_parts(old, state, changed, touched, callers)


def _replace_files(
    old: dict[str, Any], files: Collection[str], new: dict[str, Any], *, sort_keys: bool
) -> dict[str, Any]:
    """``old`` 去掉 ``files`` 后并入 ``new``；``sort_keys`` 时键集合变化则按路径重排。"""
    result = {path: value for path, value in old.items() if path not in files}
    result.update(new)
    if sort_keys and result.keys() != old.keys():
        return dict(sorted(result.items()))
    if not sort_keys:
        return result
    # 键集合不变：按 ``old`` 的键顺序（即路径顺序）重建，值取新值。
    return {path: result[path] for path in old}


def _patch_imports(
    old: ContextState, changed: set[str], rows: list[Any]
) -> tuple[dict[str, list[ImportEntry]], dict[str, int]]:
    fresh: dict[str, list[ImportEntry]] = {}
    first: dict[str, int] = {
        path: ident
        for path, ident in old.import_first_id.items()
        if path not in changed
    }
    for row in rows:
        entry = _import_entry(row)
        first.setdefault(entry.file_path, int(row[0]))
        fresh.setdefault(entry.file_path, []).append(entry)
    merged = {path: v for path, v in old.imports_by_file.items() if path not in changed}
    merged.update(fresh)
    ordered = dict(sorted(merged.items(), key=lambda item: first[item[0]]))
    return ordered, {path: first[path] for path in ordered}


def _star_importers(
    imports_by_file: dict[str, list[ImportEntry]],
    changed: set[str],
    module_to_file: dict[str, str],
    star_target: StarTarget,
) -> set[str]:
    """星号导入了 ``changed`` 中某文件的导入方（其展开依赖目标文件的符号）。"""
    found: set[str] = set()
    for caller, entries in imports_by_file.items():
        for entry in entries:
            if entry.is_star and star_target(entry, caller, module_to_file) in changed:
                found.add(caller)
                break
    return found


def _functions_for(
    path: str, symbols: list[tuple[str, str, int]]
) -> list[dict[str, Any]]:
    return [
        {"name": name, "kind": kind, "file": path, "id": sid}
        for name, kind, sid in symbols
        if kind in ("function", "method", "class")
    ]


def _named(name: str, entries: list[tuple[str, int]]) -> list[dict[str, Any]]:
    return [{"name": name, "file": path, "id": sid} for path, sid in entries]


def _combined(state: ContextState, path: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    merged.update(state.name_to_source.get(path, {}))
    merged.update(state.alias_target.get(path, {}))
    return merged


def _with_callee_parts(state: ContextState) -> ContextState:
    by_file = {
        path: functions
        for path, symbols in state.file_symbols.items()
        if (functions := _functions_for(path, symbols))
    }
    by_name = {
        name: _named(name, entries) for name, entries in state.global_name_table.items()
    }
    combined: dict[str, dict[str, str]] = {}
    for path in [*state.name_to_source, *state.alias_target]:
        if path not in combined:
            combined[path] = _combined(state, path)
    return _replace(state, by_name, by_file, combined)


def _patch_callee_parts(
    old: ContextState,
    state: ContextState,
    changed: set[str],
    touched: set[str],
    callers: set[str],
) -> ContextState:
    by_file = {p: v for p, v in old.functions_by_file.items() if p not in changed}
    for path in changed:
        functions = _functions_for(path, state.file_symbols.get(path, []))
        if functions:
            by_file[path] = functions
    by_name = dict(old.functions_by_name)
    for name in touched:
        entries = state.global_name_table.get(name)
        if entries:
            by_name[name] = _named(name, entries)
        else:
            by_name.pop(name, None)
    combined = {p: v for p, v in old.combined_sources.items() if p not in callers}
    for path in callers:
        if path in state.name_to_source or path in state.alias_target:
            combined[path] = _combined(state, path)
    return _replace(state, by_name, by_file, combined)


def _replace(
    state: ContextState,
    by_name: dict[str, list[dict[str, Any]]],
    by_file: dict[str, list[dict[str, Any]]],
    combined: dict[str, dict[str, str]],
) -> ContextState:
    from dataclasses import replace

    return replace(
        state,
        functions_by_name=by_name,
        functions_by_file=by_file,
        combined_sources=combined,
    )
