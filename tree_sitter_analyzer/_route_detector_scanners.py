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
    extract_template_string,
    find_keyword,
    function_name_after_decorator,
    method_after_annotation,
    parse_methods_list,
    unquote,
    unquote_java_string,
    walk,
)

# Finding F4: AST node types whose presence anywhere in the argument list
# means the call cannot be a normal ``app.get(url, callback)`` route — they
# replace the callback slot with a non-callable value. We surface a marker
# string (``<object>`` / ``<inline>``) instead of falling back to the URL
# pattern, which used to leak through as a bogus ``handler_name``.
_OBJECT_HANDLER_TYPES = frozenset(
    {
        "object",  # { method: 'GET', fn: handler } — config object
        "object_pattern",  # destructuring (rare, but legal at this slot)
    }
)
_INLINE_HANDLER_TYPES = frozenset(
    {
        "arrow_function",  # (req, res) => res.send('ok')
        "function_expression",  # function (req, res) { ... }
        "function",  # bare ``function`` node in some grammars
    }
)
_REFERENCE_HANDLER_TYPES = frozenset(
    {
        "identifier",  # myHandler
        "member_expression",  # users.list
        "call_expression",  # myFn.bind(this)  / wrap(handler)
        "subscript_expression",  # handlers['get']  (TS subscript form)
    }
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


# Finding 3: receiver-name whitelist for Express HTTP-verb calls.
#
# The previous implementation matched ``X.post(...)`` for any identifier X
# whose first arg started with ``/``. That mis-classifies client-side HTTP
# wrappers like ``apiClient.post('/save', ...)`` (and any custom RPC helper
# named with an HTTP verb) as Express routes — they are not, and the file
# usually does not even import ``express``.
#
# We now require the receiver name to:
#   (a) be in a small, conventional whitelist (``app``/``router``/``server``
#       /``api``), OR
#   (b) end with ``Router`` / ``router`` (e.g. ``userRouter``, ``adminRouter``,
#       ``v2Router``), which is by far the most common naming pattern for
#       Express ``Router()`` instances.
#
# As an additional gate the source file must contain a recognisable Express
# import (``require('express')`` / ``from 'express'`` / dynamic ``import('express')``).
# Both checks must pass — receiver-name on its own would still misfire when a
# custom helper happens to be named ``app`` or ``router``; the import check
# alone is too loose because real codebases sometimes have client utilities
# in the same file as the Express setup.
_EXPRESS_RECEIVER_WHITELIST = frozenset({"app", "router", "server", "api", "express"})
# Accept identifiers that *end* in "Router" or "router". Covers:
#   userRouter, AdminRouter, v2Router       (CamelCase)
#   user_router, admin_router               (snake_case)
#   Router, router                          (bare — already in the whitelist)
# Rejects identifiers that merely *contain* router (routerHelper, RouterFactory).
_EXPRESS_RECEIVER_SUFFIX = re.compile(r"[A-Za-z0-9_$]+[Rr]outer$")
_EXPRESS_IMPORT_RE = re.compile(
    r"""(?x)
    (?:
        \brequire\s*\(\s*['"]express['"]\s*\)        # CommonJS require
      | \bfrom\s+['"]express['"]                       # ES module import
      | \bimport\s*\(\s*['"]express['"]\s*\)          # dynamic import()
    )
    """
)


def _file_imports_express(root: Any) -> bool:
    """Return True when the parsed file imports ``express`` in any form."""
    try:
        source = root.text.decode()
    except (AttributeError, UnicodeDecodeError):
        return False
    return bool(_EXPRESS_IMPORT_RE.search(source))


def _is_express_receiver(receiver: str) -> bool:
    """Decide whether ``receiver`` (the text before ``.get``/``.post``/...)
    looks like an Express ``app``/``router`` reference.

    A receiver may be a chain like ``users.router`` — we only consider the
    last identifier in the chain so chained ``router`` accessors still match.
    """
    if not receiver:
        return False
    tail = receiver.rsplit(".", 1)[-1]
    if tail in _EXPRESS_RECEIVER_WHITELIST:
        return True
    return bool(_EXPRESS_RECEIVER_SUFFIX.search(tail))


def _extract_express_handler_name(args_node: Any) -> str:
    """Resolve the handler name for an Express ``app.<verb>(...)`` call.

    Finding F4: ``extract_js_handler`` (in ``_route_detector_helpers``) only
    looked at the second positional argument. When that slot held an
    *object literal* (e.g. ``{ method: 'GET', fn: handler }``) — or when
    Express received a middleware array followed by the real callback —
    the function silently fell back to the URL pattern (``children[0]``),
    so we ended up reporting the URL itself as the ``handler_name``.

    The new contract:

    - if the callback slot holds a function expression  -> ``<inline>`` (or
      the variable name when the grammar exposes one)
    - if it holds a callable reference (identifier, member expression,
      ``foo.bind(...)``)                                -> that reference
    - if it holds an object/array literal               -> ``<object>``
    - else                                              -> ``<unknown>``

    We scan all positional args (skipping the URL pattern and any
    middleware-array slots) and return the *last* callable-shaped child,
    matching Express's "last function wins" semantics. When none of the
    args look callable but one is clearly a config object, we return
    ``<object>`` so the symbol can never be mistaken for an identifier.
    """
    positional: list[Any] = [
        c
        for c in args_node.children
        if c.type not in (",", "(", ")", "comment", "line_comment", "block_comment")
    ]
    # First positional is the URL pattern — handled by the caller. Walk the
    # rest looking for the last callable slot.
    if len(positional) < 2:
        return "<unknown>"
    rest = positional[1:]

    last_callable: Any | None = None
    saw_object = False
    for arg in rest:
        node_type = arg.type
        if node_type in _INLINE_HANDLER_TYPES:
            last_callable = arg
        elif node_type in _REFERENCE_HANDLER_TYPES:
            last_callable = arg
        elif node_type in _OBJECT_HANDLER_TYPES:
            saw_object = True
        elif node_type == "array":
            # Middleware list — not the handler itself; ignored.
            continue
        elif node_type in ("string", "template_string"):
            # A literal-string handler is legal in some routers; treat it
            # the same way extract_js_handler did: strip quotes, cap length.
            last_callable = arg
        # Anything else (numbers, booleans, ``null``, ``undefined``) is
        # ignored — they cannot be real handlers and we'd rather report
        # ``<unknown>`` than something misleading.

    if last_callable is not None:
        node_type = last_callable.type
        if node_type in _INLINE_HANDLER_TYPES:
            return "<inline>"
        if node_type == "call_expression":
            return last_callable.text.decode()[:80]
        if node_type in ("string", "template_string"):
            return last_callable.text.decode().strip("\"'`")[:80]
        # identifier / member_expression / subscript_expression
        return last_callable.text.decode()[:80]

    if saw_object:
        return "<object>"
    return "<unknown>"


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
    file_imports_express = _file_imports_express(root)
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
        receiver, method_name = parts[0], parts[1].lower()
        if method_name not in http_methods:
            continue
        # Finding 3: skip non-Express receivers (apiClient.post,
        # fetcher.get, etc.). Require both signals — receiver shape
        # AND a recognisable express import in the file — before
        # treating the call as a route.
        if not _is_express_receiver(receiver):
            continue
        if not file_imports_express:
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
        handler_name = _extract_express_handler_name(args_node)
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


def parse_request_mapping(node: Any) -> tuple[str, str | None]:
    """Extract (http_method, url_pattern) from a Spring @RequestMapping.

    Defaults to GET. Returns ``(method, None)`` if no URL pattern is found.
    """
    method = "GET"
    url: str | None = None
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
                        vm = re.search(r"RequestMethod\.(\w+)", val.text.decode())
                        if vm:
                            method = vm.group(1).upper()
    return method, url
