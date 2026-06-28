"""Local HTTP service for interactive knowledge graph exploration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import posixpath
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, urlparse

from .query import KnowledgeGraphQueryBackend, open_query_backend
from .stores import JsonKnowledgeGraphStore, LadybugKnowledgeGraphStore

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """Service facade over LadybugDB with JSON sidecar fallback."""

    def __init__(self, project_root: str) -> None:
        self.project_root = os.path.abspath(project_root)
        self.backend: KnowledgeGraphQueryBackend = open_query_backend(self.project_root)

    def graph(
        self,
        *,
        lod: str = "file",
        focus: str | None = None,
        max_nodes: int = 1200,
        max_edges: int = 4000,
    ) -> dict[str, Any]:
        """Return an overview graph for the current filters."""
        return self.backend.graph(
            lod=lod,
            focus=focus,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def search(self, query: str, *, limit: int = 50) -> dict[str, Any]:
        """Return matching nodes without loading a new graph view."""
        return self.backend.search(query, limit=limit)

    def files(self, query: str = "", *, limit: int = 5000) -> dict[str, Any]:
        """Return file and Markdown nodes for the persistent Explorer."""
        return self.backend.files(query, limit=limit)

    def node(self, node_id: str, *, limit: int = 80) -> dict[str, Any]:
        """Return a selected node and capped incoming/outgoing relationships."""
        return self.backend.node(node_id, limit=limit)

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        edge_kind: str = "all",
        max_nodes: int = 300,
        max_edges: int = 1000,
    ) -> dict[str, Any]:
        """Return a graphology payload centered on one node."""
        return self.backend.neighborhood(
            node_id,
            depth=depth,
            edge_kind=edge_kind,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )


def serve_knowledge_graph(
    project_root: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    watch: bool = False,
    watch_backend: str = "poll",
) -> None:
    """Start a blocking local knowledge graph HTTP service."""
    prepare_reason = _prepare_reason(project_root) or "startup incremental update"
    print(f"TSA knowledge graph preparing: {prepare_reason}", flush=True)
    prepare_result = ensure_knowledge_graph_ready(project_root)
    if prepare_result.get("prepared"):
        print(
            f"TSA knowledge graph prepared: {prepare_result.get('reason')}",
            flush=True,
        )
    service = KnowledgeGraphService(project_root)

    # Start FileWatcherDaemon if watch mode enabled
    daemon = None
    if watch:
        from ..ast_cache import ASTCache
        from ..file_watcher import FileWatcherDaemon

        on_sync = _make_on_sync_callback(project_root)
        daemon = FileWatcherDaemon(
            ASTCache(project_root),
            backend=watch_backend,
            on_sync=on_sync,
        )
        daemon.start()
        print(f"TSA file watcher started: {watch_backend} backend", flush=True)

    handler_cls = _make_handler(service)
    server = ThreadingHTTPServer((host, port), handler_cls)
    url = f"http://{host}:{server.server_port}/"
    print(f"TSA knowledge graph service: {url}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        if daemon:
            daemon.stop()
        server.server_close()


def ensure_knowledge_graph_ready(
    project_root: str,
    *,
    force_update: bool = True,
) -> dict[str, Any]:
    """Materialize graph sidecars before opening the browser service."""
    reason = _prepare_reason(project_root)
    if not reason and not force_update:
        return {"prepared": False, "reason": "fresh"}
    if not reason:
        reason = "startup incremental update"
    from ..mcp.tools.knowledge_graph_tool import CodeGraphKnowledgeIndexTool

    tool = CodeGraphKnowledgeIndexTool(project_root=project_root)
    result = asyncio.run(
        tool.execute(
            {
                "mode": "update",
                "backend": "auto",
                "max_files": 1_000_000,
                "max_nodes": 0,
                "max_edges": 0,
                "include_docs": True,
                "output_format": "json",
            }
        )
    )
    if not result.get("success", False):
        raise RuntimeError(str(result.get("error", "knowledge graph update failed")))
    result["prepared"] = True
    result["reason"] = reason
    return result


def _prepare_reason(project_root: str) -> str:
    json_store = JsonKnowledgeGraphStore(project_root)
    ladybug_store = LadybugKnowledgeGraphStore(project_root)
    if not json_store.exists():
        return "json sidecar missing"
    if LadybugKnowledgeGraphStore.available() and not ladybug_store.exists():
        return "LadybugDB mirror missing"
    index_mtime = _mtime_ns(os.path.join(project_root, ".ast-cache", "index.db"))
    if index_mtime is None:
        return ""
    json_mtime = _mtime_ns(json_store.path)
    if json_mtime is not None and json_mtime < index_mtime:
        return "json sidecar older than SQLite index"
    if LadybugKnowledgeGraphStore.available():
        ladybug_mtime = _mtime_ns(ladybug_store.path)
        if ladybug_mtime is not None and ladybug_mtime < index_mtime:
            return "LadybugDB mirror older than SQLite index"
    return ""


def _mtime_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _make_on_sync_callback(project_root: str) -> Any:
    """Create a callback for FileWatcherDaemon that updates LadybugDB incrementally."""

    def on_sync(sync_result: dict[str, Any]) -> None:
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
            from .builder import KnowledgeGraphBuilder

            lb_store = LadybugKnowledgeGraphStore(project_root)
            for fp in deleted:
                lb_store.delete_by_file(fp)
            if changed:
                # CRITICAL: delete old nodes before patch to prevent ghost nodes
                for fp in changed:
                    lb_store.delete_by_file(fp)
                builder = KnowledgeGraphBuilder(project_root)
                delta = builder.build_delta(changed)
                lb_store.patch(list(delta.nodes), [], list(delta.edges), [])
        except Exception:
            logger.debug("on_sync LadybugDB update failed", exc_info=True)

    return on_sync


def _uml_for_node(
    project_root: str,
    backend: KnowledgeGraphQueryBackend,
    node_id: str,
    diagram_type: str,
) -> dict[str, Any]:
    """Generate UML diagram for a node's file."""
    from .builder import KnowledgeGraphBuilder

    # Find the node
    node_result = backend.node(node_id, limit=1)
    node = node_result.get("node")
    if not node:
        return {"error": "node not found"}
    file_path = node.get("file_path")
    if not file_path:
        return {"error": "node has no file_path"}

    # Build subgraph for this file
    builder = KnowledgeGraphBuilder(project_root)
    delta = builder.build_delta([file_path])

    # Generate diagram based on type
    if diagram_type == "class":
        class_nodes = [
            n for n in delta.nodes if n.kind in ("class", "interface", "enum")
        ]
        # CRITICAL: fallback to component if no class nodes
        if not class_nodes:
            diagram_type = "component"
            return _generate_component_diagram(delta, diagram_type)
        return _generate_class_diagram(class_nodes, delta.edges, diagram_type)
    elif diagram_type == "sequence":
        # CRITICAL: limit max_nodes to 30 to avoid Mermaid maxTextSize overflow
        limited_nodes = list(delta.nodes)[:30]
        return _generate_sequence_diagram(limited_nodes, delta.edges, diagram_type)
    else:  # component
        return _generate_component_diagram(delta, diagram_type)


