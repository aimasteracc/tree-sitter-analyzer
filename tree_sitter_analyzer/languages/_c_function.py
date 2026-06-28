"""C function extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Function
from ..utils import log_debug, log_error


def extract_c_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_function_signature: Callable,
    calculate_complexity: Callable,
    extract_comment_for_line: Callable,
) -> Function | None:
    """Extract C function definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        function_info = parse_function_signature(node)
        if not function_info:
            return None

        name, return_type, parameters, modifiers = function_info
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_function_raw_text(content_lines, start_line, end_line),
            language="c",
            parameters=parameters,
            return_type=return_type or "int",
            modifiers=modifiers,
            is_static="static" in modifiers,
            visibility="public",
            docstring=extract_comment_for_line(start_line),
            complexity_score=calculate_complexity(node),
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract function info: {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error in function extraction: {e}")
        return None


def _function_raw_text(content_lines: list[str], start_line: int, end_line: int) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])
