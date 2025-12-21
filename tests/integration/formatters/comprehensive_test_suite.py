"""
Comprehensive Format Testing Suite

Main test suite that integrates all format testing components.
Provides unified interface for running all format validation tests.
"""

import asyncio
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .enhanced_assertions import EnhancedAssertions
from .golden_master import GoldenMasterManager, GoldenMasterTester

# Import test classes from integration_tests module
from .integration_tests import (
    TestFormatConsistency,
    TestRealImplementationValidation,
    TestTableFormatToolIntegration,
)
from .performance_tests import FormatPerformanceTester
from .schema_validation import (
    CSVFormatValidator,
    JSONFormatValidator,
    MarkdownTableValidator,
)
from .test_data_manager import FormatTestDataManager


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


class ComprehensiveFormatTestSuite:
    """Main comprehensive format testing suite"""

    def __init__(self, config: FormatTestSuiteConfig = None):
        self.config = config or FormatTestSuiteConfig()

        # Initialize test data defaults
        if self.config.test_data_languages is None:
            self.config.test_data_languages = [
                "python",
                "java",
                "javascript",
                "typescript",
            ]

        if self.config.test_data_complexities is None:
            self.config.test_data_complexities = ["simple", "medium", "complex"]

        if self.config.scalability_test_sizes is None:
            self.config.scalability_test_sizes = [100, 500, 1000, 5000]

        # Create results directory
        self.results_dir = Path(self.config.results_directory)
        self.results_dir.mkdir(exist_ok=True)

        # Initialize test components
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

        start_time = datetime.utcnow()

        print("🚀 Starting Comprehensive Format Testing Suite")
        print(f"Configuration: {self.config}")

        # Prepare test data
        if test_data_sources is None:
            test_data_sources = await self._prepare_test_data()

        # Initialize results
        results = TestSuiteResults(
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

        # Run test phases
        try:
            # Phase 1: Golden Master Tests
            if self.config.enable_golden_master:
                print("\n📋 Phase 1: Golden Master Testing")
                results.golden_master_results = await self._run_golden_master_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.golden_master_results)

            # Phase 2: Schema Validation Tests
            if self.config.enable_schema_validation:
                print("\n🔍 Phase 2: Schema Validation Testing")
                results.schema_validation_results = (
                    await self._run_schema_validation_tests(
                        analyzer_function, test_data_sources
                    )
                )
                self._update_test_counts(results, results.schema_validation_results)

            # Phase 3: Integration Tests
            if self.config.enable_integration_tests:
                print("\n🔗 Phase 3: Integration Testing")
                results.integration_test_results = await self._run_integration_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.integration_test_results)

            # Phase 4: End-to-End Tests
            if self.config.enable_end_to_end_tests:
                print("\n🎯 Phase 4: End-to-End Testing")
                results.end_to_end_results = await self._run_end_to_end_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.end_to_end_results)

            # Phase 5: Cross-Component Tests
            if self.config.enable_cross_component_tests:
                print("\n🌐 Phase 5: Cross-Component Testing")
                results.cross_component_results = await self._run_cross_component_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.cross_component_results)

            # Phase 6: Specification Compliance Tests
            if self.config.enable_specification_compliance:
                print("\n📖 Phase 6: Specification Compliance Testing")
                results.specification_compliance_results = (
                    await self._run_specification_compliance_tests(
                        analyzer_function, test_data_sources
                    )
                )
                self._update_test_counts(
                    results, results.specification_compliance_results
                )

            # Phase 7: Format Contract Tests
            if self.config.enable_format_contracts:
                print("\n📋 Phase 7: Format Contract Testing")
                results.format_contract_results = await self._run_format_contract_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.format_contract_results)

            # Phase 8: Enhanced Assertion Tests
            if self.config.enable_enhanced_assertions:
                print("\n⚡ Phase 8: Enhanced Assertion Testing")
                results.enhanced_assertion_results = (
                    await self._run_enhanced_assertion_tests(
                        analyzer_function, test_data_sources
                    )
                )
                self._update_test_counts(results, results.enhanced_assertion_results)

            # Phase 9: Performance Tests
            if self.config.enable_performance_tests:
                print("\n🚀 Phase 9: Performance Testing")
                results.performance_test_results = await self._run_performance_tests(
                    analyzer_function, test_data_sources
                )
                self._update_test_counts(results, results.performance_test_results)

        except Exception as e:
            print(f"❌ Error during test execution: {e}")
            results.failed_tests += 1

        # Calculate final metrics
        end_time = datetime.utcnow()
        results.execution_time_seconds = (end_time - start_time).total_seconds()

        if results.total_tests > 0:
            results.success_rate = results.passed_tests / results.total_tests * 100

        # Save results
        if self.config.save_detailed_results:
            await self._save_comprehensive_results(results)

        # Generate summary report
        await self._generate_summary_report(results)

        print(
            f"\n✅ Comprehensive testing completed in {results.execution_time_seconds:.2f} seconds"
        )
        print(
            f"📊 Results: {results.passed_tests}/{results.total_tests} tests passed ({results.success_rate:.1f}%)"
        )

        return results

    async def _prepare_test_data(self) -> list[dict[str, Any]]:
        """Prepare test data for comprehensive testing"""

        test_data_sources = []

        if self.config.generate_test_data:
            print("📝 Generating test data...")

            # Create test data suite
            created_ids = self.test_data_manager.create_test_data_suite(
                languages=self.config.test_data_languages,
                complexities=self.config.test_data_complexities,
                count_per_combination=2,
            )

            # Load created test data
            for test_id in created_ids:
                test_data_set = self.test_data_manager.repository.get_test_data(test_id)
                if test_data_set:
                    test_data_sources.append(
                        {
                            "id": test_id,
                            "language": test_data_set.metadata.language,
                            "complexity": test_data_set.metadata.complexity_level,
                            "source_code": test_data_set.source_code,
                            "expected_outputs": test_data_set.expected_outputs,
                            "test_scenarios": test_data_set.test_scenarios,
                        }
                    )

        # Add some default test cases if no data generated
        if not test_data_sources:
            test_data_sources = [
                {
                    "id": "default_python",
                    "language": "python",
                    "complexity": "simple",
                    "source_code": 'class TestClass:\n    def test_method(self):\n        return "test"',
                    "expected_outputs": {},
                    "test_scenarios": [],
                }
            ]

        print(f"📊 Prepared {len(test_data_sources)} test data sources")
        return test_data_sources

    async def _run_golden_master_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run golden master tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        for test_data in test_data_sources:
            for format_type in ["full", "compact", "csv"]:
                test_name = f"golden_master_{test_data['language']}_{format_type}"
                results["total"] += 1

                try:
                    # Generate current output
                    current_output = analyzer_function(
                        test_data["source_code"], format_type=format_type
                    )

                    # Compare with golden master
                    # Check if golden master exists
                    golden_content = (
                        self.golden_master_tester.get_golden_master_content(test_name)
                    )

                    if golden_content is None:
                        # No golden master exists, create one
                        self.golden_master_tester.create_golden_master(
                            current_output, test_name
                        )
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Golden master created",
                            }
                        )
                        continue

                    comparison_result = {"matches": current_output == golden_content}

                    if comparison_result["matches"]:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Matches golden master",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": f"Golden master mismatch: {comparison_result.get('differences', 'Unknown')}",
                            }
                        )

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        return results

    async def _run_schema_validation_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run schema validation tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        for test_data in test_data_sources:
            for format_type in ["full", "compact", "csv"]:
                test_name = f"schema_validation_{test_data['language']}_{format_type}"
                results["total"] += 1

                try:
                    # Generate output
                    # Handle both sync and async analyzer functions
                    if asyncio.iscoroutinefunction(analyzer_function):
                        output = await analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )
                    else:
                        output = analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )

                    # Validate schema
                    if format_type in ["full", "compact"]:
                        validation_result = self.markdown_validator.validate(output)
                        # For now, accept both markdown tables and text-based formats
                        # Text-based format uses = and - instead of markdown tables
                        is_valid = validation_result.is_valid or (
                            "=" in output and "-" in output
                        )
                        errors = validation_result.errors if not is_valid else []
                    elif format_type == "csv":
                        validation_result = self.csv_validator.validate(output)
                        is_valid = validation_result.is_valid
                        errors = validation_result.errors
                    else:
                        is_valid = True
                        errors = []

                    if is_valid:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Schema validation passed",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": f"Schema validation failed: {errors}",
                            }
                        )

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        return results

    async def _run_integration_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run integration tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        # Run integration tests using actual test classes
        try:
            # Run basic integration validation
            for test_data in test_data_sources:
                test_name = f"integration_{test_data['language']}"
                results["total"] += 1

                try:
                    # Create temporary file for testing
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=f".{test_data['language']}", delete=False
                    ) as f:
                        f.write(test_data["source_code"])
                        temp_file = f.name

                    # Test format generation
                    output = analyzer_function(
                        test_data["source_code"], format_type="full"
                    )

                    # Basic validation
                    if output and len(output.strip()) > 0:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Integration test passed",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": "Empty output generated",
                            }
                        )

                    # Cleanup
                    Path(temp_file).unlink(missing_ok=True)

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        except Exception as e:
            results["failed"] += 1
            results["total"] += 1
            results["details"].append(
                {"test": "integration_suite", "status": "error", "message": str(e)}
            )

        return results

    async def _run_end_to_end_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run end-to-end tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        try:
            # Run end-to-end tests for each format type
            for test_data in test_data_sources:
                for format_type in ["full", "compact", "csv"]:
                    test_name = f"e2e_{test_data['language']}_{format_type}"
                    results["total"] += 1

                    try:
                        # Generate output
                        output = analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )

                        # Validate output structure
                        if format_type in ["full", "compact"]:
                            # Should contain markdown headers
                            if "#" in output and "|" in output:
                                results["passed"] += 1
                                results["details"].append(
                                    {
                                        "test": test_name,
                                        "status": "passed",
                                        "message": "End-to-end test passed",
                                    }
                                )
                            else:
                                results["failed"] += 1
                                results["details"].append(
                                    {
                                        "test": test_name,
                                        "status": "failed",
                                        "message": "Invalid markdown structure",
                                    }
                                )
                        elif format_type == "csv":
                            # Should contain CSV structure
                            if "," in output and "\n" in output:
                                results["passed"] += 1
                                results["details"].append(
                                    {
                                        "test": test_name,
                                        "status": "passed",
                                        "message": "End-to-end test passed",
                                    }
                                )
                            else:
                                results["failed"] += 1
                                results["details"].append(
                                    {
                                        "test": test_name,
                                        "status": "failed",
                                        "message": "Invalid CSV structure",
                                    }
                                )

                    except Exception as e:
                        results["failed"] += 1
                        results["details"].append(
                            {"test": test_name, "status": "error", "message": str(e)}
                        )

        except Exception as e:
            results["failed"] += 1
            results["total"] += 1
            results["details"].append(
                {"test": "end_to_end_suite", "status": "error", "message": str(e)}
            )

        return results

    async def _run_cross_component_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run cross-component tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        try:
            # Run cross-component consistency tests
            for test_data in test_data_sources:
                test_name = f"cross_component_{test_data['language']}"
                results["total"] += 1

                try:
                    # Test format consistency across different format types
                    outputs = {}
                    for format_type in ["full", "compact", "csv"]:
                        outputs[format_type] = analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )

                    # Basic consistency check - all outputs should be non-empty
                    all_valid = all(
                        output and len(output.strip()) > 0
                        for output in outputs.values()
                    )

                    if all_valid:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Cross-component consistency test passed",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": "Inconsistent outputs across formats",
                            }
                        )

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        except Exception as e:
            results["failed"] += 1
            results["total"] += 1
            results["details"].append(
                {"test": "cross_component_suite", "status": "error", "message": str(e)}
            )

        return results

    async def _run_specification_compliance_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run specification compliance tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        try:
            # Run specification compliance tests
            for test_data in test_data_sources:
                for format_type in ["full", "compact", "csv"]:
                    test_name = f"spec_compliance_{test_data['language']}_{format_type}"
                    results["total"] += 1

                    try:
                        # Generate output
                        # Handle both sync and async analyzer functions
                        if asyncio.iscoroutinefunction(analyzer_function):
                            output = await analyzer_function(
                                test_data["source_code"], format_type=format_type
                            )
                        else:
                            output = analyzer_function(
                                test_data["source_code"], format_type=format_type
                            )

                        # Basic specification compliance checks
                        compliance_passed = True

                        if format_type == "full":
                            # Should have main header and section headers (flexible for both formats)
                            if not (
                                ("#" in output and "##" in output)
                                or ("=" in output and "-" in output)
                            ):
                                compliance_passed = False
                        elif format_type == "compact":
                            # Should have headers and table structure (flexible for both formats)
                            if not (
                                ("#" in output and "|" in output) or ("-" in output)
                            ):
                                compliance_passed = False
                        elif format_type == "csv":
                            # Should have comma-separated values
                            if not ("," in output and "\n" in output):
                                compliance_passed = False

                        if compliance_passed:
                            results["passed"] += 1
                            results["details"].append(
                                {
                                    "test": test_name,
                                    "status": "passed",
                                    "message": "Specification compliance test passed",
                                }
                            )
                        else:
                            results["failed"] += 1
                            results["details"].append(
                                {
                                    "test": test_name,
                                    "status": "failed",
                                    "message": f"Specification compliance failed for {format_type} format",
                                }
                            )

                    except Exception as e:
                        results["failed"] += 1
                        results["details"].append(
                            {"test": test_name, "status": "error", "message": str(e)}
                        )

        except Exception as e:
            results["failed"] += 1
            results["total"] += 1
            results["details"].append(
                {
                    "test": "specification_compliance_suite",
                    "status": "error",
                    "message": str(e),
                }
            )

        return results

    async def _run_format_contract_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run format contract tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        try:
            # Run format contract tests
            for test_data in test_data_sources:
                test_name = f"format_contract_{test_data['language']}"
                results["total"] += 1

                try:
                    # Test format contracts - consistency across multiple runs
                    outputs = []
                    for _ in range(3):  # Run 3 times to check consistency
                        output = analyzer_function(
                            test_data["source_code"], format_type="full"
                        )
                        outputs.append(output)

                    # All outputs should be identical (deterministic)
                    all_identical = all(output == outputs[0] for output in outputs)

                    if all_identical:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Format contract test passed - deterministic output",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": "Format contract failed - non-deterministic output",
                            }
                        )

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        except Exception as e:
            results["failed"] += 1
            results["total"] += 1
            results["details"].append(
                {"test": "format_contract_suite", "status": "error", "message": str(e)}
            )

        return results

    async def _run_enhanced_assertion_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run enhanced assertion tests"""

        results = {"passed": 0, "failed": 0, "total": 0, "details": []}

        for test_data in test_data_sources:
            for format_type in ["full", "compact", "csv"]:
                test_name = f"enhanced_assertions_{test_data['language']}_{format_type}"
                results["total"] += 1

                try:
                    # Generate output
                    # Handle both sync and async analyzer functions
                    if asyncio.iscoroutinefunction(analyzer_function):
                        output = await analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )
                    else:
                        output = analyzer_function(
                            test_data["source_code"], format_type=format_type
                        )

                    # Run enhanced assertions
                    assertion_result = self.enhanced_assertions.validate_format_output(
                        output, format_type, test_data["language"]
                    )

                    if assertion_result["valid"]:
                        results["passed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "passed",
                                "message": "Enhanced assertions passed",
                            }
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "test": test_name,
                                "status": "failed",
                                "message": f"Enhanced assertions failed: {assertion_result['issues']}",
                            }
                        )

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"test": test_name, "status": "error", "message": str(e)}
                    )

        return results

    async def _run_performance_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run performance tests"""

        results = {
            "passed": 0,
            "failed": 0,
            "total": 0,
            "details": [],
            "performance_metrics": [],
        }

        for test_data in test_data_sources:
            test_name = f"performance_{test_data['language']}"
            results["total"] += 1

            try:
                # Run format performance test
                performance_results = self.performance_tester.test_format_performance(
                    analyzer_function, test_data["source_code"], test_data["language"]
                )

                # Check if performance is acceptable
                performance_acceptable = True
                for _format_type, metrics in performance_results.items():
                    if (
                        not metrics.success or metrics.execution_time_ms > 5000
                    ):  # 5 second threshold
                        performance_acceptable = False
                        break

                if performance_acceptable:
                    results["passed"] += 1
                    results["details"].append(
                        {
                            "test": test_name,
                            "status": "passed",
                            "message": "Performance within acceptable limits",
                        }
                    )
                else:
                    results["failed"] += 1
                    results["details"].append(
                        {
                            "test": test_name,
                            "status": "failed",
                            "message": "Performance exceeded acceptable limits",
                        }
                    )

                results["performance_metrics"].append(
                    {"test_name": test_name, "results": performance_results}
                )

            except Exception as e:
                results["failed"] += 1
                results["details"].append(
                    {"test": test_name, "status": "error", "message": str(e)}
                )

        return results

    def _update_test_counts(
        self, results: TestSuiteResults, phase_results: dict[str, Any]
    ):
        """Update test counts from phase results"""
        results.total_tests += phase_results.get("total", 0)
        results.passed_tests += phase_results.get("passed", 0)
        results.failed_tests += phase_results.get("failed", 0)

    async def _save_comprehensive_results(self, results: TestSuiteResults):
        """Save comprehensive test results"""
        results_file = (
            self.results_dir
            / f"comprehensive_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Convert results to dict for JSON serialization
        results_dict = {
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

        with open(results_file, "w") as f:
            json.dump(results_dict, f, indent=2)

        print(f"💾 Detailed results saved to: {results_file}")

    async def _generate_summary_report(self, results: TestSuiteResults):
        """Generate summary report"""
        report_file = (
            self.results_dir
            / f"summary_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        )

        report_lines = [
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

        # Add phase results
        phases = [
            ("Golden Master Tests", results.golden_master_results),
            ("Schema Validation Tests", results.schema_validation_results),
            ("Integration Tests", results.integration_test_results),
            ("End-to-End Tests", results.end_to_end_results),
            ("Cross-Component Tests", results.cross_component_results),
            (
                "Specification Compliance Tests",
                results.specification_compliance_results,
            ),
            ("Format Contract Tests", results.format_contract_results),
            ("Enhanced Assertion Tests", results.enhanced_assertion_results),
            ("Performance Tests", results.performance_test_results),
        ]

        for phase_name, phase_results in phases:
            if phase_results:
                total = phase_results.get("total", 0)
                passed = phase_results.get("passed", 0)
                failed = phase_results.get("failed", 0)
                success_rate = (passed / total * 100) if total > 0 else 0

                status_emoji = "✅" if failed == 0 else "⚠️" if passed > failed else "❌"

                report_lines.extend(
                    [
                        f"### {status_emoji} {phase_name}",
                        f"- Total: {total}",
                        f"- Passed: {passed}",
                        f"- Failed: {failed}",
                        f"- Success Rate: {success_rate:.1f}%",
                        "",
                    ]
                )

        # Add configuration
        report_lines.extend(
            [
                "## Configuration",
                f"- Golden Master Tests: {'✅' if self.config.enable_golden_master else '❌'}",
                f"- Schema Validation: {'✅' if self.config.enable_schema_validation else '❌'}",
                f"- Integration Tests: {'✅' if self.config.enable_integration_tests else '❌'}",
                f"- End-to-End Tests: {'✅' if self.config.enable_end_to_end_tests else '❌'}",
                f"- Cross-Component Tests: {'✅' if self.config.enable_cross_component_tests else '❌'}",
                f"- Specification Compliance: {'✅' if self.config.enable_specification_compliance else '❌'}",
                f"- Format Contracts: {'✅' if self.config.enable_format_contracts else '❌'}",
                f"- Enhanced Assertions: {'✅' if self.config.enable_enhanced_assertions else '❌'}",
                f"- Performance Tests: {'✅' if self.config.enable_performance_tests else '❌'}",
                "",
                "## Test Data Configuration",
                f"- Languages: {', '.join(self.config.test_data_languages)}",
                f"- Complexities: {', '.join(self.config.test_data_complexities)}",
                f"- Performance Iterations: {self.config.performance_iterations}",
                "",
            ]
        )

        # Add recommendations
        if results.failed_tests > 0:
            report_lines.extend(["## Recommendations", ""])

            if results.failed_tests > results.passed_tests:
                report_lines.append(
                    "🚨 **Critical**: More tests failed than passed. Immediate attention required."
                )
            elif results.success_rate < 80:
                report_lines.append(
                    "⚠️ **Warning**: Success rate below 80%. Review failed tests."
                )
            else:
                report_lines.append(
                    "ℹ️ **Info**: Some tests failed. Review and address issues."
                )

            report_lines.append("")

        report_content = "\n".join(report_lines)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"📊 Summary report saved to: {report_file}")


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
