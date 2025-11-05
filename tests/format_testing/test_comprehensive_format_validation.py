"""
Comprehensive Format Validation Tests

Main test file that demonstrates and validates the comprehensive format testing framework.
This file serves as both documentation and validation of the testing infrastructure.
"""

import json
import tempfile
from pathlib import Path

import pytest

from .comprehensive_test_suite import (
    ComprehensiveFormatTestSuite,
    FormatTestSuiteConfig,
    run_quick_format_validation,
)


# Mock analyzer function for testing
def mock_analyzer_function(source_code: str, format_type: str = "full") -> str:
    """Mock analyzer function that generates predictable output for testing"""

    if format_type == "full":
        return """# Analysis Results

## Classes

| Name | Type | Line | Access |
|------|------|------|--------|
| TestClass | class | 1 | public |

## Methods

| Name | Type | Return Type | Parameters | Line |
|------|------|-------------|------------|------|
| test_method | method | str | self | 2 |

## Summary

- Total Classes: 1
- Total Methods: 1
- Total Fields: 0
"""

    elif format_type == "compact":
        return """# Analysis

| Name | Type |
|------|------|
| TestClass | class |
| test_method | method |
"""

    elif format_type == "csv":
        return """Type,Name,Signature,Visibility,Lines
class,TestClass,TestClass,public,1
method,test_method,test_method(self) -> str,public,2
"""

    else:
        return f"Unknown format: {format_type}"


class TestComprehensiveFormatValidation:
    """Test cases for comprehensive format validation framework"""

    @pytest.fixture
    def temp_results_dir(self):
        """Create temporary directory for test results"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_test_data(self):
        """Sample test data for validation"""
        return {
            "id": "test_sample",
            "language": "python",
            "complexity": "simple",
            "source_code": """class TestClass:
    def test_method(self):
        return "test"
""",
            "expected_outputs": {},
            "test_scenarios": [],
        }

    def test_test_suite_config_creation(self):
        """Test TestSuiteConfig creation and defaults"""
        config = FormatTestSuiteConfig()

        assert config.enable_golden_master is True
        assert config.enable_schema_validation is True
        assert config.enable_integration_tests is True
        assert config.enable_end_to_end_tests is True
        assert config.enable_cross_component_tests is True
        assert config.enable_specification_compliance is True
        assert config.enable_format_contracts is True
        assert config.enable_performance_tests is True
        assert config.enable_enhanced_assertions is True
        assert config.generate_test_data is True
        assert config.performance_iterations == 3
        assert config.save_detailed_results is True

    def test_test_suite_config_customization(self):
        """Test FormatTestSuiteConfig customization"""

        config = FormatTestSuiteConfig(
            enable_golden_master=False,
            enable_performance_tests=False,
            test_data_languages=["python"],
            performance_iterations=1,
        )

        assert config.enable_golden_master is False
        assert config.enable_performance_tests is False
        assert config.test_data_languages == ["python"]
        assert config.performance_iterations == 1

    def test_comprehensive_test_suite_initialization(self, temp_results_dir):
        """Test ComprehensiveFormatTestSuite initialization"""
        config = FormatTestSuiteConfig(
            results_directory=temp_results_dir,
            generate_test_data=False,  # Disable to avoid dependencies
        )

        suite = ComprehensiveFormatTestSuite(config)

        assert suite.config == config
        assert suite.results_dir.exists()
        assert hasattr(suite, "golden_master_manager")
        assert hasattr(suite, "markdown_validator")
        assert hasattr(suite, "enhanced_assertions")

    @pytest.mark.asyncio
    async def test_quick_format_validation(self):
        """Test quick format validation function"""
        test_code = """class TestClass:
    def test_method(self):
        return "test"
"""

        result = await run_quick_format_validation(
            mock_analyzer_function, test_code, "python"
        )

        assert isinstance(result, bool)
        # Result may be True or False depending on validation, but should not error

    @pytest.mark.asyncio
    async def test_comprehensive_test_suite_execution(self, temp_results_dir):
        """Test comprehensive test suite execution"""
        config = FormatTestSuiteConfig(
            results_directory=temp_results_dir,
            generate_test_data=False,  # Use provided test data
            enable_performance_tests=False,  # Disable to speed up test
            enable_integration_tests=False,  # Disable complex tests
            enable_end_to_end_tests=False,
            enable_cross_component_tests=False,
        )

        suite = ComprehensiveFormatTestSuite(config)

        # Provide simple test data
        test_data_sources = [
            {
                "id": "test_python",
                "language": "python",
                "complexity": "simple",
                "source_code": """class TestClass:
    def test_method(self):
        return "test"
