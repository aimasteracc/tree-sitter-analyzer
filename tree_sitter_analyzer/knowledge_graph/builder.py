"""Build a human/program friendly knowledge graph from TSA indexes."""

from __future__ import annotations

import glob
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from ..ast_cache import ASTCache
from ..doc_sync import extract_file_refs
from ..graph.edge_store import file_node, parse_node_id, symbol_node
from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode

_DEFAULT_DOC_PATTERNS = ("**/*.md",)
_SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", ".tox"}


class KnowledgeGraphBuilder:
    """Project graph builder backed by the existing AST cache and edge store."""

    def __init__(self, project_root: str) -> None:
        self.project_root = os.path.abspath(project_root)

    def build(
        self,
        *,
        include_docs: bool = True,
        doc_patterns: list[str] | None = None,
        max_nodes: int = 0,
        max_edges: int = 0,
    ) -> KnowledgeGraphSnapshot:
        """Build a capped whole-project graph projection from persisted indexes."""
        node_cap = _cap(max_nodes)
        edge_cap = _cap(max_edges)
        cache = ASTCache(self.project_root)
        try:
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT file_path, language, symbols_json FROM ast_index "
                "ORDER BY file_path"
            ).fetchall()

            nodes: dict[str, KnowledgeNode] = {}
            edges: dict[str, KnowledgeEdge] = {}

            for row in rows:
                self._add_file_and_symbols(nodes, edges, row)
                if _at_cap(len(nodes), node_cap):
                    break

            edge_query = (
                "SELECT source_node_id, target_node_id, kind, line, provenance, "
                "metadata, caller_name, callee_name, file_path, language, "
                "callee_resolved_file FROM edges "
                "ORDER BY kind, source_node_id, target_node_id, line "
            )
            if edge_cap is None:
                edge_rows = conn.execute(edge_query).fetchall()
            else:
                edge_rows = conn.execute(edge_query + "LIMIT ?", (edge_cap,)).fetchall()
            for row in edge_rows:
                self._add_existing_edge(nodes, edges, row)
                if _at_cap(len(nodes), node_cap) or _at_cap(len(edges), edge_cap):
                    break

            if (
                include_docs
                and not _at_cap(len(nodes), node_cap)
                and not _at_cap(len(edges), edge_cap)
            ):
                self._add_markdown_links(
                    nodes,
                    edges,
                    doc_patterns or list(_DEFAULT_DOC_PATTERNS),
                    max_nodes=node_cap,
                    max_edges=edge_cap,
                )

            stats = {
                "project_root": self.project_root,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "indexed_files": len(rows),
                "node_kinds": dict(Counter(node.kind for node in nodes.values())),
                "edge_kinds": dict(Counter(edge.kind for edge in edges.values())),
                "truncated": _at_cap(len(nodes), node_cap)
                or _at_cap(len(edges), edge_cap),
                "max_nodes": max_nodes,
                "max_edges": max_edges,
            }
            return KnowledgeGraphSnapshot(
                nodes=sorted(nodes.values(), key=lambda n: n.id),
                edges=sorted(edges.values(), key=lambda e: e.id),
                stats=stats,
            )
        finally:
            cache.close()

    def build_delta(self, changed_file_paths: list[str]) -> KnowledgeGraphSnapshot:
        """Build a subgraph snapshot limited to the changed files."""
        if not changed_file_paths:
            return KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})
        # ast_index stores relative paths; normalise to relative
        rel_paths = []
        for p in changed_file_paths:
            if os.path.isabs(p):
                try:
                    rel_paths.append(os.path.relpath(p, self.project_root).replace("\\", "/"))
                except ValueError:
                    rel_paths.append(p)
            else:
                rel_paths.append(p.replace("\\", "/"))
        cache = ASTCache(self.project_root)
        try:
            conn = cache.get_conn()
            placeholders = ",".join("?" * len(rel_paths))
            rows = conn.execute(
                f"SELECT file_path, language, symbols_json FROM ast_index "
                f"WHERE file_path IN ({placeholders}) ORDER BY file_path",
                rel_paths,
            ).fetchall()
            nodes: dict[str, KnowledgeNode] = {}
            edges: dict[str, KnowledgeEdge] = {}
            for row in rows:
                self._add_file_and_symbols(nodes, edges, row)
            if nodes:
                node_ids = list(nodes.keys())
                id_placeholders = ",".join("?" * len(node_ids))
                edge_rows = conn.execute(
                    f"SELECT source_node_id, target_node_id, kind, line, provenance, "
                    f"metadata, caller_name, callee_name, file_path, language, "
                    f"callee_resolved_file FROM edges "
                    f"WHERE source_node_id IN ({id_placeholders}) "
                    f"OR target_node_id IN ({id_placeholders}) "
                    f"ORDER BY kind, source_node_id, target_node_id, line",
                    node_ids + node_ids,
                ).fetchall()
                for row in edge_rows:
                    self._add_existing_edge(nodes, edges, row)
            stats = {"node_count": len(nodes), "edge_count": len(edges),
                     "delta": True, "changed_files": len(changed_file_paths)}
            return KnowledgeGraphSnapshot(
                nodes=sorted(nodes.values(), key=lambda n: n.id),
                edges=sorted(edges.values(), key=lambda e: e.id),
                stats=stats,
            )
        finally:
            cache.close()

    def _add_file_and_symbols(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        row: Any,
    ) -> None:
        file_path = row["file_path"]
        language = row["language"]
        file_id = file_node(file_path)
        self._upsert_node(
            nodes,
            KnowledgeNode(
                id=file_id,
                kind="file",
                label=file_path,
                file_path=file_path,
                language=language,
            ),
        )

        package_id = self._package_node_id(file_path)
        self._upsert_node(
            nodes,
            KnowledgeNode(
                id=package_id,
                kind="package",
                label=package_id.removeprefix("package:"),
                metadata={"directory": str(Path(file_path).parent)},
            ),
        )
        self._add_edge(
            edges,
            source=package_id,
            target=file_id,
            kind="contains",
            provenance="tsa-package",
        )

        symbols = json.loads(row["symbols_json"] or "{}").get("symbols", [])
        for symbol in symbols:
            name = str(symbol.get("name") or "")
            if not name:
                continue
            line = _as_int(symbol.get("line"), 0)
            node_id = symbol_node(file_path, name, line)
            kind = str(symbol.get("kind") or "symbol")
            self._upsert_node(
                nodes,
                KnowledgeNode(
                    id=node_id,
                    kind=kind,
                    label=name,
                    file_path=file_path,
                    language=language,
                    metadata={
                        "line": line,
                        "end_line": _as_int(symbol.get("end_line"), line),
                    },
                ),
            )
            self._add_edge(
                edges,
                source=file_id,
                target=node_id,
                kind="contains",
                line=line,
                provenance="tree-sitter",
            )

    def _add_existing_edge(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        row: Any,
    ) -> None:
        source = row["source_node_id"]
        target = row["target_node_id"]
        if source not in nodes:
            self._add_placeholder_node(nodes, source, row["language"])
        if target not in nodes:
            self._add_placeholder_node(nodes, target, row["language"])
        metadata = _json_obj(row["metadata"])
        if row["callee_resolved_file"]:
            metadata["callee_resolved_file"] = row["callee_resolved_file"]
        self._add_edge(
            edges,
            source=source,
            target=target,
            kind=row["kind"],
            line=_nullable_int(row["line"]),
            provenance=row["provenance"] or "tree-sitter",
            metadata=metadata,
        )

    def _add_markdown_links(
        self,
        nodes: dict[str, KnowledgeNode],
        edges: dict[str, KnowledgeEdge],
        patterns: list[str],
        *,
        max_nodes: int | None,
        max_edges: int | None,
    ) -> None:
        for md_path in _iter_markdown_files(self.project_root, patterns):
            if _at_cap(len(nodes), max_nodes) or _at_cap(len(edges), max_edges):
                return
            rel_doc = os.path.relpath(md_path, self.project_root).replace("\\", "/")
            doc_id = f"doc:{rel_doc}"
            self._upsert_node(
                nodes,
                KnowledgeNode(
                    id=doc_id,
                    kind="markdown",
                    label=rel_doc,
                    file_path=rel_doc,
                    language="markdown",
                ),
            )
            try:
                content = Path(md_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for ref in extract_file_refs(content, rel_doc):
                target = _resolve_project_ref(ref.path, rel_doc, self.project_root)
                if target is None:
                    continue
                target_id = file_node(target)
                if target_id not in nodes:
                    self._upsert_node(
                        nodes,
                        KnowledgeNode(
                            id=target_id,
                            kind="file",
                            label=target,
                            file_path=target,
                        ),
                    )
                self._add_edge(
                    edges,
                    source=doc_id,
                    target=target_id,
                    kind="doc_links",
                    line=ref.line,
                    provenance="markdown",
                    metadata={"raw_ref": ref.path},
                )
                if _at_cap(len(edges), max_edges):
                    return

    def _add_placeholder_node(
        self,
        nodes: dict[str, KnowledgeNode],
        node_id: str,
        language: str,
    ) -> None:
        parsed = parse_node_id(node_id)
        kind = "file" if node_id.startswith("file:") else "symbol"
        label = parsed.file_path if kind == "file" else parsed.name or node_id
        self._upsert_node(
            nodes,
            KnowledgeNode(
                id=node_id,
                kind=kind,
                label=label,
                file_path=parsed.file_path,
                language=language,
                metadata={"line": parsed.line} if parsed.line else {},
            ),
        )

    @staticmethod
    def _upsert_node(
        nodes: dict[str, KnowledgeNode],
        node: KnowledgeNode,
    ) -> None:
        nodes.setdefault(node.id, node)

    @staticmethod
    def _add_edge(
        edges: dict[str, KnowledgeEdge],
        *,
        source: str,
        target: str,
        kind: str,
        line: int | None = None,
        provenance: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        edge_id = _edge_id(source, target, kind, line)
        edges.setdefault(
            edge_id,
            KnowledgeEdge(
                id=edge_id,
                source=source,
                target=target,
                kind=kind,
                line=line,
                provenance=provenance,
                metadata=metadata or {},
            ),
        )

    @staticmethod
    def _package_node_id(file_path: str) -> str:
        directory = str(Path(file_path).parent)
        if directory in ("", "."):
            directory = "<root>"
        return "package:" + directory.replace("/", ".")


def _edge_id(source: str, target: str, kind: str, line: int | None) -> str:
    raw = f"{source}\0{target}\0{kind}\0{line or ''}"
    return "edge:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _cap(value: int) -> int | None:
    return value if value > 0 else None


def _at_cap(count: int, cap: int | None) -> bool:
    return cap is not None and count >= cap


def _json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _nullable_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int) -> int:
    parsed = _nullable_int(value)
    return default if parsed is None else parsed


def _iter_markdown_files(project_root: str, patterns: list[str]) -> list[str]:
    matches: set[str] = set()
    for pattern in patterns:
        for candidate in glob.glob(os.path.join(project_root, pattern), recursive=True):
            if not os.path.isfile(candidate):
                continue
            rel_parts = Path(os.path.relpath(candidate, project_root)).parts
            if any(part in _SKIP_DIRS for part in rel_parts):
                continue
            matches.add(candidate)
    return sorted(matches)


def _resolve_project_ref(path: str, doc_file: str, project_root: str) -> str | None:
    candidates = [
        os.path.join(project_root, path),
        os.path.normpath(os.path.join(project_root, os.path.dirname(doc_file), path)),
        os.path.join(project_root, "tree_sitter_analyzer", path),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.relpath(candidate, project_root).replace("\\", "/")
    return None
