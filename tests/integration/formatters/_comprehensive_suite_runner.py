"""Suite orchestration helpers for comprehensive formatter validation."""

from typing import Any

from ._comprehensive_suite_models import TestSuiteResults
from ._comprehensive_suite_reporting import update_test_counts

PHASES = [
    (
        "enable_golden_master",
        "\n📋 Phase 1: Golden Master Testing",
        "golden_master_results",
        "_run_golden_master_tests",
    ),
    (
        "enable_schema_validation",
        "\n🔍 Phase 2: Schema Validation Testing",
        "schema_validation_results",
        "_run_schema_validation_tests",
    ),
    (
        "enable_integration_tests",
        "\n🔗 Phase 3: Integration Testing",
        "integration_test_results",
        "_run_integration_tests",
    ),
    (
        "enable_end_to_end_tests",
        "\n🎯 Phase 4: End-to-End Testing",
        "end_to_end_results",
        "_run_end_to_end_tests",
    ),
    (
        "enable_cross_component_tests",
        "\n🌐 Phase 5: Cross-Component Testing",
        "cross_component_results",
        "_run_cross_component_tests",
    ),
    (
        "enable_specification_compliance",
        "\n📖 Phase 6: Specification Compliance Testing",
        "specification_compliance_results",
        "_run_specification_compliance_tests",
    ),
    (
        "enable_format_contracts",
        "\n📋 Phase 7: Format Contract Testing",
        "format_contract_results",
        "_run_format_contract_tests",
    ),
    (
        "enable_enhanced_assertions",
        "\n⚡ Phase 8: Enhanced Assertion Testing",
        "enhanced_assertion_results",
        "_run_enhanced_assertion_tests",
    ),
    (
        "enable_performance_tests",
        "\n🚀 Phase 9: Performance Testing",
        "performance_test_results",
        "_run_performance_tests",
    ),
]


async def run_enabled_phases(
    suite: Any,
    analyzer_function: callable,
    test_data_sources: list[dict[str, Any]],
    results: TestSuiteResults,
) -> None:
    """Run enabled suite phases and update aggregate counts."""
    for config_attr, phase_banner, result_attr, method_name in PHASES:
        if getattr(suite.config, config_attr):
            print(phase_banner)
            phase_results = await getattr(suite, method_name)(
                analyzer_function, test_data_sources
            )
            setattr(results, result_attr, phase_results)
            update_test_counts(results, phase_results)
