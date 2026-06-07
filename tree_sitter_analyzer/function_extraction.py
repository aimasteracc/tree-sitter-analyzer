"""Shared function-definition and call-site extraction helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

_CALL_NODE_TYPES = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "java": {"method_invocation", "class_body"},
    "go": {"call_expression"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
    # RFC-0010 activation (node types verified empirically against each grammar).
    "rust": {"call_expression", "macro_invocation"},
}

_FUNC_DEF_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
    "rust": {"function_item"},
}

# ---------------------------------------------------------------------------
# Per-language function-name extractors
# ---------------------------------------------------------------------------

_IDENT_TYPES_JS = ("identifier", "property_identifier")
_IDENT_TYPES_GO = ("identifier", "field_identifier")
_IDENT_TYPES_C = ("identifier", "field_identifier", "destructor_name")


def _func_name_identifier(node: Any) -> str | None:
    """Python / Java: first ``identifier`` child."""
    for child in node.children:
        if child.type == "identifier":
            return _node_text_value(child)
    return None


def _func_name_js(node: Any) -> str | None:
    """JavaScript / TypeScript: identifier or property_identifier child."""
    for child in node.children:
        if child.type in _IDENT_TYPES_JS:
            return _node_text_value(child)
    return None


def _func_name_go(node: Any) -> str | None:
    """Go: prefer named field, fall back to identifier/field_identifier child."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text_value(name_node)
    for child in node.children:
        if child.type in _IDENT_TYPES_GO:
            return _node_text_value(child)
    return None


def _declarator_name(declarator_node: Any) -> str | None:
    """Find the first identifier inside a ``function_declarator`` node."""
    for sub in declarator_node.children:
        if sub.type in ("identifier", "field_identifier"):
            return _node_text_value(sub)
    return None


def _func_name_c(node: Any) -> str | None:
    """C / C++: direct identifier types, or recurse into function_declarator."""
    for child in node.children:
        if child.type in _IDENT_TYPES_C:
            return _node_text_value(child)
        if child.type == "function_declarator":
            result = _declarator_name(child)
            if result:
                return result
    return None


