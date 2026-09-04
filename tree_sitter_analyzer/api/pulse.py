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
import sqlite3
from dataclasses import dataclass, field
from typing import Any

# Languages where call-graph extraction is not supported.
_NO_CALL_GRAPH_LANGUAGES = frozenset({
    "bash", "scala", "css", "html", "json", "yaml", "sql", "markdown",
})

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
    text: str       # first 80 chars, markers stripped
    kind: str       # 'inline'|'block'


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
    WHERE  file_path = :file_path AND name = :symbol_name
    LIMIT  1
),
callers AS (
    SELECT e.caller_name AS name, e.file_path AS file, e.caller_line AS line,
           COALESCE(a.mod_count_30d, 0) AS hot30
    FROM   edges e
    JOIN   target t
    LEFT   JOIN ast_symbol_rows cs ON cs.name = e.caller_name AND cs.file_path = e.file_path
    LEFT   JOIN ast_symbol_activation a ON a.symbol_id = cs.id
    WHERE  e.kind = 'calls'
    AND    e.callee_name = t.name
    AND    (e.callee_resolved_file = t.file_path
            OR (e.file_path = t.file_path
                AND (e.callee_resolved_file IS NULL OR e.callee_resolved_file = '')))
    ORDER  BY hot30 DESC
    LIMIT  :max_callers
),
callees AS (
    SELECT e.callee_name AS name, e.callee_resolved_file AS file,
           e.callee_line AS line, e.callee_resolution AS resolution
    FROM   edges e
    JOIN   target t ON e.caller_name = t.name AND e.file_path = t.file_path
    WHERE  e.kind = 'calls'
    ORDER  BY (e.callee_resolution = 'resolved') DESC
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
    AND    (e.callee_name = t.name OR e.file_path = t.file_path)
    LIMIT  20
),
git_heat AS (
    SELECT a.last_modified_commit AS commit,
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
    SELECT SUBSTR(i.symbols_json, 1, 500) AS raw
    FROM   ast_index i
    JOIN   target t ON i.file_path = t.file_path
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
        json_object('name',name,'file',file,'line',line,'resolution',resolution))
     FROM callees) AS callees_json,
    (SELECT json_group_array(json_object('module',module,'file',file))
     FROM file_imports) AS imports_json,
    (SELECT json_group_array(importer) FROM imported_by) AS imported_by_json,
    (SELECT json_object('commit',commit,'commit_msg',commit_msg,'at',at,
                        'mod_30d',mod_30d,'mod_90d',mod_90d,'mod_all',mod_all,
                        'state',state)
     FROM git_heat) AS git_heat_json,
    (SELECT json_group_array(json_object('name',name,'kind',kind,'line',line))
     FROM siblings) AS siblings_json,
    (SELECT raw FROM docstring_cte) AS docstring_raw,
    (SELECT json_group_array(json_object('line',line,'text',text,'kind',kind))
     FROM comments_cte) AS comments_json
