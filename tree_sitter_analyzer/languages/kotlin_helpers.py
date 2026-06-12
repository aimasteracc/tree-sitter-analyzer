"""Kotlin import, visibility, and utility helpers — extracted from kotlin_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error


def extract_import(node: Any, get_node_text: Callable[..., str]) -> Import | None:
    """Extract a Kotlin import statement.

    Reads the AST children instead of splitting the statement text, so
    trailing semicolons, inline comments, wildcards and aliases all yield
    clean qualified names:

        import (statement node)
          'import' keyword leaf  <- same node type; has no children -- skip
          qualified_identifier   <- the module path
          [ '.' '*' ]            <- wildcard import
          [ 'as' identifier ]    <- alias import
          [ ';' ]                <- optional terminator

    Falls back to whitespace parsing for grammar versions that emit
    ``import_header`` without a ``qualified_identifier`` child.
    """
    try:
        raw_text = get_node_text(node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        qualified: str | None = None
        is_wildcard = False
        alias: str | None = None
        saw_as = False
        for child in node.children:
            if child.type == "qualified_identifier":
                qualified = get_node_text(child)
            elif child.type == "*":
                is_wildcard = True
            elif child.type == "as":
                saw_as = True
            elif child.type == "identifier" and saw_as:
                alias = get_node_text(child)

        if qualified is None:
            # Leaf 'import' keyword token (no children) or an older grammar's
            # import_header: fall back to text parsing.
            parts = raw_text.split()
            if len(parts) < 2:
                return None
            name = parts[1].rstrip(";")
            is_wildcard = name.endswith(".*")
        else:
            name = qualified + (".*" if is_wildcard else "")

        return Import(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            import_statement=raw_text,
            module_name=name,
            is_wildcard=is_wildcard,
            alias=alias,
        )
    except Exception as e:
        log_error(f"Error extracting Kotlin import: {e}")
        return None


def determine_visibility(modifiers_text: str) -> str:
    """Determine visibility from Kotlin modifiers text."""
    if "private" in modifiers_text:
        return "private"
    elif "protected" in modifiers_text:
        return "protected"
    elif "internal" in modifiers_text:
        return "internal"
    return "public"


def extract_kotlin_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """Extract Kotlin function parameters.

    r37dt (dogfood): flatten nesting 6 → 3 via ``_kotlin_parameter_pair``.
    Theme E (2026-06-10): tree-sitter-kotlin exposes the parameter list as a
    child node of type ``function_value_parameters``, not as a named field
    ``"parameters"`` — ``child_by_field_name("parameters")`` always returned
    None, leaving every Kotlin function with zero parameters.  Scan children
    for the correct node type.  Also track ``parameter_modifiers`` (e.g.
    ``vararg``) immediately preceding a ``parameter`` node and prepend the
    modifier text to the emitted parameter string.
    """
    parameters: list[str] = []
    params_node = None
    for child in node.children:
        if child.type == "function_value_parameters":
            params_node = child
            break
    if params_node is None:
        return parameters
    pending_modifier: str = ""
    for child in params_node.children:
        if child.type == "parameter_modifiers":
            pending_modifier = get_node_text(child)
        elif child.type == "parameter":
            param_name, param_type = _kotlin_parameter_pair(child, get_node_text)
            if param_name:
                if pending_modifier:
                    parameters.append(
                        f"{pending_modifier} {param_name}: {param_type or 'Any'}"
                    )
                else:
                    parameters.append(f"{param_name}: {param_type or 'Any'}")
            pending_modifier = ""
        else:
            pending_modifier = ""
    return parameters


def _kotlin_parameter_pair(
    parameter_node: Any, get_node_text: Callable[..., str]
) -> tuple[str, str]:
    """Return ``(name, type)`` from a Kotlin ``parameter`` AST node.

    Iterates the parameter node's children looking for a name node
    (``simple_identifier`` or ``identifier`` — grammar version-dependent)
    and a type-like node (``user_type`` or any node whose ``type`` string
    contains ``"type"``). Empty strings default when either part is missing;
    caller fills ``"Any"`` for blank types.

    Theme E (2026-06-10): tree-sitter-kotlin emits ``identifier`` (not
    ``simple_identifier``) for parameter names in the tested grammar version;
    accept both so the helper works across grammar versions.
    """
    param_name = ""
    param_type = ""
    for grandchild in parameter_node.children:
        if grandchild.type in ("simple_identifier", "identifier"):
            if not param_name:  # first identifier is the name
                param_name = get_node_text(grandchild)
        elif "type" in grandchild.type or grandchild.type == "user_type":
            param_type = get_node_text(grandchild)
    return param_name, param_type


def _kotlin_extension_receiver(
    node: Any, get_node_text: Callable[..., str]
) -> str | None:
    """Return the extension receiver type name, or None.

    ``fun String.shout()`` parses as:
        function_declaration
          user_type  ← receiver type
          .
          identifier ← function name
          …

    We detect the pattern by scanning children for a ``user_type`` node
    that is immediately followed by a ``.`` child before any
    ``function_value_parameters`` node.
    """
    children = list(node.children)
    for i, child in enumerate(children):
        if child.type == "function_value_parameters":
            break
        if child.type in ("user_type", "nullable_type"):
            # Check next non-error sibling is '.'
            # P2a (2026-06-11 adversarial review): ``fun String?.safe()``
            # emits a ``nullable_type`` node (not ``user_type``) before the
            # dot — return its full text including the trailing '?'.
            if i + 1 < len(children) and children[i + 1].type == ".":
                return get_node_text(child)
    return None


def _kotlin_owning_type(node: Any) -> tuple[str | None, bool]:
    """Walk the parent chain and return ``(owner_name, is_companion)``.

    Traversal stops at the first owning declaration:
    - ``class_declaration`` → (name, False) for regular class members
    - ``object_declaration`` → (name, False) for object members
    - ``companion_object`` → walk further to the enclosing
      ``class_declaration`` and return (name, True)
    - ``source_file`` or None → (None, False)

    Boundary nodes that abort the walk with (None, False):
    - ``function_declaration``: local functions declared inside a method
      body must not be attributed to the outer class.
    - ``object_literal``: ``override fun`` inside an anonymous
      ``object : Runnable { ... }`` inside a method belongs to the
      anonymous object, not the enclosing class.

    The walk traverses through ``enum_class_body`` without stopping —
    enum entries can contain method declarations that belong to the enum.

    Depth-capped at 256 to prevent unbounded loops on non-conforming node
    objects (e.g. MagicMock infinite parent chains — 140 GB OOM 2026-06-10).
    """
    parent = node.parent
    in_companion = False
    for _ in range(256):
        if parent is None:
            return None, False
        if parent.type == "source_file":
            return None, False
        # P1 (2026-06-11 adversarial review): local funs and anonymous-object
        # overrides must not be attributed to the outer enclosing class.
        if parent.type in ("function_declaration", "object_literal"):
            return None, False
        if parent.type == "companion_object":
            in_companion = True
        elif parent.type in ("class_declaration", "object_declaration"):
            name_node = parent.child_by_field_name("name")
            if name_node is None:
                for child in parent.children:
                    if child.type == "identifier":
                        name_node = child
                        break
            if name_node is not None:
                # Use node.text if available (real tree-sitter nodes),
                # otherwise fall back to a callable get_node_text is not
                # in scope here, so we rely on node.text directly.
                try:
                    name = name_node.text.decode("utf-8", errors="replace")
                except (AttributeError, UnicodeDecodeError):
                    name = str(name_node.text)
                return name, in_companion
            return None, False
        parent = parent.parent
    return None, False


def _kotlin_expression_body_type(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Infer the return type of an expression-body function (issue #591).

    Returns:
        * ``None`` — no expression body (block body or abstract fun);
          caller keeps the ``Unit`` default, which is correct there.
        * a pinned literal type (``String``/``Int``/``Boolean``/``Double``)
          for trivial literal bodies.
        * ``""`` (unknown) for any other expression body — honest "no
          claim", never a fabricated ``Unit``.
    """
    body = None
    for child in node.children:
        if child.type == "function_body":
            body = child
            break
    if body is None or body.child_count == 0 or body.children[0].type != "=":
        return None  # block body or no body → Unit default is correct
    if body.child_count < 2:
        return ""
    expr = body.children[1]
    if expr.type == "string_literal":
        return "String"
    if expr.type == "float_literal":
        return "Double"
    if expr.type == "number_literal":
        # Only pure-digit literals are Int; 42L / 0xFF etc. stay unknown.
        text = get_node_text(expr)
        return "Int" if text.isdigit() else ""
    if expr.type in ("boolean_literal", "identifier"):
        if get_node_text(expr) in ("true", "false"):
            return "Boolean"
        return ""
    return ""


