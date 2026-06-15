"""
Comprehensive Format Testing Suite

Main test suite that integrates all format testing components.
Provides unified interface for running all format validation tests.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._comprehensive_suite_data import ComprehensiveSuiteDataMixin
from ._comprehensive_suite_models import (
    FormatTestSuiteConfig,
    TestSuiteResults,
    create_test_suite_results,
    finalize_test_suite_results,
)
from ._comprehensive_suite_phases import ComprehensiveSuitePhasesMixin
from ._comprehensive_suite_reporting import (
    generate_summary_report,
    save_comprehensive_results,
)
from ._comprehensive_suite_runner import run_enabled_phases
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
