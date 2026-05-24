"""Assertion helpers for format contract integration tests."""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._format_contract_tests_data import FORMAT_TYPES


@dataclass(frozen=True)
class _CountExpectation:
    key: str
    label: str
    expected_count: int


def extract_table_output(result: dict[str, Any]) -> str:
    """Return table output from a tool response regardless of response shape."""
    return (
        result["table_output"]
        if "table_output" in result
        else result.get("content", "")
    )


async def collect_format_outputs(
    tool: Any,
    file_path: Path,
    format_types: tuple[str, ...] = FORMAT_TYPES,
) -> dict[str, str]:
    """Generate table outputs for the requested format types."""
    outputs = {}
    for format_type in format_types:
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "format_type": format_type,
                "language": "java",
                "output_format": "json",
            }
        )
        outputs[format_type] = extract_table_output(result)
    return outputs


def extract_contract_infos(
    contract_validator: Any, outputs: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Extract full, compact, and CSV contract information."""
    return (
        contract_validator._extract_full_format_info(outputs["full"]),
        contract_validator._extract_compact_format_info(outputs["compact"]),
        contract_validator._extract_csv_format_info(outputs["csv"]),
    )


def assert_outputs_contain_class_name(outputs: dict[str, str], class_name: str) -> None:
    """Assert every generated format includes the source class name."""
    for format_type, output in outputs.items():
        assert class_name in output, f"{format_type} format missing class name"


def assert_method_count_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    expected_methods: int,
) -> None:
    """Assert all formats report the same method count."""
    _assert_named_count_consistency(
        full_info,
        compact_info,
        csv_info,
        _CountExpectation("methods", "Method", expected_methods),
    )


def assert_field_count_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    expected_fields: int,
) -> None:
    """Assert all formats report the same field count."""
    _assert_named_count_consistency(
        full_info,
        compact_info,
        csv_info,
        _CountExpectation("fields", "Field", expected_fields),
    )


def assert_csv_parameter_encoding(csv_output: str, contract_validator: Any) -> None:
    """Assert CSV method parameter strings follow the expected encoding."""
    try:
        reader = csv.reader(io.StringIO(csv_output))
        next(reader)
        for row in reader:
            if len(row) >= 4 and row[0] in ["method", "constructor"]:
                _assert_valid_parameter_cell(row[3], contract_validator)
    except (csv.Error, StopIteration) as exc:
        raise AssertionError(
            "Failed to parse CSV output for parameter validation"
        ) from exc


def assert_access_modifier_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
) -> None:
    """Assert method access modifiers match across formats."""
    for method_row in full_info.get("methods", []):
        if len(method_row) < 4:
            continue

        method_name = method_row[0]
        full_access = method_row[3]
        compact_method = _find_markdown_row(
            compact_info.get("methods", []), method_name, minimum_length=3
        )
        if compact_method:
            _assert_matching_access(
                method_name, full_access, compact_method[2], "compact"
            )

        csv_method = _find_csv_row(csv_info.get("methods", []), method_name)
        if csv_method:
            _assert_matching_access(
                method_name, full_access, csv_method.get("Access", ""), "csv"
            )


def assert_line_number_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
) -> None:
    """Assert method line numbers match across formats."""
    for method_row in full_info.get("methods", []):
        if len(method_row) < 5:
            continue

        method_name = method_row[0]
        full_line = method_row[4]
        compact_method = _find_markdown_row(
            compact_info.get("methods", []),
            method_name,
            minimum_length=4,
            line_number=full_line,
        )
        if compact_method:
            _assert_matching_line(method_name, full_line, compact_method[3], "compact")

        csv_method = _find_csv_row(
            csv_info.get("methods", []), method_name, line_number=full_line
        )
        if csv_method:
            _assert_matching_line(
                method_name, full_line, csv_method.get("Line", ""), "csv"
            )


def assert_backward_compatibility_contract(current_outputs: dict[str, str]) -> None:
    """Assert the legacy format sections are still present."""
    for section in ["# ", "## Class Info", "## Methods", "## Fields"]:
        assert section in current_outputs["full"], (
            f"Backward compatibility: missing {section} in full format"
        )

    for section in ["# ", "## Info", "## Methods", "## Fields"]:
        assert section in current_outputs["compact"], (
            f"Backward compatibility: missing {section} in compact format"
        )

    expected_csv_header = "Type,Name,ReturnType,Parameters,Access,Static,Final,Line"
    assert current_outputs["csv"].startswith(expected_csv_header), (
        "Backward compatibility: CSV header format changed"
    )


def assert_cross_format_data_integrity(
    outputs: dict[str, str],
    class_name: str,
    is_consistent: bool,
    is_contract_valid: bool,
    report: dict[str, Any],
) -> None:
    """Assert all cross-format data integrity checks pass."""
    assert is_consistent and is_contract_valid, (
        f"Data integrity contract violated: {report['violations']}"
    )
    assert_outputs_contain_class_name(outputs, class_name)

    full_lines = len(outputs["full"].split("\n"))
    compact_lines = len(outputs["compact"].split("\n"))
    assert full_lines >= compact_lines, (
        "Full format should have more or equal lines compared to compact format"
    )


def _assert_valid_parameter_cell(parameters: str, contract_validator: Any) -> None:
    if parameters.strip():
        assert contract_validator._validate_csv_parameters(parameters), (
            f"Invalid parameter encoding: {parameters}"
        )


def _assert_named_count_consistency(
    full_info: dict[str, Any],
    compact_info: dict[str, Any],
    csv_info: dict[str, Any],
    expectation: _CountExpectation,
) -> None:
    full_count = len(full_info.get(expectation.key, []))
    compact_count = len(compact_info.get(expectation.key, []))
    csv_count = len(csv_info.get(expectation.key, []))

    assert full_count == compact_count, (
        f"{expectation.label} count mismatch: "
        f"full={full_count}, compact={compact_count}"
    )
    assert full_count == csv_count, (
        f"{expectation.label} count mismatch: full={full_count}, csv={csv_count}"
    )
    assert full_count >= expectation.expected_count - 1, (
        f"Expected at least {expectation.expected_count - 1} "
        f"{expectation.key}, got {full_count}"
    )


def _find_markdown_row(
    rows: list[list[str]],
    name: str,
    minimum_length: int,
    line_number: str | None = None,
) -> list[str] | None:
    for row in rows:
        if len(row) < minimum_length or row[0] != name:
            continue
        if line_number is None or row[minimum_length - 1] == line_number:
            return row
    return None


def _find_csv_row(
    rows: list[dict[str, str]], name: str, line_number: str | None = None
) -> dict[str, str] | None:
    for row in rows:
        if row.get("Name") != name:
            continue
        if line_number is None or row.get("Line", "") == line_number:
            return row
    return None


def _assert_matching_access(
    method_name: str, full_access: str, compared_access: str, compared_format: str
) -> None:
    assert full_access == compared_access, (
        f"Access modifier mismatch for method {method_name}: "
        f"full='{full_access}', {compared_format}='{compared_access}'"
    )


def _assert_matching_line(
    method_name: str, full_line: str, compared_line: str, compared_format: str
) -> None:
    assert full_line == compared_line, (
        f"Line number mismatch for method {method_name}: "
        f"full='{full_line}', {compared_format}='{compared_line}'"
    )
