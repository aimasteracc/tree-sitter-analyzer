#!/usr/bin/env python3
"""CLI dispatchers for cache/index commands: autoindex, full-index, metrics.

These three commands all wrap MCP tools (``codegraph_autoindex``,
``codegraph_full_index``, ``codegraph_metrics``). They live in a single
module because they share the same execution shape — instantiate tool,
build a kwargs dict, ``await tool.execute(...)``, print JSON or TOON.

Keeping them out of :mod:`tree_sitter_analyzer.cli.commands.mcp_commands`
avoids growing the already-large MCP_COMMAND_SPECS table and matches the
pattern set by ``constraint_check_command``: each new "named" command
gets its own dispatcher with explicit kwargs assembly.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

OutputJsonFn = Callable[[dict[str, Any]], None]
OutputErrorFn = Callable[[str], None]


def _project_root(args: Any) -> str:
    return getattr(args, "project_root", None) or os.getcwd()


def _output_format(args: Any) -> str:
    """Map argparse-visible output format to MCP tool format.

    Delegates to :func:`tree_sitter_analyzer.cli.output_format.resolve_mcp_tool_format`
    so the args→tool-format mapping has one source of truth (r37an).
    """
    from tree_sitter_analyzer.cli.output_format import resolve_mcp_tool_format

    return resolve_mcp_tool_format(args)


def _print(result: dict[str, Any], output_format: str) -> None:
    """Write the MCP tool response to stdout in the requested shape."""
    if output_format == "toon":
        print(result.get("toon_content", ""))
    else:
        print(json.dumps(result, indent=2, default=str))


def _exit_code_for(result: dict[str, Any]) -> int:
    return 0 if result.get("success", False) else 1


def _autoindex_payload(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "mode": getattr(args, "autoindex_mode", "status") or "status",
        "max_files": int(getattr(args, "autoindex_max_files", 20_000)),
        "output_format": output_format,
    }


def _full_index_payload(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "mode": getattr(args, "full_index_mode", "incremental") or "incremental",
        "max_files": int(getattr(args, "full_index_max_files", 20_000)),
        "include_activation": bool(
            getattr(args, "full_index_include_activation", False)
        ),
        "output_format": output_format,
    }


def _incremental_sync_payload(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "mode": getattr(args, "incremental_sync_mode", "sync") or "sync",
        "max_files": int(getattr(args, "incremental_sync_max_files", 20_000)),
        "output_format": output_format,
    }


def _knowledge_graph_index_payload(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "mode": getattr(args, "knowledge_graph_index_mode", "update") or "update",
        "backend": getattr(args, "knowledge_graph_backend", "auto") or "auto",
        "max_files": int(getattr(args, "knowledge_graph_max_files", 1_000_000)),
        "max_nodes": int(getattr(args, "knowledge_graph_max_nodes", 0)),
        "max_edges": int(getattr(args, "knowledge_graph_max_edges", 0)),
        "include_docs": not bool(getattr(args, "knowledge_graph_no_docs", False)),
        "output_format": output_format,
    }


def _knowledge_graph_serve_payload(args: Any) -> dict[str, Any]:
    return {
        "project_root": _project_root(args),
        "host": getattr(args, "knowledge_graph_host", "127.0.0.1") or "127.0.0.1",
        "port": int(getattr(args, "knowledge_graph_port", 8765)),
        "open_browser": not bool(getattr(args, "knowledge_graph_no_browser", False)),
    }


def _metrics_payload(args: Any, output_format: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"output_format": output_format}
    sections = getattr(args, "codegraph_metrics_sections", None)
    if sections:
        payload["sections"] = list(sections)
    return payload


def run_autoindex(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--autoindex`` → ``codegraph_autoindex`` MCP tool."""
    try:
        from ...mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--autoindex failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphAutoIndexTool(project_root=_project_root(args))
    try:
        result = asyncio.run(tool.execute(_autoindex_payload(args, output_format)))
    except Exception as exc:  # noqa: BLE001
        output_error(f"--autoindex failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_full_index(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--full-index`` → ``codegraph_full_index`` MCP tool."""
    try:
        from ...mcp.tools.full_index_tool import CodeGraphFullIndexTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--full-index failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphFullIndexTool(project_root=_project_root(args))
    try:
        result = asyncio.run(tool.execute(_full_index_payload(args, output_format)))
    except Exception as exc:  # noqa: BLE001
        output_error(f"--full-index failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_incremental_sync(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--incremental-sync`` → ``codegraph_incremental_sync`` MCP tool."""
    try:
        from ...mcp.tools.incremental_sync_tool import CodeGraphIncrementalSyncTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--incremental-sync failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphIncrementalSyncTool(project_root=_project_root(args))
    try:
        result = asyncio.run(
            tool.execute(_incremental_sync_payload(args, output_format))
        )
    except Exception as exc:  # noqa: BLE001
        output_error(f"--incremental-sync failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_knowledge_graph_index(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--knowledge-graph-index`` → ``codegraph_knowledge_index``."""
    try:
        from ...mcp.tools.knowledge_graph_tool import CodeGraphKnowledgeIndexTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--knowledge-graph-index failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphKnowledgeIndexTool(project_root=_project_root(args))
    try:
        result = asyncio.run(
            tool.execute(_knowledge_graph_index_payload(args, output_format))
        )
    except Exception as exc:  # noqa: BLE001
        output_error(f"--knowledge-graph-index failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_knowledge_graph_serve(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--knowledge-graph-serve`` → local HTTP service."""
    try:
        from ...knowledge_graph.server import serve_knowledge_graph
    except Exception as exc:  # pragma: no cover  # noqa: BLE001
        output_error(f"--knowledge-graph-serve failed to import service: {exc}")
        return 1

    payload = _knowledge_graph_serve_payload(args)
    try:
        serve_knowledge_graph(**payload)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        output_error(f"--knowledge-graph-serve failed: {exc}")
        return 1
    return 0


def run_knowledge_graph_watch(args: Any) -> int:
    """Dispatch ``--knowledge-graph-watch`` → resident watch daemon."""
    from ...ast_cache import ASTCache
    from ...file_watcher import FileWatcherDaemon
    from ...knowledge_graph.builder import KnowledgeGraphBuilder
    from ...knowledge_graph.stores import LadybugKnowledgeGraphStore

    project_root = _project_root(args)

    # Perform initial indexing
    cache = ASTCache(project_root)
    cache.index_project()
    cache.close()

    # Build initial knowledge graph
    builder = KnowledgeGraphBuilder(project_root)
    snapshot = builder.build(include_docs=True)
    lb_store = LadybugKnowledgeGraphStore(project_root)
    lb_store.write(snapshot)

    # Define on_sync callback
    def on_sync(sync_result: dict) -> None:
        details = sync_result.get("details", [])
        if not details:
            return
        changed = [
            d["file"] for d in details if d.get("considered") in ("indexed", "updated")
        ]
        deleted = [d["file"] for d in details if d.get("considered") == "deleted"]
        if not changed and not deleted:
            return
        try:
            for fp in deleted:
                lb_store.delete_by_file(fp)
            if changed:
                for fp in changed:
                    lb_store.delete_by_file(fp)
                delta = builder.build_delta(changed)
                lb_store.patch(list(delta.nodes), [], list(delta.edges), [])
        except Exception:
            pass

    # Start daemon
    backend = getattr(args, "knowledge_graph_watch_backend", "poll") or "poll"
    daemon = FileWatcherDaemon(cache, backend=backend, on_sync=on_sync)
    daemon.start()
    print(f"TSA knowledge graph watch started: {backend} backend", flush=True)
    print("Press Ctrl-C to stop.", flush=True)

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        daemon.stop()
        return 0


def run_codegraph_metrics(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--codegraph-metrics`` → ``codegraph_metrics`` MCP tool."""
    try:
        from ...mcp.tools.codegraph_metrics_tool import CodeGraphMetricsTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--codegraph-metrics failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphMetricsTool(project_root=_project_root(args))
    try:
        result = asyncio.run(tool.execute(_metrics_payload(args, output_format)))
    except Exception as exc:  # noqa: BLE001
        output_error(f"--codegraph-metrics failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)
