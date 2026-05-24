"""Assertion methods for enhanced formatter validation."""

from typing import Any

from ._enhanced_assertion_models import AssertionResult
from ._enhanced_assertion_reports import (
    build_assertion_report,
    compare_format_counts,
    count_format_elements,
)


class EnhancedFormatAssertionsAssertMixin:
    """Assertion helpers used by EnhancedFormatAssertions."""

    def assert_semantic_correctness(
        self,
        format_output: str,
        format_type: str,
        language: str,
        source_code: str | None = None,
    ) -> list[AssertionResult]:
        """Assert semantic correctness of format output"""
        results = []
        results.extend(
            self.semantic_validator.validate_semantic_consistency(
                format_output, format_type, language
            )
        )
        results.extend(
            self.structural_validator.validate_table_structure(
                format_output, format_type
            )
        )

        results.extend(
            _content_accuracy_results(
                self.content_validator, format_output, source_code, language
            )
        )

        return results

    def assert_format_completeness(
        self, format_output: str, expected_elements: dict[str, int]
    ) -> list[AssertionResult]:
        """Assert format output completeness"""
        actual_counts = count_format_elements(format_output)
        return _count_mismatch_results(actual_counts, expected_elements)

    def assert_format_consistency(
        self, outputs: dict[str, str]
    ) -> list[AssertionResult]:
        """Assert consistency across different format types"""
        format_counts = {
            format_type: count_format_elements(output)
            for format_type, output in outputs.items()
        }
        return compare_format_counts(format_counts)

    def generate_assertion_report(
        self, results: list[AssertionResult]
    ) -> dict[str, Any]:
        """Generate comprehensive assertion report"""
        return build_assertion_report(results)


def _count_mismatch_results(
    actual_counts: dict[str, int],
    expected_elements: dict[str, int],
) -> list[AssertionResult]:
    results = []

    for element_type, expected_count in expected_elements.items():
        result = _count_mismatch_result_for_expected(
            element_type, expected_count, actual_counts
        )
        if result:
            results.append(result)

    return results


def _count_mismatch_result_for_expected(
    element_type: str,
    expected_count: int,
    actual_counts: dict[str, int],
) -> AssertionResult | None:
    actual_count = actual_counts.get(element_type, 0)
    if actual_count == expected_count:
        return None
    return _count_mismatch_result(
        element_type, expected_count, actual_count, actual_counts
    )


def _content_accuracy_results(
    content_validator: Any,
    format_output: str,
    source_code: str | None,
    language: str,
) -> list[AssertionResult]:
    if not source_code:
        return []
    return content_validator.validate_content_accuracy(
        format_output, source_code, language
    )


def _count_mismatch_result(
    element_type: str,
    expected_count: int,
    actual_count: int,
    actual_counts: dict[str, int],
) -> AssertionResult:
    return AssertionResult(
        passed=False,
        message=f"Element count mismatch for {element_type}",
        details={
            "element_type": element_type,
            "expected_count": expected_count,
            "actual_count": actual_count,
            "all_counts": actual_counts,
        },
        severity="error",
        suggestion=f"Ensure {element_type} count matches expected value",
    )
