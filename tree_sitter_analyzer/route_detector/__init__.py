#!/usr/bin/env python3
# mypy: disable-error-code="no-any-return, no-untyped-def"
"""
Framework Route Detection — Auto-detect URL→Handler mappings.

Scans project source files using Tree-sitter AST parsing to discover
HTTP route declarations from popular web frameworks:

- Python: Flask (@app.route), Django (path()/re_path()), FastAPI (@app.get/post)
- JavaScript/TypeScript: Express (router.get/post/put/delete)
- Java: Spring Boot (@GetMapping/@PostMapping/@RequestMapping)

CodeGraph parity: equivalent to CodeGraph's route-map feature.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..registry.route_cache import RouteCache
from .go import scan_go_routes
from .scanners import (
    scan_django_urls,
    scan_express_routes,
    scan_fastapi_decorators,
    scan_flask_decorators,
    scan_spring_annotations,
)
from ..core.parser import Parser
from ..project_graph import _language_from_ext

logger = logging.getLogger(__name__)

# Type alias for route cache records — reduces generic nesting depth in annotations.
_CacheRecord = tuple[str, str, int, list[dict[str, Any]]]

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
    "vendor",
    "target",
    ".gradle",
    ".mvn",
}

_SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
}

_FRAMEWORK_FILES = {
    "python": {
        "flask": {"flask", "flask_restful", "flask_restx"},
        "django": {"django", "django.urls"},
        "fastapi": {"fastapi"},
        "starlette": {"starlette"},
    },
    "javascript": {
        "express": {"express"},
        "koa": {"koa", "@koa/router"},
        "fastify": {"fastify"},
        "next": {"next"},
    },
    "java": {
        "spring": {"org.springframework"},
    },
}


_ROUTE_INFO_FIELDS = frozenset(
    {
        "http_method",
        "url_pattern",
        "handler_name",
        "file_path",
        "line_number",
        "framework",
        "language",
    }
)


@dataclass
class RouteInfo:
    """A detected HTTP route mapping."""

    http_method: str
    url_pattern: str
    handler_name: str
    file_path: str
    line_number: int
    framework: str
    language: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_method": self.http_method,
            "url_pattern": self.url_pattern,
            "handler_name": self.handler_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "framework": self.framework,
            "language": self.language,
            **self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteInfo":
        """Rebuild a RouteInfo from a cached to_dict() output."""
        known = _ROUTE_INFO_FIELDS
        return cls(
            http_method=data["http_method"],
            url_pattern=data["url_pattern"],
            handler_name=data["handler_name"],
            file_path=data["file_path"],
            line_number=int(data["line_number"]),
            framework=data["framework"],
            language=data["language"],
            extra={k: v for k, v in data.items() if k not in known},
        )


def _resolve_symlink_target(symlink_path: str, root: Path) -> Path | None:
    """Resolve a file-symlink, returning its target if it lives under ``root``.

    r37bf: extracted so ``RouteDetector._classify_dir_entry`` reads as a
    flat dispatch. Returns ``None`` on any resolution / boundary / extension
    miss — caller treats that as "skip this entry".
    """
    try:
        target = Path(symlink_path).resolve()
        target.relative_to(root)
    except (OSError, ValueError):
        return None
    if target.suffix.lower() not in _SOURCE_EXTENSIONS:
        return None
    return target


class RouteDetector:
    """
    Detect HTTP route declarations across web frameworks.

    Usage:
        detector = RouteDetector("/path/to/project")
        routes = detector.detect_all()
        for route in routes:
            print(f"{route.http_method} {route.url_pattern} -> {route.handler_name}")
    """

    def __init__(
        self,
        project_root: str,
        *,
        cache_enabled: bool = True,
        cache_db_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self._parser = Parser()
        self._routes: list[RouteInfo] | None = None
        self._cache: RouteCache | None = None
        if cache_enabled:
            db_path = (
                Path(cache_db_path)
                if cache_db_path is not None
                else self.project_root / ".ast-cache" / "routes.db"
            )
            try:
                self._cache = RouteCache(db_path)
            except (OSError, sqlite3.Error) as exc:
                # Falling back to no-cache mode keeps detection working even when
                # the workspace is read-only or the .ast-cache dir cannot be created.
                logger.debug("route cache disabled: %s", exc)
                self._cache = None
        # Lightweight hit/miss counters — used by CLI/MCP and by tests.
        self._cache_hits = 0
        self._cache_misses = 0

    def cache_stats(self) -> dict[str, Any]:
        base = {"hits": self._cache_hits, "misses": self._cache_misses}
        if self._cache is not None:
            base.update({"enabled": True, **self._cache.stats()})
        else:
            base["enabled"] = False
        return base

    def detect_all(self) -> list[RouteInfo]:
        if self._routes is not None:
            return self._routes
        files = [str(p) for p in self._walk_source_files()]
        if self._cache is None:
            routes: list[RouteInfo] = []
            for file_path in files:
                try:
                    routes.extend(self.detect_file(file_path))
                except Exception as exc:
                    logger.debug("route detection failed for %s: %s", file_path, exc)
            self._routes = routes
            return routes
        return self._detect_all_cached(files)

    def _detect_all_cached(self, files: list[str]) -> list[RouteInfo]:
        """Cache-aware bulk path used when ``self._cache`` is enabled.

        Single ``bulk_get_by_stat`` lookup short-circuits the warm pass;
        misses are parsed individually then flushed back with one
        ``bulk_put`` transaction at the end. Reduces SQLite chatter from
        2N (lookups + inserts) to ~2 queries total.
        """
        # r37bf: was ``assert self._cache is not None`` — bandit B101 flags
        # asserts as stripped under ``-O``. Replace with an explicit raise so
        # the invariant holds in all build modes.
        if self._cache is None:
            raise RuntimeError("_detect_all_cached called without an enabled cache")
        path_with_mtime: list[tuple[str, int]] = []
        mtime_lookup: dict[str, int] = {}
        for fp in files:
            mt = self._cache.stat_mtime(fp)
            if mt is not None:
                path_with_mtime.append((fp, mt))
                mtime_lookup[fp] = mt
        hits_by_path = self._cache.bulk_get_by_stat(path_with_mtime)
        routes: list[RouteInfo] = []
        new_records: list[_CacheRecord] = []
        for fp in files:
            cached = hits_by_path.get(fp)
            if cached is not None:
                self._cache_hits += 1
                routes.extend(RouteInfo.from_dict(item) for item in cached)
                continue
            self._cache_misses += 1
            try:
                file_routes = self.detect_file(fp)
            except Exception as exc:
                logger.debug("route detection failed for %s: %s", fp, exc)
                continue
            routes.extend(file_routes)
            freshness = self._cache.freshness_key(fp)
            if freshness is None:
                continue
            content_hash, mtime_ns = freshness
            new_records.append(
                (fp, content_hash, mtime_ns, [r.to_dict() for r in file_routes])
            )
        if new_records:
            try:
                self._cache.bulk_put(new_records)
            except sqlite3.Error as exc:
                logger.debug("route cache bulk_put failed: %s", exc)
        self._routes = routes
        return routes

    def detect_file(self, file_path: str) -> list[RouteInfo]:
        lang = _language_from_ext(file_path)
        if not lang:
            return []

        if lang == "python":
            return self._detect_python_routes(file_path)
        elif lang in ("javascript", "typescript"):
            return self._detect_js_routes(file_path, lang)
        elif lang == "java":
            return self._detect_java_routes(file_path)
        elif lang == "go":
            return self._detect_go_routes(file_path)
        return []

    def summary(self) -> dict[str, Any]:
        routes = self.detect_all()
        by_framework: dict[str, int] = {}
        by_method: dict[str, int] = {}
        for r in routes:
            by_framework[r.framework] = by_framework.get(r.framework, 0) + 1
            by_method[r.http_method] = by_method.get(r.http_method, 0) + 1
        return {
            "total_routes": len(routes),
            "by_framework": by_framework,
            "by_method": by_method,
            "file_count": len({r.file_path for r in routes}),
        }

    def lookup_handler(self, url_pattern: str) -> list[RouteInfo]:
        routes = self.detect_all()
        return [r for r in routes if r.url_pattern == url_pattern]

    def lookup_url_prefix(self, prefix: str) -> list[RouteInfo]:
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        routes = self.detect_all()
        return [r for r in routes if r.url_pattern.startswith(prefix)]

    def _walk_source_files(self) -> list[Path]:
        """Manual ``os.scandir`` walk: prune excluded directories at the
        directory level (so we never stat their entire contents) and only
        ``resolve()`` symlinks, which on most projects is 0% of the tree.

        On the analyzer's own repo this dropped walk time from 260 ms to
        ~30 ms (5–8× faster), and it scales linearly with source-file count
        rather than total tree size.

        r37bf (dogfood): tool flagged this at nesting depth 8 (L318). The
        per-entry classification (excluded dir / dir / symlink / file)
        moved into ``_classify_dir_entry`` so this method now walks the
        stack and delegates each entry. Behaviour preserved.
        """
        import os as _os

        files: list[Path] = []
        root = self.project_root
        stack: list[str] = [str(root)]
        while stack:
            current = stack.pop()
            try:
                it = _os.scandir(current)
            except OSError:
                continue
            with it:
                for entry in it:
                    self._classify_dir_entry(entry, root, stack, files)
        return files

    @staticmethod
    def _classify_dir_entry(
        entry: Any,
        root: Path,
        stack: list[str],
        files: list[Path],
    ) -> None:
        """Sort a single scandir entry into ``stack`` (recurse) or ``files``.

        r37bf (dogfood): extracted to flatten 8-deep nesting in
        ``_walk_source_files``. Excluded dirs are dropped, plain files
        get an extension check, file-symlinks are resolved-then-checked
        for boundary + extension.
        """
        name = entry.name
        if name in _EXCLUDE_DIRS or name.startswith("."):
            return
        if entry.is_dir(follow_symlinks=False):
            stack.append(entry.path)
            return
        if not entry.is_file(follow_symlinks=False):
            if entry.is_symlink():
                resolved = _resolve_symlink_target(entry.path, root)
                if resolved is not None:
                    files.append(Path(entry.path))
            return
        # Plain file — extension filter (cheaper than path ops).
        dot = name.rfind(".")
        if dot == -1:
            return
        if name[dot:].lower() not in _SOURCE_EXTENSIONS:
            return
        files.append(Path(entry.path))

    def _parse_tree(self, file_path: str, language: str):
        result = self._parser.parse_file(file_path, language)
        if not result.success or result.tree is None:
            return None
        return result.tree

    # ------------------------------------------------------------------
    # Python: Flask / FastAPI decorators + Django path()/re_path()
    # ------------------------------------------------------------------

    def _detect_python_routes(self, file_path: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, "python")
        if not tree:
            return []
        source = tree.root_node.text.decode()
        root = tree.root_node
        routes: list[RouteInfo] = []
        routes.extend(scan_flask_decorators(root, file_path, source, RouteInfo))
        routes.extend(scan_fastapi_decorators(root, file_path, source, RouteInfo))
        routes.extend(scan_django_urls(root, file_path, source, RouteInfo))
        return routes

    def _detect_js_routes(self, file_path: str, language: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, language)
        if not tree:
            return []
        return scan_express_routes(tree.root_node, file_path, language, RouteInfo)

    def _detect_java_routes(self, file_path: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, "java")
        if not tree:
            return []
        return scan_spring_annotations(tree.root_node, file_path, RouteInfo)

    def _detect_go_routes(self, file_path: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, "go")
        if not tree:
            return []
        return scan_go_routes(tree.root_node, file_path, RouteInfo)

    # Static helpers moved to tree_sitter_analyzer._route_detector_helpers
    # to keep this module under the project's 500-line file-size cap.
