#!/usr/bin/env python3
"""Benchmark real Java corpus indexing through the knowledge graph pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.knowledge_graph.query import open_query_backend
from tree_sitter_analyzer.mcp.tools.knowledge_graph_tool import (
    CodeGraphKnowledgeIndexTool,
)


def main() -> int:
    args = _parser().parse_args()
    if args.files < 1:
        raise SystemExit("--files must be >= 1")
    if args.packages < 1:
        raise SystemExit("--packages must be >= 1")
    if args.methods_per_file < 1:
        raise SystemExit("--methods-per-file must be >= 1")

    workspace = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp())
    result = run_end_to_end(
        workspace=workspace,
        files=args.files,
        packages=args.packages,
        methods_per_file=args.methods_per_file,
        backend=args.backend,
        clean=args.clean,
        include_docs=not args.no_docs,
        max_files=args.max_files,
        query_max_nodes=args.query_max_nodes,
        query_max_edges=args.query_max_edges,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def run_end_to_end(
    *,
    workspace: Path,
    files: int,
    packages: int,
    methods_per_file: int,
    backend: str,
    clean: bool,
    include_docs: bool,
    max_files: int,
    query_max_nodes: int,
    query_max_edges: int,
) -> dict[str, Any]:
    if clean and workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()
    generated = _timed(
        lambda: create_java_corpus(
            workspace,
            files=files,
            packages=packages,
            methods_per_file=methods_per_file,
        )
    )
    index_limit = max_files if max_files > 0 else files + 100
    indexed = _timed(
        lambda: asyncio.run(
            _build_knowledge_index(
                workspace,
                backend=backend,
                max_files=index_limit,
                include_docs=include_docs,
            )
        )
    )
    indexed["result"] = _compact_index_result(indexed["result"])
    query = _query_smoke(
        workspace,
        max_nodes=query_max_nodes,
        max_edges=query_max_edges,
    )
    return {
        "workspace": str(workspace),
        "files": files,
        "packages": packages,
        "methods_per_file": methods_per_file,
        "generated": generated,
        "index": indexed,
        "query": query,
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "notes": [
            "This measures real Java source parsing through ASTCache, SQLite, knowledge graph materialization, and the selected graph sidecar.",
            "It does not compile Java; it validates the analyzer/indexer path used by TSA.",
        ],
    }


def create_java_corpus(
    workspace: Path,
    *,
    files: int,
    packages: int,
    methods_per_file: int,
) -> dict[str, Any]:
    source_root = workspace / "src" / "main" / "java"
    source_root.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        package_name = _package_name(index, packages)
        package_dir = source_root / Path(package_name.replace(".", "/"))
        package_dir.mkdir(parents=True, exist_ok=True)
        java_file = package_dir / f"Service{index:06d}.java"
        java_file.write_text(
            render_java_source(
                index,
                files=files,
                packages=packages,
                methods_per_file=methods_per_file,
            ),
            encoding="utf-8",
        )
    return {
        "source_root": str(source_root),
        "files_written": files,
        "bytes": sum(path.stat().st_size for path in source_root.rglob("*.java")),
    }


def render_java_source(
    index: int,
    *,
    files: int,
    packages: int,
    methods_per_file: int,
) -> str:
    package_name = _package_name(index, packages)
    next_index = (index + 1) % files
    next_package = _package_name(next_index, packages)
    class_name = f"Service{index:06d}"
    next_class = f"Service{next_index:06d}"
    imports = (
        ""
        if next_package == package_name
        else f"import {next_package}.{next_class};\n\n"
    )
    methods: list[str] = []
    for method_index in range(methods_per_file):
        if method_index == 0:
            body = f"return value + {index % 97};"
        elif method_index == methods_per_file - 1:
            body = (
                f"return method{method_index - 1}(value) + "
                f"new {next_class}().method0(value);"
            )
        else:
            body = f"return method{method_index - 1}(value) + {method_index};"
        methods.append(
            "    public int method"
            f"{method_index}(int value) {{\n"
            f"        {body}\n"
            "    }\n"
        )
    return (
        f"package {package_name};\n\n"
        f"{imports}"
        f"public class {class_name} {{\n" + "\n".join(methods) + "}\n"
    )


async def _build_knowledge_index(
    workspace: Path,
    *,
    backend: str,
    max_files: int,
    include_docs: bool,
) -> dict[str, Any]:
    tool = CodeGraphKnowledgeIndexTool(project_root=str(workspace))
    return await tool.execute(
        {
            "mode": "build",
            "backend": backend,
            "max_files": max_files,
            "max_nodes": 0,
            "max_edges": 0,
            "include_docs": include_docs,
            "output_format": "json",
        }
    )


def _query_smoke(
    workspace: Path,
    *,
    max_nodes: int,
    max_edges: int,
) -> dict[str, Any]:
    backend = open_query_backend(str(workspace))
    graph = _timed(
        lambda: backend.graph(
            lod="file",
            focus=None,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
    )
    search = _timed(lambda: backend.search("Service000000", limit=20))
    focus_id = _select_focus_node(search["result"])
    node: dict[str, Any] = {"result": {"found": False}, "total_seconds": 0.0}
    neighborhood: dict[str, Any] = {"result": {}, "total_seconds": 0.0}
    if focus_id:
        node = _timed(lambda: backend.node(focus_id, limit=20))
        neighborhood = _timed(
            lambda: backend.neighborhood(
                focus_id,
                depth=2,
                edge_kind="calls",
                max_nodes=min(max_nodes, 500),
                max_edges=min(max_edges, 1500),
            )
        )
    graph_result = graph["result"]
    neighborhood_result = neighborhood["result"]
    return {
        "backend": backend.backend_name,
        "graph_seconds": graph["total_seconds"],
        "graph_nodes": graph_result.get("stats", {}).get("export_node_count"),
        "graph_edges": graph_result.get("stats", {}).get("export_edge_count"),
        "search_seconds": search["total_seconds"],
        "search_matches": len(search["result"].get("matches", [])),
        "focus_id": focus_id,
        "node_seconds": node["total_seconds"],
        "node_found": node["result"].get("found"),
        "neighborhood_seconds": neighborhood["total_seconds"],
        "neighborhood_nodes": neighborhood_result.get("stats", {}).get(
            "export_node_count"
        ),
        "neighborhood_edges": neighborhood_result.get("stats", {}).get(
            "export_edge_count"
        ),
    }


def _select_focus_node(search_result: dict[str, Any]) -> str:
    matches = search_result.get("matches", [])
    for method_name in ("method2", "method1", "method0"):
        for node in matches:
            if node.get("kind") == "method" and method_name in str(node.get("id", "")):
                return str(node.get("id", ""))
    for kind in ("method", "class", "symbol", "file"):
        for node in matches:
            if node.get("kind") == kind:
                return str(node.get("id", ""))
    if matches:
        return str(matches[0].get("id", ""))
    return ""


def _package_name(index: int, packages: int) -> str:
    return f"com.example.p{index % packages:04d}"


def _compact_index_result(result: dict[str, Any]) -> dict[str, Any]:
    sync = {
        key: value
        for key, value in result.get("sync", {}).items()
        if key not in {"details", "files", "new", "updated", "deleted"}
    }
    compact = {
        key: result.get(key)
        for key in (
            "success",
            "verdict",
            "mode",
            "backend",
            "effective_backend",
            "graph",
            "writes",
        )
        if key in result
    }
    compact["sync"] = sync
    return compact


def _timed(fn: Any) -> dict[str, Any]:
    started = time.perf_counter()
    result = fn()
    return {"result": result, "total_seconds": round(time.perf_counter() - started, 3)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--packages", type=int, default=100)
    parser.add_argument("--methods-per-file", type=int, default=3)
    parser.add_argument("--output-dir")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--backend",
        choices=["auto", "json", "ladybug", "hybrid"],
        default="auto",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="ASTCache full-build cap; 0 means files + 100.",
    )
    parser.add_argument("--query-max-nodes", type=int, default=20000)
    parser.add_argument("--query-max-edges", type=int, default=80000)
    parser.add_argument("--no-docs", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