"""

# Fallback SQL when lsp_resolution_cache does not exist — identical to the
# main query but without the LSP JOIN on callees.
_PULSE_SQL_NO_LSP = _PULSE_SQL  # same query; LSP enrichment is done in Python


def _enrich_callees_with_lsp(
    conn: sqlite3.Connection,
    callees: tuple[CalleeRef, ...],
    file_path: str,
) -> tuple[CalleeRef, ...]:
    """Upgrade CalleeRef resolution fields using lsp_resolution_cache.

    For each callee whose resolution is ``'unresolved'`` or ``'heuristic'``,
    look up the lsp_resolution_cache table (keyed by the edge that matches
    the callee call-site).  If a cached LSP result is found with a resolved
    file or type, replace the CalleeRef with the enriched version.

    Args:
        conn:      Open SQLite connection (may not have lsp_resolution_cache).
        callees:   Tuple of CalleeRef objects from the main query.
        file_path: Source file path (used to narrow the edge lookup).

    Returns:
        Tuple of CalleeRef — same order, some entries may have richer data.
    """
    try:
        enriched: list[CalleeRef] = []
        for ce in callees:
            if ce.resolution not in ("unresolved", "heuristic"):
                enriched.append(ce)
                continue
            try:
                row = conn.execute(
                    """
                    SELECT lrc.resolved_file, lrc.resolved_line, lrc.resolved_type
                    FROM   lsp_resolution_cache lrc
                    JOIN   edges e ON e.id = lrc.edge_id
                    WHERE  e.callee_name = ?
                    AND    e.file_path   = ?
                    LIMIT  1
                    """,
                    (ce.name, file_path),
                ).fetchone()
            except sqlite3.OperationalError:
                # lsp_resolution_cache table not present yet (schema V15 pending).
                enriched.append(ce)
                continue
            if row:
                resolved_file, resolved_line, resolved_type = row
                enriched.append(
                    CalleeRef(
                        name=ce.name,
                        file=resolved_file or ce.file,
                        line=resolved_line or ce.line,
                        resolution=(
                            "resolved" if (resolved_file or resolved_type) else ce.resolution
                        ),
                    )
                )
            else:
                enriched.append(ce)
        return tuple(enriched)
    except Exception:
        # Never crash the Pulse query for an optional enrichment.
        return callees


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_json_obj(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


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
    """Execute the 9-CTE Pulse query and return a :class:`PulseResponse`.

    Returns ``None`` when the symbol is not found in the index.
    """
    params = {
        "file_path": file_path,
        "symbol_name": symbol_name,
        "max_callers": max_callers,
        "max_callees": max_callees,
        "max_siblings": max_siblings,
        "max_imports": max_imports,
        "max_comments": max_comments,
    }

    # Try with LSP-enriched callees; fall back when lsp_resolution_cache is absent.
    try:
        row = conn.execute(_PULSE_SQL, params).fetchone()
    except sqlite3.OperationalError:
        return None

    if row is None:
        return None

    target_raw = row[0] if isinstance(row, (list, tuple)) else row["target_json"]
    if not target_raw:
        return None

    # Support both dict-row and tuple-row SQLite access styles.
    def _get(idx: int, key: str) -> Any:
        try:
            return row[key]
        except (IndexError, TypeError):
            return row[idx]

    target_d = _parse_json_obj(_get(0, "target_json"))
    if not target_d:
        return None

    language = target_d.get("language", "")
    call_graph_available = language not in _NO_CALL_GRAPH_LANGUAGES
    call_graph_reason = (
        f"{language}: call-graph not supported" if not call_graph_available else ""
    )

    callers_raw = _parse_json_list(_get(1, "callers_json"))
    callees_raw = _parse_json_list(_get(2, "callees_json"))
    imports_raw = _parse_json_list(_get(3, "imports_json"))
    imported_by_raw = _parse_json_list(_get(4, "imported_by_json"))
    git_heat_d = _parse_json_obj(_get(5, "git_heat_json"))
    siblings_raw = _parse_json_list(_get(6, "siblings_json"))
    docstring_raw = _get(7, "docstring_raw") or ""
    comments_raw = _parse_json_list(_get(8, "comments_json"))

    # Extract docstring from symbols_json blob (best-effort).
    docstring: str | None = None
    if docstring_raw:
        try:
            sym_data = json.loads(docstring_raw)
            syms = sym_data.get("symbols", []) if isinstance(sym_data, dict) else []
            for sym in syms:
                if sym.get("name") == symbol_name and sym.get("docstring"):
                    docstring = str(sym["docstring"])[:200]
                    break
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

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
        git_heat = GitHeat(
            commit=git_heat_d.get("commit"),
            commit_msg=git_heat_d.get("commit_msg"),
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

    # Enrich callees with LSP resolution data (try/except — never crashes).
    callees = _enrich_callees_with_lsp(conn, callees, file_path)

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
        import tiktoken  # type: ignore
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
    "callers":     150,
    "callees":     120,
    "git_heat":     80,
    "imports":     100,
    "imported_by":  60,
    "siblings":    120,
    "comments":    100,
}

_FIELD_TOP_N = {
    "callers":     5,
    "callees":     10,
    "imports":    10,
    "imported_by": 5,
    "siblings":   10,
    "comments":   10,
}


def apply_budget(pulse: PulseResponse, token_budget: int) -> PulseResponse:
    """Trim ``pulse`` to fit within ``token_budget`` tokens.

    The ``symbol`` field is never dropped.  Other fields are trimmed
    (lowest priority first) until the estimate fits.  Returns a new
    :class:`PulseResponse` — the input is not mutated.
    """
    # Start with the symbol field (always kept).
    sym_tokens = _estimate_tokens(dataclasses.asdict(pulse.symbol))
    remaining = token_budget - sym_tokens
    truncated: list[str] = []

    # Collect current field values (may already be pre-trimmed by SQL LIMIT).
    field_values: dict[str, Any] = {
        "callers":     tuple(pulse.callers[: _FIELD_TOP_N.get("callers", 100)]),
        "callees":     tuple(pulse.callees[: _FIELD_TOP_N.get("callees", 100)]),
        "git_heat":    pulse.git_heat,
        "imports":     tuple(pulse.imports[: _FIELD_TOP_N.get("imports", 100)]),
        "imported_by": tuple(pulse.imported_by[: _FIELD_TOP_N.get("imported_by", 100)]),
        "siblings":    tuple(pulse.siblings[: _FIELD_TOP_N.get("siblings", 100)]),
        "comments":    tuple(pulse.comments[: _FIELD_TOP_N.get("comments", 100)]),
    }

    # Accumulate tokens for fields in priority order; drop when over budget.
    for field_name in _PRIORITY_ORDER:
        val = field_values[field_name]
        tok = _estimate_tokens(val)
        if remaining >= tok:
            remaining -= tok
        else:
            # Drop this field.
            if isinstance(field_values[field_name], tuple) and len(field_values[field_name]) > 0:
                truncated.append(field_name)
            elif field_values[field_name] is not None:
                truncated.append(field_name)
            if isinstance(val, tuple):
                field_values[field_name] = ()
            else:
                field_values[field_name] = None

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
