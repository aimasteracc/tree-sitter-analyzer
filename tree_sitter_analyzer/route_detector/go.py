# mypy: disable-error-code="no-any-return, no-untyped-def"
"""Go route scanners for ``route_detector``.

Supports four Go web stacks:

- ``net/http``: ``http.HandleFunc("/x", h)`` / ``http.Handle("/x", h)``
- Gin: ``r.GET("/x", h)`` / ``r.POST(...)`` / ... (uppercase HTTP verbs)
- Echo: ``e.GET(...)`` / ``e.Any("/x", h)``
- Fiber: ``app.Get(...)`` / ``app.Post(...)`` / ... (Title-Case verbs)

Framework dispatch is **import-driven**: Gin/Echo/Fiber scanners only run
when the file imports the corresponding package, so we don't double-count
``r.GET(...)`` as both Gin and Echo. The ``net/http`` scanner is gated
by a recognisable ``net/http`` import too — bare ``HandleFunc`` calls
in a non-HTTP file (rare but possible) get ignored.
"""

from __future__ import annotations

import re
from typing import Any

from .helpers import walk

_GO_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
)

_FIBER_METHOD_MAP = {
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

# Import-string patterns. Go imports look like:
#   import "net/http"
#   import "github.com/gin-gonic/gin"
#   import ( "github.com/labstack/echo" )
# We only need to know whether the import path appears at all — quote-included
# substring match is enough since Go import paths are always string literals.
_NET_HTTP_IMPORT_RE = re.compile(r'"net/http"')
_GIN_IMPORT_RE = re.compile(r'"github\.com/gin-gonic/gin[^"]*"')
_ECHO_IMPORT_RE = re.compile(r'"github\.com/labstack/echo[^"]*"')
_FIBER_IMPORT_RE = re.compile(r'"github\.com/gofiber/fiber[^"]*"')


def _go_source(root: Any) -> str:
    """Decode the parse-tree root's source. Empty string on failure."""
    try:
        return root.text.decode()
    except (AttributeError, UnicodeDecodeError):
        return ""


def _go_imports(source: str) -> dict[str, bool]:
    """Return a flat dict of which Go packages the file imports."""
    return {
        "net_http": bool(_NET_HTTP_IMPORT_RE.search(source)),
        "gin": bool(_GIN_IMPORT_RE.search(source)),
        "echo": bool(_ECHO_IMPORT_RE.search(source)),
        "fiber": bool(_FIBER_IMPORT_RE.search(source)),
    }


def _go_extract_string_arg(call_node: Any) -> str | None:
    """Extract the first interpreted_string literal from a Go call_expression."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return None
    for child in args_node.children:
        if child.type != "interpreted_string_literal":
            continue
        # Inner content node carries the unquoted text; fall back to stripping
        # quotes if the grammar doesn't expose it.
        for inner in child.children:
            if inner.type == "interpreted_string_literal_content":
                return inner.text.decode()
        text = child.text.decode()
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            return text[1:-1]
    return None


def _go_handler_name(call_node: Any) -> str:
    """Extract the handler argument from a Go route registration.

    The handler is the second positional argument (after the URL string).
    For ``http.Handle("/static/", http.FileServer(nil))`` we return the
    selector text (``http.FileServer``) — callers can match against that.
    """
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return "<unknown>"
    positional = [
        c for c in args_node.children if c.type not in (",", "(", ")", "comment")
    ]
    if len(positional) < 2:
        return "<unknown>"
    second = positional[1]
    node_type = second.type
    if node_type == "identifier":
        return second.text.decode()
    if node_type == "selector_expression":
        return second.text.decode()
    if node_type == "func_literal":
        return "<anonymous>"
    if node_type == "call_expression":
        # e.g. http.FileServer(nil) — return the called function's text.
        func = second.child_by_field_name("function")
        if func is not None:
            return func.text.decode()[:80]
        return second.text.decode()[:80]
    # Fall back to a truncated raw text — never the URL pattern.
    return second.text.decode()[:80]


def _selector_field(func_node: Any) -> str | None:
    """Return the ``field`` text from a selector_expression, or None."""
    if func_node is None or func_node.type != "selector_expression":
        return None
    field = func_node.child_by_field_name("field")
    if field is None:
        return None
    return field.text.decode()


def scan_go_net_http(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan a Go AST for net/http stdlib route registrations.

    Matches ``<recv>.HandleFunc("/x", h)`` and ``<recv>.Handle("/x", h)`` —
    typically ``http.HandleFunc`` or ``mux.HandleFunc``. The file must
    import ``net/http``.
    """
    source = _go_source(root)
    if not _NET_HTTP_IMPORT_RE.search(source):
        return []
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call_expression":
            continue
        field = _selector_field(node.child_by_field_name("function"))
        if field not in ("HandleFunc", "Handle"):
            continue
        url = _go_extract_string_arg(node)
        if url is None or not url.startswith("/"):
            continue
        handler = _go_handler_name(node)
        routes.append(
            route_info_cls(
                http_method="GET",  # net/http registers a handler for all methods; default to GET
                url_pattern=url,
                handler_name=handler,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="net/http",
                language="go",
            )
        )
    return routes


def _scan_go_verb_routes(
    root: Any,
    file_path: str,
    route_info_cls: type,
    *,
    framework: str,
    verb_map: dict[str, str] | None,
    accept_uppercase: bool,
    extra_verbs: dict[str, str] | None = None,
) -> list[Any]:
    """Generic verb-based Go route scanner used by Gin/Echo/Fiber.

    Parameters
    ----------
    verb_map:
        Optional explicit mapping (Fiber's Title-Case names → HTTP method).
    accept_uppercase:
        When True, any UPPERCASE name matching ``_GO_HTTP_METHODS`` is
        accepted (Gin / Echo behaviour).
    extra_verbs:
        Optional extra method aliases (Echo's ``Any``/``Match``).
    """
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call_expression":
            continue
        field = _selector_field(node.child_by_field_name("function"))
        if field is None:
            continue
        http_method: str | None = None
        if verb_map is not None and field in verb_map:
            http_method = verb_map[field]
        elif accept_uppercase and field.upper() == field and field in _GO_HTTP_METHODS:
            http_method = field
        elif extra_verbs is not None and field in extra_verbs:
            http_method = extra_verbs[field]
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
                framework=framework,
                language="go",
            )
        )
    return routes


