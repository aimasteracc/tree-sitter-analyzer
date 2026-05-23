# mypy: disable-error-code="no-any-return, no-untyped-def"
"""Framework-specific route scanners for ``route_detector``.

Each ``scan_*`` function takes a tree-sitter root node, the absolute file
path, and (for some scanners) auxiliary context, and returns a list of
``RouteInfo``. Split out of ``route_detector.py`` to keep the main module
under the project's 500-line cap.

Scanners use the helpers in :mod:`_route_detector_helpers` for tree walking
and per-token text extraction.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Python — Flask / FastAPI / Django
# ---------------------------------------------------------------------------


def scan_flask_decorators(
    root: Any, file_path: str, _source: str, route_info_cls: type
) -> list[Any]:
    routes: list[Any] = []
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
            routes.append(
                route_info_cls(
                    http_method=method.upper(),
                    url_pattern=url_pattern,
                    handler_name=handler,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    framework="flask",
                    language="python",
                )
            )
    return routes


def scan_fastapi_decorators(
    root: Any, file_path: str, _source: str, route_info_cls: type
) -> list[Any]:
    routes: list[Any] = []
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
        routes.append(
            route_info_cls(
                http_method=method_str.upper(),
                url_pattern=url_pattern,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="fastapi",
                language="python",
            )
        )
    return routes


def scan_django_urls(
    root: Any, file_path: str, _source: str, route_info_cls: type
) -> list[Any]:
    routes: list[Any] = []
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
        handler_name = extract_django_handler(arg_texts[1])
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        kw_node = find_keyword(args, "method")
        if kw_node:
            kw_val = kw_node.child_by_field_name("value")
            if kw_val:
                methods = parse_methods_list(kw_val.text.decode())
                if not methods:
                    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        for method in methods:
            routes.append(
                route_info_cls(
                    http_method=method.upper(),
                    url_pattern=url_pattern,
                    handler_name=handler_name,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    framework="django",
                    language="python",
                )
            )
    return routes


# ---------------------------------------------------------------------------
# JavaScript / TypeScript — Express
# ---------------------------------------------------------------------------


def scan_express_routes(
    root: Any, file_path: str, language: str, route_info_cls: type
) -> list[Any]:
    routes: list[Any] = []
    http_methods = {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "options",
        "all",
        "use",
    }
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
        routes.append(
            route_info_cls(
                http_method=http_method,
                url_pattern=url_pattern,
                handler_name=handler_name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="express",
                language=language,
            )
        )
    return routes


# ---------------------------------------------------------------------------
# Java — Spring Boot annotations
# ---------------------------------------------------------------------------


_SPRING_ANNOTATION_MAP = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}


def scan_spring_annotations(
    root: Any, file_path: str, route_info_cls: type
) -> list[Any]:
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "marker_annotation" and node.type != "annotation":
            continue
        name_node = node.child_by_field_name("name")
        if name_node is None:
            continue
        ann_name = name_node.text.decode()
        simple_name = ann_name.rsplit(".", 1)[-1]
        http_method = _SPRING_ANNOTATION_MAP.get(simple_name)
        if not http_method:
            if simple_name == "RequestMapping":
                http_method, url_pattern = parse_request_mapping(node)
                if url_pattern is None:
                    continue
                routes.append(
                    route_info_cls(
                        http_method=http_method,
                        url_pattern=url_pattern,
                        handler_name=method_after_annotation(node),
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        framework="spring",
                        language="java",
                    )
                )
            continue
        url_pattern = extract_annotation_value(node) or ""
        routes.append(
            route_info_cls(
                http_method=http_method,
                url_pattern=url_pattern,
                handler_name=method_after_annotation(node),
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="spring",
                language="java",
            )
        )
    return routes


def _url_from_paren_child(node: Any) -> str | None:
    """Return the URL string literal that immediately follows '(' in node."""
    children = list(node.children)
    for idx, child in enumerate(children):
        if child.type == "(":
            nxt = children[idx + 1] if idx + 1 < len(children) else None
            if nxt is not None and nxt.type == "string_literal":
                return unquote_java_string(nxt.text.decode())
    return None


def _method_from_args_node(args_node: Any) -> str:
    """Return the HTTP method declared inside a @RequestMapping args node."""
    for child in args_node.children:
        text = child.text.decode()
        if "method" in text and "=" in text:
            m = re.search(r"RequestMethod\.(\w+)", text)
            if m:
                return m.group(1).upper()
            kw_node = find_keyword(args_node, "method")
            if kw_node:
                val = kw_node.child_by_field_name("value")
                if val:
                    vm = re.search(r"RequestMethod\.(\w+)", val.text.decode())
                    if vm:
                        return vm.group(1).upper()
    return "GET"


# ---------------------------------------------------------------------------
# Go — net/http, Gin, Echo, Fiber
# ---------------------------------------------------------------------------

_GO_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def _go_extract_string_arg(call_node: Any) -> str | None:
    """Extract the first interpreted_string literal from a Go call_expression."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return None
    for child in args_node.children:
        if child.type == "interpreted_string_literal":
            text = child.text.decode()
            if text.startswith('"') and text.endswith('"'):
                return text[1:-1]
    return None


