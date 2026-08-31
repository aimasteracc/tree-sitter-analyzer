"""Handlers for the RFC-0027 §L7/§L8 capability flags.

Three capabilities that were built, tested, and reachable from nothing:

===================  ==================  =============================
CLI flag             MCP twin            what it answers
===================  ==================  =============================
``--project-card``   project action=card  "what is this project?"
``--plan-rename``    edit action=plan_rename  "what would this rename touch?"
``--refactor-queue`` health action=refactor_queue  "what do I clean up first?"
===================  ==================  =============================

Each handler routes through the *same facade* the MCP surface uses, so parity
is structural rather than duplicated. ``--plan-rename`` therefore inherits the
facade's ``PLAN_RENAME_IS_PREVIEW_ONLY`` guard for free: the CLI has no way to
express an apply because there is no flag for it and the facade would reject
the argument anyway.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a circular import; only needed for annotations
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext


def _ensure_tsa_config(project_root: str) -> None:
    """Write .tsa/config.json if it does not already exist."""
    import json
    from pathlib import Path

    tsa_dir = Path(project_root) / ".tsa"
    tsa_dir.mkdir(exist_ok=True)
    config_path = tsa_dir / "config.json"
    if config_path.exists():
        return
    config = {
        "severity_thresholds": {"critical": 400, "review": 100},
        "default_depth": 3,
        "default_top_n": 20,
        "default_page_size": 20,
        "supported_extensions": [".py", ".ts", ".js", ".java", ".go", ".rs", ".c", ".cpp"],
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _write_index_meta(project_root: str, files_indexed: int, languages: list[str]) -> None:
    """Write .tsa/index-meta.json after a successful --hotspot run."""
    import datetime
    import importlib.metadata
    import json
    from pathlib import Path

    tsa_dir = Path(project_root) / ".tsa"
    tsa_dir.mkdir(exist_ok=True)

    try:
        version = importlib.metadata.version("tree-sitter-analyzer")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0+dev"

    meta = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files_indexed": files_indexed,
        "languages": languages,
        "tsa_version": version,
    }
    (tsa_dir / "index-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _execute_facade(
    facade: Any,
    tool_args: dict[str, Any],
    output_format: str,
    label: str,
    context: SpecialCommandContext,
) -> int:
    """Run one facade action and emit its payload. Same shape as nav's helper."""
    import asyncio

    try:
        result: dict[str, Any] = asyncio.run(facade.execute(tool_args))
    except Exception as exc:  # noqa: BLE001 — CLI boundary: never traceback
        context.output_error(f"{label} failed: {exc}")
        return 1
    context.output_json(result)
    return 0 if result.get("success", False) else 1


