#!/usr/bin/env python3
"""
CodeGraph Full Index MCP Tool — One-shot complete project intelligence.

Runs the entire indexing pipeline in a single call:
  1. AST cache: parse all source files, extract symbols/imports/structure
  2. Call edges: extract function calls and build call graph edges
  3. FTS5: build full-text search index over all symbols
  4. Incremental sync: detect changed/new/deleted files, re-index only changed
  5. Synapse resolution: resolve cross-file callee targets

Returns a unified report with file counts, symbol counts, call edges, and
timing per phase. Agents call this ONCE at session start instead of making
5+ separate tool calls.

CodeGraph parity: equivalent to CodeGraph's "index everything" single command.
"""

from __future__ import annotations

import time
from typing import Any

from ...index_source_snapshot import (
    SourceScopeDescriptor,
    make_source_scope_descriptor,
)
from ...indexing_limits import normalize_index_max_files
from ...indexing_snapshot import (
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
)
from ...utils import setup_logger
from ..utils.auto_index_guard import mark_dirty
from ..utils.error_sanitizer import (
    bounded_safe_error_message,
    sanitize_error_detail,
)
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_ERROR_DETAILS_CAP = 20
_INCREMENTAL_DETAILS_NEXT_STEP = (
    "Run --incremental-sync --format json for uncapped per-file details."
)


def _safe_close_cache(cache: Any | None) -> None:
    """Close an owned cache without masking the primary phase result."""
    if cache is None:
        return
    try:
        cache.close()
    except Exception as exc:
        logger.debug("AST cache close failed (%s)", type(exc).__name__)