def _go_handler_name(call_node: Any) -> str:
    """Extract the handler function name from a Go route registration call."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return "<unknown>"
    children = [c for c in args_node.children if c.type not in (",", "(", ")")]
    if len(children) >= 2:
        second = children[1]
        if second.type == "identifier":
            return second.text.decode()
        if second.type == "selector_expression":
            return second.text.decode()
        if second.type == "func_literal":
            return "<anonymous>"
        return second.text.decode()[:80]
    return "<unknown>"


def _go_method_from_call(call_node: Any) -> str | None:
    """Extract HTTP method from a Go Gin/Echo/Fiber-style call like r.GET(...)."""
    func = call_node.child_by_field_name("function")
    if func is None:
        return None
    if func.type == "selector_expression":
        method_node = func.child_by_field_name("field")
        if method_node is not None:
            method = method_node.text.decode().upper()
            if method in _GO_HTTP_METHODS:
                return method
    return None


def scan_go_net_http(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan Go files for net/http stdlib route registrations.

    Detects:
      - http.HandleFunc("/path", handler)
      - http.Handle("/path", handler)
      - mux.HandleFunc("/path", handler)
      - mux.Handle("/path", handler)
      - http.HandlerFunc("/path")
    """
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call_expression":
            continue
        func = node.child_by_field_name("function")
        if func is None:
            continue
        func_text = func.text.decode()
        method = None
        if func_text.endswith(".HandleFunc") or func_text.endswith(".Handle"):
            name_part = func_text.rsplit(".", 1)[-1]
            if name_part == "HandleFunc":
                method = "GET"
            elif name_part == "Handle":
                method = "GET"
        if method is None:
            continue
        url = _go_extract_string_arg(node)
        if url is None or not url.startswith("/"):
            continue
        handler = _go_handler_name(node)
        routes.append(
            route_info_cls(
                http_method=method,
                url_pattern=url,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="net/http",
                language="go",
            )
        )
    return routes


def scan_go_gin(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan Go files for Gin framework route registrations.

    Detects: r.GET("/path", handler), r.POST("/path", handler), etc.
    Also: router.GET(...), engine.GET(...), g.GET(...)
    """
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call_expression":
            continue
        http_method = _go_method_from_call(node)
        if http_method is None:
            continue
        url = _go_extract_string_arg(node)
        if url is None or not url.startswith("/"):
            continue
        handler = _go_handler_name(node)
        routes.append(
            route_info_cls(
                http_method=http_method,
                url_pattern=url,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="gin",
                language="go",
            )
        )
    return routes


def scan_go_echo(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan Go files for Echo framework route registrations.

    Detects: e.GET("/path", handler), e.POST("/path", handler), etc.
    Also detects: e.Any(...), e.Match(methods, "/path", handler)
    """
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call_expression":
            continue
        func = node.child_by_field_name("function")
        if func is None:
            continue
        if func.type != "selector_expression":
            continue
        method_node = func.child_by_field_name("field")
        if method_node is None:
            continue
        method_name = method_node.text.decode()
        http_method = None
        if method_name.upper() in _GO_HTTP_METHODS:
            http_method = method_name.upper()
        elif method_name == "Any":
            http_method = "ANY"
        elif method_name == "Match":
            http_method = "MATCH"
        if http_method is None:
            continue
        url = _go_extract_string_arg(node)
        if url is None or not url.startswith("/"):
            continue
        handler = _go_handler_name(node)
        routes.append(
            route_info_cls(
                http_method=http_method,
                url_pattern=url,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="echo",
                language="go",
            )
        )
    return routes


def scan_go_fiber(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan Go files for Fiber framework route registrations.

    Detects: app.Get("/path", handler), app.Post("/path", handler), etc.
    Fiber uses Title-Case method names (Get, Post, Put, Delete, etc.).
    """
    routes: list[Any] = []
    _fiber_method_map = {
        "Get": "GET",
        "Post": "POST",
        "Put": "PUT",
        "Delete": "DELETE",
        "Patch": "PATCH",
        "Head": "HEAD",
        "Options": "OPTIONS",
        "All": "ALL",
        "Use": "USE",
    }
    for node in walk(root):
        if node.type != "call_expression":
            continue
        func = node.child_by_field_name("function")
        if func is None:
            continue
        if func.type != "selector_expression":
            continue
        method_node = func.child_by_field_name("field")
        if method_node is None:
            continue
        go_method = method_node.text.decode()
        http_method = _fiber_method_map.get(go_method)
        if http_method is None:
            continue
        url = _go_extract_string_arg(node)
        if url is None or not url.startswith("/"):
            continue
        handler = _go_handler_name(node)
        routes.append(
            route_info_cls(
                http_method=http_method,
                url_pattern=url,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="fiber",
                language="go",
            )
        )
    return routes


def parse_request_mapping(node: Any) -> tuple[str, str | None]:
    """Extract (http_method, url_pattern) from a Spring @RequestMapping.

    Defaults to GET. Returns ``(method, None)`` if no URL pattern is found.
    """
    args_node = node.child_by_field_name("arguments")
    if args_node is None:
        return "GET", _url_from_paren_child(node)

    url: str | None = None
    for child in args_node.children:
        if child.type == "string_literal":
            url = unquote_java_string(child.text.decode())
            break
    method = _method_from_args_node(args_node)
    return method, url
