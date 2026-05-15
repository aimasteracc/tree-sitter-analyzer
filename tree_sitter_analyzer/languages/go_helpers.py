"""Go import, doc, and utility helpers — extracted from go_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Package, Variable
from ..utils import log_error


def extract_imports_from_tree(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract Go import declarations."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "import_declaration":
            imps = _extract_import_declaration(child, get_node_text)
            if imps:
                imports.extend(imps)

    return imports


def extract_import_spec(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract single import spec."""
    try:
        raw_text = get_node_text(node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        alias = None
        path = None

        for child in node.children:
            if child.type == "package_identifier":
                alias = get_node_text(child)
            elif child.type == "blank_identifier":
                alias = "_"
            elif child.type == "dot":
                alias = "."
            elif child.type == "interpreted_string_literal":
                path = get_node_text(child).strip('"')

        if path:
            name = path.split("/")[-1] if "/" in path else path
            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="go",
                module_name=path,
                import_statement=raw_text,
                alias=alias,
            )
        return None
    except Exception as e:
        log_error(f"Error extracting Go import spec: {e}")
        return None


def extract_parameters(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract function/method parameters."""
    parameters: list[str] = []
    params_node = node.child_by_field_name("parameters")
    if params_node:
        for child in params_node.children:
            if child.type == "parameter_declaration":
                parameters.append(get_node_text(child))
    return parameters


def extract_return_type(node: Any, get_node_text: Callable[..., str]) -> str:
    """Extract function/method return type."""
    result_node = node.child_by_field_name("result")
    if result_node:
        return get_node_text(result_node)
    return ""


def extract_var_spec(
    node: Any,
    is_const: bool,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract single var/const spec."""
    variables: list[Variable] = []
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        raw_text = get_node_text(node)

        names: list[str] = []
        var_type = ""

        for child in node.children:
            if child.type == "identifier":
                names.append(get_node_text(child))
            elif child.type in (
                "type_identifier",
                "pointer_type",
                "array_type",
                "slice_type",
                "map_type",
                "channel_type",
                "qualified_type",
            ):
                var_type = get_node_text(child)

        for name in names:
            visibility = "public" if name[0].isupper() else "private"
            variables.append(
                Variable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="go",
                    variable_type=var_type,
                    visibility=visibility,
                    is_constant=is_const,
                )
            )
    except Exception as e:
        log_error(f"Error extracting Go var spec: {e}")
    return variables


