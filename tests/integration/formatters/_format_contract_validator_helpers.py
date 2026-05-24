"""Validator helpers for format contract integration tests."""

import csv
import io
import re
from typing import Any

from ._format_contract_info_helpers import (
    extract_compact_format_info,
    extract_full_format_info,
)

CSV_HEADER = [
    "Type",
    "Name",
    "ReturnType",
    "Parameters",
    "Access",
    "Static",
    "Final",
    "Line",
]


def validate_class_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    violations: list[str],
) -> bool:
    """Validate class information consistency."""
    full_class = full_info.get("class_name", "")
    compact_class = compact_info.get("class_name", "")
    csv_class = csv_info.get("class_name", "")

    _append_class_mismatch(violations, "full", full_class, "compact", compact_class)
    _append_class_mismatch(violations, "full", full_class, "csv", csv_class)
    _append_class_mismatch(violations, "compact", compact_class, "csv", csv_class)
    return True


def validate_count_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    violations: list[str],
) -> bool:
    """Validate count information consistency."""
    del csv_info
    full_method_count = len(full_info.get("methods", []))
    full_field_count = len(full_info.get("fields", []))
    compact_counts = compact_info.get("counts", {})

    _append_reported_count_mismatch(
        violations,
        compact_counts.get("methods"),
        full_method_count,
        "methods",
    )
    _append_reported_count_mismatch(
        violations,
        compact_counts.get("fields"),
        full_field_count,
        "fields",
    )
    return True


def validate_full_format_contracts(output: str, violations: list[str]) -> bool:
    """Validate Full Format specific contracts."""
    for section in ["## Class Info", "## Methods", "## Fields"]:
        if section not in output:
            violations.append(f"Full format missing required section: {section}")

    _validate_section_contains(
        output,
        "Methods",
        ["Parameters"],
        "Full format Methods table missing {column} column",
        violations,
    )
    _validate_section_contains(
        output,
        "Fields",
        ["Static", "Final"],
        "Full format Fields table missing {column} column",
        violations,
    )
    return True


def validate_compact_format_contracts(
    output: str, violations: list[str], warnings: list[str]
) -> bool:
    """Validate Compact Format specific contracts."""
    if "## Info" not in output:
        violations.append("Compact format missing required Info section")

    if "Parameters" in output:
        warnings.append("Compact format should omit detailed parameter information")

    header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
    if header_match and "." in header_match.group(1):
        warnings.append("Compact format header should omit package information")

    return True


def validate_csv_format_contracts(output: str, violations: list[str]) -> bool:
    """Validate CSV Format specific contracts."""
    try:
        reader = csv.reader(io.StringIO(output))
        header = next(reader)
        rows = list(reader)
    except (csv.Error, StopIteration) as exc:
        violations.append(f"CSV format structure violation: {exc}")
        return True

    if header != CSV_HEADER:
        violations.append(f"CSV format header contract violation: {header}")

    if not any(row and row[0] == "class" for row in rows):
        violations.append("CSV format must contain at least one class row")

    _validate_csv_parameter_rows(rows, violations)
    return True


def validate_cross_format_contracts(
    full_output: str, compact_output: str, violations: list[str]
) -> bool:
    """Validate contracts that span multiple formats."""
    full_info = extract_full_format_info(full_output)
    compact_info = extract_compact_format_info(compact_output)

    _append_extra_compact_entries(
        violations, full_info, compact_info, "methods", "methods"
    )
    _append_extra_compact_entries(
        violations, full_info, compact_info, "fields", "fields"
    )
    return True


def validate_csv_parameters(parameters: str) -> bool:
    """Validate CSV parameter encoding format."""
    if not parameters.strip():
        return True

    return all(_is_valid_csv_parameter(param) for param in parameters.split(";"))


def _append_class_mismatch(
    violations: list[str],
    left_label: str,
    left_class: str,
    right_label: str,
    right_class: str,
) -> None:
    if left_class and right_class and left_class != right_class:
        violations.append(
            f"Class name mismatch: "
            f"{left_label}='{left_class}', {right_label}='{right_class}'"
        )


def _append_reported_count_mismatch(
    violations: list[str],
    reported_count: int | None,
    actual_count: int,
    label: str,
) -> None:
    if reported_count is not None and reported_count != actual_count:
        violations.append(
            f"Compact format reports {reported_count} {label}, "
            f"but full format has {actual_count}"
        )


def _validate_section_contains(
    output: str,
    section_name: str,
    columns: list[str],
    message_template: str,
    violations: list[str],
) -> None:
    if f"## {section_name}" not in output:
        return

    section = re.search(rf"## {section_name}\n(.*?)(?=\n##|\n$)", output, re.DOTALL)
    if not section:
        return

    table_content = section.group(1)
    for column in columns:
        if column not in table_content:
            violations.append(message_template.format(column=column))


def _validate_csv_parameter_rows(rows: list[list[str]], violations: list[str]) -> None:
    for row in rows:
        if len(row) >= 4 and row[3] and not validate_csv_parameters(row[3]):
            violations.append(f"CSV format invalid parameter encoding: {row[3]}")


def _append_extra_compact_entries(
    violations: list[str],
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    key: str,
    label: str,
) -> None:
    compact_names = {row[0] for row in compact_info.get(key, []) if row}
    full_names = {row[0] for row in full_info.get(key, []) if row}
    extra_entries = compact_names - full_names
    if extra_entries:
        violations.append(
            f"Compact format has {label} not in full format: {extra_entries}"
        )


def _is_valid_csv_parameter(param: str) -> bool:
    parts = param.strip().split(":")
    if len(parts) != 2:
        return False

    name, type_name = parts
    return bool(name.strip() and type_name.strip())
