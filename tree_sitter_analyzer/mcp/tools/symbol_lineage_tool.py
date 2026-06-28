#!/usr/bin/env python3
"""
Symbol Lineage / Impact Preview MCP Tool.

Given a symbol name, traces its lineage: definitions, callers, downstream
dependents, and risk assessment. Combines AST-level reference search with
file-level dependency graph analysis for a complete impact preview.

Tells AI agents: "If you change X, here's everything affected."
"""

import copy
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cache.fingerprint import (
    GraphFingerprint,
    compute_graph_fingerprint,
    is_ast_index_stale,
)

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from ...utils.test_detection import is_test_file as _is_test_file
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .query_symbol_search import execute_find_references
from .utils.lineage_formatter import (
    _DEF_LIMIT,
    _DOWNSTREAM_LIMIT,
    _HIER_LIMIT,
    _REF_LIMIT,
    _TEST_LIMIT,
    _UPSTREAM_LIMIT,
    _assess_risk,
    _build_agent_summary_block,
    _build_truncations_and_summary_line,
    _filter_references_to_scope,
    _normalize_scope_file_paths,
    _reclassify_definition_like,
    _verdict_and_next_step,
)
from .utils.lineage_graph_builder import (
    _apply_grep_fallback_defs,
    _enrich_references_with_callers,
)

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
                "Optional scope filter for references/call sites. Definitions "
                "are still resolved project-wide so the symbol location remains "
                "available."
            ),
        },
    },
    "required": ["symbol"],
    "additionalProperties": False,
}


class SymbolLineageTool(BaseMCPTool):
    """Trace symbol lineage: definitions, references, file-level downstream impact."""

    def __init__(self, project_root: str | None = None) -> None:
        # Lazy graph + per-symbol response cache. Built on the first call,
        # reset on project_root rebind via _on_project_root_changed.
        self._dep_graph: DependencyGraph | None = None
        self._symbol_cache: dict[tuple[str, int, tuple[str, ...]], dict[str, Any]] = {}
        # H4 fix: fingerprint snapshot for the cached graph + symbol cache.
        self._dep_graph_fingerprint: GraphFingerprint | None = None
        self._dep_graph_built_at: float | None = None
        self._cache_invalidated_reason: str | None = None
        # #568: hierarchy section is derived from the AST index.
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
        """Return cached dependency graph, building it on first use."""
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
            self._symbol_cache = {}
            try:
                self._dep_graph = DependencyGraph(str(self.project_root))
                self._dep_graph_fingerprint = current_fp
                self._dep_graph_built_at = time.time()
                self._cache_invalidated_reason = reason
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"DependencyGraph build failed: {exc}")
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
        """Symbol lineage analysis with cache + grep fallback + blast radius."""
        started = time.perf_counter()
        symbol = arguments["symbol"].strip()
        max_depth = int(arguments.get("max_depth", 3))
        output_format = arguments.get("output_format", "toon")
        self._validate_project_root()
        file_paths = arguments.get("file_paths") or []
        scope_files = _normalize_scope_file_paths(str(self.project_root), file_paths)
        graph = self._get_dep_graph()
        self._invalidate_symbol_cache_on_index_change()
        self._invalidate_symbol_cache_on_stale_ast_index()

        cache_key = (symbol, max_depth, tuple(sorted(scope_files)))
        cached_response = self._try_cached_lineage(cache_key, started)
        if cached_response is not None:
            return apply_toon_format_to_response(cached_response, output_format)

        definitions, references = await self._collect_definitions_and_refs(symbol)
        if scope_files:
            references = _filter_references_to_scope(references, scope_files)
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

        if scope_files:
            response["scope_filter"] = sorted(scope_files)
            response["scope_filtered"] = True
            response["scope_note"] = (
                "file_paths filters references and call sites; definitions "
                "remain project-wide so the symbol location is preserved."
            )
        else:
            response["scope_filtered"] = False

        return self._finalize_and_cache_response(
            response, cache_key, started, output_format
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
        cache_key: tuple[str, int, tuple[str, ...]],
        started: float,
    ) -> dict[str, Any] | None:
        """Return a deep-copied cached response if one exists, else ``None``."""
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

        definitions, references = _reclassify_definition_like(
            definitions, references, str(self.project_root), symbol
        )

        if not definitions:
            definitions, references = _apply_grep_fallback_defs(
                definitions, references, str(self.project_root), symbol
            )

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
        """Max ``mtime_ns`` across the AST index DB and its WAL/SHM sidecars."""
        assert self.project_root is not None
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
        """Clear the per-symbol cache when the AST index changed (#568)."""
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
        """#568: the advertised inheritance/override lineage."""
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
            if cache is not None:
                cache.close()
        index_mtime_ns = self._index_signature()
        if index_mtime_ns == 0:
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
            "verdict": verdict,
            "agent_summary": agent_summary,
            **({"hierarchy": hierarchy} if hierarchy else {}),
        }

    def _finalize_and_cache_response(
        self,
        response: dict[str, Any],
        cache_key: tuple[str, int, tuple[str, ...]],
        started: float,
        output_format: str,
    ) -> dict[str, Any]:
        """Cache a deep copy, stamp elapsed/from_cache, apply TOON formatting."""
        self._symbol_cache[cache_key] = copy.deepcopy(response)
        self._ast_index_mtime_ns = self._index_signature()

        response["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        response["from_cache"] = False
        if self._dep_graph_built_at is not None:
            response["cache_age_s"] = round(time.time() - self._dep_graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            response["cache_invalidated_reason"] = self._cache_invalidated_reason
        return apply_toon_format_to_response(response, output_format)
