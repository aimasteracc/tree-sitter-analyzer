"""Report builders for enhanced assertion results."""

from typing import Any

from ._enhanced_assertion_models import AssertionResult


def build_assertion_report(results: list[AssertionResult]) -> dict[str, Any]:
    """Build a grouped assertion report with summary and detail sections."""
    total_assertions = len(results)
    passed_assertions = sum(1 for result in results if result.passed)
    failed_assertions = total_assertions - passed_assertions

    by_severity = _group_by_severity(results)
    by_message_type = _group_by_message_type(results)

    return {
        "summary": {
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "failed_assertions": failed_assertions,
            "success_rate": (
                passed_assertions / total_assertions if total_assertions > 0 else 0
            ),
        },
        "by_severity": {
            severity: {
                "count": len(grouped_results),
                "messages": [result.message for result in grouped_results],
            }
            for severity, grouped_results in by_severity.items()
        },
        "by_message_type": {
            msg_type: len(grouped_results)
            for msg_type, grouped_results in by_message_type.items()
        },
        "detailed_results": [
            {
                "passed": result.passed,
                "message": result.message,
                "severity": result.severity,
                "location": result.location,
                "suggestion": result.suggestion,
                "details": result.details,
            }
            for result in results
        ],
    }


def count_format_elements(output: str) -> dict[str, int]:
    """Count table rows and section headings in format output."""
    counts: dict[str, int] = {}

    for line in output.split("\n"):
        line = line.strip()

        if "|" in line and not line.startswith("|--") and not line.startswith("##"):
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if cells and len(cells) > 1:
                element_type = cells[0].lower() if cells else "unknown"
                counts[element_type] = counts.get(element_type, 0) + 1

        elif line.startswith("##"):
            section_type = line.replace("#", "").strip().lower()
            counts[f"section_{section_type}"] = (
                counts.get(f"section_{section_type}", 0) + 1
            )

    return counts


def compare_format_counts(
    format_counts: dict[str, dict[str, int]],
) -> list[AssertionResult]:
    """Compare element counts across format outputs."""
    if len(format_counts) <= 1:
        return []

    results = []
    format_types = list(format_counts.keys())
    base_format = format_types[0]
    base_counts = format_counts[base_format]

    for other_format in format_types[1:]:
        other_counts = format_counts[other_format]
        results.extend(
            _compare_one_format_count(
                base_format, base_counts, other_format, other_counts
            )
        )
    return results


def _compare_one_format_count(
    base_format: str,
    base_counts: dict[str, int],
    other_format: str,
    other_counts: dict[str, int],
) -> list[AssertionResult]:
    results = []
    for element_type in base_counts:
        if element_type in other_counts:
            if base_counts[element_type] != other_counts[element_type]:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Element count inconsistency between {base_format} and {other_format}",
                        details={
                            "element_type": element_type,
                            "base_format": base_format,
                            "base_count": base_counts[element_type],
                            "other_format": other_format,
                            "other_count": other_counts[element_type],
                        },
                        severity="error",
                        suggestion=f"Ensure {element_type} count is consistent across all formats",
                    )
                )
    return results


def _group_by_severity(
    results: list[AssertionResult],
) -> dict[str, list[AssertionResult]]:
    by_severity: dict[str, list[AssertionResult]] = {}
    for result in results:
        severity = result.severity
        if severity not in by_severity:
            by_severity[severity] = []
        by_severity[severity].append(result)
    return by_severity


def _group_by_message_type(
    results: list[AssertionResult],
) -> dict[str, list[AssertionResult]]:
    by_message_type: dict[str, list[AssertionResult]] = {}
    for result in results:
        message_type = (
            result.message.split(":")[0]
            if ":" in result.message
            else result.message.split(" ")[0]
        )
        if message_type not in by_message_type:
            by_message_type[message_type] = []
        by_message_type[message_type].append(result)
    return by_message_type
