"""C include extraction helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Import
from ..utils import log_debug


def extract_include_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract include directive information."""
    try:
        include_text = get_node_text(node)
        line_num = node.start_point[0] + 1
        match = _include_path_match(include_text)
        if match:
            return _include_import(match.group(1), include_text, line_num)
    except Exception as e:
        log_debug(f"Failed to extract include info: {e}")

    return None


def extract_includes_fallback(source_code: str) -> list[Import]:
    """Fallback include extraction using regex."""
    imports: list[Import] = []

    for line_num, line in enumerate(source_code.split("\n"), 1):
        include = _include_from_line(line.strip(), line_num)
        if include:
            imports.append(include)

    return imports


def _include_path_match(include_text: str) -> re.Match[str] | None:
    if "<" in include_text:
        return re.search(r"<([^>]+)>", include_text)
    return re.search(r'"([^"]+)"', include_text)


def _include_from_line(line: str, line_num: int) -> Import | None:
    if not line.startswith("#include"):
        return None

    system_match = re.search(r"#include\s*<([^>]+)>", line)
    if system_match:
        return _include_import(system_match.group(1), line, line_num)

    local_match = re.search(r'#include\s*"([^"]+)"', line)
    if local_match:
        return _include_import(local_match.group(1), line, line_num)

    return None


def _include_import(include_path: str, raw_text: str, line_num: int) -> Import:
    return Import(
        name=include_path,
        start_line=line_num,
        end_line=line_num,
        raw_text=raw_text,
        language="c",
        module_name=include_path,
        import_statement=raw_text,
    )