def scan_go_gin(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan for Gin routes — ``r.GET("/x", h)``, ``r.POST(...)``, etc."""
    source = _go_source(root)
    if not _GIN_IMPORT_RE.search(source):
        return []
    return _scan_go_verb_routes(
        root,
        file_path,
        route_info_cls,
        framework="gin",
        verb_map=None,
        accept_uppercase=True,
    )


def scan_go_echo(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan for Echo routes — ``e.GET(...)``, ``e.Any(...)``, ``e.Match(...)``."""
    source = _go_source(root)
    if not _ECHO_IMPORT_RE.search(source):
        return []
    return _scan_go_verb_routes(
        root,
        file_path,
        route_info_cls,
        framework="echo",
        verb_map=None,
        accept_uppercase=True,
        extra_verbs={"Any": "ANY", "Match": "MATCH"},
    )


def scan_go_fiber(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Scan for Fiber routes — ``app.Get(...)``, ``app.Post(...)``, etc.

    Fiber uses Title-Case method names that don't collide with Gin/Echo's
    UPPERCASE convention.
    """
    source = _go_source(root)
    if not _FIBER_IMPORT_RE.search(source):
        return []
    return _scan_go_verb_routes(
        root,
        file_path,
        route_info_cls,
        framework="fiber",
        verb_map=_FIBER_METHOD_MAP,
        accept_uppercase=False,
    )


def scan_go_routes(root: Any, file_path: str, route_info_cls: type) -> list[Any]:
    """Run all four Go framework scanners on a parsed Go file.

    Each scanner self-gates on imports so this composite is safe.
    """
    routes: list[Any] = []
    routes.extend(scan_go_net_http(root, file_path, route_info_cls))
    routes.extend(scan_go_gin(root, file_path, route_info_cls))
    routes.extend(scan_go_echo(root, file_path, route_info_cls))
    routes.extend(scan_go_fiber(root, file_path, route_info_cls))
    return routes


def go_imports(source: str) -> dict[str, bool]:
    """Public alias for ``_go_imports`` used by tests."""
    return _go_imports(source)
