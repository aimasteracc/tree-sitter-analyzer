"""Import extraction helpers for the JavaScript extractor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...models import Import
from ...utils import log_debug

if TYPE_CHECKING:
    import tree_sitter


ImportStatementParts = tuple[str, list[str], str, bool, bool]


def extract_import_names(
    import_clause_node: tree_sitter.Node,
    source_code: str,
) -> list[str]:
    """Extract imported names from a JavaScript import clause."""
    source_bytes = source_code.encode("utf-8")
    names: list[str] = []

    for child in import_clause_node.children:
        if child.type == "import_default_specifier":
            names.extend(_identifier_names(child.children, source_bytes))
        elif child.type == "named_imports":
            names.extend(_named_import_names(child.children, source_bytes))

    return names


def extract_commonjs_requires(source_code: str) -> list[Import]:
    """Extract CommonJS require() statements."""
    imports: list[Import] = []

    try:
        require_pattern = (
            r"(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
        )
        for match in re.finditer(require_pattern, source_code):
            imports.append(_commonjs_import_from_match(match, source_code))
    except Exception as e:
        log_debug(f"Failed to extract CommonJS requires: {e}")
        raise

    return imports


def parse_import_statement(import_text: str) -> ImportStatementParts | None:
    """Parse import statement to extract details."""
    try:
        clean_text = import_text.strip().rstrip(";")
        source_match = re.search(r"from\s+[\"']([^\"']+)[\"']", clean_text)
        if not source_match:
            return None

        source = source_match.group(1)
        if "import * as" in clean_text:
            return _namespace_import_parts(clean_text, source)
        if "import {" in clean_text:
            return _named_import_parts(clean_text, source)
        return _default_import_parts(clean_text, source)
    except Exception:
        return None


def _commonjs_import_from_match(match: re.Match[str], source_code: str) -> Import:
    var_name = match.group(1)
    module_path = match.group(2)
    line_num = source_code[: match.start()].count("\n") + 1
    return Import(
        name=var_name,
        start_line=line_num,
        end_line=line_num,
        raw_text=match.group(0),
        language="javascript",
        module_path=module_path,
        module_name=module_path,
        imported_names=[var_name],
    )


def _namespace_import_parts(
    clean_text: str,
    source: str,
) -> ImportStatementParts | None:
    namespace_match = re.search(r"import\s+\*\s+as\s+(\w+)", clean_text)
    if namespace_match:
        return "namespace", [namespace_match.group(1)], source, False, True
    return None


def _named_import_parts(clean_text: str, source: str) -> ImportStatementParts | None:
    named_match = re.search(r"import\s+\{([^}]+)\}", clean_text)
    if named_match:
        names_text = named_match.group(1)
        names = [name.strip() for name in names_text.split(",")]
        return "named", names, source, False, False
    return None


def _default_import_parts(clean_text: str, source: str) -> ImportStatementParts | None:
    default_match = re.search(r"import\s+(\w+)", clean_text)
    if default_match:
        return "default", [default_match.group(1)], source, True, False
    return None


def _named_import_names(
    nodes: list[tree_sitter.Node],
    source_bytes: bytes,
) -> list[str]:
    names: list[str] = []
    for node in nodes:
        if node.type == "import_specifier":
            names.extend(_identifier_names(node.children, source_bytes))
    return names


def _identifier_names(
    nodes: list[tree_sitter.Node],
    source_bytes: bytes,
) -> list[str]:
    return [
        _node_text(node, source_bytes) for node in nodes if node.type == "identifier"
    ]


def _node_text(node: tree_sitter.Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8")
