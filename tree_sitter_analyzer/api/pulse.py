"""Pulse API — 1-query symbol context for AI agents.

The ``pulse()`` function answers "what do I need to know about this symbol?"
in a single SQL round-trip (9-CTE query), returning a structured
:class:`PulseResponse` with callers, callees, git heat, imports, siblings,
and inline comments — all token-budgeted for compact LLM consumption.

Usage::

    conn = cache.get_conn()
    response = query_pulse(conn, "tree_sitter_analyzer/api/pulse.py", "query_pulse")
    budgeted = apply_budget(response, token_budget=600)
    payload  = serialize(budgeted, format="compact")  # see serialization.py
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Languages where call-graph extraction is not supported.
_NO_CALL_GRAPH_LANGUAGES = frozenset(
    {
        "bash",
        "scala",
        "css",
        "html",
        "json",
        "yaml",
        "sql",
        "markdown",
    }
)

# ---------------------------------------------------------------------------
# Dataclasses (frozen=True enforces immutability — REQ-NF-004)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolInfo:
    """Core symbol identity."""

    name: str
    kind: str
    file: str
    line: int
    end_line: int
    language: str
    class_name: str | None = None
    docstring: str | None = None  # first 200 chars


@dataclass(frozen=True)
class CallerRef:
    """A symbol that calls the target."""

    name: str
    file: str
    line: int
    hot30: int  # mod_count_30d


@dataclass(frozen=True)
class CalleeRef:
    """A symbol called by the target."""

    name: str
    file: str | None = None
    line: int | None = None
    resolution: str = "unresolved"  # resolved|class_method|heuristic|unresolved


@dataclass(frozen=True)
class ImportRef:
    """An import in the target's file."""

    module: str
    file: str | None = None


@dataclass(frozen=True)
class GitHeat:
    """Git modification statistics for the target symbol."""

    commit: str | None = None
    commit_msg: str | None = None
    at: int | None = None  # unix timestamp of last modification
    mod_30d: int = 0
    mod_90d: int = 0
    mod_all: int = 0
    state: str = "tracked"


@dataclass(frozen=True)
class SiblingRef:
    """Another symbol in the same file."""

    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class CommentRef:
    """An inline or block comment near the target symbol."""

    line: int
    text: str  # first 80 chars, markers stripped
    kind: str  # 'inline'|'block'


@dataclass(frozen=True)
class BranchContext:
    """Control-flow context in which a call was made."""

    kind: str
    condition_text: str | None = None
    nesting_depth: int = 0