def _phase_error(
    exc: BaseException,
    project_root: str | None,
    *,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    error, truncated = bounded_safe_error_message(exc, project_root)
    result: dict[str, Any] = {
        "status": "error",
        "error": error,
        "error_truncated": truncated,
    }
    if elapsed_seconds is not None:
        result["elapsed_seconds"] = elapsed_seconds
    return result


def _bounded_error_details(
    details: Any,
    errors: int,
    project_root: str | None,
    *,
    next_step: str,
) -> dict[str, Any]:
    """Build a deterministic, response-safe summary of per-file errors."""
    detail_items = details if isinstance(details, list) else []
    candidates = [
        sanitize_error_detail(detail, project_root)
        for detail in detail_items
        if isinstance(detail, dict) and detail.get("status") == "error"
    ]
    candidates.sort(
        key=lambda detail: (
            str(detail.get("file", "")),
            str(detail.get("error_type", "")),
            str(
                detail.get(
                    "reason",
                    detail.get("error_message", detail.get("error", "")),
                )
            ),
        )
    )
    total = len(candidates)
    listed = min(total, _ERROR_DETAILS_CAP)
    truncated = total > listed
    summary: dict[str, Any] = {
        "error_details": candidates[:listed],
        "error_details_total": total,
        "error_details_listed": listed,
        "error_details_cap": _ERROR_DETAILS_CAP,
        "error_details_truncated": truncated,
        "unattributed_errors": max(0, errors - total),
    }
    if truncated:
        summary["error_details_next_step"] = next_step
    return summary


def _resolve_exclude_patterns(
    extra_patterns: list[str],
    no_default_excludes: bool,
) -> frozenset[str]:
    """Resolve the one effective scope shared by both indexing phases."""
    from ...cache.indexer import _DEFAULT_EXCLUDE_PATTERNS

    extra = frozenset(pattern.replace("\\", "/") for pattern in extra_patterns)
    if no_default_excludes:
        return extra
    return _DEFAULT_EXCLUDE_PATTERNS | extra


def _candidate_snapshot_report(
    snapshot: IndexCandidateSnapshot,
    ast_phase: dict[str, Any],
    incremental_phase: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile immutable scope metrics with both phase outcomes."""
    ast_changed = set(ast_phase.get("changed_during_run_files", []))
    incremental_changed = set(incremental_phase.get("changed_during_run_files", []))
    changed_files = sorted(ast_changed | incremental_changed)
    detail_by_file = {
        str(detail.get("file", "")): detail
        for detail in (
            list(ast_phase.get("changed_during_run_details", []))
            + list(incremental_phase.get("changed_during_run_details", []))
        )
        if isinstance(detail, dict) and detail.get("file")
    }
    changed_details = [
        detail_by_file[path] for path in changed_files if path in detail_by_file
    ]
    ast_processed = int(ast_phase.get("processed", 0))
    incremental_processed = int(incremental_phase.get("processed", 0))
    selected_paths = {entry.rel_path for entry in snapshot.selected_entries}
    changed_paths = set(changed_files)
    processed = len(selected_paths - changed_paths)
    report: dict[str, Any] = {
        **snapshot.metrics(),
        "processed": processed,
        "changed_during_run": len(changed_files),
        "changed_during_run_files": changed_files,
        "changed_during_run_details": changed_details[:_ERROR_DETAILS_CAP],
        "changed_during_run_details_total": len(changed_details),
        "changed_during_run_details_truncated": (
            len(changed_details) > _ERROR_DETAILS_CAP
        ),
    }
    report["selection_reconciled"] = changed_paths <= selected_paths and (
        snapshot.selected == processed + len(changed_paths)
    )
    report["phase_totals_reconciled"] = snapshot.selected == ast_processed + int(
        ast_phase.get("changed_during_run", 0)
    ) and snapshot.selected == incremental_processed + int(
        incremental_phase.get("changed_during_run", 0)
    )
    return report


class CodeGraphFullIndexTool(BaseMCPTool):
    """MCP Tool for one-shot complete project intelligence indexing."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_full_index",
            "description": (
                "One-shot complete project intelligence index (CodeGraph parity). "
                "Runs AST parse + call edges + FTS5 + incremental sync + "
                "cross-file resolution in a single call. "
                "Agents call this once at session start — all codegraph tools "
                "become instant afterward. "
                "Mode 'full' forces re-index; 'incremental' only processes changes. "
                "No other tool runs the complete indexing pipeline."
            ),
            "inputSchema": self.get_tool_schema(),
            # destructive depending on mode (rebuild/warm/sync write the cache)
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["full", "incremental"],
                    "description": (
                        "'full' forces re-index of all files (slow, thorough); "
                        "'incremental' only processes changed files (fast, default)"
                    ),
                    "default": "incremental",
                },
                "max_files": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Positive maximum files to index; zero is invalid "
                        "(default: 20000)"
                    ),
                    "default": 20000,
                },
                "resolve_synapse": {
                    "type": "boolean",
                    "description": "Run cross-file callee resolution after indexing (default: true)",
                    "default": True,
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "Compute temporal git activation during AST cache indexing. "
                        "Default false keeps large-repo warm-up fast."
                    ),
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
                "exclude_patterns": {
                    "type": "array",
                    "maxItems": 1024,
                    "items": {"type": "string", "maxLength": 65_000},
                    "description": (
                        "Additional fnmatch glob patterns (relative to project root) "
                        'to exclude from indexing. Example: ["tests/golden/corpus_*"]. '
                        "Combined with built-in defaults unless no_default_excludes=true."
                    ),
                    "default": [],
                },
                "no_default_excludes": {
                    "type": "boolean",
                    "description": (
                        "When true, disable the built-in default exclude patterns "
                        "(e.g. tests/golden/corpus_*) and use only the patterns "
                        "supplied in exclude_patterns. Default: false."
                    ),
                    "default": False,
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "incremental")
        if mode not in ("full", "incremental"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'full' or 'incremental'")
        arguments["max_files"] = normalize_index_max_files(arguments.get("max_files"))
        extra_patterns = arguments.get("exclude_patterns", [])
        if not isinstance(extra_patterns, list) or any(
            not isinstance(pattern, str) for pattern in extra_patterns
        ):
            raise ValueError("exclude_patterns must be an array of strings")
        no_default_excludes = arguments.get("no_default_excludes", False)
        if not isinstance(no_default_excludes, bool):
            raise ValueError("no_default_excludes must be a boolean")
        normalized_patterns = sorted(
            {pattern.replace("\\", "/") for pattern in extra_patterns}
        )
        make_source_scope_descriptor(
            no_default_excludes=no_default_excludes,
            exclude_patterns=tuple(normalized_patterns),
            certification_max_files=arguments["max_files"],
        )
        arguments["exclude_patterns"] = normalized_patterns
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "verdict": "ERROR",
                    "error": "project_root not set. Call set_project_path first.",
                },
                arguments.get("output_format", "toon"),
            )

        mode = arguments.get("mode", "incremental")
        max_files = arguments["max_files"]
        resolve_synapse = arguments.get("resolve_synapse", True)
        include_activation = bool(arguments.get("include_activation", False))
        output_format = arguments.get("output_format", "toon")
        extra_patterns: list[str] = list(arguments.get("exclude_patterns", None) or [])
        no_default_excludes: bool = bool(arguments.get("no_default_excludes", False))
        exclude_patterns = _resolve_exclude_patterns(
            extra_patterns,
            no_default_excludes,
        )
        source_scope = make_source_scope_descriptor(
            no_default_excludes=no_default_excludes,
            exclude_patterns=tuple(extra_patterns),
            certification_max_files=max_files,
        )
        t_start = time.monotonic()
        candidate_snapshot = self._build_candidate_snapshot(
            max_files,
            exclude_patterns,
        )

        phases: dict[str, Any] = {}

        if mode == "full":
            mark_dirty(self.project_root)

        ast_phase = self._phase_ast_cache(
            mode == "full",
            max_files,
            include_activation=include_activation,
            exclude_patterns=exclude_patterns,
            candidate_snapshot=candidate_snapshot,
            source_scope=source_scope,
        )
        phases["ast_cache"] = ast_phase
        incremental_phase = self._phase_incremental_sync(
            max_files,
            exclude_patterns,
            candidate_snapshot=candidate_snapshot,
            source_scope=source_scope,
        )
        phases["incremental_sync"] = incremental_phase
        phases["fts5"] = self._phase_fts5_stats()

        if resolve_synapse:
            # A1: the ast_cache phase already ran the complete backfill chain
            # (cross-file + synapse + edge-store refresh + unresolved_refs) via
            # _post_index_backfill. Re-running index_project(resolve_only=True)
            # here repeated the whole O(edges) chain a second time — on large
            # Java repos that doubled backfill time and was a primary stall/OOM
            # cause. Report from the already-computed stats instead of re-running.
            phases["synapse_resolution"] = self._phase_synapse(ast_phase)

        phases["call_edges"] = self._phase_call_edge_stats()

        elapsed = round(time.monotonic() - t_start, 3)

        # #860: propagate phase-level errors to top-level verdict so callers
        # don't receive "success: True / verdict: INFO" when a DB flush failed.
        any_phase_error = any(
            p.get("status") == "error" for p in phases.values() if isinstance(p, dict)
        )
        snapshot_report = _candidate_snapshot_report(
            candidate_snapshot,
            ast_phase,
            incremental_phase,
        )
        snapshot_warning = (
            snapshot_report["changed_during_run"] > 0
            or int(ast_phase.get("backfill_errors", 0)) > 0
            or not snapshot_report["selection_reconciled"]
            or not snapshot_report["phase_totals_reconciled"]
        )
        top_verdict = "WARN" if any_phase_error or snapshot_warning else "INFO"
        stats = self._collect_final_stats(
            stamp_manifest=(
                top_verdict == "INFO" and not candidate_snapshot.truncated_by_max_files
            ),
            source_scope=source_scope,
        )
        manifest_certified = bool(stats.pop("_manifest_certified", False))
        if not manifest_certified or stats.get("manifest_warning") is not None:
            top_verdict = "WARN"
        summary_line = f"codegraph_full_index: completed with {top_verdict.lower()}"

        result: dict[str, Any] = {
            "success": True,
            "verdict": top_verdict,
            "summary_line": summary_line,
            "agent_summary": {
                "verdict": top_verdict,
                "summary_line": summary_line,
            },
            "mode": mode,
            "elapsed_seconds": elapsed,
            "phases": phases,
            "candidate_snapshot": snapshot_report,
            **stats,
        }

        return apply_toon_format_to_response(result, output_format)

    def _build_candidate_snapshot(
        self,
        max_files: int,
        exclude_patterns: frozenset[str],
    ) -> IndexCandidateSnapshot:
        from ...cache.indexer import _walk_source_files
        from ...project_graph import _language_from_ext

        return build_index_candidate_snapshot(
            self.project_root or ".",
            max_files=max_files,
            exclude_patterns=exclude_patterns,
            walk_fn=_walk_source_files,
            language_fn=_language_from_ext,
        )

    def _phase_ast_cache(
        self,
        force: bool,
        max_files: int,
        *,
        include_activation: bool = False,
        exclude_patterns: frozenset[str] | None = None,
        candidate_snapshot: IndexCandidateSnapshot | None = None,
        source_scope: SourceScopeDescriptor | None = None,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        cache: Any | None = None
        try:
            from ...ast_cache import ASTCache

            if exclude_patterns is None:
                exclude_patterns = _resolve_exclude_patterns([], False)

            cache = ASTCache(self.project_root or ".")
            index_kwargs: dict[str, Any] = {
                "max_files": max_files,
                "force": force,
                "include_activation": include_activation,
                "exclude_patterns": exclude_patterns,
            }
            if source_scope is not None:
                index_kwargs["source_scope"] = source_scope
            if candidate_snapshot is not None:
                index_kwargs["candidate_snapshot"] = candidate_snapshot
            result = cache.index_project(**index_kwargs)
            elapsed = round(time.monotonic() - t0, 3)
            indexed = result.get("indexed", 0)
            cached = result.get("cached", 0)
            errors = result.get("errors", 0)
            error_summary = _bounded_error_details(
                result.get("files", []),
                errors,
                str(self.project_root) if self.project_root else None,
                next_step=_INCREMENTAL_DETAILS_NEXT_STEP,
            )
            changed_details = [
                {
                    "file": detail.get("file"),
                    "status": "skipped",
                    "reason": detail.get("reason"),
                }
                for detail in result.get("files", [])
                if isinstance(detail, dict)
                and detail.get("status") == "skipped"
                and "candidate snapshot" in str(detail.get("reason", ""))
            ]
            return {
                "status": (
                    "error"
                    if errors > 0
                    or int(result.get("backfill_errors", 0)) > 0
                    or error_summary["error_details_total"] > 0
                    else "ok"
                ),
                "elapsed_seconds": elapsed,
                "files_indexed": indexed,
                "files_cached": cached,
                "errors": errors,
                "backfill_errors": int(result.get("backfill_errors", 0)),
                "processed": int(result.get("processed", indexed + cached)),
                "changed_during_run": int(result.get("changed_during_run", 0)),
                "changed_during_run_files": sorted(
                    result.get("changed_during_run_files", [])
                ),
                "changed_during_run_details": changed_details,
                "mode_used": result.get("mode_used", "unknown"),
                "activation_enabled": result.get("activation_enabled", False),
                "truncated_by_max_files": bool(
                    result.get("truncated_by_max_files", False)
                ),
                # Surface the backfill counts produced by _post_index_backfill so
                # the synapse_resolution phase can report without re-running (A1).
                "cross_file_backfill": result.get("cross_file_backfill"),
                "synapse_backfill": result.get("synapse_backfill"),
                "unresolved_refs_backfill": result.get("unresolved_refs_backfill"),
                **error_summary,
            }
        except Exception as exc:
            return _phase_error(
                exc,
                str(self.project_root) if self.project_root else None,
                elapsed_seconds=round(time.monotonic() - t0, 3),
            )
        finally:
            _safe_close_cache(cache)

    def _phase_incremental_sync(
        self,
        max_files: int = 20_000,
        exclude_patterns: frozenset[str] | None = None,
        *,
        candidate_snapshot: IndexCandidateSnapshot | None = None,
        source_scope: SourceScopeDescriptor | None = None,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        cache: Any | None = None
        try:
            from ...ast_cache import ASTCache
            from ...incremental_sync import IncrementalSync

            if exclude_patterns is None:
                exclude_patterns = _resolve_exclude_patterns([], False)
            cache = ASTCache(self.project_root or ".")
            sync = IncrementalSync(cache)
            sync_kwargs: dict[str, Any] = {
                "max_files": max_files,
                "exclude_patterns": exclude_patterns,
            }
            if source_scope is not None:
                sync_kwargs["source_scope"] = source_scope
            if candidate_snapshot is not None:
                sync_kwargs["candidate_snapshot"] = candidate_snapshot
            result = sync.sync(**sync_kwargs)
            elapsed = round(time.monotonic() - t0, 3)
            error_summary = _bounded_error_details(
                result.details,
                result.errors,
                str(self.project_root) if self.project_root else None,
                next_step=_INCREMENTAL_DETAILS_NEXT_STEP,
            )
            changed_details = [
                {
                    "file": detail.get("file"),
                    "status": "skipped",
                    "reason": detail.get("reason"),
                }
                for detail in result.details
                if isinstance(detail, dict)
                and detail.get("status") == "skipped"
                and "candidate snapshot" in str(detail.get("reason", ""))
            ]
            # #860: surface DB flush failures — sync catches them into result.errors
            # so they never raise but also must NOT be silently reported as "ok".
            status = (
                "error"
                if result.errors > 0 or error_summary["error_details_total"] > 0
                else "ok"
            )
            return {
                "status": status,
                "elapsed_seconds": elapsed,
                "scanned": result.scanned,
                "new_files": result.new_files,
                "updated_files": result.updated_files,
                "deleted_files": result.deleted_files,
                "unchanged_files": result.unchanged_files,
                "errors": result.errors,
                "processed": result.processed,
                "changed_during_run": result.changed_during_run,
                "changed_during_run_files": result.changed_during_run_files,
                "changed_during_run_details": changed_details,
                "truncated_by_max_files": result.truncated_by_max_files,
                **error_summary,
            }
        except Exception as exc:
            return _phase_error(
                exc,
                str(self.project_root) if self.project_root else None,
                elapsed_seconds=round(time.monotonic() - t0, 3),
            )
        finally:
            _safe_close_cache(cache)

    def _phase_fts5_stats(self) -> dict[str, Any]:
        cache: Any | None = None
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            stats = cache.get_stats()
            return {
                "status": "ok",
                "fts5_available": stats.get("fts5_available", False),
                "fts_indexed_symbols": stats.get("fts_indexed_symbols", 0),
            }
        except Exception as exc:
            return _phase_error(
                exc, str(self.project_root) if self.project_root else None
            )
        finally:
            _safe_close_cache(cache)

    def _phase_synapse(self, ast_phase: dict[str, Any]) -> dict[str, Any]:
        """Report cross-file resolution results.

        A1: cross-file resolution is performed once inside the ast_cache phase
        (``index_project`` -> ``_post_index_backfill``). This phase no longer
        re-runs the backfill chain; it summarizes the counts the ast_cache phase
        already produced. This halves backfill time on large repos and removes
        the duplicate full EdgeStore rewrite that caused the stall/OOM.
        """
        synapse = ast_phase.get("synapse_backfill") or {}
        unresolved = ast_phase.get("unresolved_refs_backfill") or {}
        resolved_edges = 0
        if isinstance(synapse, dict):
            resolved_edges += int(synapse.get("resolved", 0))
        if isinstance(unresolved, dict):
            resolved_edges += int(unresolved.get("resolved", 0))
        backfill_errors = int(ast_phase.get("backfill_errors", 0))
        phase_failed = ast_phase.get("status") == "error" or backfill_errors > 0
        return {
            "status": "error" if phase_failed else "ok",
            "elapsed_seconds": 0.0,
            "resolved_edges": resolved_edges,
            "backfill_errors": backfill_errors,
            "note": "resolved during ast_cache phase (single-pass backfill)",
        }

    def _phase_call_edge_stats(self) -> dict[str, Any]:
        cache: Any | None = None
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            has_edges = cache.has_call_edges()
            stats = cache.get_stats()
            return {
                "status": "ok",
                "has_call_edges": has_edges,
                "total_files": stats.get("total_files", 0),
                "total_symbols": stats.get("total_symbols", 0),
            }
        except Exception as exc:
            return _phase_error(
                exc, str(self.project_root) if self.project_root else None
            )
        finally:
            _safe_close_cache(cache)

    def _collect_final_stats(
        self,
        *,
        stamp_manifest: bool = False,
        source_scope: SourceScopeDescriptor | None = None,
    ) -> dict[str, Any]:
        cache: Any | None = None
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            manifest_warning: str | None = None
            if stamp_manifest:
                from ...index_snapshot_schema import stamp_full_index_manifest

                try:
                    stamp_full_index_manifest(
                        cache.get_conn(), self.project_root or ".", source_scope
                    )
                except Exception:
                    logger.warning(
                        "index snapshot manifest certification failed", exc_info=True
                    )
                    manifest_warning = "INDEX_MANIFEST_CERTIFICATION_FAILED"
                    conn = cache.get_conn()
                    conn.rollback()
                    conn.execute("DELETE FROM ast_index_snapshot_manifest")
                    conn.commit()
            else:
                conn = cache.get_conn()
                conn.execute("DELETE FROM ast_index_snapshot_manifest")
                conn.commit()
            stats = cache.get_stats()
            result = {
                "_manifest_certified": stamp_manifest and manifest_warning is None,
                "total_files": stats.get("total_files", 0),
                "total_symbols": stats.get("total_symbols", 0),
                "by_language": stats.get("by_language", {}),
                "fts5_available": stats.get("fts5_available", False),
                "fts_indexed_symbols": stats.get("fts_indexed_symbols", 0),
            }
            if manifest_warning is not None:
                result["manifest_warning"] = manifest_warning
            return result
        except Exception:
            return {}
        finally:
            _safe_close_cache(cache)
