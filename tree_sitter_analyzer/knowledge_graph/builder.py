"""Build whole-project knowledge graph snapshots from existing TSA indexes."""

from __future__ import annotations

import glob
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..ast_cache import ASTCache
from ..doc_sync import extract_file_refs
from ..graph.edge_store import file_node, parse_node_id, symbol_node
from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode

_SOURCE_EDGE_KINDS = (
    "calls",
    "imports",
    "extends",
    "implements",
    "references",
    "contains",
    "overrides",
)
_DEFAULT_DOC_PATTERNS = ("**/*.md",)
_DEFAULT_MAX_NODES = 50_000
_DEFAULT_MAX_EDGES = 100_000


class KnowledgeGraphBuilder:
    """Read ASTCache/EdgeStore/Markdown refs and emit a bounded graph snapshot."""

    def __init__(self, project_root: str) -> None:
        self.project_root = os.path.abspath(project_root)

    def build(
        self,
        *,
        level: str = "file",
        focus: str | None = None,
        include_docs: bool = True,
        include_symbols: bool = True,
        max_nodes: int = _DEFAULT_MAX_NODES,
        max_edges: int = _DEFAULT_MAX_EDGES,
        doc_patterns: list[str] | None = None,
    ) -> KnowledgeGraphSnapshot:
        """Build a graph snapshot at package/file/symbol detail.

        ``level=package`` groups files by package/directory and is the safe
        whole-repo overview for very large Java trees. ``level=file`` is the
        Obsidian-style file/doc graph. ``level=symbol`` includes function/class
        nodes plus calls/inheritance/imports.
        """

        if level not in {"package", "file", "symbol"}:
            raise ValueError("level must be one of: package, file, symbol")
        if max_nodes < 1:
            raise ValueError("max_nodes must be a positive integer")
        if max_edges < 1:
            raise ValueError("max_edges must be a positive integer")

        cache = ASTCache(self.project_root)
        try:
            nodes: dict[str, KnowledgeNode] = {}
            edges: dict[str, KnowledgeEdge] = {}
            rows = self._read_ast_rows(cache)

            for row in rows:
                rel_path = row["file_path"]
                if focus and focus not in rel_path:
                    continue
                self._add_package_and_file_nodes(nodes, edges, rel_path, row)
                if include_symbols:
                    self._add_symbol_nodes(nodes, edges, rel_path, row)

            self._add_symbol_edges(cache, nodes, edges, focus=focus)
            self._add_file_edges(cache, nodes, edges, focus=focus)
            self._add_package_edges(cache, nodes, edges, focus=focus)

            if include_docs:
                self._add_doc_links(
                    nodes, edges, doc_patterns or list(_DEFAULT_DOC_PATTERNS), focus
                )

            return self._bounded_snapshot(nodes, edges, level, max_nodes, max_edges)
        finally:
            cache.close()

    def _read_ast_rows(self, cache: ASTCache) -> list[dict[str, Any]]:
        conn = cache.get_conn()
        try:
            rows = conn.execute(
                "SELECT file_path, language, file_size, content_hash, symbols_json, imports_json "
                "FROM ast_index ORDER BY file_path"
            ).fetchall()
        except Exception:
            return []
        return [dict(row) for row in rows]

    def _add_package_and_file_nodes(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        rel_path: str,
        row: dict[str, Any],
    ) -> None:
        package = _package_for_file(rel_path)
        package_id = f"package:{package}"
        nodes.setdefault(
            package_id,
            KnowledgeNode(
                id=package_id,
                label=package,
                kind="package",
                package=package,
                metadata={"source": "ast_cache"},
            ),
        )
        file_id = file_node(rel_path)
        nodes[file_id] = KnowledgeNode(
            id=file_id,
            label=Path(rel_path).name,
            kind="file",
            file_path=rel_path,
            language=str(row.get("language") or ""),
            package=package,
            metadata={
                "file_size": int(row.get("file_size") or 0),
                "content_hash": str(row.get("content_hash") or ""),
            },
        )
        edge = _edge(package_id, file_id, "contains", "ast_cache")
        edges[edge.id] = edge

    def _add_symbol_nodes(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        rel_path: str,
        row: dict[str, Any],
    ) -> None:
        try:
            symbols = json.loads(row.get("symbols_json") or "{}").get("symbols", [])
        except (TypeError, json.JSONDecodeError):
            symbols = []
        file_id = file_node(rel_path)
        package = _package_for_file(rel_path)
        for sym in symbols:
            if not isinstance(sym, dict):
                continue
            name = str(sym.get("name") or "")
            if not name:
                continue
            line = _as_int_or_none(sym.get("line"))
            node_id = symbol_node(rel_path, name, line)
            kind = str(sym.get("kind") or "symbol")
            nodes[node_id] = KnowledgeNode(
                id=node_id,
                label=name,
                kind=kind,
                file_path=rel_path,
                language=str(row.get("language") or ""),
                line=line,
                package=package,
                metadata={
                    "end_line": _as_int_or_none(sym.get("end_line")),
                    "class": sym.get("class") or "",
                    "complexity": sym.get("complexity"),
                },
            )
            edge = _edge(file_id, node_id, "contains", "ast_cache", line=line)
            edges[edge.id] = edge

    def _add_package_edges(
        self,
        cache: ASTCache,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        *,
        focus: str | None,
    ) -> None:
        for source_file, target_file, kind, line in self._iter_file_relationships(
            cache, focus=focus
        ):
            source_pkg = f"package:{_package_for_file(source_file)}"
            target_pkg = f"package:{_package_for_file(target_file)}"
            if source_pkg == target_pkg:
                continue
            if source_pkg not in nodes or target_pkg not in nodes:
                continue
            edge = _edge(source_pkg, target_pkg, kind, "edge_store", line=line)
            edges[edge.id] = _combine_weight(edges.get(edge.id), edge)

    def _add_file_edges(
        self,
        cache: ASTCache,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        *,
        focus: str | None,
    ) -> None:
        for source_file, target_file, kind, line in self._iter_file_relationships(
            cache, focus=focus
        ):
            source_id = file_node(source_file)
            target_id = file_node(target_file)
            if source_id not in nodes or target_id not in nodes:
                continue
            edge = _edge(source_id, target_id, kind, "edge_store", line=line)
            edges[edge.id] = _combine_weight(edges.get(edge.id), edge)

    def _add_symbol_edges(
        self,
        cache: ASTCache,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        *,
        focus: str | None,
    ) -> None:
        conn = cache.get_conn()
        try:
            rows = conn.execute(
                # Placeholders are derived from fixed constants; values are bound.
                "SELECT source_node_id, target_node_id, kind, line, provenance, metadata, "  # nosec B608
                "file_path, callee_resolved_file FROM edges "
                "WHERE kind IN ({}) ORDER BY kind, source_node_id, target_node_id".format(
                    ",".join("?" for _ in _SOURCE_EDGE_KINDS)
                ),
                _SOURCE_EDGE_KINDS,
            ).fetchall()
        except Exception:
            return
        for row in rows:
            source_id = row["source_node_id"]
            target_id = row["target_node_id"]
            if row["kind"] == "calls" and row["callee_resolved_file"]:
                parsed = parse_node_id(target_id)
                target_id = symbol_node(
                    row["callee_resolved_file"], parsed.name, parsed.line
                )
            if focus and focus not in source_id and focus not in target_id:
                continue
            if source_id not in nodes:
                source = parse_node_id(source_id)
                if source.file_path:
                    nodes[source_id] = _node_from_ref(source_id, source, "symbol")
            if target_id not in nodes:
                target = parse_node_id(target_id)
                if target.file_path:
                    nodes[target_id] = _node_from_ref(target_id, target, "symbol")
            if source_id not in nodes or target_id not in nodes:
                continue
            edge = _edge(
                source_id,
                target_id,
                row["kind"],
                row["provenance"] or "edge_store",
                line=_as_int_or_none(row["line"]),
                metadata=_json_dict(row["metadata"]),
            )
            edges[edge.id] = edge

    def _iter_file_relationships(
        self,
        cache: ASTCache,
        *,
        focus: str | None,
    ) -> list[tuple[str, str, str, int | None]]:
        conn = cache.get_conn()
        try:
            rows = conn.execute(
                # Placeholders are derived from fixed constants; values are bound.
                "SELECT kind, file_path, target_node_id, callee_resolved_file, line "  # nosec B608
                "FROM edges WHERE kind IN ({}) ORDER BY kind, file_path, target_node_id".format(
                    ",".join("?" for _ in _SOURCE_EDGE_KINDS)
                ),
                _SOURCE_EDGE_KINDS,
            ).fetchall()
        except Exception:
            return []
        relationships: list[tuple[str, str, str, int | None]] = []
        for row in rows:
            source_file = str(
                row["file_path"] or parse_node_id(row["target_node_id"]).file_path
            )
            target_file = str(
                row["callee_resolved_file"]
                or parse_node_id(row["target_node_id"]).file_path
            )
            if not source_file or not target_file or source_file == target_file:
                continue
            if focus and focus not in source_file and focus not in target_file:
                continue
            relationships.append(
                (source_file, target_file, row["kind"], _as_int_or_none(row["line"]))
            )
        return relationships

    def _add_doc_links(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        patterns: list[str],
        focus: str | None,
    ) -> None:
        for md_path in _collect_md_files(self.project_root, patterns):
            rel_doc = os.path.relpath(md_path, self.project_root).replace("\\", "/")
            if focus and focus not in rel_doc:
                continue
            doc_id = f"doc:{rel_doc}"
            nodes[doc_id] = KnowledgeNode(
                id=doc_id,
                label=Path(rel_doc).name,
                kind="markdown",
                file_path=rel_doc,
                language="markdown",
                package=_package_for_file(rel_doc),
            )
            try:
                content = Path(md_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for ref in extract_file_refs(content, rel_doc):
                target = _resolve_doc_target(self.project_root, ref.path, rel_doc)
                if not target:
                    continue
                target_id = (
                    f"doc:{target}" if target.endswith(".md") else file_node(target)
                )
                if target_id not in nodes:
                    nodes[target_id] = KnowledgeNode(
                        id=target_id,
                        label=Path(target).name,
                        kind="markdown" if target.endswith(".md") else "file",
                        file_path=target,
                        language="markdown" if target.endswith(".md") else "",
                        package=_package_for_file(target),
                    )
                edge = _edge(
                    doc_id,
                    target_id,
                    "doc_links",
                    "markdown",
                    line=ref.line,
                    metadata={"raw_path": ref.path},
                )
                edges[edge.id] = edge

    def _bounded_snapshot(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        level: str,
        max_nodes: int,
        max_edges: int,
    ) -> KnowledgeGraphSnapshot:
        ordered_nodes = sorted(nodes.values(), key=lambda node: (node.kind, node.id))
        allowed_ids = {node.id for node in ordered_nodes[:max_nodes]}
        ordered_edges = [
            edge
            for edge in sorted(
                edges.values(),
                key=lambda edge: (edge.kind, edge.source, edge.target, edge.id),
            )
            if edge.source in allowed_ids and edge.target in allowed_ids
        ][:max_edges]
        truncated = len(nodes) > max_nodes or len(edges) > max_edges
        stats = {
            "level": level,
            "node_count": len(ordered_nodes[:max_nodes]),
            "edge_count": len(ordered_edges),
            "total_nodes_available": len(nodes),
            "total_edges_available": len(edges),
            "project_root": self.project_root,
            "node_kinds": _counts(node.kind for node in ordered_nodes),
            "edge_kinds": _counts(edge.kind for edge in edges.values()),
        }
        if truncated:
            stats["max_nodes"] = max_nodes
            stats["max_edges"] = max_edges
        return KnowledgeGraphSnapshot(
            nodes=ordered_nodes[:max_nodes],
            edges=ordered_edges,
            stats=stats,
            truncated=truncated,
        )


def _collect_md_files(project_root: str, patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(project_root, pattern), recursive=True))
    return sorted({path for path in files if os.path.isfile(path)})