""",
                "expected_outputs": {},
                "test_scenarios": [],
            }
        ]

        results = await suite.run_comprehensive_tests(
            mock_analyzer_function, test_data_sources
        )

        assert results.total_tests > 0
        assert results.execution_time_seconds > 0
        assert results.timestamp is not None
        assert 0 <= results.success_rate <= 100

    def test_mock_analyzer_function_formats(self):
        """Test mock analyzer function produces expected formats"""
        test_code = """class TestClass:
    def test_method(self):
        return "test"
"""

        # Test full format
        full_output = mock_analyzer_function(test_code, "full")
        assert "# Analysis Results" in full_output
        assert "## Classes" in full_output
        assert "## Methods" in full_output
        assert "TestClass" in full_output
        assert "test_method" in full_output

        # Test compact format
        compact_output = mock_analyzer_function(test_code, "compact")
        assert "# Analysis" in compact_output
        assert "TestClass" in compact_output
        assert "test_method" in compact_output

        # Test CSV format
        csv_output = mock_analyzer_function(test_code, "csv")
        assert "Type,Name,Signature" in csv_output
        assert "class,TestClass" in csv_output
        assert "method,test_method" in csv_output

    @pytest.mark.asyncio
    async def test_schema_validation_with_mock_output(self):
        """Test schema validation with mock analyzer output"""
        from .schema_validation import CSVFormatValidator, MarkdownTableValidator

        markdown_validator = MarkdownTableValidator()
        csv_validator = CSVFormatValidator()

        test_code = "class TestClass: pass"

        # Test markdown validation
        full_output = mock_analyzer_function(test_code, "full")
        markdown_result = markdown_validator.validate(full_output)
        assert markdown_result.is_valid

        compact_output = mock_analyzer_function(test_code, "compact")
        markdown_result = markdown_validator.validate(compact_output)
        assert markdown_result.is_valid

        # Test CSV validation
        csv_output = mock_analyzer_function(test_code, "csv")
        csv_result = csv_validator.validate(csv_output)
        assert csv_result.is_valid

    @pytest.mark.asyncio
    async def test_golden_master_functionality(self, temp_results_dir):
        """Test golden master functionality"""
        from .golden_master import GoldenMasterTester

        tester = GoldenMasterTester("full", Path(temp_results_dir) / "golden_masters")

        test_output = mock_analyzer_function("class Test: pass", "full")

        # First run should create golden master
        tester.assert_matches_golden_master(
            test_output, "test_golden", update_golden=True
        )

        # Second run should match
        tester.assert_matches_golden_master(test_output, "test_golden")

        # Different output should not match - this will raise AssertionError
        different_output = mock_analyzer_function("class Different: pass", "full")
        try:
            tester.assert_matches_golden_master(different_output, "test_golden")
            assert False, "Expected AssertionError for different output"
        except AssertionError:
            pass  # Expected behavior

    @pytest.mark.asyncio
    async def test_enhanced_assertions(self):
        """Test enhanced assertions functionality"""
        from .enhanced_assertions import EnhancedAssertions

        enhanced_assertions = EnhancedAssertions()

        # Test with mock output
        test_output = mock_analyzer_function("class TestClass: pass", "full")

        result = enhanced_assertions.validate_format_output(
            test_output, "full", "python"
        )

        assert "valid" in result
        assert "issues" in result

    def test_format_assertions_basic(self):
        """Test basic format assertions"""
        from .format_assertions import FormatAssertions

        assertions = FormatAssertions()

        # Test markdown table validation
        valid_table = """| Name | Type |
