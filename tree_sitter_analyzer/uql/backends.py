"""Index-backed producers the unified query engine composes (RFC-0041 §5).

Nothing here re-derives a relation. Selection runs the Hyphae evaluator;
callers / callees are the ``nav`` tools themselves (``CodeGraphCallersTool`` /
``CodeGraphCalleesTool``) so their completeness and reason codes are consumed
exactly as ``nav action=callers`` reports them; index readiness, unindexed
sources and source freshness reuse the gates the callers tool runs.

The engine talks to the :class:`Backends` protocol so tests can inject a fake
producer and pin the propagation rules without an index.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from ..hyphae.ast import SelectorList
from .coverage import (
    COMPLETE_COVERAGE,
    INCOMPLETE,
    UNKNOWN,
    Coverage,
    gap,
)

#: Probes the evaluator's read path needs (mirrors pre-RFC ``tql_execute``):
#: some older cache read paths swallow SQL errors, so the tables are checked
#: before evaluation instead of trusting an empty result.
_READ_PROBES = (
    "SELECT file_path, language, symbols_json FROM ast_index LIMIT 0",
    "SELECT id, name, kind, file_path, language, line FROM ast_symbol_rows LIMIT 0",
    "SELECT kind, caller_name, callee_name, file_path, caller_line, "
    "callee_symbol_id, callee_resolved_file, metadata FROM edges LIMIT 0",
    "SELECT symbol_id, file_path, last_modified_at, mod_count_30d "
    "FROM ast_symbol_activation LIMIT 0",
    "SELECT rule_id, caller_file, caller_name FROM ast_constraint_violations LIMIT 0",
)

#: Symbol kinds that are definitions (the ``symbol()`` source and the
#: single-definition check share this one list).
DEFINITION_KINDS = (
    "function",
    "method",
    "class",
    "interface",
    "struct",
    "trait",
    "enum",
    "type",
    "variable",
    "constant",
)
#: The evaluator's hard cap on materialised matches per query.
SELECT_CAP = 10_000
#: Relation rows requested per producer call (nav callers lists this many).
RELATION_LIST_CAP = 10_000


@dataclass(frozen=True)
class IndexState:
    """``ready`` / ``empty`` / ``missing`` / ``unavailable`` plus detail."""

    state: str
    indexed_files: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class Selection:
    rows: list[dict[str, Any]]
    total: int
    truncated: bool


class Backends(Protocol):
    def index_state(self) -> IndexState: ...

    def select(self, selector: SelectorList, cap: int) -> Selection: ...

    def source_gate(self, files: list[str], languages: frozenset[str]) -> Coverage: ...

    def definitions(
        self, name: str, *, cls: str | None, file: str | None
    ) -> list[dict[str, Any]]: ...

    def definition_count(self, name: str) -> int | None: ...

    async def callers(self, name: str, file: str | None) -> dict[str, Any]: ...

    async def callees(self, name: str, file: str | None) -> dict[str, Any]: ...

    def generation(self) -> str | None: ...


class IndexBackends:
    """The production :class:`Backends` over one project's AST cache."""

    def __init__(self, project_root: str, cache: Any = None) -> None:
        self.project_root = project_root
        self._cache = cache
        self._nav_facade: Any = None

    @property
    def cache(self) -> Any:
        if self._cache is None:
            from ..ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    # -- index ------------------------------------------------------------
    def index_state(self) -> IndexState:
        try:
            conn = self.cache.get_conn()
            for probe in _READ_PROBES:
                conn.execute(probe)
        except Exception as exc:  # noqa: BLE001 — any read failure is "unavailable"
            return IndexState("unavailable", 0, str(exc))
        try:
            stats = self.cache.get_stats() or {}
            total = int(stats.get("total_files", 0) or 0)
        except Exception:  # noqa: BLE001
            return IndexState("missing")
        return IndexState("ready", total) if total > 0 else IndexState("empty")

    def select(self, selector: SelectorList, cap: int) -> Selection:
        from ..hyphae import Evaluator

        evaluator = Evaluator(self.cache, max_results=cap)
        rows = _with_class(self.cache, evaluator.eval(selector))
        return Selection(rows, evaluator.total_matches(), evaluator.was_truncated())

    def source_gate(self, files: list[str], languages: frozenset[str]) -> Coverage:
        """Unindexed-source and freshness gates, as ``nav action=callers`` runs them.

        A non-empty answer is a lower bound when a gate fails (``incomplete``);
        an empty answer is then not evidence of absence (``unknown``).
        """
        from ..mcp.tools.callers_absence import _freshness_gap
        from ..mcp.tools.relation_freshness import relation_source_evidence
        from ..mcp.tools.unindexed_sources import (
            UNCHECKED_REASON,
            UNINDEXED_REASON,
            unindexed_source_files,
        )

        failed = INCOMPLETE if files else UNKNOWN
        langs = languages or self._indexed_languages()
        if langs is None:
            return gap(UNKNOWN, UNCHECKED_REASON)
        unindexed = unindexed_source_files(self.cache, self.project_root, langs)
        if unindexed is None:
            return gap(failed, UNCHECKED_REASON)
        if unindexed:
            return gap(failed, UNINDEXED_REASON)
        evidence, _changed = relation_source_evidence(
            self.cache, self.project_root, files, absence=not files
        )
        reason = _freshness_gap(evidence)
        return gap(failed, reason) if reason else COMPLETE_COVERAGE

    def _indexed_languages(self) -> frozenset[str] | None:
        try:
            rows = self.cache.get_conn().execute(
                "SELECT DISTINCT language FROM ast_index"
            )
            return frozenset(str(r[0]) for r in rows if r[0])
        except (sqlite3.Error, AttributeError):
            return None

    def definitions(
        self, name: str, *, cls: str | None, file: str | None
    ) -> list[dict[str, Any]]:
        """Exact-name definitions (the ``symbol()`` source).

        Same rows as Hyphae ``#name[class=..][file=..]`` without its fuzzy
        search tiers, which cost ~0.9 s on TSA's own index and are then
        discarded by the exact-name filter.
        """
        placeholders = ", ".join("?" for _ in DEFINITION_KINDS)
        rows = (
            self.cache.get_conn()
            .execute(
                "SELECT name, kind, file_path, line, end_line, language "
                f"FROM ast_symbol_rows WHERE name = ? AND kind IN ({placeholders}) "
                "ORDER BY file_path, line",
                (name, *DEFINITION_KINDS),
            )
            .fetchall()
        )
        found = [
            {
                "name": r["name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "line": r["line"],
                "end_line": r["end_line"],
                "language": r["language"],
            }
            for r in rows
            if not file or file in str(r["file_path"])
        ]
        found = _with_class(self.cache, found)
        return [r for r in found if not cls or r.get("class") == cls]

    def definition_count(self, name: str) -> int | None:
        """Indexed definitions named ``name``; ``None`` when unreadable."""
        try:
            row = (
                self.cache.get_conn()
                .execute(
                    "SELECT COUNT(*) FROM ast_symbol_rows WHERE name = ? AND kind IN "
                    "('function', 'method', 'class', 'enum', 'variable', 'constant')",
                    (name,),
                )
                .fetchone()
            )
        except (sqlite3.Error, AttributeError):
            return None
        return int(row[0]) if row else None

    # -- relations ---------------------------------------------------------
    def _nav(self) -> Any:
        if self._nav_facade is None:
            from ..mcp.tools.nav_facade import build_nav_facade

            self._nav_facade = build_nav_facade(self.project_root)
        return self._nav_facade

    async def _relation(
        self, action: str, name: str, file: str | None
    ) -> dict[str, Any]:
        # Through the public ``nav`` facade, not the inner tool: the payload is
        # literally the ``nav action=callers`` contract, and the facade's
        # generation-keyed answer cache (RFC-0027 L6.1) is shared with it.
        args: dict[str, Any] = {
            "action": action,
            "function_name": name,
            "include_bodies": False,
            "limit": RELATION_LIST_CAP,
        }
        if file:
            args["file_path"] = file
        result = await self._nav().execute(args)
        return result if isinstance(result, dict) else {"success": False}

    async def callers(self, name: str, file: str | None) -> dict[str, Any]:
        return await self._relation("callers", name, file)

    async def callees(self, name: str, file: str | None) -> dict[str, Any]:
        return await self._relation("callees", name, file)

    def generation(self) -> str | None:
        from ..cache.answer_cache_policy import current_generation

        return current_generation(self.project_root)


def _with_class(cache: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copies of ``rows`` with ``class`` filled where the evaluator lacked it.

    ``#name`` rows come from the cascade search, which has no class column;
    the per-file function rows do. One read per distinct file; evaluator rows
    may be shared cache objects, so they are copied rather than mutated.
    """
    missing = {r.get("file") for r in rows if not r.get("class") and r.get("file")}
    getter = getattr(cache, "get_functions_by_file", None)
    owners: dict[tuple[Any, Any, Any], Any] = {}
    if missing and callable(getter):
        for file in missing:
            try:
                for fn in getter(file) or []:
                    owners[(file, fn.get("name"), fn.get("line"))] = fn.get("class")
            except Exception:  # noqa: BLE001 — enrichment is display data only
                continue
    out: list[dict[str, Any]] = []
    for row in rows:
        cls = row.get("class") or owners.get(
            (row.get("file"), row.get("name"), row.get("line"))
        )
        out.append({**row, "class": cls})
    return out