def extract_kotlin_function(
    node: Any,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Function | None:
    """Extract Kotlin function declaration."""
    try:
        name = "anonymous"
        name_node = node.child_by_field_name("name")
        if name_node:
            name = get_node_text(name_node)
        else:
            for child in node.children:
                if child.type == "simple_identifier":
                    name = get_node_text(child)
                    break
            # Extension funs: name identifier follows the '.' after receiver type
            if name == "anonymous":
                children = list(node.children)
                for i, child in enumerate(children):
                    if child.type == "." and i + 1 < len(children):
                        if children[i + 1].type == "identifier":
                            name = get_node_text(children[i + 1])
                            break

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        parameters = extract_kotlin_parameters(node, get_node_text)

        return_type = "Unit"
        explicit_type = False
        for i, child in enumerate(node.children):
            if child.type == ":":
                if i + 1 < len(node.children):
                    return_type = get_node_text(node.children[i + 1])
                    explicit_type = True
                break
        if not explicit_type:
            # Issue #591: ``fun get() = "legacy"`` must not claim Unit — the
            # expression body infers the type. Full inference is a non-goal;
            # pin trivial literals, otherwise emit "" (unknown, matching the
            # Go plugin's absent-return-type convention). Block bodies
            # ``{ ... }`` without an explicit type really are Unit — keep.
            inferred = _kotlin_expression_body_type(node, get_node_text)
            if inferred is not None:
                return_type = inferred

        visibility = "public"
        is_suspend = False
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            mods = get_node_text(modifiers_node)
            visibility = determine_visibility(mods)
            is_suspend = "suspend" in mods

        raw_text = get_node_text(node)

        func = Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
        )
        func.is_suspend = is_suspend

        # Theme-A (2026-06-11): class/object ownership. Functions inside
        # ``class Dog { fun feed() }`` were flattened to top-level with no
        # receiver_type — an agent could not tell ``feed`` belongs to ``Dog``.
        #
        # Resolution order:
        # 1. Extension receiver: ``fun String.shout()`` → receiver_type='String',
        #    is_method=True (declared explicitly in the function signature).
        # 2. Owning class/object via parent walk:
        #    - class/object member → receiver_type=owner, is_method=True
        #    - companion object member → receiver_type=enclosing class, is_method=False
        ext_receiver = _kotlin_extension_receiver(node, get_node_text)
        if ext_receiver is not None:
            func.receiver_type = ext_receiver
            func.is_method = True
        else:
            owner, is_companion = _kotlin_owning_type(node)
            if owner is not None:
                func.receiver_type = owner
                func.is_method = not is_companion
                # P2b (2026-06-11 adversarial review): companion funs are
                # static-like (no implicit ``this``); flag them so agents
                # can distinguish them from instance methods, matching
                # Java/C#/etc. conventions for companion/static members.
                if is_companion:
                    func.is_static = True

        return func

    except Exception as e:
        log_error(f"Error extracting Kotlin function: {e}")
        return None