def _package_for_file(rel_path: str) -> str:
    parent = Path(rel_path).parent
    if str(parent) in {"", "."}:
        return "<root>"
    parts = parent.parts
    if "src" in parts and "java" in parts:
        java_idx = parts.index("java")
        package_parts = parts[java_idx + 1 :]
        if package_parts:
            return ".".join(package_parts)
    return "/".join(parts[:3])


def _resolve_doc_target(project_root: str, raw_path: str, rel_doc: str) -> str | None:
    doc_dir = Path(project_root) / Path(rel_doc).parent
    candidates = [Path(project_root) / raw_path, doc_dir / raw_path]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return os.path.relpath(candidate, project_root).replace("\\", "/")
    prefixed = Path(project_root) / "tree_sitter_analyzer" / raw_path
    if prefixed.exists() and prefixed.is_file():
        return os.path.relpath(prefixed, project_root).replace("\\", "/")
    return None


def _node_from_ref(node_id: str, ref: Any, kind: str) -> KnowledgeNode:
    return KnowledgeNode(
        id=node_id,
        label=ref.name or Path(ref.file_path).name,
        kind=kind,
        file_path=ref.file_path,
        line=ref.line or None,
        package=_package_for_file(ref.file_path),
    )


def _edge(
    source: str,
    target: str,
    kind: str,
    provenance: str,
    *,
    line: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeEdge:
    raw = f"{source}\0{target}\0{kind}\0{line or 0}\0{json.dumps(metadata or {}, sort_keys=True)}"
    edge_id = "kg:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return KnowledgeEdge(
        id=edge_id,
        source=source,
        target=target,
        kind=kind,
        provenance=provenance,
        line=line,
        metadata=metadata or {},
    )


def _combine_weight(
    existing: KnowledgeEdge | None, edge: KnowledgeEdge
) -> KnowledgeEdge:
    if existing is None:
        return edge
    return KnowledgeEdge(
        id=existing.id,
        source=existing.source,
        target=existing.target,
        kind=existing.kind,
        weight=existing.weight + 1.0,
        provenance=existing.provenance,
        line=existing.line,
        metadata=existing.metadata,
    )


def _as_int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
