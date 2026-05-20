"""Models and result helpers for the comprehensive formatter test suite."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class FormatTestSuiteConfig:
    """Configuration for comprehensive test suite"""

    enable_golden_master: bool = True
    enable_schema_validation: bool = True
    enable_integration_tests: bool = True
    enable_end_to_end_tests: bool = True
    enable_cross_component_tests: bool = True
    enable_specification_compliance: bool = True
    enable_format_contracts: bool = True
    enable_performance_tests: bool = True
    enable_enhanced_assertions: bool = True

    # Test data configuration
    generate_test_data: bool = True
    test_data_languages: list[str] = None
    test_data_complexities: list[str] = None

    # Performance test configuration
    performance_iterations: int = 3
    scalability_test_sizes: list[int] = None

    # Output configuration
    save_detailed_results: bool = True
    results_directory: str = "comprehensive_test_results"


@dataclass
class TestSuiteResults:
    """Results from comprehensive test suite execution"""

    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int

    golden_master_results: dict[str, Any]
    schema_validation_results: dict[str, Any]
    integration_test_results: dict[str, Any]
    end_to_end_results: dict[str, Any]
    cross_component_results: dict[str, Any]
    specification_compliance_results: dict[str, Any]
    format_contract_results: dict[str, Any]
    performance_test_results: dict[str, Any]
    enhanced_assertion_results: dict[str, Any]

    execution_time_seconds: float
    timestamp: str
    success_rate: float


def create_test_suite_results(start_time: datetime) -> TestSuiteResults:
    """Create an empty result object for a suite run."""
    return TestSuiteResults(
        total_tests=0,
        passed_tests=0,
        failed_tests=0,
        skipped_tests=0,
        golden_master_results={},
        schema_validation_results={},
        integration_test_results={},
        end_to_end_results={},
        cross_component_results={},
        specification_compliance_results={},
        format_contract_results={},
        performance_test_results={},
        enhanced_assertion_results={},
        execution_time_seconds=0,
        timestamp=start_time.isoformat(),
        success_rate=0.0,
    )


def finalize_test_suite_results(
    results: TestSuiteResults,
    start_time: datetime,
) -> None:
    """Populate final timing and success-rate metrics."""
    end_time = datetime.now(UTC)
    results.execution_time_seconds = (end_time - start_time).total_seconds()

    if results.total_tests > 0:
        results.success_rate = results.passed_tests / results.total_tests * 100


def suite_results_to_dict(results: TestSuiteResults) -> dict[str, Any]:
    """Convert result dataclass to JSON-serializable dictionary."""
    return {
        "total_tests": results.total_tests,
        "passed_tests": results.passed_tests,
        "failed_tests": results.failed_tests,
        "skipped_tests": results.skipped_tests,
        "success_rate": results.success_rate,
        "execution_time_seconds": results.execution_time_seconds,
        "timestamp": results.timestamp,
        "golden_master_results": results.golden_master_results,
        "schema_validation_results": results.schema_validation_results,
        "integration_test_results": results.integration_test_results,
        "end_to_end_results": results.end_to_end_results,
        "cross_component_results": results.cross_component_results,
        "specification_compliance_results": results.specification_compliance_results,
        "format_contract_results": results.format_contract_results,
        "performance_test_results": results.performance_test_results,
        "enhanced_assertion_results": results.enhanced_assertion_results,
    }
