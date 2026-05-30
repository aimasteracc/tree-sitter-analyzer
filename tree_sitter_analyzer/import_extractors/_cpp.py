"""C/C++ import extractor."""

from typing import Any

from ._shared import _node_text


def _cpp_import_entry(raw: str, is_relative: bool) -> dict[str, Any]:
    """Build import entry dict for a C/C++ include directive."""
    return {
        "module_name": raw,
        "resolved_path": raw,
        "names": [],
        "is_relative": is_relative,
        "language": "cpp",
    }


def _extract_cpp_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract C/C++ #include directives.

    Handles:
        #include <stdio.h>
        #include "myheader.h"
        #include <vector>
    """
    node_type = getattr(node, "type", None)
    if node_type != "preproc_include":
        return

    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "string_literal":
            raw = _node_text(child, source).strip('"')
            if raw:
                entry = _cpp_import_entry(raw, True)
                imports.append(entry)
                return
        if ct == "system_lib_string":
            raw = _node_text(child, source).strip("<>")
            if raw:
                entry = _cpp_import_entry(raw, False)
                imports.append(entry)
                return
