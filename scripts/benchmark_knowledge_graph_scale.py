#!/usr/bin/env python3
"""Benchmark synthetic Java-shaped knowledge graph materialization."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeEdge,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
    LadybugKnowledgeGraphStore,
)
from tree_sitter_analyzer.knowledge_graph.query import open_query_backend


def main() -> int:
    args = _parser().parse_args()
    workspace = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp())
    if args.output_dir and workspace.exists() and args.clean:
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    snapshot = build_java_snapshot(
        files=args.files,
        packages=args.packages,
        methods_per_file=args.methods_per_file,
    )
    build_seconds = time.perf_counter() - started

    writes: dict[str, Any] = {}
    if not args.no_json:
        writes["json"] = _timed(
            lambda: JsonKnowledgeGraphStore(str(workspace)).write(snapshot)
        )
    if not args.no_ladybug:
        writes["ladybug"] = _timed(
            lambda: LadybugKnowledgeGraphStore(str(workspace)).write(snapshot)
        )

    query_result: dict[str, Any] = {}
    if not args.no_ladybug:
        query_result = _query_smoke(str(workspace))

    result = {
        "workspace": str(workspace),
        "files": args.files,
        "packages": args.packages,
        "methods_per_file": args.methods_per_file,
        "snapshot": snapshot.stats,
        "build_seconds": round(build_seconds, 3),
        "writes": writes,
        "query": query_result,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_java_snapshot(
    *,
    files: int,
    packages: int,
    methods_per_file: int,
) -> KnowledgeGraphSnapshot:
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    package_ids = [f"package:com.example.p{i:04d}" for i in range(packages)]
    for package_id in package_ids:
        nodes.append(
            KnowledgeNode(
                id=package_id,
                kind="package",
                label=package_id.removeprefix("package:"),
                language="java",
            )
        )
    for i in range(files):
        package_id = package_ids[i % packages]
        package_path = package_id.removeprefix("package:").replace(".", "/")
        file_path = f"src/main/java/{package_path}/Service{i:06d}.java"
        file_id = f"file:{file_path}"
        class_id = f"{file_path}:Service{i:06d}:1"
        nodes.append(
            KnowledgeNode(
                id=file_id,
                kind="file",
                label=file_path,
                file_path=file_path,
                language="java",
            )
        )
        nodes.append(
            KnowledgeNode(
                id=class_id,
                kind="class",
                label=f"Service{i:06d}",
                file_path=file_path,
                language="java",
                metadata={"line": 1},
            )
        )
        edges.append(_edge(package_id, file_id, "contains", i))
        edges.append(_edge(file_id, class_id, "contains", i))
        previous_method_id = ""
        for method_idx in range(methods_per_file):
            line = 10 + method_idx * 5
            method_id = f"{file_path}:method{method_idx}: {line}".replace(": ", ":")
            nodes.append(
                KnowledgeNode(
                    id=method_id,
                    kind="method",
                    label=f"method{method_idx}",
                    file_path=file_path,
                    language="java",
                    metadata={"line": line},
                )
            )
            edges.append(_edge(class_id, method_id, "contains", i * 10 + method_idx))
            if previous_method_id:
                edges.append(
                    _edge(
                        previous_method_id,
                        method_id,
                        "calls",
                        i * 10 + method_idx,
                        {"callee_name": f"method{method_idx}"},
                    )
                )
            previous_method_id = method_id
        next_i = (i + 1) % files
        next_package = (
            package_ids[next_i % packages]
            .removeprefix("package:")
            .replace(
                ".",
                "/",
            )
        )
        target_file = f"src/main/java/{next_package}/Service{next_i:06d}.java"
        edges.append(_edge(file_id, f"file:{target_file}", "imports", i))
        edges.append(
            _edge(
                previous_method_id,
                f"{target_file}:method0:10",
                "calls",
                i,
                {"callee_name": "method0"},
            )
        )
    stats = {
        "project_root": "<synthetic-java>",
        "indexed_files": files,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_kinds": _counts(node.kind for node in nodes),
        "edge_kinds": _counts(edge.kind for edge in edges),
        "truncated": False,
        "max_nodes": 0,
        "max_edges": 0,
    }
    return KnowledgeGraphSnapshot(nodes=nodes, edges=edges, stats=stats)


def _query_smoke(project_root: str) -> dict[str, Any]:
    backend = open_query_backend(project_root)
    started = time.perf_counter()
    graph = backend.graph(lod="symbol", focus=None, max_nodes=1200, max_edges=3600)
    graph_seconds = time.perf_counter() - started
    started = time.perf_counter()
    search = backend.search("Service000999", limit=5)
    search_seconds = time.perf_counter() - started
    node_id = "src/main/java/com/example/p0000/Service000000.java:method0:10"
    started = time.perf_counter()
    node = backend.node(node_id, limit=20)
    node_seconds = time.perf_counter() - started
    started = time.perf_counter()
    neighborhood = backend.neighborhood(
        node_id,
        depth=2,
        edge_kind="calls",
        max_nodes=200,
        max_edges=500,
    )
    neighborhood_seconds = time.perf_counter() - started
    return {
        "backend": backend.backend_name,
        "graph_seconds": round(graph_seconds, 3),
        "search_seconds": round(search_seconds, 3),
        "node_seconds": round(node_seconds, 3),
        "neighborhood_seconds": round(neighborhood_seconds, 3),
        "graph_nodes": graph["stats"].get("export_node_count"),
        "graph_edges": graph["stats"].get("export_edge_count"),
        "search_matches": len(search.get("matches", [])),
        "node_found": node.get("found"),
        "neighborhood_nodes": neighborhood["stats"].get("export_node_count"),
        "neighborhood_edges": neighborhood["stats"].get("export_edge_count"),
    }


def _edge(
    source: str,
    target: str,
    kind: str,
    seed: int,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeEdge:
    return KnowledgeEdge(
        id=f"edge:{kind}:{seed}:{abs(hash((source, target, kind))) & 0xFFFFFFFFFFFF:x}",
        source=source,
        target=target,
        kind=kind,
        line=seed % 200 + 1,
        provenance="synthetic-java",
        metadata=metadata or {},
    )


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _timed(fn: Any) -> dict[str, Any]:
    started = time.perf_counter()
    result = fn()
    result["total_seconds"] = round(time.perf_counter() - started, 3)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=50_000)
    parser.add_argument("--packages", type=int, default=500)
    parser.add_argument("--methods-per-file", type=int, default=2)
    parser.add_argument("--output-dir")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--no-json", action="store_true")
    parser.add_argument("--no-ladybug", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
