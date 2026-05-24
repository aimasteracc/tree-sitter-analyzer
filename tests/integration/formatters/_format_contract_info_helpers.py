"""Format-info extraction helpers for format contract tests."""

import csv
import io
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _NamedEntrySpec:
    singular: str
    plural: str
    key: str


@dataclass(frozen=True)
class _NamedEntryNames:
    full: set[str]
    compact: set[str]
    csv: set[str]


def parse_markdown_table(table_content: str) -> list[list[str]]:
    """Parse Markdown table content into rows."""
    lines = [line.strip() for line in table_content.strip().split("\n") if line.strip()]
    if len(lines) < 2:
        return []

    return [
        [cell.strip() for cell in line.split("|")[1:-1]]
        for line in lines[2:]
        if line.startswith("|") and line.endswith("|")
    ]


def extract_full_format_info(output: str) -> dict[str, Any]:
    """Extract structured information from full format."""
    info = {
        "class_name": "",
        "package": "",
        "methods": [],
        "fields": [],
        "imports": [],
    }
    _add_full_header_info(output, info)
    info["methods"] = _extract_markdown_section_rows(output, "Methods")
    info["fields"] = _extract_markdown_section_rows(output, "Fields")
    info["imports"] = _extract_import_rows(output)
    return info


def extract_compact_format_info(output: str) -> dict[str, Any]:
    """Extract structured information from compact format."""
    info = {"class_name": "", "methods": [], "fields": [], "counts": {}}
    header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
    if header_match:
        info["class_name"] = header_match.group(1)

    _add_compact_counts(output, info)
    info["methods"] = _extract_markdown_section_rows(output, "Methods")
    info["fields"] = _extract_markdown_section_rows(output, "Fields")
    return info


def extract_csv_format_info(output: str) -> dict[str, Any]:
    """Extract structured information from CSV format."""
    info = {"class_name": "", "methods": [], "fields": [], "classes": []}
    try:
        reader = csv.reader(io.StringIO(output))
        header = next(reader)
    except (csv.Error, StopIteration):
        return info

    for row in reader:
        if len(row) >= 8:
            _add_csv_row(info, dict(zip(header, row, strict=False)))
    return info


def validate_method_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    violations: list[str],
) -> bool:
    """Validate method information consistency."""
    return _validate_named_entry_consistency(
        _NamedEntrySpec("Method", "Methods", "methods"),
        full_info,
        compact_info,
        csv_info,
        violations,
    )


def validate_field_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    violations: list[str],
) -> bool:
    """Validate field information consistency."""
    return _validate_named_entry_consistency(
        _NamedEntrySpec("Field", "Fields", "fields"),
        full_info,
        compact_info,
        csv_info,
        violations,
    )


def _add_full_header_info(output: str, info: dict[str, Any]) -> None:
    header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
    if not header_match:
        return

    full_name = header_match.group(1)
    if "." in full_name:
        parts = full_name.split(".")
        info["class_name"] = parts[-1]
        info["package"] = ".".join(parts[:-1])
        return

    info["class_name"] = full_name


def _extract_markdown_section_rows(output: str, section_name: str) -> list[list[str]]:
    section = re.search(
        rf"## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)",
        output,
        re.DOTALL,
    )
    return parse_markdown_table(section.group(1)) if section else []


def _extract_import_rows(output: str) -> list[list[str]]:
    imports_section = re.search(r"## Imports\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL)
    if not imports_section:
        return []

    content = imports_section.group(1)
    if "```" not in content:
        return parse_markdown_table(content)

    code_match = re.search(r"```\w*\n(.*?)\n```", content, re.DOTALL)
    if not code_match:
        return []

    import_lines = code_match.group(1).strip().split("\n")
    return [[line.strip()] for line in import_lines if line.strip()]


def _add_compact_counts(output: str, info: dict[str, Any]) -> None:
    info_section = re.search(r"## Info\n(.*?)\n\n", output, re.DOTALL)
    if not info_section:
        return

    for row in parse_markdown_table(info_section.group(1)):
        if len(row) < 2:
            continue
        property_name = row[0].lower()
        if property_name not in ["methods", "fields"]:
            continue
        try:
            info["counts"][property_name] = int(row[1])
        except ValueError:
            pass


def _add_csv_row(info: dict[str, Any], row_dict: dict[str, str]) -> None:
    row_type = row_dict.get("Type", "")
    if row_type == "class":
        info["classes"].append(row_dict)
        class_name = row_dict.get("Name", "")
        info["class_name"] = (
            class_name.split(".")[-1] if "." in class_name else class_name
        )
    elif row_type in ["method", "constructor"]:
        info["methods"].append(row_dict)
    elif row_type in ["field", "property"]:
        info["fields"].append(row_dict)


def _validate_named_entry_consistency(
    spec: _NamedEntrySpec,
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    violations: list[str],
) -> bool:
    names = _NamedEntryNames(
        full=_markdown_row_names(full_info.get(spec.key, [])),
        compact=_markdown_row_names(compact_info.get(spec.key, [])),
        csv={row.get("Name", "") for row in csv_info.get(spec.key, [])},
    )
    names.csv.discard("")

    _append_count_mismatches(spec, names, violations)
    _append_name_mismatches(spec, names, violations)
    return True


def _markdown_row_names(rows: list[list[str]]) -> set[str]:
    names = {row[0] for row in rows if row}
    names.discard("")
    return names


def _append_count_mismatches(
    spec: _NamedEntrySpec, names: _NamedEntryNames, violations: list[str]
) -> None:
    if len(names.full) != len(names.compact):
        violations.append(
            f"{spec.singular} count mismatch: "
            f"full={len(names.full)}, compact={len(names.compact)}"
        )

    if len(names.full) != len(names.csv):
        violations.append(
            f"{spec.singular} count mismatch: "
            f"full={len(names.full)}, csv={len(names.csv)}"
        )


def _append_name_mismatches(
    spec: _NamedEntrySpec, names: _NamedEntryNames, violations: list[str]
) -> None:
    if names.full and names.compact:
        _append_set_difference(
            violations,
            names.full - names.compact,
            f"{spec.plural} missing in compact format",
        )
        _append_set_difference(
            violations,
            names.compact - names.full,
            f"Extra {spec.key} in compact format",
        )

    if names.full and names.csv:
        _append_set_difference(
            violations,
            names.full - names.csv,
            f"{spec.plural} missing in CSV format",
        )
        _append_set_difference(
            violations, names.csv - names.full, f"Extra {spec.key} in CSV format"
        )


def _append_set_difference(
    violations: list[str], difference: set[str], message: str
) -> None:
    if difference:
        violations.append(f"{message}: {difference}")
