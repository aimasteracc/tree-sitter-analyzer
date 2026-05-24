"""Shared helpers for comprehensive formatter test phases."""

import inspect
from dataclasses import dataclass
from typing import Any

FORMAT_TYPES = ["full", "compact", "csv"]


@dataclass
class PhaseCase:
    """Inputs for one phase case execution."""

    analyzer_function: callable
    test_data: dict[str, Any]
    test_name: str
    results: dict[str, Any]
    format_type: str | None = None


def new_phase_results(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a standard phase result dictionary."""
    results = {"passed": 0, "failed": 0, "total": 0, "details": []}
    if extra:
        results.update(extra)
    return results


def add_pass(results: dict[str, Any], test_name: str, message: str) -> None:
    """Record a passed test detail."""
    results["passed"] += 1
    results["details"].append(
        {"test": test_name, "status": "passed", "message": message}
    )


def add_failure(results: dict[str, Any], test_name: str, message: str) -> None:
    """Record a failed test detail."""
    results["failed"] += 1
    results["details"].append(
        {"test": test_name, "status": "failed", "message": message}
    )


def add_error(results: dict[str, Any], test_name: str, error: Exception | str) -> None:
    """Record an errored test detail."""
    results["failed"] += 1
    results["details"].append(
        {"test": test_name, "status": "error", "message": str(error)}
    )


async def call_analyzer(
    analyzer_function: callable,
    source_code: str,
    format_type: str,
) -> str:
    """Call analyzer functions that may be sync or async."""
    if inspect.iscoroutinefunction(analyzer_function):
        return await analyzer_function(source_code, format_type=format_type)
    return analyzer_function(source_code, format_type=format_type)


def is_non_empty_output(output: str) -> bool:
    return bool(output and len(output.strip()) > 0)


def is_valid_e2e_output(format_type: str, output: str) -> bool:
    if format_type in ["full", "compact"]:
        return "#" in output and "|" in output
    if format_type == "csv":
        return "," in output and "\n" in output
    return False


def e2e_failure_message(format_type: str) -> str:
    if format_type in ["full", "compact"]:
        return "Invalid markdown structure"
    if format_type == "csv":
        return "Invalid CSV structure"
    return f"Invalid {format_type} structure"


def is_schema_valid(
    suite: Any,
    format_type: str,
    output: str,
) -> tuple[bool, list[Any]]:
    """Validate generated output against the configured schema validator."""
    if format_type in ["full", "compact"]:
        validation_result = suite.markdown_validator.validate(output)
        is_valid = validation_result.is_valid or ("=" in output and "-" in output)
        return is_valid, validation_result.errors if not is_valid else []
    if format_type == "csv":
        validation_result = suite.csv_validator.validate(output)
        return validation_result.is_valid, validation_result.errors
    return True, []


def is_specification_compliant(format_type: str, output: str) -> bool:
    """Check the lightweight format compliance rules used by this suite."""
    if format_type == "full":
        return ("#" in output and "##" in output) or ("=" in output and "-" in output)
    if format_type == "compact":
        return ("#" in output and "|" in output) or ("-" in output)
    if format_type == "csv":
        return "," in output and "\n" in output
    return True
