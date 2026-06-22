"""Local HTTP service for interactive knowledge graph exploration."""

from __future__ import annotations

import asyncio
import json
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
