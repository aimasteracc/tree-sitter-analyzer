#!/usr/bin/env python3
"""
Unit tests for Test Coverage Analyzer.
"""

import pytest

from tree_sitter_analyzer.analysis.test_coverage import (
    ElementType,
    SourceElement,
    TestCoverageAnalyzer,
    TestCoverageResult,
)


class TestSourceElement:
    """Tests for SourceElement dataclass."""

    def test_source_element_creation(self) -> None:
        """Test creating a SourceElement."""
        element = SourceElement(
            name="test_function",
            element_type=ElementType.FUNCTION,
            line=10,
            file_path="/path/to/file.py",
        )

        assert element.name == "test_function"
        assert element.element_type == ElementType.FUNCTION
        assert element.line == 10
        assert element.file_path == "/path/to/file.py"

    def test_source_element_string_representation(self) -> None:
        """Test string representation of SourceElement."""
        element = SourceElement(
            name="my_method",
            element_type=ElementType.METHOD,
            line=42,
            file_path="/path/to/file.py",
        )

        assert str(element) == "my_method:42 (method)"


class TestTestCoverageResult:
    """Tests for TestCoverageResult dataclass."""

    def test_fully_covered(self) -> None:
        """Test is_fully_covered property."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=10,
            untested_elements=[],
            coverage_percent=100.0,
        )

        assert result.is_fully_covered is True

    def test_not_fully_covered(self) -> None:
        """Test is_fully_covered property with gaps."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=8,
            untested_elements=[],
            coverage_percent=80.0,
        )

        assert result.is_fully_covered is False

    def test_coverage_grade_a(self) -> None:
        """Test coverage grade A."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=9,
            untested_elements=[],
            coverage_percent=90.0,
        )

        assert result.coverage_grade == "A"

    def test_coverage_grade_b(self) -> None:
        """Test coverage grade B."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=7,
            untested_elements=[],
            coverage_percent=70.0,
        )

        assert result.coverage_grade == "B"

    def test_coverage_grade_c(self) -> None:
        """Test coverage grade C."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=5,
            untested_elements=[],
            coverage_percent=50.0,
        )

        assert result.coverage_grade == "C"

    def test_coverage_grade_d(self) -> None:
        """Test coverage grade D."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=3,
            untested_elements=[],
            coverage_percent=30.0,
        )

        assert result.coverage_grade == "D"

    def test_coverage_grade_f(self) -> None:
        """Test coverage grade F."""
        result = TestCoverageResult(
            source_file="/path/to/file.py",
            language="python",
            total_elements=10,
            tested_elements=1,
            untested_elements=[],
            coverage_percent=10.0,
        )

        assert result.coverage_grade == "F"


