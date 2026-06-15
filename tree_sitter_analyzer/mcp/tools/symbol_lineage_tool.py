#!/usr/bin/env python3
"""
Symbol Lineage / Impact Preview MCP Tool.

Given a symbol name, traces its lineage: definitions, callers, downstream
dependents, and risk assessment. Combines AST-level reference search with
file-level dependency graph analysis for a complete impact preview.

Tells AI agents: "If you change X, here's everything affected."
"""

import copy
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from ...utils.test_detection import is_test_file as _is_test_file
from ..utils.format_helper import apply_toon_format_to_response
from ._graph_cache_fingerprint import (
    GraphFingerprint,
    compute_graph_fingerprint,
    is_ast_index_stale,
)
from .base_tool import BaseMCPTool
from .query_symbol_search import execute_find_references

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string",
            "description": "Symbol name to trace lineage for",
        },
        "max_depth": {
            "type": "integer",
            "default": 3,
            "description": "Max dependency graph traversal depth (1-5)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
        "file_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Informational only — symbol-lineage always searches the whole "
                "project. Passing file_paths adds a scope_note to the response "
                "to signal that this parameter is not a scope filter here."
            ),
        },
    },
    "required": ["symbol"],
    "additionalProperties": False,
}

# r37be: response envelope caps (G6 truncation transparency) — module-level
# so the response builder + truncation summary share a single source.
_DEF_LIMIT = 20
_REF_LIMIT = 30
_DOWNSTREAM_LIMIT = 50
_UPSTREAM_LIMIT = 20
_TEST_LIMIT = 20
_HIER_LIMIT = 50

# Risk level → verdict mapping (canonical vocab per CLAUDE.md).
# Lineage is an informational analyser, not a modification guard, so
# the "found and clean" path emits INFO (not SAFE which implies a
# write-safety judgement). Missing symbols emit NOT_FOUND so agents
# branching on ``verdict`` no longer treat None/"n/a" as INFO and
# delete symbols that don't exist anywhere.
_RISK_TO_VERDICT: dict[str, str] = {
    "high": "CAUTION",
    "medium": "REVIEW",
    "low": "INFO",
    "unknown": "NOT_FOUND",
}