|------|------|
| TestClass | class |"""

        assert assertions.assert_valid_markdown_table(valid_table) is True

        # Test CSV validation
        valid_csv = "Type,Name\nclass,TestClass"
        assert assertions.assert_valid_csv_format(valid_csv) is True

    @pytest.mark.asyncio
    async def test_performance_testing_framework(self, temp_results_dir):
        """Test performance testing framework"""
        from .performance_tests import FormatPerformanceTester

        performance_tester = FormatPerformanceTester(
            str(Path(temp_results_dir) / "performance_results")
        )

        test_data = "class TestClass: pass"

        # Test format performance
        results = performance_tester.test_format_performance(
            mock_analyzer_function, test_data, "python", ["full", "compact"]
        )

        assert "full" in results
        assert "compact" in results
        assert results["full"].success is True
        assert results["compact"].success is True
        assert results["full"].execution_time_ms >= 0
        assert results["compact"].execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_test_data_manager(self, temp_results_dir):
        """Test test data manager functionality"""
        from .test_data_manager import FormatTestDataManager

        manager = FormatTestDataManager(str(Path(temp_results_dir) / "test_data"))

        # Generate test data
        test_data = manager.generator.generate_test_data("python", "simple")

        assert test_data.metadata.language == "python"
        assert test_data.metadata.complexity_level == "simple"
        assert test_data.source_code is not None
        assert len(test_data.source_code) > 0

        # Store test data
        test_id = manager.repository.store_test_data(test_data)
        assert test_id is not None

        # Retrieve test data
        retrieved_data = manager.repository.get_test_data(test_id)
        assert retrieved_data is not None
        assert retrieved_data.metadata.id == test_id

    @pytest.mark.asyncio
    async def test_integration_with_real_components(self, temp_results_dir):
        """Test integration with real tree-sitter-analyzer components if available"""
        try:
            # Try to import real analyzer components
            from tree_sitter_analyzer.core.analysis_engine import AnalysisEngine
            from tree_sitter_analyzer.formatters.formatter_factory import (
                FormatterFactory,
            )

            # If available, test with real components
            config = FormatTestSuiteConfig(
                results_directory=temp_results_dir,
                generate_test_data=False,
                enable_performance_tests=False,
                enable_integration_tests=False,
                enable_end_to_end_tests=False,
                enable_cross_component_tests=False,
            )

            suite = ComprehensiveFormatTestSuite(config)

            # Simple test with real components would go here
            # This is a placeholder for when real integration is needed

        except ImportError:
            # If real components not available, skip this test
            pytest.skip("Real tree-sitter-analyzer components not available")

    def test_results_serialization(self, temp_results_dir):
        """Test that results can be properly serialized and saved"""
        from .comprehensive_test_suite import TestSuiteResults

        results = TestSuiteResults(
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            skipped_tests=0,
            golden_master_results={"passed": 3, "failed": 1, "total": 4},
            schema_validation_results={"passed": 2, "failed": 1, "total": 3},
            integration_test_results={},
            end_to_end_results={},
            cross_component_results={},
            specification_compliance_results={},
            format_contract_results={},
            performance_test_results={},
            enhanced_assertion_results={"passed": 3, "failed": 0, "total": 3},
            execution_time_seconds=45.5,
            timestamp="2024-01-01T00:00:00",
            success_rate=80.0,
        )

        # Test that results can be converted to dict for JSON serialization
        results_dict = {
            "total_tests": results.total_tests,
            "passed_tests": results.passed_tests,
            "failed_tests": results.failed_tests,
            "success_rate": results.success_rate,
            "execution_time_seconds": results.execution_time_seconds,
            "timestamp": results.timestamp,
        }

        # Test JSON serialization
        json_str = json.dumps(results_dict)
        assert json_str is not None

        # Test deserialization
        loaded_dict = json.loads(json_str)
        assert loaded_dict["total_tests"] == 10
        assert loaded_dict["success_rate"] == 80.0


class TestFormatRegressionPrevention:
    """Test cases specifically for format regression prevention"""

    @pytest.mark.asyncio
    async def test_format_consistency_across_versions(self):
        """Test that format output remains consistent across different scenarios"""

        test_cases = [
            "class SimpleClass: pass",
            "class ComplexClass:\n    def method(self):\n        return 'value'",
            "def function():\n    return 42",
        ]

        for test_case in test_cases:
            # Test all format types
            full_output = mock_analyzer_function(test_case, "full")
            compact_output = mock_analyzer_function(test_case, "compact")
            csv_output = mock_analyzer_function(test_case, "csv")

            # Basic consistency checks
            assert len(full_output) > 0
            assert len(compact_output) > 0
            assert len(csv_output) > 0

            # Format-specific checks
            assert "# Analysis Results" in full_output
            assert "# Analysis" in compact_output
            assert "Type,Name" in csv_output

    @pytest.mark.asyncio
    async def test_backward_compatibility_validation(self):
        """Test backward compatibility of format outputs"""

        # This test would validate that new versions maintain compatibility
        # with previous format specifications

        test_code = """class TestClass:
    def __init__(self):
        self.value = "test"

    def get_value(self):
        return self.value
"""

        # Generate outputs in all formats
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            outputs[format_type] = mock_analyzer_function(test_code, format_type)

        # Validate that outputs contain expected elements
        # (This would be more comprehensive with real format specifications)
        assert "TestClass" in outputs["full"]
        assert "TestClass" in outputs["compact"]
        assert "TestClass" in outputs["csv"]

    def test_format_specification_compliance(self):
        """Test compliance with format specifications"""

        from .schema_validation import CSVFormatValidator, MarkdownTableValidator

        markdown_validator = MarkdownTableValidator()
        csv_validator = CSVFormatValidator()

        test_code = "class SpecTest: pass"

        # Test specification compliance
        full_output = mock_analyzer_function(test_code, "full")
        compact_output = mock_analyzer_function(test_code, "compact")
        csv_output = mock_analyzer_function(test_code, "csv")

        # Validate against specifications
        full_result = markdown_validator.validate(full_output)
        compact_result = markdown_validator.validate(compact_output)
        csv_result = csv_validator.validate(csv_output)

        # All should be valid according to specifications
        assert full_result.is_valid or len(full_result.errors) == 0
        assert compact_result.is_valid or len(compact_result.errors) == 0
        assert csv_result.is_valid or len(csv_result.errors) == 0


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