def _handle_hotspot(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    import sys

    from tree_sitter_analyzer.dependency_matrix import DependencyMatrix
    from tree_sitter_analyzer.hotspot_analyzer import (
        build_alias_ca_map,
        build_ca_from_source_imports,
        build_ca_raw_map,
        build_heatmap_map,
        build_import_edges_from_source,
        compute_scores,
        heatmaps_from_project_analysis,
    )
    from tree_sitter_analyzer.output_schema import (
        AliasDiffSummary,
        HotspotResult,
        SubgraphSummary,
        paginate,
        result_to_dict,
    )

    project_root = getattr(args, "project_root", None) or os.getcwd()
    top_n = getattr(args, "hotspot_top_n", 20)
    page = getattr(args, "page", 1)
    page_size = min(getattr(args, "page_size", 20), 100)
    show_alias_diff = getattr(args, "hotspot_show_alias_diff", False)
    trace_from = getattr(args, "trace_from", None)
    if trace_from is not None:
        trace_from = trace_from.replace("\\", "/")
    depth = getattr(args, "depth", 3)

    # --- Argument validation ---
    if top_n < 1:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="invalid_argument",
            error_category="configuration", recovery_hint="fix_argument",
            message="Invalid value for --hotspot-top-n: must be >= 1",
        )))
        return 1
    top_n = min(top_n, 200)
    if page < 1:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="invalid_argument",
            error_category="configuration", recovery_hint="fix_argument",
            message="Invalid value for --page: must be >= 1",
        )))
        return 1
    if page_size < 1:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="invalid_argument",
            error_category="configuration", recovery_hint="fix_argument",
            message="Invalid value for --page-size: must be >= 1",
        )))
        return 1
    if depth < 1:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="invalid_argument",
            error_category="configuration", recovery_hint="fix_argument",
            message="Invalid value for --depth: must be 1-5",
        )))
        return 1
    if depth > 5:
        print(f"WARNING: --depth {depth} exceeds max (5); capping at 5", file=sys.stderr)
        depth = 5

    # --- Write .tsa/config.json ---
    _ensure_tsa_config(project_root)

    # --- Build DependencyMatrix ---
    dm = DependencyMatrix(project_root)
    try:
        dm.build()
    except FileNotFoundError:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="index_not_built",
            error_category="state", recovery_hint="fix_then_retry",
            message="Index not found — run 'tsa --ast-cache . --ast-cache-mode index' first, then retry --hotspot",
        )))
        return 1
    except OSError:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="index_build_error",
            error_category="transient", recovery_hint="retry",
            message="Transient I/O error reading index — retry should succeed",
        )))
        return 1
    except Exception:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="index_not_built",
            error_category="state", recovery_hint="fix_then_retry",
            message="Index not found — run 'tsa --ast-cache . --ast-cache-mode index' first, then retry --hotspot",
        )))
        return 1

    # --- Heatmap data ---
    try:
        heatmap_files = heatmaps_from_project_analysis(project_root)
    except TimeoutError:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="parse_timeout",
            error_category="transient", recovery_hint="retry",
            message="File parse timeout — transient, retry should succeed",
        )))
        return 1
    except OSError:
        context.output_json(result_to_dict(HotspotResult(
            success=False, error="fs_busy",
            error_category="transient", recovery_hint="retry",
            message="Transient I/O error — retry should succeed",
        )))
        return 1

    ca_map = build_ca_raw_map(dm)
    _known_files: list[str] | None = None

    # If DependencyMatrix returned no data (cache not built), fall back to
    # regex-based source parsing. Scan ALL project Python files so that
    # imports from tests/, scripts/, etc. are counted — not just heatmap files.
    # Also build import_edges for BFS (P5) and alias Ca (P3).
    if not ca_map or not dm._import_edges:
        import os as _os

        from tree_sitter_analyzer.complexity_heatmap import _collect_source_files
        all_py = _collect_source_files(project_root, "python", None, 5000)
        _known_files = [
            _os.path.relpath(fp, project_root).replace("\\", "/")
            for fp, _ in all_py
        ]
        if not ca_map:
            target_files = [fh.file.replace("\\", "/") for fh in heatmap_files]
            ca_map = build_ca_from_source_imports(project_root, _known_files, target_files)
        if not dm._import_edges:
            dm._import_edges = build_import_edges_from_source(project_root, _known_files)

    heatmap_map = build_heatmap_map(heatmap_files)

    # --- Alias-aware Ca (P3) ---
    # Pass _known_files when available to avoid expensive rglob on large repos
    alias_ca_map = build_alias_ca_map(ca_map, dm._import_edges, project_root, _known_files)

    # --- BFS subgraph (P5: trace_from != None) ---
    reachable = None
    subgraph_summary = None
    total_project_files = len(set(ca_map) | set(heatmap_map))

    if trace_from is not None:
        from tree_sitter_analyzer.subgraph_traverser import get_subgraph
        reachable = get_subgraph(dm, trace_from, depth)
        if reachable is None:
            # Isolated file: no imports, no importers — still a valid entry at hop 0
            if trace_from in heatmap_map:
                reachable = {trace_from: 0}
            else:
                context.output_json(result_to_dict(HotspotResult(
                    success=False, error="entry_point_not_found",
                    error_category="data", recovery_hint="try_alternative",
                    message=(
                        f"Entry point not found: {trace_from} — "
                        "try '--trace-from src/' or check path with 'tsa health'"
                    ),
                )))
                return 1
        subgraph_summary = SubgraphSummary(
            entry_point=trace_from,
            depth=depth,
            files_in_subgraph=len(reachable),
            total_project_files=total_project_files,
        )

    # --- Score & paginate ---
    ranked = compute_scores(
        ca_map=ca_map,
        heatmap_map=heatmap_map,
        alias_ca_map=alias_ca_map,
        reachable=reachable,
        top_n=top_n,
        show_alias_diff=show_alias_diff,
    )
    page_entries, meta = paginate(ranked, page, page_size)

    n_critical = sum(1 for e in ranked if e.severity == "CRITICAL")
    n_review = sum(1 for e in ranked if e.severity == "REVIEW")
    verdict = "CRITICAL" if n_critical > 0 else ("REVIEW" if n_review > 0 else "OK")
    summary_line = (
        f"hotspot: top={min(top_n, len(ranked))} files "
        f"CRITICAL={n_critical} REVIEW={n_review} OK={len(ranked)-n_critical-n_review}"
    )
    result = HotspotResult(
        success=True,
        metadata=meta,
        threshold={"critical": 400, "review": 100},
        results=page_entries,
        subgraph_summary=subgraph_summary,
        summary_line=summary_line,
        verdict=verdict,
        agent_summary={"summary_line": summary_line, "verdict": verdict},
    )
    if not ranked:
        result.message = "No files exceed CRITICAL or REVIEW threshold — codebase is in good shape"

    # --- Alias gap summary (P3) ---
    if show_alias_diff:
        gaps = sum(1 for f in alias_ca_map if alias_ca_map[f] > ca_map.get(f, 0))
        result.alias_gap_summary = AliasDiffSummary(
            files_with_alias_gap=gaps,
            total_files=len(set(ca_map) | set(heatmap_map)),
        )

    # --- Write index-meta.json (P6) ---
    if result.success:
        langs = list({fh.language for fh in heatmap_files if fh.language})
        _write_index_meta(project_root, len(heatmap_files), sorted(langs))

    context.output_json(result_to_dict(result))
    return 0