def _apply_grep_fallback_defs(
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    project_root: str,
    symbol: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """K3 fix: text-grep the project for definitions when the AST scan missed them.

    Promotes any matching reference to a definition (file + start_line key)
    and removes it from ``references`` to avoid double-counting. Pure
    helper — no side effects on the caller's lists.
    """
    fallback_defs = _find_definitions_via_grep(project_root, symbol)
    if not fallback_defs:
        return definitions, references

    out_defs = list(definitions)
    seen_def_keys = {(d.get("file", ""), d.get("start_line", 0)) for d in out_defs}
    ref_keys_to_drop: set[tuple[str, int]] = set()
    for fd in fallback_defs:
        key = (fd["file"], fd["start_line"])
        if key in seen_def_keys:
            continue
        seen_def_keys.add(key)
        ref_keys_to_drop.add(key)
        out_defs.append(fd)
    if not ref_keys_to_drop:
        return out_defs, references
    out_refs = [
        r
        for r in references
        if (r.get("file", ""), r.get("start_line", 0)) not in ref_keys_to_drop
    ]
    return out_defs, out_refs


def _build_truncations_and_summary_line(
    symbol: str,
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    downstream_files: set[str],
    risk: dict[str, Any],
) -> tuple[list[str], str]:
    """G6: compose the truncation list + the headline summary_line."""
    truncations: list[str] = []
    if len(references) > _REF_LIMIT:
        truncations.append("references")
    if len(downstream_files) > _DOWNSTREAM_LIMIT:
        truncations.append("downstream_files")
    summary_line = (
        f"{symbol} defs={len(definitions)} refs={len(references)} "
        f"downstream={len(downstream_files)} risk={risk['level']}"
    )
    if truncations:
        summary_line += f" truncated={'+'.join(truncations)}"
    return truncations, summary_line


def _verdict_and_next_step(risk_level: str) -> tuple[str, str]:
    """Map a risk level to (verdict, next_step) per the lineage contract."""
    verdict = _RISK_TO_VERDICT.get(risk_level, "NOT_FOUND")
    if risk_level == "high":
        next_step = "trace_impact and run listed test files before changing signature"
    elif risk_level == "medium":
        next_step = "review callers in listed files, then run downstream tests"
    elif risk_level == "low":
        next_step = "proceed with edit, run nearest test file"
    else:
        next_step = "verify symbol name — no definitions found"
    return verdict, next_step


def _build_agent_summary_block(
    summary_line: str,
    next_step: str,
    verdict: str,
    truncations: list[str],
) -> dict[str, Any]:
    """Canonical agent_summary block with optional ``truncations`` echo."""
    block: dict[str, Any] = {
        "summary_line": summary_line,
        "next_step": next_step,
        "verdict": verdict,
    }
    if truncations:
        block["truncations"] = truncations
    return block


class SymbolLineageTool(BaseMCPTool):
    """Trace symbol lineage: definitions, references, file-level downstream impact."""

    def __init__(self, project_root: str | None = None) -> None:
        # Lazy graph + per-symbol response cache. Built on the first call,
        # reset on project_root rebind via _on_project_root_changed.
        self._dep_graph: DependencyGraph | None = None
        self._symbol_cache: dict[tuple[str, int], dict[str, Any]] = {}
        # H4 fix: fingerprint snapshot for the cached graph + symbol cache.
        # When the source tree changes, both the graph and the per-symbol
        # response cache are invalidated together — the symbol responses
        # bake in the graph's downstream/upstream sets.
        self._dep_graph_fingerprint: GraphFingerprint | None = None
        self._dep_graph_built_at: float | None = None
        self._cache_invalidated_reason: str | None = None
        # #568: the hierarchy section is derived from the AST index (index.db),
        # not the source tree, so it must invalidate the per-symbol cache on its
        # own — else a lineage call made before indexing caches a no-hierarchy
        # response that the source-only fingerprint can't refresh once the index
        # is built (Codex P2).
        self._ast_index_mtime_ns: int | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # ARCH-A4 hook: invalidate every per-project cache when rebinding.
        self._dep_graph = None
        self._symbol_cache = {}
        self._dep_graph_fingerprint = None
        self._dep_graph_built_at = None
        self._cache_invalidated_reason = None
        self._ast_index_mtime_ns = None

    def _get_dep_graph(self) -> DependencyGraph | None:
        """Return cached dependency graph, building it on first use.

        Returns ``None`` if graph construction fails (keeps the tool usable
        with reduced fidelity — downstream/upstream stay empty).
        """
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        current_fp = compute_graph_fingerprint(str(self.project_root))
        reason: str | None = None
        if self._dep_graph is None:
            reason = "cold"
        elif self._dep_graph_fingerprint != current_fp:
            reason = self._explain_fingerprint_delta(
                self._dep_graph_fingerprint, current_fp
            )

        if reason is not None:
            # Invalidate downstream caches that depend on the graph.
            self._symbol_cache = {}
            try:
                self._dep_graph = DependencyGraph(str(self.project_root))
                self._dep_graph_fingerprint = current_fp
                self._dep_graph_built_at = time.time()
                self._cache_invalidated_reason = reason
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"DependencyGraph build failed: {exc}")
                # Keep the prior state so the next call retries on its own.
                self._dep_graph = None
                self._dep_graph_fingerprint = None
                self._dep_graph_built_at = None
                self._cache_invalidated_reason = None
                return None
        else:
            self._cache_invalidated_reason = None
        return self._dep_graph

    @staticmethod
    def _explain_fingerprint_delta(
        old: GraphFingerprint | None, new: GraphFingerprint
    ) -> str:
        if old is None:
            return "cold"
        if old.file_count != new.file_count:
            delta = new.file_count - old.file_count
            return (
                f"file_count_changed ({delta:+d}, {old.file_count}->{new.file_count})"
            )
        if old.max_mtime_ns != new.max_mtime_ns:
            return "source_modified"
        return "unknown"

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "symbol_lineage",
            "description": (
                "Symbol lineage: definition → callers → downstream files → risk. "
                "Shows what breaks if you change a symbol. "
                "Combines AST references with file dependency graph. "
                "SLOW: traverses AST references plus the full dependency graph "
                "(5-15s per symbol on medium repos). Cache via project_index."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        symbol = arguments.get("symbol", "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        max_depth = arguments.get("max_depth", 3)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 5:
            raise ValueError("max_depth must be 1-5")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Symbol lineage analysis with cache + grep fallback + blast radius.

        r37be (dogfood): tool flagged this at 246 lines. Split into 8
        phases (validate / cache lookup / find refs / blast radius /
        truncation / verdict / envelope / cache store). Every behaviour
        preserved: H4 cache refresh, H12 reclassify, K3 grep fallback,
        G6 truncation transparency, r37u top-level verdict mirror.
        """
        started = time.perf_counter()
        symbol = arguments["symbol"].strip()
        max_depth = int(arguments.get("max_depth", 3))
        output_format = arguments.get("output_format", "toon")
        # #756: file_paths is accepted in the schema (so MCP callers don't
        # get schema-validation errors) but symbol-lineage is always
        # project-wide — it does not scope results to listed paths.
        file_paths = arguments.get("file_paths") or []

        self._validate_project_root()
        # H4 fix: refresh dep graph (clears _symbol_cache on rebuild) before
        # the cache lookup below.
        graph = self._get_dep_graph()
        # #568: also clear the per-symbol cache when the AST index changed
        # (hierarchy is index-derived; the source fingerprint above can't see it).
        self._invalidate_symbol_cache_on_index_change()
        # #932: an unchanged index DB can still be stale relative to source
        # edits/adds/deletes. Check before serving the per-symbol cache so a
        # warm lineage response never hides stale hierarchy/index_hint data.
        self._invalidate_symbol_cache_on_stale_ast_index()

        cached_response = self._try_cached_lineage(symbol, max_depth, started)
        if cached_response is not None:
            return apply_toon_format_to_response(cached_response, output_format)

        definitions, references = await self._collect_definitions_and_refs(symbol)
        all_symbol_files = self._collect_symbol_files(definitions, references)
        downstream_files, upstream_files = self._compute_blast_radius(
            graph, all_symbol_files
        )

        risk = _assess_risk(len(definitions), len(references), len(downstream_files))
        test_files = sorted(
            f for f in (downstream_files | all_symbol_files) if _is_test_file(f)
        )

        truncations, summary_line = _build_truncations_and_summary_line(
            symbol, definitions, references, downstream_files, risk
        )
        verdict, next_step = _verdict_and_next_step(risk["level"])
        agent_summary = _build_agent_summary_block(
            summary_line, next_step, verdict, truncations
        )

        response = self._assemble_lineage_response(
            symbol=symbol,
            definitions=definitions,
            references=references,
            all_symbol_files=all_symbol_files,
            downstream_files=downstream_files,
            upstream_files=upstream_files,
            test_files=test_files,
            risk=risk,
            summary_line=summary_line,
            verdict=verdict,
            agent_summary=agent_summary,
            hierarchy=self._hierarchy_for(symbol),
        )

        # #756: when the caller provided file_paths, emit a scope_note so they
        # know results are project-wide and file_paths is not a scope filter
        # for symbol-lineage.
        if file_paths:
            response["scope_note"] = (
                "symbol-lineage always searches the whole project. "
                "file_paths is not a scope filter here — all project files "
                "are included in the result regardless of this parameter."
            )

        return self._finalize_and_cache_response(
            response, (symbol, max_depth), started, output_format
        )

    def _validate_project_root(self) -> None:
        """Reject when project_root is unset or not a directory."""
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

    def _try_cached_lineage(
        self,
        symbol: str,
        max_depth: int,
        started: float,
    ) -> dict[str, Any] | None:
        """Return a deep-copied cached response if one exists, else ``None``.

        Per-symbol response cache — the tool does an expensive cross-file
        walk + dep-graph traversal that orchestrators repeat. Cache key
        is ``(symbol, max_depth)``; reset on project_root rebind.
        """
        cache_key = (symbol, max_depth)
        cached = self._symbol_cache.get(cache_key)
        if cached is None:
            return None
        result = copy.deepcopy(cached)
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        result["from_cache"] = True
        if self._dep_graph_built_at is not None:
            result["cache_age_s"] = round(time.time() - self._dep_graph_built_at, 3)
        return result

    async def _collect_definitions_and_refs(
        self, symbol: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Find references, reclassify (H12), K3 grep fallback, and #757 caller enrichment."""
        ref_args = {"symbol": symbol, "output_format": "json"}
        refs_result = await execute_find_references(self.project_root, ref_args)

        definitions = refs_result.get("definitions", [])
        references = refs_result.get("references", [])

        # H12: tree-sitter element types are short canonical names (function /
        # method / decorated_definition / class). ``execute_find_references``
        # only promotes hits to "definition" when the type substring contains
        # ``definition`` / ``declaration`` / ``class`` / ``struct``, so most
        # actual def sites land in ``references``. Reclassify here.
        definitions, references = _reclassify_definition_like(
            definitions, references, str(self.project_root), symbol
        )

        # K3: ``execute_find_references`` caps at 500 files. When defs are
        # empty, run a text-grep fallback scanning ALL project source files
        # so symbols whose owning file sorts past the 500th still get found.
        if not definitions:
            definitions, references = _apply_grep_fallback_defs(
                definitions, references, str(self.project_root), symbol
            )

        # #757: ``execute_find_references`` walks AST *elements* (imports,
        # definitions) but NOT call-site edges — so reference_count only
        # counts import statements, not actual callers.  Enrich with the
        # call graph to surface real call sites.
        references = _enrich_references_with_callers(
            references, str(self.project_root), symbol
        )

        return definitions, references

    @staticmethod
    def _collect_symbol_files(
        definitions: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> set[str]:
        """Union of ``file`` keys across definitions + references."""
        def_files = {d["file"] for d in definitions}
        ref_files = {r["file"] for r in references}
        return def_files | ref_files

    @staticmethod
    def _compute_blast_radius(
        graph: Any,
        all_symbol_files: set[str],
    ) -> tuple[set[str], set[str]]:
        """Forward + reverse blast radius from the dep graph (empty when graph absent)."""
        downstream_files: set[str] = set()
        upstream_files: set[str] = set()
        if not graph:
            return downstream_files, upstream_files
        for f in all_symbol_files:
            if not graph.has_node(f):
                continue
            br = BlastRadius(graph)
            fwd = br.forward(f)
            if fwd:
                downstream_files.update(fwd)
            rev = br.reverse(f)
            if rev:
                upstream_files.update(rev)
        return downstream_files, upstream_files

    def _index_signature(self) -> int:
        """Max ``mtime_ns`` across the AST index DB and its WAL/SHM sidecars.

        SQLite in WAL mode writes new rows to ``index.db-wal`` without
        touching ``index.db``'s mtime until a checkpoint (Codex P2), so a
        bare ``index.db`` stat misses index updates. Taking the max over all
        three files makes the signature flip on any index write. Returns 0
        when no index exists. Called only after ``_validate_project_root``.
        """
        assert self.project_root is not None  # guaranteed by _validate_project_root
        cache_dir = Path(self.project_root) / ".ast-cache"
        sig = 0
        for name in ("index.db", "index.db-wal", "index.db-shm"):
            try:
                mtime = (cache_dir / name).stat().st_mtime_ns
            except OSError:
                continue
            if mtime > sig:
                sig = mtime
        return sig

    def _invalidate_symbol_cache_on_index_change(self) -> None:
        """Clear the per-symbol cache when the AST index changed (#568).

        The hierarchy section is derived from the AST index, which an
        autoindex/build can refresh without touching source files — so the
        source-tree fingerprint would otherwise serve a stale no-hierarchy hit.
        The recorded signature is refreshed in ``_finalize_and_cache_response``
        (AFTER this call's own index reads/writes), so a call that *creates*
        the index as a side effect — ``find_references`` / ``_hierarchy_for``
        both touch ``.ast-cache`` — does not spuriously evict the next call's
        warm hit. Only called from ``execute`` after ``_validate_project_root``.
        """
        if self._index_signature() != self._ast_index_mtime_ns:
            self._symbol_cache = {}

    def _invalidate_symbol_cache_on_stale_ast_index(self) -> None:
        """Clear cached lineage responses when source has outpaced ast_index."""
        if not self.project_root:
            return
        if is_ast_index_stale(str(self.project_root)):
            self._symbol_cache = {}
            self._cache_invalidated_reason = "ast_index_stale"

    def _hierarchy_for(self, symbol: str) -> dict[str, Any] | None:
        """#568: the advertised inheritance/override lineage.

        The lineage action documents "class/function inheritance and override
        lineage" but only returned an impact profile. Ask ClassHierarchy
        (extends edges) directly — its ``has_class`` is the authoritative gate,
        which works regardless of how the definition was found (Codex P2s):

        * the symbol is resolved to its BARE name (``pkg.Base`` -> ``Base``) —
          ClassHierarchy stores classes by bare name from the AST cache;
        * detection does NOT depend on the definition's ``kind``/``type``, so a
          class found only via the K3 grep fallback (``type='definition'``, no
          ``kind``) still gets its hierarchy.

        Returns ``None`` for non-class symbols (or an empty/unbuilt index).
        Only called from ``execute`` after ``_validate_project_root``.
        """
        bare = symbol.rsplit(".", 1)[-1]
        cache = None
        try:
            from ...ast_cache import ASTCache
            from ...class_hierarchy import ClassHierarchy

            cache = ASTCache(str(self.project_root))
            ch = ClassHierarchy(cache)
            ch.build()
            if not ch.has_class(bare):
                return None
            subs = ch.subclasses_of(bare)
            supers = ch.superclasses_of(bare)
        except Exception as exc:  # noqa: BLE001 — degrade to no hierarchy
            logger.warning(f"lineage hierarchy lookup failed for {symbol}: {exc}")
            return None
        finally:
            # Release the SQLite handle so Windows can delete the cache dir
            # (WinError 32: index.db locked at tmp teardown otherwise).
            if cache is not None:
                cache.close()
        # #703: authoritative staleness — query each indexed file's recorded
        # mtime_ns and compare against on-disk. Language-complete: covers Kotlin,
        # Ruby, PHP, Swift, etc. that _SOURCE_EXTS-based fingerprinting missed.
        # Falls back to the old fingerprint approach if the index is absent.
        index_mtime_ns = self._index_signature()
        if index_mtime_ns == 0:
            # No index at all → stale (hierarchy built from in-memory cache).
            stale = True
        else:
            stale = is_ast_index_stale(str(self.project_root))
        hier: dict[str, Any] = {
            "subclasses": subs[:_HIER_LIMIT],
            "subclass_count": len(subs),
            "subclasses_truncated": len(subs) > _HIER_LIMIT,
            "superclasses": supers,
            "superclass_count": len(supers),
            "index_stale": stale,
        }
        if stale:
            hier["index_hint"] = (
                "Source changed since last index; run project_index/index"
                " action=auto to refresh inheritance."
            )
        return hier

    @staticmethod
    def _assemble_lineage_response(
        *,
        symbol: str,
        definitions: list[dict[str, Any]],
        references: list[dict[str, Any]],
        all_symbol_files: set[str],
        downstream_files: set[str],
        upstream_files: set[str],
        test_files: list[str],
        risk: dict[str, Any],
        summary_line: str,
        verdict: str,
        agent_summary: dict[str, Any],
        hierarchy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assemble the canonical lineage envelope with G6 truncation + r37u verdict."""
        sorted_downstream = sorted(downstream_files)
        sorted_upstream = sorted(upstream_files)
        references_truncated = len(references) > _REF_LIMIT
        downstream_truncated = len(sorted_downstream) > _DOWNSTREAM_LIMIT

        if test_files:
            hint_tail = "Run the listed test files before committing."
        else:
            hint_tail = "No test files detected."

        return {
            "success": True,
            "symbol": symbol,
            "definitions": definitions[:_DEF_LIMIT],
            "definition_count": len(definitions),
            "references": references[:_REF_LIMIT],
            "reference_count": len(references),
            "references_truncated": references_truncated,
            "references_limit": _REF_LIMIT,
            "references_available": len(references),
            "files_containing_symbol": sorted(all_symbol_files),
            "downstream_files": sorted_downstream[:_DOWNSTREAM_LIMIT],
            "downstream_file_count": len(downstream_files),
            "downstream_files_truncated": downstream_truncated,
            "downstream_files_limit": _DOWNSTREAM_LIMIT,
            "downstream_files_available": len(downstream_files),
            "upstream_files": sorted_upstream[:_UPSTREAM_LIMIT],
            "upstream_file_count": len(upstream_files),
            "test_files_to_run": test_files[:_TEST_LIMIT],
            "test_file_count": len(test_files),
            "risk": risk,
            "smart_workflow_hint": (
                f"Symbol '{symbol}' has {risk['level']} change risk "
                f"({len(references)} refs, {len(downstream_files)} downstream files). "
                f"{hint_tail} "
                "Use analyze_change_impact after editing for git-diff level detail."
            ),
            "summary_line": summary_line,
            "verdict": verdict,  # r37u: top-level verdict mirror
            "agent_summary": agent_summary,
            # #568: the advertised inheritance/override lineage — present only
            # for class symbols (None for functions/non-classes, omitted below).
            **({"hierarchy": hierarchy} if hierarchy else {}),
        }

    def _finalize_and_cache_response(
        self,
        response: dict[str, Any],
        cache_key: tuple[str, int],
        started: float,
        output_format: str,
    ) -> dict[str, Any]:
        """Cache a deep copy, stamp elapsed/from_cache, apply TOON formatting."""
        self._symbol_cache[cache_key] = copy.deepcopy(response)
        # #568: record the index signature AFTER this call's own index
        # reads/writes so creating the index here doesn't evict the next
        # warm hit (the invalidation check above compares against this).
        self._ast_index_mtime_ns = self._index_signature()

        response["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        response["from_cache"] = False
        if self._dep_graph_built_at is not None:
            response["cache_age_s"] = round(time.time() - self._dep_graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            response["cache_invalidated_reason"] = self._cache_invalidated_reason
        return apply_toon_format_to_response(response, output_format)


# H12: element_type values that mean "this hit IS the symbol's definition
# site". Mirrors the keywords used by ``execute_find_references`` plus the
# short canonical types returned by tree-sitter element extractors across
# the languages most used in this repo's dogfood data:
# - Python: function, method, decorated_definition, class
# - JS/TS: function, arrow_function, function_declaration,
#   class, class_declaration
# - Java: method, class, interface, method_declaration, class_declaration
# - Go: function, method, function_declaration, method_declaration
# - Rust/C/C++/C#: function, struct, class, declaration
# Matched as substrings (case-insensitive) so language-specific variants
# like ``async_function_definition`` still classify correctly.
_DEFINITION_LIKE_TYPES: tuple[str, ...] = (
    "function",
    "method",
    "constructor",
    "decorated_definition",
    "arrow_function",
    "function_declaration",
    "method_declaration",
    "function_definition",
    "method_definition",
    "class",
    "class_declaration",
    "class_definition",
    "struct",
    "struct_declaration",
    "interface",
    "interface_declaration",
    "enum",
    "enum_declaration",
    "definition",
    "declaration",
    "trait",
    "impl_item",
)

# Source-line prefixes that indicate a definition site. We check the
# actual content of the source file at the hit's ``start_line`` before
# promoting a reference to a definition — element_type alone is too
# coarse because tree-sitter returns ``function`` for both ``def`` sites
# (the actual definition) and synthetic test fixtures that mock call
# sites. Reading the source provides the ground truth: a line that
# *starts* with ``def``/``class``/``func``/etc. is a definition; a line
# that just contains the symbol elsewhere is a reference.
_DEFINITION_LINE_PREFIXES: tuple[str, ...] = (
    "def ",
    "async def ",
    "class ",
    "function ",
    "function* ",
    "async function ",
    "func ",
    "fn ",
    "struct ",
    "interface ",
    "trait ",
    "enum ",
    "type ",
    "public ",
    "private ",
    "protected ",
    "static ",
    "abstract ",
    "@",  # Python decorator on the line above the def is still part of
)


def _is_definition_like(element_type: str) -> bool:
    """Return ``True`` when ``element_type`` denotes a definition site.

    Tree-sitter element extractors return short, language-specific names
    (e.g. ``function`` for Python ``def``). The upstream classifier in
    ``execute_find_references`` only checks for ``definition``/
    ``declaration``/``class``/``struct`` substrings, so Python ``def``
    sites get misrouted into ``references``. This predicate covers the
    canonical names emitted across the languages this repo's dogfood
    actually hits.
    """
    if not element_type:
        return False
    lowered = element_type.lower()
    return any(kind in lowered for kind in _DEFINITION_LIKE_TYPES)


def _line_looks_like_definition(
    project_root: str,
    file_rel: str,
    line_no: int,
    symbol: str,
) -> bool:
    """Return ``True`` when the source line at ``line_no`` is a def site.

    Reads the file relative to ``project_root`` and inspects the line.
    Definition sites begin with a definition keyword (``def``, ``class``,
    ``function``, ``func``, ``fn``, …) and contain the symbol name. This
    is more reliable than ``element_type`` alone for the H12 fix —
    tree-sitter returns the short canonical type ``function`` for both
    actual def sites and any synthetic test reference, so we need a
    content-level check.
    """
    if not file_rel or line_no < 1 or not symbol:
        return False
    try:
        path = Path(project_root) / file_rel
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = text.splitlines()
    if line_no > len(lines):
        return False
    line = lines[line_no - 1]
    stripped = line.lstrip()
    if symbol not in stripped:
        return False
    # Match any line that starts with a definition keyword and mentions
    # the symbol. Decorators on the line above the def are tolerated by
    # checking the next non-empty line too — but the basic case is a
    # direct prefix.
    if any(stripped.startswith(prefix) for prefix in _DEFINITION_LINE_PREFIXES):
        return True
    return False


def _reclassify_definition_like(
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    project_root: str | None = None,
    symbol: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """H12 fix: promote definition-like references into ``definitions``.

    The upstream ``execute_find_references`` misclassifies Python ``def``
    sites (``element_type="function"``) and Java methods
    (``element_type="method"``) as references. Walk the references list
    once and route each definition-like hit into a new ``definitions``
    list.

    Two tests must both pass for promotion:

    1. ``element_type`` is a definition-like type (``function``,
       ``method``, ``class``, …) — the upstream classifier already
       narrowed the universe to nameable elements, but we re-check
       defensively.
    2. The source line at ``start_line`` starts with a definition
       keyword (``def``, ``class``, ``func``, …) and mentions the
       symbol. This filters out synthetic test fixtures that mock
       references pointing at files that don't exist on disk.

    Hits with ``role="related"`` are kept as references regardless —
    they are substring matches on similarly-named symbols, not the
    symbol's own def site.
    """
    if not references:
        return definitions, references

    promoted: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    seen_def_keys: set[tuple[str, int]] = {
        (d.get("file", ""), d.get("start_line", 0)) for d in definitions
    }

    for entry in references:
        role = entry.get("role")
        etype = entry.get("type", "")
        # ``related`` hits are substring matches, not the symbol's own
        # def — keep them as references regardless of element_type.
        if role == "related":
            remaining.append(entry)
            continue
        if not _is_definition_like(etype):
            remaining.append(entry)
            continue
        # Content check: only promote when the source line really IS a
        # def site. Synthetic test fixtures point at files that don't
        # exist on disk; the read fails and we leave the entry in
        # references.
        looks_like_def = False
        if project_root and symbol:
            looks_like_def = _line_looks_like_definition(
                project_root,
                entry.get("file", ""),
                int(entry.get("start_line", 0)),
                symbol,
            )
        if not looks_like_def:
            remaining.append(entry)
            continue
        # Dedupe against any existing definitions to avoid duplicate
        # entries when both classifiers happen to fire.
        key = (entry.get("file", ""), entry.get("start_line", 0))
        if key in seen_def_keys:
            continue
        seen_def_keys.add(key)
        new_entry = dict(entry)
        new_entry["role"] = "definition"
        promoted.append(new_entry)

    if not promoted:
        return definitions, references
    return [*definitions, *promoted], remaining


def _assess_risk(
    def_count: int, ref_count: int, downstream_count: int
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if def_count == 0:
        return {"level": "unknown", "score": 0, "reasons": ["Symbol not found"]}

    if def_count > 1:
        score += 1
        reasons.append(f"Multiple definitions ({def_count})")

    if ref_count > 20:
        score += 3
        reasons.append(f"Many references ({ref_count})")
    elif ref_count > 5:
        score += 2
        reasons.append(f"Moderate references ({ref_count})")
    elif ref_count > 0:
        score += 1
        reasons.append(f"Few references ({ref_count})")

    if downstream_count > 10:
        score += 3
        reasons.append(f"Wide blast radius ({downstream_count} downstream files)")
    elif downstream_count > 3:
        score += 2
        reasons.append(f"Moderate blast radius ({downstream_count} downstream files)")
    elif downstream_count > 0:
        score += 1
        reasons.append(f"Small blast radius ({downstream_count} downstream files)")

    if score <= 2:
        level = "low"
    elif score <= 5:
        level = "medium"
    else:
        level = "high"

    return {"level": level, "score": score, "reasons": reasons}


def _enrich_references_with_callers(
    references: list[dict[str, Any]],
    project_root: str,
    symbol: str,
) -> list[dict[str, Any]]:
    """#757: augment AST-element references with real call-site callers.

    ``execute_find_references`` walks AST *elements* (imports, definitions)
    but not call-edge rows, so its references[] contains only import
    statements — never actual call sites.  The call graph (populated by
    ``index_project``) stores every call edge as a row with
    ``caller_name / caller_file / caller_line``.  Querying it yields the
    real callers that the AST-element walk misses.

    Deduplication is by ``(file, start_line)`` so an AST import hit at
    the same position as a call-graph edge is not double-counted.

    Returns a new list (immutable input) with call-site rows appended.
    """
    bare_name = symbol.rsplit(".", 1)[-1]
    try:
        from ...ast_cache import ASTCache

        cache = ASTCache(project_root)
        if not cache.has_call_edges():
            cache.close()
            return references
        raw_callers = cache.query_callers(bare_name)
        cache.close()
    except Exception:  # nosec BLE001 — degrade gracefully; no callers added
        return references

    if not raw_callers:
        return references

    # Build a seen-key set from existing references to avoid duplicates.
    seen: set[tuple[str, int]] = {
        (r.get("file", ""), int(r.get("start_line", 0))) for r in references
    }

    new_refs = list(references)
    for edge in raw_callers:
        caller_name = edge.get("caller_name", "")
        caller_file = edge.get("caller_file", "")
        caller_line = int(edge.get("caller_line", 0))
        # Skip unattributed call sites (module-level callers with no
        # enclosing function — same rule as callers_tool #638 fix).
        if not caller_name or not caller_file:
            continue
        key = (caller_file, caller_line)
        if key in seen:
            continue
        seen.add(key)
        new_refs.append(
            {
                "name": caller_name,
                "type": "call_site",
                "file": caller_file,
                "start_line": caller_line,
                "end_line": caller_line,
                "role": "caller",
            }
        )
    return new_refs


# K3 fallback: project-wide text scan for definition sites. Used when
# ``execute_find_references`` returns 0 definitions because its 500-file
# cap dropped the def-bearing file. We scan ALL project source files
# (no cap) but only read files whose path contains a fast first-pass
# substring check (the symbol name) — keeps the scan cheap.
_K3_FALLBACK_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".java",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".kt",
        ".cs",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
    }
)
_K3_FALLBACK_EXCLUDE: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "htmlcov",
        ".cache",
        ".eggs",
        ".claude",
        ".ast-cache",
        ".tree-sitter-cache",
    }
)


def _find_definitions_via_grep(
    project_root: str,
    symbol: str,
) -> list[dict[str, Any]]:
    """Project-wide text scan for definition sites of ``symbol``.

    r37be (dogfood): tool flagged this at 108 lines. Split into
    bare-name normalisation + regex build + file walk + per-line scan.
    Behaviour preserved: 2-layer substring/word filter, no tree-sitter.
    """
    bare_name = _normalize_bare_symbol(symbol)
    if not bare_name:
        return []
    root = Path(project_root).resolve()
    if not root.is_dir():
        return []

    word_re, line_re = _build_grep_definition_regexes(bare_name)
    hits: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()
    for file_path in _iter_grep_candidate_files(root):
        _scan_file_for_definitions(
            file_path, root, bare_name, word_re, line_re, hits, seen_keys
        )
    return hits


def _normalize_bare_symbol(symbol: str) -> str:
    """Return the trailing component of ``a.b.c`` style symbols."""
    if not symbol:
        return ""
    return symbol.split(".")[-1]


def _build_grep_definition_regexes(
    bare_name: str,
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Return (whole-word file-pre-check, full-line definition match) regexes."""
    word_re = re.compile(r"\b" + re.escape(bare_name) + r"\b")
    keyword_alternation = (
        r"(?:def|async\s+def|class|function|function\*|async\s+function|"
        r"func|fn|struct|interface|trait|enum|type|impl|namespace|module)"
    )
    line_re = re.compile(
        r"^\s*"
        r"(?:(?:public|private|protected|static|abstract|final|virtual|"
        r"override|sealed|unsafe|async|export|default)\s+)*"
        + keyword_alternation
        + r"\s+"
        + re.escape(bare_name)
        + r"(?:\b|[\s\(:<])"
    )
    return word_re, line_re


def _iter_grep_candidate_files(root: Path) -> Iterator[Path]:
    """Yield source files under ``root`` (manual scandir walk, excludes pruned)."""
    import os as _os

    stack: list[str] = [str(root)]
    while stack:
        current = stack.pop()
        try:
            it = _os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                name = entry.name
                if name in _K3_FALLBACK_EXCLUDE:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                dot = name.rfind(".")
                if dot == -1:
                    continue
                if name[dot:].lower() not in _K3_FALLBACK_EXTS:
                    continue
                yield Path(entry.path)


def _scan_file_for_definitions(
    file_path: Path,
    root: Path,
    bare_name: str,
    word_re: re.Pattern[str],
    line_re: re.Pattern[str],
    hits: list[dict[str, Any]],
    seen_keys: set[tuple[str, int]],
) -> None:
    """Read ``file_path`` and append every matching definition line to ``hits``."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if not word_re.search(text):
        return
    rel = str(file_path.relative_to(root))
    for i, line in enumerate(text.splitlines(), start=1):
        if not line_re.match(line):
            continue
        key = (rel, i)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        hits.append(
            {
                "name": bare_name,
                "type": "definition",
                "file": rel,
                "start_line": i,
                "end_line": i,
                "role": "definition",
            }
        )