def _kotlin_primary_ctor_class_name(
    node: Any, get_node_text: Callable[..., str]
) -> str:
    """Return the enclosing class name for a ``primary_constructor`` node.

    Grammar shape:
        class_declaration
          identifier  ← class name
          primary_constructor  ← ``node`` is here
          ...

    Walk up one level (node.parent = class_declaration) and read the first
    ``identifier`` child.
    """
    parent = node.parent
    if parent is None:
        return "anonymous"
    for child in parent.children:
        if child.type == "identifier":
            return get_node_text(child)
    return "anonymous"


def extract_kotlin_primary_constructor(
    node: Any,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Function | None:
    """Extract a Kotlin ``primary_constructor`` as a Function(is_constructor=True).

    Issue #567 scope-B: ``primary_constructor`` nodes were not in the
    extractor dispatch map so ``data class Point(val x: Int, val y: Int)``
    produced no constructor element — an agent could not distinguish class
    instantiation from method calls.

    Convention (matching C++ same-name-constructor and Java constructor):
    - ``name`` = enclosing class name
    - ``is_constructor = True``
    - ``parameters`` extracted from ``class_parameters`` child nodes

    Visibility defaults to public; Kotlin primary constructors can carry an
    explicit ``constructor_modifier`` but that is rare and left for a
    follow-up.
    """
    try:
        name = _kotlin_primary_ctor_class_name(node, get_node_text)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        raw_text = get_node_text(node)

        # Parameters live in class_parameters > class_parameter children.
        parameters: list[str] = []
        for child in node.children:
            if child.type == "class_parameters":
                for param in child.children:
                    if param.type == "class_parameter":
                        param_name, param_type = _kotlin_parameter_pair(
                            param, get_node_text
                        )
                        if param_name:
                            parameters.append(f"{param_name}: {param_type or 'Any'}")
                break

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            parameters=parameters,
            return_type="void",
            visibility="public",
            is_constructor=True,
        )

    except Exception as e:
        log_error(f"Error extracting Kotlin primary constructor: {e}")
        return None


# Extract elements from AST: extract_kotlin_class_or_object
_KOTLIN_CLASS_KIND_MODIFIERS = frozenset({"enum", "annotation", "data", "sealed"})


def _refine_kotlin_class_kind(node: Any, get_node_text: Callable[..., str]) -> str:
    """Return the declaration kind from the class_modifier, if any.

    ``enum class`` / ``annotation class`` / ``data class`` / ``sealed class``
    carry their kind as a ``class_modifier`` token under ``modifiers``.
    """
    for child in node.children:
        if child.type != "modifiers":
            continue
        for modifier in child.children:
            text = get_node_text(modifier)
            if text in _KOTLIN_CLASS_KIND_MODIFIERS:
                return str(text)
    return "class"


