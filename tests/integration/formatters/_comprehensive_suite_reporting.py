"""Result persistence and report generation for comprehensive formatter suite."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._comprehensive_suite_models import (
    FormatTestSuiteConfig,
    TestSuiteResults,
    test_suite_results_to_dict,
)


def update_test_counts(
    results: TestSuiteResults, phase_results: dict[str, Any]
) -> None:
    """Update test counts from phase results."""
    results.total_tests += phase_results.get("total", 0)
    results.passed_tests += phase_results.get("passed", 0)
    results.failed_tests += phase_results.get("failed", 0)


async def save_comprehensive_results(
    results_dir: Path,
    results: TestSuiteResults,
) -> None:
    """Save comprehensive test results."""
    results_file = (
        results_dir
        / f"comprehensive_results_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(results_file, "w") as output_file:
        json.dump(test_suite_results_to_dict(results), output_file, indent=2)

    print(f"💾 Detailed results saved to: {results_file}")


async def generate_summary_report(
    results_dir: Path,
    config: FormatTestSuiteConfig,
    results: TestSuiteResults,
) -> None:
    """Generate summary report."""
    report_file = (
        results_dir / f"summary_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.md"
    )

    report_content = "\n".join(_summary_report_lines(config, results))

    with open(report_file, "w", encoding="utf-8") as output_file:
        output_file.write(report_content)

    print(f"📊 Summary report saved to: {report_file}")


def _summary_report_lines(
    config: FormatTestSuiteConfig, results: TestSuiteResults
) -> list[str]:
    report_lines = _summary_header_lines(results)
    report_lines.extend(_phase_result_lines(results))
    report_lines.extend(_configuration_lines(config))
    report_lines.extend(_recommendation_lines(results))
    return report_lines


def _summary_header_lines(results: TestSuiteResults) -> list[str]:
    return [
        "# Comprehensive Format Testing Report",
        f"Generated: {results.timestamp}",
        f"Execution Time: {results.execution_time_seconds:.2f} seconds",
        "",
        "## Summary",
        f"- **Total Tests**: {results.total_tests}",
        f"- **Passed**: {results.passed_tests}",
        f"- **Failed**: {results.failed_tests}",
        f"- **Success Rate**: {results.success_rate:.1f}%",
        "",
        "## Test Phase Results",
        "",
    ]


def _phase_result_lines(results: TestSuiteResults) -> list[str]:
    report_lines = []
    for phase_name, phase_results in _phase_results(results):
        if phase_results:
            report_lines.extend(_one_phase_result_lines(phase_name, phase_results))
    return report_lines


def _phase_results(results: TestSuiteResults) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("Golden Master Tests", results.golden_master_results),
        ("Schema Validation Tests", results.schema_validation_results),
        ("Integration Tests", results.integration_test_results),
        ("End-to-End Tests", results.end_to_end_results),
        ("Cross-Component Tests", results.cross_component_results),
        ("Specification Compliance Tests", results.specification_compliance_results),
        ("Format Contract Tests", results.format_contract_results),
        ("Enhanced Assertion Tests", results.enhanced_assertion_results),
        ("Performance Tests", results.performance_test_results),
    ]


def _one_phase_result_lines(
    phase_name: str,
    phase_results: dict[str, Any],
) -> list[str]:
    total = phase_results.get("total", 0)
    passed = phase_results.get("passed", 0)
    failed = phase_results.get("failed", 0)
    success_rate = (passed / total * 100) if total > 0 else 0
    status_emoji = "✅" if failed == 0 else "⚠️" if passed > failed else "❌"

    return [
        f"### {status_emoji} {phase_name}",
        f"- Total: {total}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Success Rate: {success_rate:.1f}%",
        "",
    ]


def _configuration_lines(config: FormatTestSuiteConfig) -> list[str]:
    return [
        "## Configuration",
        f"- Golden Master Tests: {'✅' if config.enable_golden_master else '❌'}",
        f"- Schema Validation: {'✅' if config.enable_schema_validation else '❌'}",
        f"- Integration Tests: {'✅' if config.enable_integration_tests else '❌'}",
        f"- End-to-End Tests: {'✅' if config.enable_end_to_end_tests else '❌'}",
        f"- Cross-Component Tests: {'✅' if config.enable_cross_component_tests else '❌'}",
        f"- Specification Compliance: {'✅' if config.enable_specification_compliance else '❌'}",
        f"- Format Contracts: {'✅' if config.enable_format_contracts else '❌'}",
        f"- Enhanced Assertions: {'✅' if config.enable_enhanced_assertions else '❌'}",
        f"- Performance Tests: {'✅' if config.enable_performance_tests else '❌'}",
        "",
        "## Test Data Configuration",
        f"- Languages: {', '.join(config.test_data_languages)}",
        f"- Complexities: {', '.join(config.test_data_complexities)}",
        f"- Performance Iterations: {config.performance_iterations}",
        "",
    ]


def _recommendation_lines(results: TestSuiteResults) -> list[str]:
    if results.failed_tests <= 0:
        return []

    report_lines = ["## Recommendations", ""]
    if results.failed_tests > results.passed_tests:
        report_lines.append(
            "🚨 **Critical**: More tests failed than passed. Immediate attention required."
        )
    elif results.success_rate < 80:
        report_lines.append(
            "⚠️ **Warning**: Success rate below 80%. Review failed tests."
        )
    else:
        report_lines.append("ℹ️ **Info**: Some tests failed. Review and address issues.")

    report_lines.append("")
    return report_lines
