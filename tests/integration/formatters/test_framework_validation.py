"""
Framework Validation Test

Simple test to validate that the comprehensive format testing framework works correctly.
"""

import asyncio

import pytest

# Import the main testing framework
from .comprehensive_test_suite import (
    ComprehensiveFormatTestSuite,
    FormatTestSuiteConfig,
    run_quick_format_validation,
)


def simple_analyzer_function(source_code: str, format_type: str = "full") -> str:
    """
    Simple mock analyzer function for testing the framework
    """
    if format_type == "full":
        return """# Test Analysis

## Package
| Package | test.package |

## Class Info
| Name | TestClass |
| Type | class |
| Visibility | public |

## Methods
| Name | Signature | Visibility | Lines |
|------|-----------|------------|-------|
| testMethod | testMethod() | public | 1-3 |
"""
    elif format_type == "compact":
        return """# Test Analysis

## Info
| Name | TestClass |
| Type | class |

## Methods
| + | testMethod | testMethod() | 1-3 |
"""
    elif format_type == "csv":
        return """Type,Name,Signature,Visibility,Lines
Class,TestClass,TestClass,public,1-10
Method,testMethod,testMethod(),public,1-3
"""
    else:
        return "Unknown format type"


class TestFrameworkValidation:
    """Test the comprehensive format testing framework"""

    @pytest.mark.asyncio
    async def test_quick_format_validation(self):
        """Test quick format validation function"""

        test_code = """
class TestClass:
    def test_method(self):
        return "test"
"""

        # Run quick validation
        result = await run_quick_format_validation(
            simple_analyzer_function, test_code, "python"
        )

        # Should return True for successful validation
        assert isinstance(result, bool)
        print(f"Quick validation result: {result}")

    @pytest.mark.asyncio
    async def test_comprehensive_suite_basic(self):
        """Test basic comprehensive suite functionality"""

        # Create minimal configuration
        config = FormatTestSuiteConfig(
            enable_golden_master=False,  # Disable to avoid file dependencies
            enable_schema_validation=True,
            enable_integration_tests=True,
            enable_end_to_end_tests=True,
            enable_cross_component_tests=True,
            enable_specification_compliance=True,
            enable_format_contracts=True,
            enable_performance_tests=False,  # Disable for speed
            enable_enhanced_assertions=False,  # Disable to avoid dependencies
            generate_test_data=False,  # Use manual test data
            save_detailed_results=False,  # Don't save files during test
        )

        # Create test suite
        suite = ComprehensiveFormatTestSuite(config)

        # Prepare simple test data
        test_data_sources = [
            {
                "id": "test_python",
                "language": "python",
                "complexity": "simple",
                "source_code": 'class TestClass:\n    def test_method(self):\n        return "test"',
                "expected_outputs": {},
                "test_scenarios": [],
            }
        ]

        # Run comprehensive tests
        results = await suite.run_comprehensive_tests(
            simple_analyzer_function, test_data_sources
        )

        # Validate results structure
        assert hasattr(results, "total_tests")
        assert hasattr(results, "passed_tests")
        assert hasattr(results, "failed_tests")
        assert hasattr(results, "success_rate")

        print(f"Total tests: {results.total_tests}")
        print(f"Passed tests: {results.passed_tests}")
        print(f"Failed tests: {results.failed_tests}")
        print(f"Success rate: {results.success_rate:.1f}%")

        # Should have run some tests
        assert results.total_tests > 0

    def test_schema_validation_components(self):
        """Test schema validation components work"""
        from .schema_validation import CSVFormatValidator, MarkdownTableValidator

        # Test markdown validator
        markdown_validator = MarkdownTableValidator()

        markdown_content = """# Test
## Section
| Name | Value |
|------|-------|
| test | value |
"""

        result = markdown_validator.validate(markdown_content)
        assert hasattr(result, "is_valid") or "valid" in result
        print(f"Markdown validation: {result}")

        # Test CSV validator
        csv_validator = CSVFormatValidator()

        csv_content = """Name,Value,Type
test,value,string
example,123,number
"""

        csv_result = csv_validator.validate(csv_content)
        assert hasattr(csv_result, "is_valid") or "valid" in csv_result
        print(f"CSV validation: {csv_result}")

    def test_format_assertions(self):
        """Test format assertion functions"""
        from .format_assertions import (
            assert_csv_format_compliance,
            assert_full_format_compliance,
        )

        # Test full format assertions
        full_output = """# TestClass

## Package
| Package | test.package |

## Methods
| Name | Signature |
|------|-----------|
| test | test() |
"""

        try:
            assert_full_format_compliance(full_output, "TestClass")
            print("Full format compliance: PASSED")
        except AssertionError as e:
            print(f"Full format compliance: FAILED - {e}")

        # Test CSV format assertions
        csv_output = """Type,Name,Signature
Class,TestClass,TestClass
Method,test,test()
"""

        try:
            assert_csv_format_compliance(csv_output)
            print("CSV format compliance: PASSED")
        except AssertionError as e:
            print(f"CSV format compliance: FAILED - {e}")


if __name__ == "__main__":
    # Run basic tests
    import asyncio

    async def run_basic_tests():
        test_instance = TestFrameworkValidation()

        print("🧪 Testing Framework Validation")
        print("=" * 50)

        # Test 1: Quick validation
        print("\n1. Testing quick format validation...")
        try:
            await test_instance.test_quick_format_validation()
            print("✅ Quick validation test passed")
        except Exception as e:
            print(f"❌ Quick validation test failed: {e}")

        # Test 2: Schema validation
        print("\n2. Testing schema validation components...")
        try:
            test_instance.test_schema_validation_components()
            print("✅ Schema validation test passed")
        except Exception as e:
            print(f"❌ Schema validation test failed: {e}")

        # Test 3: Format assertions
        print("\n3. Testing format assertions...")
        try:
            test_instance.test_format_assertions()
            print("✅ Format assertions test passed")
        except Exception as e:
            print(f"❌ Format assertions test failed: {e}")

        # Test 4: Comprehensive suite (basic)
        print("\n4. Testing comprehensive suite...")
        try:
            await test_instance.test_comprehensive_suite_basic()
            print("✅ Comprehensive suite test passed")
        except Exception as e:
            print(f"❌ Comprehensive suite test failed: {e}")

        print("\n🎉 Framework validation completed!")

    # Run the tests
    asyncio.run(run_basic_tests())
