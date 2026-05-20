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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._route_detector_helpers import (
    extract_annotation_value,
    extract_django_handler,
    extract_js_handler,
    extract_template_string,
    find_keyword,
    function_name_after_decorator,
    method_after_annotation,
    parse_methods_list,
    unquote,
    unquote_java_string,
    walk,
)
from .core.parser import Parser
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)

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
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
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


class RouteDetector:
    """
    Detect HTTP route declarations across web frameworks.

    Usage:
        detector = RouteDetector("/path/to/project")
        routes = detector.detect_all()
        for route in routes:
            print(f"{route.http_method} {route.url_pattern} -> {route.handler_name}")
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root).resolve()
        self._parser = Parser()
        self._routes: list[RouteInfo] | None = None

    def detect_all(self) -> list[RouteInfo]:
        if self._routes is not None:
            return self._routes

        routes: list[RouteInfo] = []
        for file_path in self._walk_source_files():
            try:
                file_routes = self.detect_file(str(file_path))
                routes.extend(file_routes)
            except Exception as exc:
                logger.debug("route detection failed for %s: %s", file_path, exc)

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
        files: list[Path] = []
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in _EXCLUDE_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in _SOURCE_EXTENSIONS:
                continue
            # Reject symlinks that point outside the project root.
            # rglob() yields symlinks but does not check what they point at;
            # without this, a `data -> /` symlink would exfiltrate the FS.
            try:
                resolved = path.resolve()
                resolved.relative_to(self.project_root)
            except (OSError, ValueError):
                continue
            files.append(path)
        return files

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
        routes: list[RouteInfo] = []
        routes.extend(self._scan_flask_decorators(tree.root_node, file_path, source))
        routes.extend(self._scan_fastapi_decorators(tree.root_node, file_path, source))
        routes.extend(self._scan_django_urls(tree.root_node, file_path, source))
        return routes

    def _scan_flask_decorators(
        self, root, file_path: str, source: str
    ) -> list[RouteInfo]:
        routes: list[RouteInfo] = []
        for node in walk(root):
            if node.type != "decorator":
                continue
            text = node.text.decode()
            m = re.match(
                r"@\s*[\w.]+\s*\.\s*route\s*\(\s*[\"']([^\"']+)[\"']\s*(?:,\s*methods\s*=\s*\[([^\]]*)\])?",
                text,
            )
            if not m:
                continue
            url_pattern = m.group(1)
            methods_str = m.group(2)
            methods = parse_methods_list(methods_str) if methods_str else ["GET"]
            handler = function_name_after_decorator(node)
            for method in methods:
                routes.append(RouteInfo(
                    http_method=method.upper(),
                    url_pattern=url_pattern,
                    handler_name=handler,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    framework="flask",
                    language="python",
                ))
        return routes

    def _scan_fastapi_decorators(
        self, root, file_path: str, source: str
    ) -> list[RouteInfo]:
        routes: list[RouteInfo] = []
        http_methods = {"get", "post", "put", "delete", "patch", "head", "options"}
        for node in walk(root):
            if node.type != "decorator":
                continue
            text = node.text.decode()
            m = re.match(
                r"@\s*[\w.]+\s*\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*[\"']([^\"']+)[\"']",
                text,
                re.IGNORECASE,
            )
            if not m:
                continue
            method_str = m.group(1).lower()
            if method_str not in http_methods:
                continue
            url_pattern = m.group(2)
            handler = function_name_after_decorator(node)
            routes.append(RouteInfo(
                http_method=method_str.upper(),
                url_pattern=url_pattern,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="fastapi",
                language="python",
            ))
        return routes

    def _scan_django_urls(
        self, root, file_path: str, source: str
    ) -> list[RouteInfo]:
        routes: list[RouteInfo] = []
        for node in walk(root):
            if node.type != "call":
                continue
            func = node.child_by_field_name("func")
            if func is None:
                continue
            func_text = func.text.decode()
            if func_text not in ("path", "re_path", "include"):
                continue

            args = node.child_by_field_name("arguments")
            if args is None:
                continue
            arg_texts = [
                c.text.decode()
                for c in args.children
                if c.type not in (",", "(", ")", "[", "]")
            ]

            if func_text == "include":
                continue

            if len(arg_texts) < 2:
                continue

            url_pattern = unquote(arg_texts[0])
            handler_text = arg_texts[1]
            handler_name = extract_django_handler(handler_text)

            methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
            kw_node = find_keyword(args, "method")
            if kw_node:
                kw_val = kw_node.child_by_field_name("value")
                if kw_val:
                    methods = parse_methods_list(kw_val.text.decode())
                    if not methods:
                        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

            for method in methods:
                routes.append(RouteInfo(
                    http_method=method.upper(),
                    url_pattern=url_pattern,
                    handler_name=handler_name,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    framework="django",
                    language="python",
                ))
        return routes

    # ------------------------------------------------------------------
    # JavaScript / TypeScript: Express router.get/post/put/delete
    # ------------------------------------------------------------------

    def _detect_js_routes(self, file_path: str, language: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, language)
        if not tree:
            return []
        return self._scan_express_routes(tree.root_node, file_path, language)

    def _scan_express_routes(
        self, root, file_path: str, language: str
    ) -> list[RouteInfo]:
        routes: list[RouteInfo] = []
        http_methods = {"get", "post", "put", "delete", "patch", "head", "options", "all", "use"}

        for node in walk(root):
            if node.type != "call_expression":
                continue
            func = node.child_by_field_name("function")
            if func is None:
                continue

            func_text = func.text.decode()
            parts = func_text.rsplit(".", 1)
            if len(parts) != 2:
                continue
            method_name = parts[1].lower()
            if method_name not in http_methods:
                continue

            args_node = node.child_by_field_name("arguments")
            if args_node is None:
                continue

            first_arg = None
            for child in args_node.children:
                if child.type in ("string", "template_string"):
                    first_arg = child
                    break

            if first_arg is None:
                continue

            if first_arg.type == "template_string":
                url_pattern = extract_template_string(first_arg)
            else:
                url_pattern = unquote(first_arg.text.decode())

            if not url_pattern or not url_pattern.startswith("/"):
                continue

            http_method = method_name.upper() if method_name != "use" else "USE"

            handler_name = extract_js_handler(args_node)

            routes.append(RouteInfo(
                http_method=http_method,
                url_pattern=url_pattern,
                handler_name=handler_name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="express",
                language=language,
            ))
        return routes

    # ------------------------------------------------------------------
    # Java: Spring Boot annotations
    # ------------------------------------------------------------------

    def _detect_java_routes(self, file_path: str) -> list[RouteInfo]:
        tree = self._parse_tree(file_path, "java")
        if not tree:
            return []
        return self._scan_spring_annotations(tree.root_node, file_path)

    def _scan_spring_annotations(
        self, root, file_path: str
    ) -> list[RouteInfo]:
        routes: list[RouteInfo] = []
        annotation_map = {
            "GetMapping": "GET",
            "PostMapping": "POST",
            "PutMapping": "PUT",
            "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH",
        }

        for node in walk(root):
            if node.type != "marker_annotation" and node.type != "annotation":
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            ann_name = name_node.text.decode()
            simple_name = ann_name.rsplit(".", 1)[-1]

            http_method = annotation_map.get(simple_name)
            if not http_method:
                if simple_name == "RequestMapping":
                    http_method, url_pattern = self._parse_request_mapping(node)
                    if url_pattern is None:
                        continue
                    handler = method_after_annotation(node)
                    routes.append(RouteInfo(
                        http_method=http_method,
                        url_pattern=url_pattern,
                        handler_name=handler,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        framework="spring",
                        language="java",
                    ))
                continue

            url_pattern = extract_annotation_value(node)
            if url_pattern is None:
                url_pattern = ""
            handler = method_after_annotation(node)
            routes.append(RouteInfo(
                http_method=http_method,
                url_pattern=url_pattern,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="spring",
                language="java",
            ))
        return routes

    def _parse_request_mapping(self, node) -> tuple[str, str | None]:
        method = "GET"
        url = None
        args_node = node.child_by_field_name("arguments")
        if args_node is None:
            for child in node.children:
                if child.type == "(":
                    idx = list(node.children).index(child)
                    if idx + 1 < len(node.children):
                        next_child = node.children[idx + 1]
                        if next_child.type == "string_literal":
                            url = unquote_java_string(next_child.text.decode())

        if args_node:
            for child in args_node.children:
                text = child.text.decode()
                if child.type == "string_literal":
                    url = unquote_java_string(text)
                elif "method" in text and "=" in text:
                    m = re.search(r"RequestMethod\.(\w+)", text)
                    if m:
                        method = m.group(1).upper()
                    kw_node = find_keyword(args_node, "method")
                    if kw_node:
                        val = kw_node.child_by_field_name("value")
                        if val:
                            vm = re.search(
                                r"RequestMethod\.(\w+)", val.text.decode()
                            )
                            if vm:
                                method = vm.group(1).upper()
        return method, url

    # Static helpers moved to tree_sitter_analyzer._route_detector_helpers
    # to keep this module under the project's 500-line file-size cap.