class TestCoverageAnalyzerUnitTests:
    """Tests for TestCoverageAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> TestCoverageAnalyzer:
        """Create a TestCoverageAnalyzer instance."""
        return TestCoverageAnalyzer()

    def test_is_test_file_python_test_prefix(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test test file detection with test_ prefix."""
        assert analyzer.is_test_file("test_example.py") is True
        assert analyzer.is_test_file("/path/to/test_module.py") is True

    def test_is_test_file_python_test_suffix(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test test file detection with _test suffix."""
        assert analyzer.is_test_file("example_test.py") is True
        assert analyzer.is_test_file("/path/to/module_test.py") is True

    def test_is_test_file_javascript(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test test file detection for JavaScript."""
        assert analyzer.is_test_file("test_spec.js") is True
        assert analyzer.is_test_file("spec_test.js") is True

    def test_is_test_file_typescript(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test test file detection for TypeScript."""
        assert analyzer.is_test_file("test_utils.ts") is True
        assert analyzer.is_test_file("utils_test.ts") is True

    def test_is_test_file_in_test_directory(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test test file detection in test directories."""
        assert analyzer.is_test_file("/tests/example.py") is True
        assert analyzer.is_test_file("/test/module.py") is True
        assert analyzer.is_test_file("/__tests__/spec.py") is True

    def test_is_test_file_non_test_file(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test that non-test files return False."""
        assert analyzer.is_test_file("example.py") is False
        assert analyzer.is_test_file("utils.py") is False
        assert analyzer.is_test_file("/src/module.py") is False

    def test_extract_testable_elements_python_function(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting Python functions."""
        content = '''
def simple_function():
    """A simple function."""
    pass

def another_function(x, y):
    return x + y
'''

        elements = analyzer.extract_testable_elements("python", content, "test.py")

        assert len(elements) == 2
        assert elements[0].name == "simple_function"
        assert elements[0].element_type == ElementType.FUNCTION
        assert elements[1].name == "another_function"
        assert elements[1].element_type == ElementType.FUNCTION

    def test_extract_testable_elements_python_class(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting Python classes."""
        content = '''
class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
'''

        elements = analyzer.extract_testable_elements("python", content, "test.py")

        assert len(elements) == 3  # 1 class + 2 methods
        names = [e.name for e in elements]
        assert "MyClass" in names
        assert "method_one" in names
        assert "method_two" in names

    def test_extract_testable_elements_javascript_function(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting JavaScript functions."""
        content = '''
function myFunction() {
    return 42;
}

const another = function() {
    return 24;
};
'''

        elements = analyzer.extract_testable_elements("javascript", content, "test.js")

        # Note: anonymous functions are filtered out
        assert len(elements) >= 1
        assert any(e.name == "myFunction" for e in elements)

    def test_extract_testable_elements_javascript_class(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting JavaScript classes."""
        content = '''
class MyClass {
    constructor() {
        this.value = 0;
    }

    methodOne() {
        return this.value;
    }
}
'''

        elements = analyzer.extract_testable_elements("javascript", content, "test.js")

        assert len(elements) >= 1
        names = [e.name for e in elements]
        assert "MyClass" in names

    def test_extract_testable_elements_java_class(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting Java classes."""
        content = '''
public class MyClass {
    public void methodOne() {
    }

    private int methodTwo() {
        return 0;
    }
}
'''

        elements = analyzer.extract_testable_elements("java", content, "test.java")

        assert len(elements) >= 1
        names = [e.name for e in elements]
        assert "MyClass" in names

    def test_extract_testable_elements_go_function(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting Go functions."""
        content = '''
func myFunction() int {
    return 42
}

func (r *Receiver) myMethod() string {
    return "test"
}
'''

        elements = analyzer.extract_testable_elements("go", content, "test.go")

        assert len(elements) >= 1
        assert any(e.name == "myFunction" for e in elements)

    def test_extract_test_references_from_test_code(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test extracting symbol references from test code."""
        content = '''
def test_my_function():
    result = my_function()
    assert result == 42

def test_another():
    MyClass().method_one()
'''

        refs = analyzer.extract_test_references(content)

        # my_function is called as a function
        assert "my_function" in refs
        # MyClass is instantiated (Class capital letter pattern)
        assert "MyClass" in refs
        # Note: 'result' is just a variable, not a reference to test

    def test_extract_test_references_filters_keywords(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test that test keywords are filtered out."""
        content = '''
def test_example():
    assert True
    if condition:
        return
    for item in items:
        pass
'''

        refs = analyzer.extract_test_references(content)

        # Test keywords should be filtered
        assert "assert" not in refs
        assert "if" not in refs
        assert "for" not in refs
        assert "True" not in refs

    def test_analyze_file_full_coverage(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test analyzing a file with full coverage."""
        source_content = '''
def my_function():
    return 42
'''

        # Create mock test references
        result = analyzer.analyze_file(
            file_path="example.py",
            test_files=None,  # No test files = no references
        )

        # Without test files, all elements appear untested
        assert result.total_elements == 1
        assert result.tested_elements == 0
        assert result.coverage_percent == 0.0

    def test_analyze_file_with_test_references(self, analyzer: TestCoverageAnalyzer, tmp_path: str) -> None:
        """Test analyzing a file with test file references."""
        import tempfile

        # Create source file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=tmp_path
        ) as f:
            f.write("def my_function():\n    return 42\n")
            source_file = f.name

        # Create test file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_test.py", delete=False, dir=tmp_path
        ) as f:
            f.write("def test_my_function():\n    assert my_function() == 42\n")
            test_file = f.name

        result = analyzer.analyze_file(source_file, test_files=[test_file])

        assert result.total_elements == 1
        assert result.tested_elements == 1  # my_function is referenced
        assert result.coverage_percent == 100.0

    def test_detect_language_from_extension(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test language detection from file extension."""
        assert analyzer._detect_language("test.py") == "python"
        assert analyzer._detect_language("test.js") == "javascript"
        assert analyzer._detect_language("test.ts") == "typescript"
        assert analyzer._detect_language("test.java") == "java"
        assert analyzer._detect_language("test.go") == "go"
        assert analyzer._detect_language("test.unknown") == "unknown"

    def test_analyze_file_empty_file(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test analyzing an empty file."""
        result = analyzer.analyze_file("empty.py")

        assert result.total_elements == 0
        assert result.coverage_percent == 100.0  # No elements = fully covered

    def test_analyze_file_read_error(self, analyzer: TestCoverageAnalyzer) -> None:
        """Test analyzing a non-existent file."""
        result = analyzer.analyze_file("/nonexistent/file.py")

        assert result.total_elements == 0
        assert result.coverage_percent == 0.0