def _handle_project_card(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    from tree_sitter_analyzer.mcp.tools.project_facade import build_project_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_project_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {"action": "card", "output_format": output_format},
        output_format,
        "--project-card",
        context,
    )


def _handle_plan_rename(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    new_name = getattr(args, "plan_rename_to", None)
    if not new_name:
        context.output_error("--plan-rename requires --plan-rename-to NEW_NAME")
        return 1

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_edit_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {
            "action": "plan_rename",
            "symbol": getattr(args, "plan_rename", None),
            "new_name": new_name,
            "output_format": output_format,
        },
        output_format,
        "--plan-rename",
        context,
    )


def _handle_refactor_queue(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_health_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {
            "action": "refactor_queue",
            "top_n": getattr(args, "refactor_queue_top_n", 5),
            "output_format": output_format,
        },
        output_format,
        "--refactor-queue",
        context,
    )


def handle_capability_actions(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Dispatch ``--project-card`` / ``--plan-rename`` / ``--refactor-queue``."""
    output_format = getattr(args, "output_format", "json") or "json"

    if getattr(args, "project_card", False):
        return _handle_project_card(args, context, output_format)
    if getattr(args, "plan_rename", None):
        return _handle_plan_rename(args, context, output_format)
    if getattr(args, "refactor_queue", False):
        return _handle_refactor_queue(args, context, output_format)
    if getattr(args, "hotspot", False):
        return _handle_hotspot(args, context, output_format)
    return None
