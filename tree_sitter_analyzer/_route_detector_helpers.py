# mypy: disable-error-code="no-any-return, no-untyped-def"
"""Static helpers for route_detector — tree walking and per-framework text extraction.

Split out of route_detector.py to keep the main module under the project's 500-line
file-size cap. All functions are pure (no shared state) and operate on tree-sitter
nodes plus raw text. Tree-sitter Node has no type stubs in this repo (see
pyproject.toml mypy.overrides `ignore_missing_imports`), which makes
``node.text.decode()`` return Any and most arguments untyped. We disable the
corresponding mypy error codes locally rather than littering the source with
per-line ``# type: ignore`` comments.
"""

from __future__ import annotations

import re


def walk(node):
    """Yield every descendant of `node` in pre-order, using a tree-cursor."""
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False


def unquote(s: str) -> str:
    """Strip a single matched pair of leading/trailing quotes."""
    s = s.strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        return s[1:-1]
    return s


def unquote_java_string(s: str) -> str:
    """Strip a Java double-quoted string's surrounding quotes."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def parse_methods_list(methods_str: str) -> list[str]:
    """Extract quoted HTTP method names from a `methods=['GET', 'POST']` fragment."""
    methods = re.findall(r"['\"](\w+)['\"]", methods_str)
    return methods if methods else []


def function_name_after_decorator(decorator_node) -> str:
    """Return the name of the function/identifier sibling that follows a decorator."""
    parent = decorator_node.parent
    if parent is None:
        return "<unknown>"
    for child in parent.children:
        if child.type == "function_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                return name_node.text.decode()
        if child.type == "identifier":
            return child.text.decode()
    return "<unknown>"


def method_after_annotation(annotation_node) -> str:
    """Return the name of the Java method declared after an annotation."""
    parent = annotation_node.parent
    if parent is None:
        return "<unknown>"
    for child in parent.children:
        if child.type == "method_declaration":
            for mc in child.children:
                if mc.type == "identifier":
                    return mc.text.decode()
    return "<unknown>"


def find_keyword(args_node, keyword: str):
    """Find a Python keyword argument by name inside an `arguments` node."""
    for child in args_node.children:
        if child.type == "keyword_argument":
            for kc in child.children:
                if kc.type == "identifier" and kc.text.decode() == keyword:
                    return child
    return None


def extract_django_handler(text: str) -> str:
    """Extract the handler name from a Django `path()` view argument expression."""
    text = text.strip()
    dot_idx = text.rfind(".")
    if dot_idx != -1 and not text.startswith('"') and not text.startswith("'"):
        return text[dot_idx + 1:]
    if text.startswith(("views.", ".")):
        return text.split(".")[-1]
    return text.strip("'\"")


def extract_js_handler(args_node) -> str:
    """Extract the handler reference from an Express call's `arguments` node."""
    children = [
        c for c in args_node.children
        if c.type not in (",", "(", ")")
    ]
    if len(children) >= 2:
        second = children[1]
        if second.type == "identifier":
            return second.text.decode()
        if second.type == "arrow_function" or second.type == "function_expression":
            return "<anonymous>"
        if second.type == "call_expression":
            return second.text.decode()[:80]
    if len(children) >= 1:
        return children[0].text.decode()[:80]
    return "<unknown>"


def extract_template_string(node) -> str:
    """Extract the inner text of a JS template-literal route pattern."""
    for child in node.children:
        if child.type == "string":
            return child.text.decode().strip("\"'")
        if child.type == "template_string":
            inner = child.text.decode()
            if inner.startswith("`") and inner.endswith("`"):
                return inner[1:-1]
    text = node.text.decode()
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def extract_annotation_value(node) -> str | None:
    """Extract the literal `value=` of a Spring annotation, returning None if absent."""
    for child in node.children:
        if child.type == "(":
            idx = list(node.children).index(child)
            if idx + 1 < len(node.children):
                next_child = node.children[idx + 1]
                text = next_child.text.decode()
                if next_child.type in ("string_literal", "string"):
                    return text.strip("\"'")
                return text
    args_node = node.child_by_field_name("arguments")
    if args_node:
        for child in args_node.children:
            if child.type == "string_literal":
                return child.text.decode().strip("\"'")
            if child.type == "string":
                text = child.text.decode()
                return unquote(text)
    return None