def _extract_kotlin_delegation(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, list[str]]:
    """Return ``(superclass, interfaces)`` from a ``class_declaration`` node.

    Iterates the ``delegation_specifiers`` child (if present).  Each
    ``delegation_specifier`` contains either a ``constructor_invocation``
    (= superclass — e.g. ``Result(value)``) or a plain ``user_type``
    (= interface — e.g. ``Displayable``).

    Grammar shape (from live AST dump):
        delegation_specifiers
          delegation_specifier
            constructor_invocation   <- superclass with call args
              user_type  "Result"
              value_arguments  "(value)"
          delegation_specifier
            user_type  "Displayable"   <- interface

    At most one ``constructor_invocation`` is valid Kotlin; we take the
    first.  All plain ``user_type`` delegates (no constructor call) are
    collected as interfaces.
    """
    superclass: str | None = None
    interfaces: list[str] = []

    for child in node.children:
        if child.type != "delegation_specifiers":
            continue
        for spec in child.children:
            if spec.type != "delegation_specifier":
                continue
            for inner in spec.children:
                if inner.type == "constructor_invocation":
                    # First child of constructor_invocation is user_type
                    for sub in inner.children:
                        if sub.type == "user_type":
                            if superclass is None:
                                superclass = get_node_text(sub)
                            break
                elif inner.type == "user_type":
                    interfaces.append(get_node_text(inner))
        break  # only one delegation_specifiers node

    return superclass, interfaces


def extract_kotlin_class_or_object(
    node: Any,
    kind: str,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Class | None:
    """Extract Kotlin class/object/interface declaration."""
    try:
        name = "anonymous"
        name_node = node.child_by_field_name("name")
        if name_node:
            name = get_node_text(name_node)
        else:
            for child in node.children:
                if child.type == "simple_identifier":
                    name = get_node_text(child)
                    break

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        visibility = "public"
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            visibility = determine_visibility(get_node_text(modifiers_node))

        if kind == "class":
            for child in node.children:
                if child.type == "interface":
                    kind = "interface"
                    break
                elif child.type == "class":
                    break
            # Theme-I (2026-06-10): class-kind fidelity. The grammar exposes
            # the declaration kind as a ``class_modifier`` inside ``modifiers``
            # ("enum class" / "annotation class" / "data class" /
            # "sealed class"); without this an agent could not tell a DTO from
            # an enum from an annotation in outlines. "inner" / "open" etc.
            # are nesting/inheritance modifiers, not kinds — left as "class".
            if kind == "class":
                kind = _refine_kotlin_class_kind(node, get_node_text)

        # Issue #561: read delegation_specifiers to populate superclass /
        # interfaces. Previously this was never read so all Kotlin classes
        # showed empty inheritance data in outline surfaces.
        superclass, interfaces = _extract_kotlin_delegation(node, get_node_text)

        raw_text = get_node_text(node)

        return Class(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            class_type=kind,
            visibility=visibility,
            package_name=current_package,
            superclass=superclass,
            interfaces=interfaces,
        )

    except Exception as e:
        log_error(f"Error extracting Kotlin class: {e}")
        return None


def _extract_kotlin_property_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Return the property name (val/var binding) for a Kotlin property node.

    r37ci (dogfood): extracted from ``extract_kotlin_property`` so the
    three lookup forms (``name`` field / ``variable_declaration`` /
    ``simple_identifier``) read as a flat chain.
    """
    name_node = node.child_by_field_name("name")
    if name_node:
        return str(get_node_text(name_node))
    for child in node.children:
        if child.type == "variable_declaration":
            for grandchild in child.children:
                if grandchild.type == "simple_identifier":
                    return str(get_node_text(grandchild))
        elif child.type == "simple_identifier":
            return str(get_node_text(child))
    return "unknown"


# Extract elements from AST: extract_kotlin_property
def extract_kotlin_property(
    node: Any,
    get_node_text: Callable[..., str],
) -> Variable | None:
    """Extract Kotlin property declaration."""
    try:
        is_val = False
        is_var = False
        text = get_node_text(node)
        if text.startswith("val "):
            is_val = True
        elif text.startswith("var "):
            is_var = True

        # r37ci (dogfood): extracted to drop nesting from 7 to ≤3.
        name = _extract_kotlin_property_name(node, get_node_text)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        prop_type = "Inferred"

        visibility = "public"
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            visibility = determine_visibility(get_node_text(modifiers_node))

        raw_text = get_node_text(node)

        var = Variable(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            variable_type=prop_type,
            visibility=visibility,
        )
        var.is_val = is_val
        var.is_var = is_var

        return var

    except Exception as e:
        log_error(f"Error extracting Kotlin property: {e}")
        return None