def extract_embedded_types(
    struct_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract embedded types from struct."""
    embedded: list[str] = []
    for child in struct_node.children:
        if child.type == "field_declaration_list":
            for field in child.children:
                if field.type == "field_declaration":
                    has_name = False
                    type_text = None
                    for fc in field.children:
                        if fc.type == "field_identifier":
                            has_name = True
                        elif fc.type in ("type_identifier", "qualified_type"):
                            type_text = get_node_text(fc)
                    if not has_name and type_text:
                        embedded.append(type_text)
    return embedded


def extract_docstring(node: Any, content_lines: list[str]) -> str | None:
    """Extract doc comments preceding the node."""
    start_line = node.start_point[0]
    if start_line == 0:
        return None

    docs: list[str] = []
    line_idx = start_line - 1

    if line_idx >= len(content_lines):
        line_idx = len(content_lines) - 1

    while line_idx >= 0:
        line = content_lines[line_idx].strip()
        if line.startswith("//"):
            docs.insert(0, line[2:].strip())
            line_idx -= 1
        elif line == "":
            line_idx -= 1
        else:
            break

    return "\n".join(docs) if docs else None


def extract_method_receiver(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, str | None]:
    """Extract method receiver name and type."""
    receiver_node = node.child_by_field_name("receiver")
    if receiver_node:
        receiver_text = get_node_text(receiver_node)
        match = re.search(r"\(\s*(\w+)\s+(\*?\w+)\s*\)", receiver_text)
        if match:
            return match.group(1), match.group(2)
    return None, None


def _extract_import_declaration(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract import declaration (may contain multiple imports)."""
    imports: list[Import] = []
    try:
        for child in node.children:
            if child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        imp = extract_import_spec(spec, get_node_text)
                        if imp:
                            imports.append(imp)
            elif child.type == "import_spec":
                imp = extract_import_spec(child, get_node_text)
                if imp:
                    imports.append(imp)
    except Exception as e:
        log_error(f"Error extracting Go import: {e}")
    return imports


def extract_go_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go function declaration."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = get_node_text(name_node)
        if not name:
            return None

        parameters = extract_parameters(node, get_node_text)
        return_type = extract_return_type(node, get_node_text)
        visibility = "public" if name[0].isupper() else "private"
        docstring = extract_docstring(node, content_lines)
        raw_text = get_node_text(node)

        return Function(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="go",
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
            docstring=docstring,
            is_public=visibility == "public",
        )
    except Exception as e:
        log_error(f"Error extracting Go function: {e}")
        return None


def extract_go_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go method declaration (function with receiver)."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = get_node_text(name_node)
        if not name:
            return None

        receiver, receiver_type = extract_method_receiver(node, get_node_text)
        parameters = extract_parameters(node, get_node_text)
        return_type = extract_return_type(node, get_node_text)
        visibility = "public" if name[0].isupper() else "private"
        docstring = extract_docstring(node, content_lines)
        raw_text = get_node_text(node)

        func = Function(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="go",
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
            docstring=docstring,
            is_public=visibility == "public",
        )
        func.receiver = receiver
        func.receiver_type = receiver_type
        func.is_method = True

        return func
    except Exception as e:
        log_error(f"Error extracting Go method: {e}")
        return None


def extract_go_type_spec(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract single Go type spec (struct, interface, type alias)."""
    try:
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")

        if not name_node:
            return None

        name = get_node_text(name_node)
        if not name:
            return None

        class_type = "type"
        if type_node:
            if type_node.type == "struct_type":
                class_type = "struct"
            elif type_node.type == "interface_type":
                class_type = "interface"
            else:
                class_type = "type_alias"

        visibility = "public" if name[0].isupper() else "private"
        docstring = extract_docstring(node, content_lines)
        raw_text = get_node_text(node)

        interfaces: list[str] = []
        if type_node and type_node.type == "struct_type":
            interfaces = extract_embedded_types(type_node, get_node_text)

        return Class(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="go",
            class_type=class_type,
            visibility=visibility,
            docstring=docstring,
            interfaces=interfaces,
        )
    except Exception as e:
        log_error(f"Error extracting Go type spec: {e}")
        return None


def extract_go_package(
    node: Any,
    get_node_text: Callable[..., str],
) -> Package | None:
    """Extract Go package declaration."""
    try:
        for child in node.children:
            if child.type == "package_identifier":
                name = get_node_text(child)
                return Package(
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=get_node_text(node),
                    language="go",
                )
        return None
    except Exception as e:
        log_error(f"Error extracting Go package: {e}")
        return None


def extract_type_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> list[Class]:
    """Extract type declaration (struct, interface, type alias)."""
    classes: list[Class] = []
    try:
        for child in node.children:
            if child.type == "type_spec":
                cls = extract_go_type_spec(child, get_node_text, content_lines)
                if cls:
                    classes.append(cls)
    except Exception as e:
        log_error(f"Error extracting Go type declaration: {e}")
    return classes


def extract_var_or_const(
    node: Any,
    is_const: bool,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract var or const declaration."""
    variables: list[Variable] = []
    try:
        for child in node.children:
            if child.type in ("const_spec", "var_spec"):
                vars_from_spec = extract_var_spec(child, is_const, get_node_text)
                if vars_from_spec:
                    variables.extend(vars_from_spec)
    except Exception as e:
        label = "const" if is_const else "var"
        log_error(f"Error extracting Go {label}: {e}")
    return variables
