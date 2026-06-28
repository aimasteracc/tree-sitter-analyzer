"""Export extraction helpers for the JavaScript extractor."""

from __future__ import annotations

import re
from typing import Any

from ...utils import log_debug

ExportStatementParts = tuple[str, list[str], bool]


def extract_commonjs_exports(source_code: str) -> list[dict[str, Any]]:
    """Extract CommonJS module.exports statements."""
    exports: list[dict[str, Any]] = []

    try:
        patterns = [
            r"module\.exports\s*=\s*(\w+)",
            r"module\.exports\.(\w+)\s*=",
            r"exports\.(\w+)\s*=",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, source_code):
                exports.append(_commonjs_export_from_match(match, source_code))
    except Exception as e:
        log_debug(f"Failed to extract CommonJS exports: {e}")

    return exports


def parse_export_statement(export_text: str) -> ExportStatementParts | None:
    """Parse export statement to extract details."""
    try:
        clean_text = export_text.strip().rstrip(";")
        if "export default" in clean_text:
            return _default_export_parts(clean_text)
        if "export {" in clean_text:
            return _named_export_parts(clean_text)
        if (
            clean_text.startswith("export ")
            and clean_text != "invalid export statement"
        ):
            return _direct_export_parts(clean_text)
        return None
    except Exception:
        return None


def _commonjs_export_from_match(
    match: re.Match[str],
    source_code: str,
) -> dict[str, Any]:
    name = match.group(1)
    line_num = source_code[: match.start()].count("\n") + 1
    return {
        "type": "commonjs",
        "names": [name],
        "is_default": "module.exports =" in match.group(0),
        "start_line": line_num,
        "end_line": line_num,
        "raw_text": match.group(0),
    }


def _default_export_parts(clean_text: str) -> ExportStatementParts:
    default_match = re.search(r"export\s+default\s+(\w+)", clean_text)
    if default_match:
        return "default", [default_match.group(1)], True
    return "default", ["default"], True


def _named_export_parts(clean_text: str) -> ExportStatementParts | None:
    named_match = re.search(r"export\s+\{([^}]+)\}", clean_text)
    if named_match:
        names_text = named_match.group(1)
        names = [name.strip() for name in names_text.split(",")]
        return "named", names, False
    return None


def _direct_export_parts(clean_text: str) -> ExportStatementParts:
    direct_match = re.search(
        r"export\s+(function|class|const|let|var)\s+(\w+)",
        clean_text,
    )
    if direct_match:
        return "direct", [direct_match.group(2)], False
    return "direct", ["unknown"], False
