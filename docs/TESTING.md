# Testing Guide

This document provides comprehensive guidelines for testing the tree-sitter-analyzer codebase, including patterns, best practices, and coverage requirements.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Writing Tests](#writing-tests)
- [Test Fixtures and Utilities](#test-fixtures-and-utilities)
- [Coverage Requirements](#coverage-requirements)
- [Running Tests](#running-tests)
- [Best Practices](#best-practices)
- [Examples](#examples)

---

## Overview

The tree-sitter-analyzer project maintains high testing standards with comprehensive test coverage across all components. Our testing philosophy prioritizes:

- **Comprehensive Coverage**: >80% overall coverage, with critical modules at >85%
- **Clear Documentation**: Self-documenting tests with descriptive names
- **Maintainability**: DRY principles with reusable fixtures and helpers
- **Fast Feedback**: Efficient test execution with parallelization where appropriate

## Test Structure

Tests are organized into the following directories:

```
tests/
├── fixtures/               # Reusable test utilities
│   ├── coverage_helpers.py    # Coverage measurement utilities
│   ├── data_generators.py     # Test data generators
│   └── assertion_helpers.py   # Custom assertion functions
├── unit/                   # Unit tests
├── integration/            # Integration tests
├── mcp/                    # MCP-specific tests
├── security/               # Security tests
└── performance/            # Performance benchmarks
```

## Writing Tests

### Test File Naming

- Unit test files: `test_<module>_comprehensive.py` or `test_<module>.py`
- Integration tests: `test_<feature>_integration.py`
- End-to-end tests: `test_<workflow>_e2e.py`

### Test Class Organization

Organize tests into logical classes based on functionality:

```python
class TestBuildParser:
    """Test argument parser construction."""
    
    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
```

### Test Method Naming

Use descriptive names that clearly indicate what is being tested:

```python
def test_minimal_valid_arguments(self) -> None:
    """Test minimal valid argument set."""
    # Test code here

def test_error_handling_with_invalid_input(self) -> None:
    """Test error handling when invalid input is provided."""
    # Test code here
```

### Docstrings

Every test should have a clear docstring explaining what it tests:

```python
def test_custom_project_root(self) -> None:
    """Test custom project root is used."""
    # Arrange
    args = argparse.Namespace(...)
    
    # Act
    result = await _run(args)
    
    # Assert
    mock_detect.assert_called_once_with(None, "/custom/path")
```

## Test Fixtures and Utilities

The `tests/fixtures/` package provides reusable utilities for testing:

### Coverage Helpers

```python
from tests.fixtures import coverage_helpers

# Create mock parser
parser = coverage_helpers.create_mock_parser("python")

# Create mock AST node
node = coverage_helpers.create_mock_node(
    type="function_definition",
    text="def foo(): pass"
)

# Create mock analysis result
result = coverage_helpers.create_mock_analysis_result(
    file_path="test.py",
    elements={"functions": [{"name": "foo"}]}
)

# Assert coverage improvements
coverage_helpers.assert_coverage_threshold(85.0, 80.0, "my_module")
```

### Data Generators

```python
from tests.fixtures import data_generators

# Generate Python code
code = data_generators.generate_python_function(
    name="my_function",
    params=["x", "y"],
    body="return x + y"
)

# Generate Java class
java_code = data_generators.generate_java_class(
    name="MyClass",
    methods=[{
        "name": "myMethod",
        "return_type": "void",
        "params": "",
        "body": "System.out.println(\"Hello\");"
    }]
)

# Generate large file for performance testing
large_code = data_generators.generate_large_file_content(
    language="python",
    num_functions=100,
    num_classes=20
)
```

### Assertion Helpers

```python
from tests.fixtures import assertion_helpers

# Assert dictionary structure
assertion_helpers.assert_has_keys(
    data={"name": "foo", "type": "function"},
    required_keys=["name", "type"],
    optional_keys=["line", "column"]
)

# Assert analysis result validity
assertion_helpers.assert_analysis_result_valid(
    result=analysis_result,
    expected_language="python",
    require_success=True
)

# Assert query results
assertion_helpers.assert_query_result_valid(
    result=query_results,
    min_matches=1,
    require_node=True,
    require_text=True
)

# Assert performance
assertion_helpers.assert_performance_acceptable(
    elapsed_time=0.5,
    max_time=1.0,
    operation="file analysis"
)
```

## Coverage Requirements

### Overall Coverage Targets

- **Overall Project**: ≥80%
- **Critical Modules** (core, interfaces, exceptions): ≥85%
- **CLI Modules**: ≥85%
- **Utility Modules**: ≥80%
- **New Code**: 100% coverage required for new features

### Module-Specific Targets

| Module Category | Coverage Target | Priority |
|----------------|----------------|----------|
| Core Engine | ≥85% | Critical |
| Exceptions | ≥90% | Critical |
| MCP Interfaces | ≥80% | High |
| CLI Commands | ≥85% | High |
| Formatters | ≥80% | Medium |
| Query Modules | ≥85% | Medium |
| Utilities | ≥80% | Medium |

### Coverage Reporting

Coverage is automatically reported to [Codecov](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) on every PR and push to main/develop branches.

View coverage locally:

```bash
# Generate coverage report
pytest --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=tree_sitter_analyzer --cov-report=term-missing
```

### Run Specific Test Files

```bash
# Single file
pytest tests/unit/test_exceptions_comprehensive.py

# Multiple files
pytest tests/unit/test_*.py
```

### Run Specific Test Classes or Methods

```bash
# Specific class
pytest tests/unit/test_exceptions_comprehensive.py::TestAnalysisError

# Specific test
pytest tests/unit/test_exceptions_comprehensive.py::TestAnalysisError::test_initialization_with_all_parameters
```

### Run Tests by Marker

```bash
# Run only fast tests
pytest -m fast

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

### Run Tests in Parallel

```bash
# Use pytest-xdist
pytest -n auto
```

### Generate Coverage Reports

```bash
# Terminal report
pytest --cov=tree_sitter_analyzer --cov-report=term-missing

# HTML report
pytest --cov=tree_sitter_analyzer --cov-report=html

# XML report (for CI)
pytest --cov=tree_sitter_analyzer --cov-report=xml

# JSON report
pytest --cov=tree_sitter_analyzer --cov-report=json
```

## Best Practices

### 1. Arrange-Act-Assert Pattern

Structure tests using the AAA pattern for clarity:

```python
def test_example(self) -> None:
    """Test example function."""
    # Arrange: Set up test data and mocks
    input_data = {"key": "value"}
    mock_service = Mock()
    
    # Act: Execute the function under test
    result = my_function(input_data, mock_service)
    
    # Assert: Verify the results
    assert result == expected_value
    mock_service.method.assert_called_once()
```

### 2. Use Fixtures for Setup

Leverage pytest fixtures for common setup:

```python
import pytest

@pytest.fixture
def sample_code():
    """Provide sample Python code for testing."""
    return "def foo():\n    pass"

@pytest.fixture
def mock_analyzer():
    """Provide a mock analyzer."""
    return Mock(spec=CodeAnalyzer)

def test_with_fixtures(sample_code, mock_analyzer):
    """Test using fixtures."""
    result = mock_analyzer.analyze(sample_code)
    assert result is not None
```

### 3. Test Error Conditions

Always test both success and failure paths:

```python
def test_success_case(self) -> None:
    """Test successful execution."""
    result = function_under_test(valid_input)
    assert result.success is True

def test_error_case(self) -> None:
    """Test error handling."""
    with pytest.raises(ValueError) as exc_info:
        function_under_test(invalid_input)
    assert "expected error message" in str(exc_info.value)
```

### 4. Mock External Dependencies

Mock external dependencies to isolate units:

```python
from unittest.mock import patch, Mock

def test_with_mocked_dependency(self) -> None:
    """Test with mocked external service."""
    with patch('module.external_service') as mock_service:
        mock_service.return_value = {"data": "mocked"}
        result = my_function()
        assert result["data"] == "mocked"
```

### 5. Use Parametrized Tests

Test multiple scenarios efficiently:

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    """Test uppercase conversion with multiple inputs."""
    assert input.upper() == expected
```

### 6. Test Async Code Properly

Use pytest-asyncio for async tests:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

### 7. Clean Up Resources

Use context managers or fixtures with yield:

```python
@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    yield file_path
    # Cleanup happens automatically
```

## Examples

### Example 1: Testing CLI Command

```python
class TestListFilesCommand:
    """Test list files CLI command."""
    
    def test_minimal_execution(self) -> None:
        """Test minimal execution with required arguments."""
        # Arrange
        args = argparse.Namespace(
            roots=["root1"],
            output_format="json",
            quiet=False,
        )
        
        # Act
        with patch('module.ListFilesTool') as mock_tool:
            mock_tool.return_value.execute = AsyncMock(return_value={})
            result = await _run(args)
        
        # Assert
        assert result == 0
```

### Example 2: Testing Exception Handling

```python
class TestAnalysisError:
    """Test AnalysisError exception."""
    
    def test_initialization_with_message(self) -> None:
        """Test exception initialization with message only."""
        # Arrange & Act
        error = AnalysisError("Test error")
        
        # Assert
        assert str(error) == "Test error"
        assert error.file_path is None
        assert error.language is None
```

### Example 3: Testing with Fixtures

```python
from tests.fixtures import data_generators, assertion_helpers

def test_python_function_analysis(tmp_path):
    """Test analysis of Python function."""
    # Arrange: Generate test code
    code = data_generators.generate_python_function(
        name="test_func",
        params=["x", "y"],
        body="return x + y"
    )
    
    # Create temporary file
    file_path = tmp_path / "test.py"
    file_path.write_text(code)
    
    # Act: Analyze the code
    result = analyze_file(str(file_path))
    
    # Assert: Validate result
    assertion_helpers.assert_analysis_result_valid(
        result,
        expected_language="python",
        require_success=True
    )
    assert len(result["elements"]["functions"]) >= 1
```

---

## Contributing

When contributing tests:

1. Ensure all new code has corresponding tests
2. Maintain or improve coverage metrics
3. Follow the naming conventions outlined above
4. Use fixtures and helpers from `tests/fixtures/`
5. Run the full test suite before submitting PRs
6. Update this guide if you introduce new testing patterns

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