def _func_name_field(node: Any) -> str | None:
    """Rust / Kotlin / Ruby / C# / PHP: name lives in the ``name`` field."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text_value(name_node)
    # Fallback: first identifier-ish child (grammars vary).
    for child in node.children:
        if child.type in ("identifier", "simple_identifier", "name", "constant"):
            return _node_text_value(child)
    return None


_FUNC_NAME_DISPATCH: dict[str, Callable] = {
    "python": _func_name_identifier,
    "javascript": _func_name_js,
    "typescript": _func_name_js,
    "java": _func_name_identifier,
    "go": _func_name_go,
    "c": _func_name_c,
    "cpp": _func_name_c,
    # RFC-0010 activation: wire call-edge extraction for the resolver-ready langs.
    "rust": _func_name_field,
}

# ---------------------------------------------------------------------------
# Per-language call-info extractors
# ---------------------------------------------------------------------------


def _call_info_field(node: Any, source: str) -> dict[str, Any] | None:
    """Python / JS / TS / Go: extract call target from the ``function`` field."""
    func_node = node.child_by_field_name("function")
    if func_node is None:
        return None
    return _call_from_text(_node_text(func_node, source), node)


def _call_info_java(node: Any, source: str) -> dict[str, Any] | None:
    """Java method_invocation: method name from the ``name`` field, receiver
    from the ``object`` field.

    ``list.add("x")`` must extract ``name='add'`` with ``receiver='list'`` (so
    RFC-0008 stdlib/external method tiers can match the method name), NOT the
    receiver identifier ``list``. tree-sitter-java exposes the method as the
    ``name`` field and the receiver as the ``object`` field; a bare call
    ``verify(s)`` has no ``object`` field (receiver is ``None``).
    """
    if node.type == "method_invocation":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = _node_text(name_node, source)
            obj_node = node.child_by_field_name("object")
            receiver = _node_text(obj_node, source) if obj_node is not None else None
            full_name = f"{receiver}.{name}" if receiver else name
            return {
                "name": name,
                "full_name": full_name,
                "line": node.start_point[0] + 1,
                "receiver": receiver,
            }
    for child in node.children:
        if child.type == "identifier":
            return _call_from_text(_node_text(child, source), node)
        if child.type in ("field_access", "method_reference"):
            return _call_from_text(_node_text(child, source), node)
    return None


def _call_info_c(node: Any, source: str) -> dict[str, Any] | None:
    """C / C++: prefer function field, fall back to first identifier child."""
    func_node = node.child_by_field_name("function")
    if func_node is not None:
        name = _node_text(func_node, source)
        return {
            "name": name,
            "full_name": name,
            "line": node.start_point[0] + 1,
            "receiver": None,
        }
    for child in node.children:
        if child.type == "identifier":
            return _call_from_text(_node_text(child, source), node)
    return None


def _call_info_rust(node: Any, source: str) -> dict[str, Any] | None:
    """Rust: ``call_expression`` exposes the callee in the ``function`` field
    (an identifier like ``foo`` or a ``field_expression`` like ``x.to_string``);
    ``macro_invocation`` (``println!``, ``format!``) exposes it in the ``macro``
    field. Never cross-language binds — the resolver gates by language family.
    """
    if node.type == "macro_invocation":
        macro_node = node.child_by_field_name("macro")
        if macro_node is not None:
            name = _node_text(macro_node, source)
            return {
                "name": name,
                "full_name": name,
                "line": node.start_point[0] + 1,
                "receiver": None,
            }
        return None
    func_node = node.child_by_field_name("function")
    if func_node is not None:
        return _call_from_text(_node_text(func_node, source), node)
    return None


_CALL_DISPATCH: dict[str, Callable] = {
    "python": _call_info_field,
    "javascript": _call_info_field,
    "typescript": _call_info_field,
    "go": _call_info_field,
    "java": _call_info_java,
    "c": _call_info_c,
    "cpp": _call_info_c,
    "rust": _call_info_rust,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_tree(node: Any, source: str, language: str) -> tuple[list[dict], list[dict]]:
    """Walk an AST and return function definitions plus call sites."""
    definitions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    fixture_types = _collect_fixture_types(node, source, language)
    _extract_recursive(
        node, source, language, definitions, calls, None, None, fixture_types
    )
    return definitions, calls


def _collect_local_var_types(
    func_node: Any, source: str, language: str
) -> dict[str, tuple[str, int]]:
    """RFC-0002: infer local variable types from ``var = ClassName(...)``.

    Returns ``{var: (class, assign_line)}``. The line makes typing
    flow-sensitive (P2, Codex): a call only takes the type if it appears AT or
    AFTER the binding line — ``pg.execute(); pg = ProjectGraph()`` must NOT type
    the pre-binding call. Static, Python only.
    """
    if language != "python":
        return {}
    types: dict[str, tuple[str, int]] = {}

    def _walk(n: Any) -> None:
        if getattr(n, "type", None) == "assignment":
            left = n.child_by_field_name("left")
            right = n.child_by_field_name("right")
            if (
                left is not None
                and right is not None
                and left.type == "identifier"
                and right.type == "call"
            ):
                fn = right.child_by_field_name("function")
                if fn is not None and fn.type == "identifier":
                    cls = _node_text(fn, source)
                    if cls and cls[0].isupper():
                        types[_node_text(left, source)] = (cls, n.start_point[0] + 1)
        for c in n.children:
            _walk(c)

    _walk(func_node)
    return types


def _func_param_names(func_node: Any, source: str) -> list[str]:
    """Parameter identifier names of a Python function def."""
    params = func_node.child_by_field_name("parameters")
    if params is None:
        return []
    names: list[str] = []
    for c in params.children:
        if c.type == "identifier":
            names.append(_node_text(c, source))
        elif c.type in (
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
        ):
            for sub in c.children:
                if sub.type == "identifier":
                    names.append(_node_text(sub, source))
                    break
    return names


def _infer_return_class(func_node: Any, source: str) -> str | None:
    """Infer the class a Python function returns: ``return ClassName(...)`` or
    ``v = ClassName(...); return v``. Used for pytest-fixture return types."""
    local = _collect_local_var_types(func_node, source, "python")
    result: str | None = None

    def _walk(n: Any) -> None:
        nonlocal result
        if getattr(n, "type", None) == "return_statement":
            for c in n.children:
                if c.type == "call":
                    fn = c.child_by_field_name("function")
                    if fn is not None and fn.type == "identifier":
                        cls = _node_text(fn, source)
                        if cls and cls[0].isupper():
                            result = cls
                elif c.type == "identifier":
                    v = _node_text(c, source)
                    if v in local:
                        result = local[v][0]
        for ch in n.children:
            _walk(ch)

    _walk(func_node)
    return result


def _collect_fixture_types(
    module_node: Any, source: str, language: str
) -> dict[str, str]:
    """RFC-0002: map function name → returned class, for pytest-fixture typing.

    A pytest test parameter is named after a fixture function; if that fixture
    returns ``ClassName(...)``, the test's parameter has that type. This is the
    dominant test pattern (``def tool(): return SearchContentTool()`` +
    ``def test(self, tool): tool.execute()`` → tool: SearchContentTool). Static,
    no runtime. Python only.
    """
    if language != "python":
        return {}
    types: dict[str, str] = {}

    def _walk(n: Any) -> None:
        # P2 (Codex): only treat ACTUAL pytest fixtures as fixtures — a
        # decorated_definition whose decorator mentions 'fixture'. A plain
        # ``def client(): return HttpClient()`` is NOT a fixture, so a normal
        # parameter named ``client`` must not be typed.
        if getattr(n, "type", None) == "decorated_definition":
            deco_text = ""
            inner = None
            for c in n.children:
                if c.type == "decorator":
                    deco_text += _node_text(c, source)
                elif c.type == "function_definition":
                    inner = c
            if inner is not None and "fixture" in deco_text:
                fname = get_func_name(inner, "python")
                rcls = _infer_return_class(inner, source)
                if fname and rcls:
                    types[fname] = rcls
        for c in n.children:
            _walk(c)

    _walk(module_node)
    return types


def _extract_recursive(
    node: Any,
    source: str,
    language: str,
    definitions: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    enclosing_class: str | None,
    local_types: dict[str, tuple[str, int]] | None,
    fixture_types: dict[str, str] | None = None,
) -> None:
    if not hasattr(node, "type"):
        return

    node_type = node.type
    if node_type in _FUNC_DEF_TYPES.get(language, set()):
        func_name = get_func_name(node, language)
        if func_name:
            parent_class = enclosing_class
            if language == "python":
                parent_class = find_parent_class_python(node) or enclosing_class
            elif language == "java":
                parent_class = find_parent_class_java(node) or enclosing_class
            elif language == "go" and node.type == "method_declaration":
                parent_class = find_receiver_type_go(node) or enclosing_class

            definitions.append(
                {
                    "name": func_name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "class": parent_class,
                }
            )
            func_types = _collect_local_var_types(node, source, language)
            # pytest-fixture typing: a parameter named after a fixture function
            # that returns a class gets that class's type. line 0 = valid for the
            # whole function body (a parameter is bound on entry).
            if language == "python" and fixture_types:
                for pname in _func_param_names(node, source):
                    if pname in fixture_types:
                        func_types[pname] = (fixture_types[pname], 0)
            for child in node.children:
                _extract_recursive(
                    child,
                    source,
                    language,
                    definitions,
                    calls,
                    parent_class,
                    func_types,
                    fixture_types,
                )
            return

    if node_type in _CALL_NODE_TYPES.get(language, set()):
        call_info = extract_call(node, source, language)
        if call_info:
            recv = call_info.get("receiver")
            if local_types and recv in local_types:
                cls, bind_line = local_types[recv]
                # flow-sensitive (P2): only type calls at/after the binding line
                if (node.start_point[0] + 1) >= bind_line:
                    call_info["receiver_type"] = cls
                    call_info["full_name"] = f"{cls}.{call_info['name']}"
            calls.append(call_info)

    for child in node.children:
        _extract_recursive(
            child,
            source,
            language,
            definitions,
            calls,
            enclosing_class,
            local_types,
            fixture_types,
        )


def get_func_name(node: Any, language: str) -> str | None:
    """Extract a function or method name from a definition node."""
    handler = _FUNC_NAME_DISPATCH.get(language)
    if handler is None:
        return None
    try:
        return cast("str | None", handler(node))
    except Exception:  # nosec B110
        return None


def extract_call(node: Any, source: str, language: str) -> dict[str, Any] | None:
    """Extract call target info from a call node."""
    handler = _CALL_DISPATCH.get(language)
    if handler is None:
        return None
    try:
        return cast("dict[str, Any] | None", handler(node, source))
    except Exception:  # nosec B110
        return None


def _call_from_text(text: str, node: Any) -> dict[str, Any]:
    receiver = None
    name = text
    if "." in name:
        receiver, name = name.rsplit(".", 1)
    return {
        "name": name,
        "full_name": text,
        "line": node.start_point[0] + 1,
        "receiver": receiver,
    }


def node_text(node: Any, source: str) -> str:
    """Extract text from a node using UTF-8 byte offsets safely."""
    return _node_text(node, source)


def _node_text(node: Any, source: str) -> str:
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        try:
            return text_attr.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return ""
    if isinstance(text_attr, str):
        return text_attr
    try:
        return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except (IndexError, TypeError, UnicodeDecodeError):
        return ""


def find_parent_class_python(node: Any) -> str | None:
    """Walk up from a Python function node to find an enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            for child in current.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        current = current.parent
    return None


def find_parent_class_java(node: Any) -> str | None:
    """Walk up from a Java method node to find an enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_declaration":
            for child in current.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        current = current.parent
    return None


def find_receiver_type_go(node: Any) -> str | None:
    """Extract the receiver type from a Go method_declaration node."""
    if node is None or node.type != "method_declaration":
        return None
    for child in node.children:
        if child.type == "parameter_list":
            for param in child.children:
                for sub in param.children if hasattr(param, "children") else []:
                    if sub.type in ("type_identifier", "generic_type", "pointer_type"):
                        return _node_text_value(sub).lstrip("*")
                    for leaf in sub.children if hasattr(sub, "children") else []:
                        if leaf.type in ("type_identifier", "generic_type"):
                            return _node_text_value(leaf).lstrip("*")
    return None


def _node_text_value(node: Any) -> str:
    text = node.text
    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