@dataclass(frozen=True)
class PulseResponse:
    """Complete one-query context for a single symbol."""

    symbol: SymbolInfo
    token_estimate: int = 0
    truncated_fields: tuple[str, ...] = field(default_factory=tuple)
    call_graph_available: bool = True
    call_graph_reason: str = ""
    callers: tuple[CallerRef, ...] = field(default_factory=tuple)
    callees: tuple[CalleeRef, ...] = field(default_factory=tuple)
    git_heat: GitHeat | None = None
    imports: tuple[ImportRef, ...] = field(default_factory=tuple)
    imported_by: tuple[str, ...] = field(default_factory=tuple)
    siblings: tuple[SiblingRef, ...] = field(default_factory=tuple)
    comments: tuple[CommentRef, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# 9-CTE SQL query
# ---------------------------------------------------------------------------

_PULSE_SQL = """
WITH
target AS (
    SELECT id, name, kind, file_path, language, line, end_line
    FROM   ast_symbol_rows
    WHERE  id = :symbol_id
),
callers AS (
    SELECT e.caller_name AS name, e.file_path AS file, e.caller_line AS line,
           COALESCE(a.mod_count_30d, 0) AS hot30
    FROM   edges e
    JOIN   target t
    LEFT   JOIN ast_symbol_rows cs ON cs.name = e.caller_name AND cs.file_path = e.file_path
                                   AND cs.line = e.caller_line
    LEFT   JOIN ast_symbol_activation a ON a.symbol_id = cs.id
    WHERE  e.kind = 'calls'
    AND    (e.callee_symbol_id = t.id
            OR (e.callee_symbol_id IS NULL AND e.callee_name = t.name
                AND e.callee_resolved_file = t.file_path))
    ORDER  BY hot30 DESC, e.id
    LIMIT  :max_callers
),
callees AS (
    SELECT e.id AS edge_id, e.callee_name AS name,
           COALESCE(cs.file_path, NULLIF(e.callee_resolved_file, '')) AS file,
           cs.line AS line, e.callee_resolution AS resolution
    FROM   edges e
    JOIN   target t ON e.caller_name = t.name AND e.file_path = t.file_path
                       AND e.caller_line = t.line
    LEFT   JOIN ast_symbol_rows cs ON cs.id = e.callee_symbol_id
        OR (e.callee_symbol_id IS NULL AND cs.file_path = e.callee_resolved_file
            AND cs.name = e.callee_name
            AND (SELECT count(*) FROM ast_symbol_rows candidate
                 WHERE candidate.file_path = cs.file_path AND candidate.name = cs.name) = 1)
    WHERE  e.kind = 'calls'
    ORDER  BY (cs.id IS NOT NULL) DESC, e.id
    LIMIT  :max_callees
),
file_imports AS (
    SELECT i.module_path AS module, NULL AS file
    FROM   ast_imports i
    JOIN   target t ON i.file_path = t.file_path
    LIMIT  :max_imports
),
imported_by AS (
    SELECT DISTINCT e.file_path AS importer
    FROM   edges e
    JOIN   target t
    WHERE  e.kind = 'imports'
    AND    (e.callee_resolved_file = t.file_path
            OR (t.language = 'python' AND e.target_node_id = :module_node))
    ORDER  BY e.file_path
    LIMIT  20
),
git_heat AS (
    SELECT a.last_modified_commit AS last_commit,
           a.last_commit_msg      AS commit_msg,
           a.last_modified_at     AS at,
           a.mod_count_30d        AS mod_30d,
           a.mod_count_90d        AS mod_90d,
           a.mod_count_all        AS mod_all,
           a.git_state            AS state
    FROM   ast_symbol_activation a
    JOIN   target t ON a.symbol_id = t.id
    LIMIT  1
),
siblings AS (
    SELECT r.name, r.kind, r.line
    FROM   ast_symbol_rows r
    JOIN   target t ON r.file_path = t.file_path
    WHERE  r.kind IN ('function','method','class')
    AND    r.id <> t.id
    ORDER  BY r.line
    LIMIT  :max_siblings
),
docstring_cte AS (
    SELECT SUBSTR(json_extract(s.value, '$.docstring'), 1, 200) AS raw
    FROM   ast_index i
    JOIN   target t ON i.file_path = t.file_path
    JOIN   json_each(CASE WHEN json_valid(i.symbols_json)
                          THEN i.symbols_json ELSE '{}' END, '$.symbols') s
    WHERE  s.type = 'object' AND json_extract(s.value, '$.name') = t.name
    AND    json_extract(s.value, '$.line') = t.line
    LIMIT  1
),
comments_cte AS (
    SELECT c.line, c.text, c.kind
    FROM   ast_symbol_comments c
    JOIN   target t ON c.symbol_id = t.id
    ORDER  BY c.line
    LIMIT  :max_comments
)
SELECT
    (SELECT json_object('id',id,'name',name,'kind',kind,'file',file_path,
                        'line',line,'end_line',end_line,'language',language)
     FROM target) AS target_json,
    (SELECT json_group_array(
        json_object('name',name,'file',file,'line',line,'hot30',hot30))
     FROM callers) AS callers_json,
    (SELECT json_group_array(
        json_object('edge_id',edge_id,'name',name,'file',file,'line',line,'resolution',resolution))
     FROM callees) AS callees_json,
    (SELECT json_group_array(json_object('module',module,'file',file))
     FROM file_imports) AS imports_json,
    (SELECT json_group_array(importer) FROM imported_by) AS imported_by_json,
    (SELECT json_object('commit',last_commit,'commit_msg',commit_msg,'at',at,
                        'mod_30d',mod_30d,'mod_90d',mod_90d,'mod_all',mod_all,
                        'state',state)
     FROM git_heat) AS git_heat_json,
    (SELECT json_group_array(json_object('name',name,'kind',kind,'line',line))
     FROM siblings) AS siblings_json,
    (SELECT raw FROM docstring_cte) AS docstring_raw,
    (SELECT json_group_array(json_object('line',line,'text',text,'kind',kind))
     FROM comments_cte) AS comments_json
"""


def _enrich_callees_with_lsp(
    conn: sqlite3.Connection,
    callees: tuple[CalleeRef, ...],
    edge_ids: tuple[int, ...],
) -> tuple[CalleeRef, ...]:
    """按原始调用边关联 LSP 缓存，并把零基定义行转换为一基行。"""
    try:
        enriched: list[CalleeRef] = []
        for ce, edge_id in zip(callees, edge_ids, strict=True):
            if ce.resolution not in ("unknown", "unresolved", "heuristic"):
                enriched.append(ce)
                continue
            try:
                row = conn.execute(
                    """
                    SELECT lrc.resolved_file, lrc.resolved_line, lrc.resolved_type
                    FROM   lsp_resolution_cache lrc
                    WHERE  lrc.edge_id = ?
                    ORDER  BY lrc.cached_at DESC, lrc.lsp_server
                    LIMIT  1
                    """,
                    (edge_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                # lsp_resolution_cache table not present yet (schema V15 pending).
                enriched.append(ce)
                continue
            if row:
                resolved_file, resolved_line, _resolved_type = row
                if not resolved_file or resolved_line is None or resolved_line < 0:
                    enriched.append(ce)
                    continue
                enriched.append(
                    CalleeRef(
                        name=ce.name,
                        file=resolved_file,
                        line=resolved_line + 1,
                        resolution="resolved",
                    )
                )
            else:
                enriched.append(ce)
        return tuple(enriched)
    except Exception:
        # Never crash the Pulse query for an optional enrichment.
        return callees


def query_pulse(
    conn: sqlite3.Connection,
    file_path: str,
    symbol_name: str,
    *,
    max_callers: int = 10,
    max_callees: int = 10,
    max_siblings: int = 15,
    max_imports: int = 20,
    max_comments: int = 10,
) -> PulseResponse | None:
    """返回符号上下文，缺少符号时返回 None。

    Python 反向 import 复用 Synapse resolver。注释必须来自新提取器写入的
    索引；旧索引或不支持注释的语言需重新索引或显式设置 max_comments=0。
    存量 activation 消息缺失时保持 NULL，并发出 COMMIT_MESSAGE_MISSING。
    """
    params: dict[str, Any] = {
        "file_path": file_path,
        "symbol_name": symbol_name,
        "max_callers": max_callers,
        "max_callees": max_callees,
        "max_siblings": max_siblings,
        "max_imports": max_imports,
        "max_comments": max_comments,
    }
    for name in (
        "max_callers",
        "max_callees",
        "max_siblings",
        "max_imports",
        "max_comments",
    ):
        if type(params[name]) is not int or not 0 <= params[name] <= 1000:
            raise ValueError(f"{name} must be an integer between 0 and 1000")

    # 先证明唯一身份；同文件同名必须由调用方消歧，不能任意取第一条。
    targets = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE file_path = ? AND name = ? LIMIT 2",
        (file_path, symbol_name),
    ).fetchall()
    if not targets:
        return None
    if len(targets) != 1:
        raise ValueError(f"AMBIGUOUS_SYMBOL: {file_path}:{symbol_name}")
    params["symbol_id"] = targets[0][0]
    from ..synapse_resolver._context import (
        _build_module_to_file,
        _local_name_as_submodule,
        _resolve_module_to_file,
    )

    modules = _build_module_to_file([file_path])
    params["module_node"] = "module:" + next(iter(modules), "")
    if max_comments:
        marker = conn.execute(
            "SELECT json_type(symbols_json, '$.comments') FROM ast_index WHERE file_path=?",
            (file_path,),
        ).fetchone()
        if marker is not None and marker[0] != "array":
            raise ValueError(
                "COMMENTS_NOT_INDEXED: rebuild the index, or set max_comments=0 for unsupported languages"
            )

    # Try with LSP-enriched callees; fall back when lsp_resolution_cache is absent.
    try:
        row = conn.execute(_PULSE_SQL, params).fetchone()
    except sqlite3.OperationalError:
        return None

    # 固定 SELECT 总会返回一行；内置 JSON 聚合生成合法 JSON，对象子查询可为 NULL。
    # 按固定列序读取，兼容 tuple 与 sqlite3.Row；索引 7 是原始文档文本，不参与解码。
    target_d, git_heat_d = (
        json.loads(row[index]) if row[index] is not None else None for index in (0, 5)
    )
    if target_d is None:
        return None
    (
        callers_raw,
        callees_raw,
        imports_raw,
        imported_by_raw,
        siblings_raw,
        comments_raw,
    ) = (json.loads(row[index]) for index in (1, 2, 3, 4, 6, 8))

    language = target_d.get("language", "")
    call_graph_available = language not in _NO_CALL_GRAPH_LANGUAGES
    call_graph_reason = (
        f"{language}: call-graph not supported" if not call_graph_available else ""
    )

    docstring_raw = row[7]

    # SQL 在完整 JSON 中定位定义后才截短文档，避免截断序列化对象。
    docstring = (
        docstring_raw if isinstance(docstring_raw, str) and docstring_raw else None
    )

    sym_info = SymbolInfo(
        name=target_d.get("name", symbol_name),
        kind=target_d.get("kind", "unknown"),
        file=target_d.get("file", file_path),
        line=target_d.get("line", 0),
        end_line=target_d.get("end_line", 0),
        language=language,
        docstring=docstring,
    )

    callers = tuple(
        CallerRef(
            name=c.get("name", ""),
            file=c.get("file", ""),
            line=c.get("line", 0) or 0,
            hot30=c.get("hot30", 0) or 0,
        )
        for c in callers_raw
        if c.get("name")
    )

    callees = tuple(
        CalleeRef(
            name=c.get("name", ""),
            file=c.get("file") or None,
            line=c.get("line") or None,
            resolution=c.get("resolution") or "unresolved",
        )
        for c in callees_raw
        if c.get("name")
    )

    git_heat: GitHeat | None = None
    if git_heat_d:
        if git_heat_d.get("commit") and not git_heat_d.get("commit_msg"):
            logger.warning("COMMIT_MESSAGE_MISSING: %s:%s", file_path, symbol_name)
        git_heat = GitHeat(
            commit=git_heat_d.get("commit"),
            commit_msg=git_heat_d.get("commit_msg") or None,
            at=git_heat_d.get("at"),
            mod_30d=git_heat_d.get("mod_30d", 0) or 0,
            mod_90d=git_heat_d.get("mod_90d", 0) or 0,
            mod_all=git_heat_d.get("mod_all", 0) or 0,
            state=git_heat_d.get("state", "tracked") or "tracked",
        )

    imports = tuple(
        ImportRef(module=i.get("module", ""), file=i.get("file"))
        for i in imports_raw
        if i.get("module")
    )

    imported_by = tuple(str(f) for f in imported_by_raw if f)
    if language == "python":
        # 只读既有索引，不做仓库扫描；使用真实模块表解析相对 import 和子模块别名。
        files = conn.execute(
            "SELECT file_path FROM ast_index WHERE language='python' "
            "UNION SELECT file_path FROM ast_symbol_rows WHERE language='python' LIMIT 10001"
        ).fetchall()
        bindings = conn.execute(
            "SELECT module_path,is_relative,file_path,local_name,alias_of FROM ast_imports "
            "WHERE language='python' LIMIT 20001"
        ).fetchall()
        if len(files) > 10000 or len(bindings) > 20000:
            raise ValueError("PULSE_IMPORT_RESOURCE_LIMIT")
        module_to_file = _build_module_to_file([r[0] for r in files])
        importers = set(imported_by)
        for module, relative, caller, local_name, alias_of in bindings:
            resolved = _resolve_module_to_file(
                module, bool(relative), caller, module_to_file
            )
            submodule = (
                _local_name_as_submodule(
                    local_name, alias_of, module, caller, module_to_file
                )
                if relative
                else ""
            )
            if file_path in (resolved, submodule):
                importers.add(caller)
        imported_by = tuple(sorted(importers)[:20])

    siblings = tuple(
        SiblingRef(
            name=s.get("name", ""),
            kind=s.get("kind", "unknown"),
            line=s.get("line", 0) or 0,
        )
        for s in siblings_raw
        if s.get("name")
    )

    comments = tuple(
        CommentRef(
            line=c.get("line", 0) or 0,
            text=c.get("text", ""),
            kind=c.get("kind", "inline"),
        )
        for c in comments_raw
    )

    # 保留 SQL 返回的边身份，不能按文件和名字重新猜测调用点。
    callees = _enrich_callees_with_lsp(
        conn, callees, tuple(c["edge_id"] for c in callees_raw if c.get("name"))
    )

    if not call_graph_available:
        callers = ()
        callees = ()

    return PulseResponse(
        symbol=sym_info,
        call_graph_available=call_graph_available,
        call_graph_reason=call_graph_reason,
        callers=callers,
        callees=callees,
        git_heat=git_heat,
        imports=imports,
        imported_by=imported_by,
        siblings=siblings,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _estimate_tokens(value: Any) -> int:
    """Estimate the token count for a JSON-serialised value."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(json.dumps(value, ensure_ascii=False, default=str)))
    except ImportError:
        return len(json.dumps(value, ensure_ascii=False, default=str)) // 4


# ---------------------------------------------------------------------------
# apply_budget — token-budget trimming
# ---------------------------------------------------------------------------

# Priority table: (field_name, token_budget_limit, top_n).
# Fields are dropped in REVERSE order (lowest priority last in this list).
_PRIORITY_ORDER = [
    "callers",
    "callees",
    "git_heat",
    "imports",
    "imported_by",
    "siblings",
    "comments",
]

_FIELD_BUDGETS = {
    "callers": 150,
    "callees": 120,
    "git_heat": 80,
    "imports": 100,
    "imported_by": 60,
    "siblings": 120,
    "comments": 100,
}

_FIELD_TOP_N = {
    "callers": 5,
    "callees": 10,
    "imports": 10,
    "imported_by": 5,
    "siblings": 10,
    "comments": 10,
}


def apply_budget(pulse: PulseResponse, token_budget: int) -> PulseResponse:
    """Trim ``pulse`` to fit within ``token_budget`` tokens.

    The ``symbol`` field is never dropped.  Other fields are trimmed
    (lowest priority first) until the estimate fits.  Returns a new
    :class:`PulseResponse` — the input is not mutated.
    """
    # Start with the symbol field (always kept).
    sym_tokens = _estimate_tokens(dataclasses.asdict(pulse.symbol))
    truncated: list[str] = []

    # Collect current field values (may already be pre-trimmed by SQL LIMIT).
    field_values: dict[str, Any] = {
        "callers": tuple(pulse.callers[: _FIELD_TOP_N.get("callers", 100)]),
        "callees": tuple(pulse.callees[: _FIELD_TOP_N.get("callees", 100)]),
        "git_heat": pulse.git_heat,
        "imports": tuple(pulse.imports[: _FIELD_TOP_N.get("imports", 100)]),
        "imported_by": tuple(pulse.imported_by[: _FIELD_TOP_N.get("imported_by", 100)]),
        "siblings": tuple(pulse.siblings[: _FIELD_TOP_N.get("siblings", 100)]),
        "comments": tuple(pulse.comments[: _FIELD_TOP_N.get("comments", 100)]),
    }

    # 从低优先级开始删减，不因某个高优先字段太大就跳过它保留低优先字段。
    total_estimate = sym_tokens + sum(
        _estimate_tokens(v) for v in field_values.values()
    )
    for field_name in reversed(_PRIORITY_ORDER):
        if total_estimate <= token_budget:
            break
        val = field_values[field_name]
        if val is None or val == ():
            continue
        truncated.append(field_name)
        field_values[field_name] = () if isinstance(val, tuple) else None
        total_estimate += _estimate_tokens(field_values[field_name]) - _estimate_tokens(
            val
        )

    total_estimate = sym_tokens + sum(
        _estimate_tokens(v) for v in field_values.values()
    )

    return dataclasses.replace(
        pulse,
        callers=field_values["callers"],
        callees=field_values["callees"],
        git_heat=field_values["git_heat"],
        imports=field_values["imports"],
        imported_by=field_values["imported_by"],
        siblings=field_values["siblings"],
        comments=field_values["comments"],
        token_estimate=total_estimate,
        truncated_fields=tuple(truncated),
    )
