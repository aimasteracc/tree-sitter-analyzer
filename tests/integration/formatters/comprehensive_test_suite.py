"""
Comprehensive Format Testing Suite

Main test suite that integrates all format testing components.
Provides unified interface for running all format validation tests.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._comprehensive_suite_models import (
    FormatTestSuiteConfig,
    TestSuiteResults,
    create_test_suite_results,
    finalize_test_suite_results,
)
from ._comprehensive_suite_phases import ComprehensiveSuitePhasesMixin
from ._comprehensive_suite_reporting import (
    update_test_counts,
    generate_summary_report,
    save_comprehensive_results,
)
from .enhanced_assertions import EnhancedAssertions
from .golden_master import GoldenMasterManager, GoldenMasterTester
from .performance_tests import FormatPerformanceTester
from .schema_validation import (
    CSVFormatValidator,
    JSONFormatValidator,
    MarkdownTableValidator,
)
from .test_data_manager import FormatTestDataManager
from .test_formatter_integration import (
    TestFormatConsistency,
    TestRealImplementationValidation,
    TestTableFormatToolIntegration,
)

__all__ = [
    "ComprehensiveFormatTestSuite",
    "FormatTestSuiteConfig",
    "TestSuiteResults",
    "run_full_validation_suite",
    "run_quick_format_validation",
    "run_regression_test_suite",
]


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


class ComprehensiveSuiteDataMixin:
    """Prepares generated or fallback test data for suite phases."""

    async def _prepare_test_data(self) -> list[dict[str, Any]]:
        """Prepare test data for comprehensive testing"""
        test_data_sources = []

        if self.config.generate_test_data:
            print("📝 Generating test data...")
            created_ids = self.test_data_manager.create_test_data_suite(
                languages=self.config.test_data_languages,
                complexities=self.config.test_data_complexities,
                count_per_combination=2,
            )
            test_data_sources.extend(self._load_created_test_data(created_ids))

        if not test_data_sources:
            test_data_sources = [_default_python_test_data()]

        print(f"📊 Prepared {len(test_data_sources)} test data sources")
        return test_data_sources

    def _load_created_test_data(self, created_ids: list[str]) -> list[dict[str, Any]]:
        test_data_sources = []
        for test_id in created_ids:
            test_data_set = self.test_data_manager.repository.get_test_data(test_id)
            if test_data_set:
                test_data_sources.append(_test_data_set_source(test_id, test_data_set))
        return test_data_sources


def _test_data_set_source(test_id: str, test_data_set: Any) -> dict[str, Any]:
    return {
        "id": test_id,
        "language": test_data_set.metadata.language,
        "complexity": test_data_set.metadata.complexity_level,
        "source_code": test_data_set.source_code,
        "expected_outputs": test_data_set.expected_outputs,
        "test_scenarios": test_data_set.test_scenarios,
    }


def _default_python_test_data() -> dict[str, Any]:
    return {
        "id": "default_python",
        "language": "python",
        "complexity": "simple",
        "source_code": 'class TestClass:\n    def test_method(self):\n        return "test"',
        "expected_outputs": {},
        "test_scenarios": [],
    }


class ComprehensiveFormatTestSuite(
    ComprehensiveSuiteDataMixin, ComprehensiveSuitePhasesMixin
):
    """Main comprehensive format testing suite"""

    def __init__(self, config: FormatTestSuiteConfig = None):
        self.config = config or FormatTestSuiteConfig()
        _ensure_config_defaults(self.config)

        self.results_dir = Path(self.config.results_directory)
        self.results_dir.mkdir(exist_ok=True)

        self._initialize_test_components()

    def _initialize_test_components(self):
        """Initialize all test components"""

        # Core testing components
        if self.config.enable_golden_master:
            self.golden_master_manager = GoldenMasterManager(
                str(self.results_dir / "golden_masters")
            )
            self.golden_master_tester = GoldenMasterTester("full")

        if self.config.enable_schema_validation:
            self.markdown_validator = MarkdownTableValidator()
            self.csv_validator = CSVFormatValidator()
            self.json_validator = JSONFormatValidator()

        if self.config.enable_enhanced_assertions:
            self.enhanced_assertions = EnhancedAssertions()

        # Test suite components - using actual test classes
        if self.config.enable_integration_tests:
            self.table_format_integration = TestTableFormatToolIntegration()
            self.format_consistency = TestFormatConsistency()
            self.real_implementation_validation = TestRealImplementationValidation()

        # Test data and performance components
        if self.config.generate_test_data:
            self.test_data_manager = FormatTestDataManager(
                str(self.results_dir / "test_data_repository")
            )

        if self.config.enable_performance_tests:
            self.performance_tester = FormatPerformanceTester(
                str(self.results_dir / "performance_results")
            )

    async def run_comprehensive_tests(
        self,
        analyzer_function: callable,
        test_data_sources: list[dict[str, Any]] | None = None,
    ) -> TestSuiteResults:
        """Run comprehensive format testing suite"""
        start_time = datetime.now(timezone.utc)

        print("🚀 Starting Comprehensive Format Testing Suite")
        print(f"Configuration: {self.config}")

        if test_data_sources is None:
            test_data_sources = await self._prepare_test_data()

        results = create_test_suite_results(start_time)

        try:
            await run_enabled_phases(
                self, analyzer_function, test_data_sources, results
            )
        except Exception as exc:
            print(f"❌ Error during test execution: {exc}")
            results.failed_tests += 1

        finalize_test_suite_results(results, start_time)

        if self.config.save_detailed_results:
            await save_comprehensive_results(self.results_dir, results)

        await generate_summary_report(self.results_dir, self.config, results)

        print(
            f"\n✅ Comprehensive testing completed in {results.execution_time_seconds:.2f} seconds"
        )
        print(
            f"📊 Results: {results.passed_tests}/{results.total_tests} tests passed ({results.success_rate:.1f}%)"
        )

        return results


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


def _ensure_config_defaults(config: FormatTestSuiteConfig) -> None:
    if config.test_data_languages is None:
        config.test_data_languages = ["python", "java", "javascript", "typescript"]

    if config.test_data_complexities is None:
        config.test_data_complexities = ["simple", "medium", "complex"]

    if config.scalability_test_sizes is None:
        config.scalability_test_sizes = [100, 500, 1000, 5000]


# Convenience functions for running specific test types
async def run_quick_format_validation(
    analyzer_function, test_data: str, language: str = "python"
) -> bool:
    """Quick format validation for development use"""
    config = FormatTestSuiteConfig(
        enable_golden_master=False,
        enable_integration_tests=False,
        enable_end_to_end_tests=False,
        enable_cross_component_tests=False,
        enable_specification_compliance=True,
        enable_format_contracts=False,
        enable_performance_tests=False,
        enable_enhanced_assertions=True,
        generate_test_data=False,
    )

    suite = ComprehensiveFormatTestSuite(config)

    test_data_sources = [
        {
            "id": "quick_test",
            "language": language,
            "complexity": "simple",
            "source_code": test_data,
            "expected_outputs": {},
            "test_scenarios": [],
        }
    ]

    results = await suite.run_comprehensive_tests(analyzer_function, test_data_sources)
    return results.success_rate >= 80.0


async def run_regression_test_suite(analyzer_function) -> TestSuiteResults:
    """Run regression test suite with focus on golden master and performance"""
    config = FormatTestSuiteConfig(
        enable_golden_master=True,
        enable_schema_validation=True,
        enable_integration_tests=False,
        enable_end_to_end_tests=False,
        enable_cross_component_tests=False,
        enable_specification_compliance=True,
        enable_format_contracts=True,
        enable_performance_tests=True,
        enable_enhanced_assertions=False,
        generate_test_data=True,
        test_data_languages=["python", "java"],
        test_data_complexities=["medium"],
    )

    suite = ComprehensiveFormatTestSuite(config)
    return await suite.run_comprehensive_tests(analyzer_function)


async def run_full_validation_suite(analyzer_function) -> TestSuiteResults:
    """Run complete validation suite with all tests enabled"""
    config = FormatTestSuiteConfig()  # All tests enabled by default
    suite = ComprehensiveFormatTestSuite(config)
    return await suite.run_comprehensive_tests(analyzer_function)
