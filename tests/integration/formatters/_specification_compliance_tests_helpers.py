"""Flow helpers for format specification compliance tests."""

from pathlib import Path
from typing import Any


async def assert_specification_compliance_across_formats(
    tool: Any, file_path: Path, class_name: str, validator: Any
) -> None:
    """Run all format validators and assert shared semantic coverage."""
    results = await _validate_all_formats(tool, file_path, class_name, validator)
    _assert_shared_information_present(results, class_name)


async def _validate_all_formats(
    tool: Any, file_path: Path, class_name: str, validator: Any
) -> dict[str, str]:
    results = {}

    for format_type in ["full", "compact", "csv"]:
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "format_type": format_type,
                "language": "java",
            }
        )

        output = result["table_output"]
        results[format_type] = output
        _assert_format_output_valid(format_type, output, class_name, validator)

    return results


def _assert_format_output_valid(
    format_type: str, output: str, class_name: str, validator: Any
) -> None:
    if format_type == "full":
        is_valid = validator.validate_full_format_specification(output, class_name)
    elif format_type == "compact":
        is_valid = validator.validate_compact_format_specification(output, class_name)
    else:
        is_valid = validator.validate_csv_format_specification(output)

    report = validator.get_validation_report()

    assert is_valid, (
        f"{format_type} format specification compliance failed: {report['errors']}"
    )


def _assert_shared_information_present(
    results: dict[str, str], class_name: str
) -> None:
    for format_type, output in results.items():
        assert class_name in output, f"{format_type} format missing class name"

        if format_type == "csv":
            assert "method," in output, (
                f"{format_type} format missing method information"
            )
            continue

        assert "processUserAnalytics" in output, (
            f"{format_type} format missing method information"
        )
