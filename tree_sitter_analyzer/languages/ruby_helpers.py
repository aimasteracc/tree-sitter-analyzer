"""Ruby require, attr, and utility helpers — extracted from ruby_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Function, Import
from ..utils import log_error


def extract_require_statement(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract require statement."""
    try:
        method_node = node.child_by_field_name("method")
        if not method_node:
            return None

        method_name = get_node_text(method_node)
        if method_name not in ("require", "require_relative", "load"):
            return None

        args_node = node.child_by_field_name("arguments")
        if not args_node or not args_node.children:
            return None

        first_arg = args_node.children[0]
        if first_arg.type == "string":
            import_name = get_node_text(first_arg).strip("\"'")
            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                alias=None,
                is_wildcard=False,
            )
    except Exception as e:
        log_error(f"Error extracting require statement: {e}")
    return None


def extract_attr_methods(
    node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
) -> list[Function]:
    """Extract attr_accessor, attr_reader, attr_writer methods."""
    functions: list[Function] = []
    try:
        method_node = node.child_by_field_name("method")
        if not method_node:
            return functions

        method_name = get_node_text(method_node)
        if method_name not in ("attr_accessor", "attr_reader", "attr_writer"):
            return functions

        args_node = node.child_by_field_name("arguments")
        if not args_node:
            return functions

        for arg in args_node.children:
            if arg.type == "simple_symbol":
                attr_name = get_node_text(arg).lstrip(":")

                functions.append(
                    Function(
                        name=(
                            f"{parent_class}#{attr_name}" if parent_class else attr_name
                        ),
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        visibility="public",
                        is_static=False,
                        is_async=False,
                        is_abstract=False,
                        parameters=[],
                        return_type="",
                        modifiers=[],
                        annotations=[],
                        is_property=True,
                    )
                )
    except Exception as e:
        log_error(f"Error extracting attr methods: {e}")
    return functions