def _generate_class_diagram(
    nodes: list[Any], edges: list[Any], diagram_type: str
) -> dict[str, Any]:
    """Generate Mermaid class diagram."""
    lines = ["classDiagram"]
    for node in nodes:
        lines.append(f"  class {node.label}")
    for edge in edges:
        if edge.kind == "inherits":
            lines.append(f"  {edge.source} --|> {edge.target}")
        elif edge.kind == "contains":
            lines.append(f"  {edge.source} *-- {edge.target}")
    return {"diagram": "\n".join(lines), "diagram_type": diagram_type}


def _generate_sequence_diagram(
    nodes: list[Any], edges: list[Any], diagram_type: str
) -> dict[str, Any]:
    """Generate Mermaid sequence diagram."""
    lines = ["sequenceDiagram"]
    for edge in edges:
        if edge.kind == "calls":
            lines.append(f"  {edge.source}->>+{edge.target}: call")
    return {"diagram": "\n".join(lines), "diagram_type": diagram_type}


def _generate_component_diagram(delta: Any, diagram_type: str) -> dict[str, Any]:
    """Generate Mermaid component diagram."""
    lines = ["graph TD"]
    for node in delta.nodes:
        lines.append(f'  {node.id}["{node.label}"]')
    for edge in delta.edges:
        lines.append(f"  {edge.source} --> {edge.target}")
    return {"diagram": "\n".join(lines), "diagram_type": diagram_type}


def _make_handler(service: KnowledgeGraphService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    self._write_static("index.html")
                elif parsed.path.startswith("/static/"):
                    self._write_static(parsed.path.removeprefix("/static/"))
                elif parsed.path == "/api/graph":
                    self._write_json(
                        service.graph(
                            lod=_first(query, "lod", "file"),
                            focus=_first(query, "focus", ""),
                            max_nodes=_int_param(query, "max_nodes", 1200),
                            max_edges=_int_param(query, "max_edges", 4000),
                        )
                    )
                elif parsed.path == "/api/node":
                    self._write_json(
                        service.node(
                            _first(query, "id", ""),
                            limit=_int_param(query, "limit", 80),
                        )
                    )
                elif parsed.path == "/api/neighborhood":
                    self._write_json(
                        service.neighborhood(
                            _first(query, "id", ""),
                            depth=_int_param(query, "depth", 1),
                            edge_kind=_first(query, "edge_kind", "all"),
                            max_nodes=_int_param(query, "max_nodes", 300),
                            max_edges=_int_param(query, "max_edges", 1000),
                        )
                    )
                elif parsed.path == "/api/search":
                    self._write_json(
                        service.search(
                            _first(query, "q", ""),
                            limit=_int_param(query, "limit", 50),
                        )
                    )
                elif parsed.path == "/api/files":
                    self._write_json(
                        service.files(
                            _first(query, "q", ""),
                            limit=_int_param(query, "limit", 5000),
                        )
                    )
                elif parsed.path == "/api/status":
                    snapshot = getattr(service.backend, "snapshot", None)
                    stats = snapshot.stats if snapshot else {}
                    self._write_json({"stats": stats})
                elif parsed.path == "/api/uml":
                    node_id = _first(query, "node_id", "")
                    diagram_type = _first(query, "diagram_type", "class")
                    result = _uml_for_node(
                        service.project_root,
                        service.backend,
                        node_id,
                        diagram_type,
                    )
                    self._write_json(result)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            except (FileNotFoundError, ValueError) as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def _write_json(self, payload: dict[str, Any]) -> None:
            self._write_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _write_static(self, name: str) -> None:
            normalized = posixpath.normpath("/" + name).lstrip("/")
            content_type = _content_type(normalized)
            path = resources.files(__package__).joinpath("static").joinpath(normalized)
            self._write_bytes(path.read_bytes(), content_type)

        def _write_bytes(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _first(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    return values[0] if values else default


def _int_param(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = _first(query, key, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _content_type(path: str) -> str:
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    if path.endswith(".js"):
        return "application/javascript; charset=utf-8"
    return "text/html; charset=utf-8"
