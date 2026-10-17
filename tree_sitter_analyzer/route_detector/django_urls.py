# mypy: disable-error-code="no-any-return, no-untyped-def"
"""Django ``urls.py`` route scanner for ``route_detector`` (#1650).

Recognised forms (bare callee identifiers, as imported from ``django.urls``):

- ``path("items/", views.items)`` / ``re_path(r"^x/$", view)``: one route per
  HTTP verb, because Django URL patterns do not restrict the method.
- ``path("api/", include("api.urls"))``: a URL *prefix* mount, not an
  endpoint. It is reported as one record with ``http_method="INCLUDE"``, the
  prefix as ``url_pattern`` and the included target as ``handler_name``
  (``"<inline>"`` for an inline list). This mirrors the Express / Fiber
  ``USE`` mount records. Prefixes are not composed into the included
  module's patterns, which keep the pattern as declared.

The scanner only runs when the file imports django, the same import gate the
Flask/FastAPI and Go scanners use, so a helper that happens to be called
``path`` is not reported as a route.
"""

from __future__ import annotations

import re
from typing import Any

from .helpers import extract_django_handler, unquote, walk

_DJANGO_ROUTE_CALLS = frozenset({"path", "re_path"})
_DJANGO_ALL_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")
_DJANGO_INCLUDE_METHOD = "INCLUDE"
_ARG_PUNCTUATION = frozenset({",", "(", ")", "comment"})
_PY_DJANGO_IMPORT_RE = re.compile(
    r"""(?xm)
    ^\s*
    (?:
        from\s+django(?:[.\s]|$)             # from django.urls import path
      | import\s+django(?:[.\s,]|$)           # import django.urls
    )
    """
)


def _source_text(root: Any, source: str) -> str:
    if source:
        return source
    try:
        return root.text.decode()
    except (AttributeError, UnicodeDecodeError):
        return ""


def _string_value(node: Any) -> str:
    """Return a Python string literal's value without quotes or ``r``/``u`` prefix."""
    if node.type == "string":
        parts = [c.text.decode() for c in node.children if c.type == "string_content"]
        if all(c.type != "interpolation" for c in node.children):
            return "".join(parts)
    return unquote(node.text.decode())


def _callee_name(call: Any) -> str | None:
    function = call.child_by_field_name("function")
    if function is None or function.type != "identifier":
        return None
    return function.text.decode()


def _include_target(call: Any) -> str:
    """Name what ``include(...)`` mounts: a module string, an expression, or inline."""
    args = call.child_by_field_name("arguments")
    positional = _positional_args(args) if args is not None else []
    if not positional:
        return "<unknown>"
    first = positional[0]
    if first.type in ("string", "concatenated_string"):
        return _string_value(first)
    if first.type in ("list", "tuple", "list_comprehension"):
        return "<inline>"
    return first.text.decode()[:80]


def _positional_args(args: Any) -> list[Any]:
    return [
        c
        for c in args.children
        if c.type not in _ARG_PUNCTUATION and c.type != "keyword_argument"
    ]


def _route_target(view: Any) -> tuple[str, tuple[str, ...]]:
    """Return ``(handler_name, methods)`` for the view argument of ``path()``."""
    if view.type == "call" and _callee_name(view) == "include":
        return _include_target(view), (_DJANGO_INCLUDE_METHOD,)
    return extract_django_handler(view.text.decode()), _DJANGO_ALL_METHODS


def scan_django_urls(
    root: Any, file_path: str, _source: str, route_info_cls: type
) -> list[Any]:
    if not _PY_DJANGO_IMPORT_RE.search(_source_text(root, _source)):
        return []
    routes: list[Any] = []
    for node in walk(root):
        if node.type != "call" or _callee_name(node) not in _DJANGO_ROUTE_CALLS:
            continue
        args = node.child_by_field_name("arguments")
        positional = _positional_args(args) if args is not None else []
        if len(positional) < 2:
            continue
        url_pattern = _string_value(positional[0])
        handler_name, methods = _route_target(positional[1])
        routes.extend(
            route_info_cls(
                http_method=method,
                url_pattern=url_pattern,
                handler_name=handler_name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                framework="django",
                language="python",
            )
            for method in methods
        )
    return routes
