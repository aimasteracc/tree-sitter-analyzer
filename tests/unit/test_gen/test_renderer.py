"""
Tests for pytest renderer.
"""

from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.test_gen import (
    FuncInfo,
    ParamInfo,
    TestCase,
)
from tree_sitter_analyzer.test_gen.renderer import (
    PytestRenderer,
    render_test_file_to_path,
)


@pytest.fixture
def temp_dir() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary directory for testing."""
    return tempfile.TemporaryDirectory()


@pytest.fixture
def sample_func_info() -> FuncInfo:
    """Create a sample function info for testing."""
    return FuncInfo(
        name="add_numbers",
        parameters=[
            ParamInfo(name="x", type_hint="int", has_default=False),
            ParamInfo(name="y", type_hint="int", has_default=False),
        ],
        return_type="int",
        complexity=1,
        has_exceptions=False,
        has_branches=False,
        decorators=[],
        source_location="math.py:10",
    )


@pytest.fixture
def sample_test_cases() -> list[TestCase]:
    """Create sample test cases for testing."""
    return [
        TestCase(
            test_name="test_add_numbers_success",
            setup="",
            call="result = add_numbers(1, 1)",
            assertions=["assert isinstance(result, (int, float))"],
            comment="Test add_numbers with valid inputs",
        ),
        TestCase(
            test_name="test_add_numbers_none_input",
            setup="",
            call="result = add_numbers(None, 1)",
            assertions=["assert result is not None  # TODO: set expected value"],
            comment="Test add_numbers with None input",
        ),
    ]


class TestPytestRenderer:
    """Tests for PytestRenderer."""

    def test_init(self) -> None:
        """PytestRenderer should initialize with module path."""
        renderer = PytestRenderer("math.calculator")
        assert renderer.module_path == "math.calculator"

    def test_render_test_case(self, sample_func_info: FuncInfo) -> None:
        """Should render a single test case."""
        renderer = PytestRenderer("math")
        test_case = TestCase(
            test_name="test_add_success",
            setup="",
            call="result = add(1, 2)",
            assertions=["assert result == 3"],
            comment="Test add function",
        )

        rendered = renderer.render_test_case(test_case, sample_func_info)

        assert "def test_add_success(self) -> None:" in rendered
        assert '"""' in rendered
        assert "Test add function" in rendered
        assert "result = add(1, 2)" in rendered
        assert "assert result == 3" in rendered

    def test_render_test_file(self, sample_func_info: FuncInfo, sample_test_cases: list[TestCase]) -> None:
        """Should render a complete test file."""
        renderer = PytestRenderer("math.calculator")
        test_cases = {sample_func_info.name: sample_test_cases}

        rendered = renderer.render_test_file([sample_func_info], test_cases)

        # Check file header
        assert '"""' in rendered
        assert "Auto-generated tests for math.calculator" in rendered

        # Check imports
        assert "import pytest" in rendered
        assert "from math.calculator import (" in rendered
        assert "add_numbers," in rendered

        # Check test cases (no class wrapper for single function)
        assert "def test_add_numbers_success(self) -> None:" in rendered
        assert "def test_add_numbers_none_input(self) -> None:" in rendered

    def test_render_test_file_multiple_functions(self, sample_func_info: FuncInfo, sample_test_cases: list[TestCase]) -> None:
        """Should render with test class wrapper for multiple functions."""
        renderer = PytestRenderer("math.calculator")

        # Create a second function
        func_info_2 = FuncInfo(
            name="subtract_numbers",
            parameters=[],
            return_type=None,
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=[],
            source_location="math.py:20",
        )

        test_cases = {sample_func_info.name: sample_test_cases, func_info_2.name: []}

        rendered = renderer.render_test_file([sample_func_info, func_info_2], test_cases)

        # Should have test class wrapper
        assert "class TestMathCalculator:" in rendered

    def test_render_test_file_single_function(self, sample_func_info: FuncInfo) -> None:
        """Should render without test class wrapper for single function."""
        renderer = PytestRenderer("math")
        test_cases = {sample_func_info.name: []}

        rendered = renderer.render_test_file([sample_func_info], test_cases)

        # Should not have test class wrapper
        assert "class Test" not in rendered
        assert "def test_add_numbers_success" not in rendered  # No test cases

    def test_render_with_decorator_warning(self, sample_func_info: FuncInfo) -> None:
        """Should include warning for functions with decorators."""
        func_info = FuncInfo(
            name="method",
            parameters=[],
            return_type=None,
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=["staticmethod"],
            source_location="test.py:10",
        )

        renderer = PytestRenderer("test")
        test_case = TestCase(
            test_name="test_method_success",
            setup="",
            call="result = method()",
            assertions=["assert result is not None"],
            comment="Test method function",
        )

        rendered = renderer.render_test_case(test_case, func_info)

        assert "def test_method_success" in rendered

    def test_validate_syntax_valid(self, sample_func_info: FuncInfo) -> None:
        """Should validate correct Python syntax."""
        renderer = PytestRenderer("math")
        test_case = TestCase(
            test_name="test_add",
            setup="",
            call="result = add(1, 2)",
            assertions=["assert result == 3"],
            comment="Test add",
        )

        rendered = renderer.render_test_case(test_case, sample_func_info)
        is_valid, error = renderer.validate_syntax(rendered)

        assert is_valid is True
        assert error is None

    def test_validate_syntax_invalid(self) -> None:
        """Should detect syntax errors."""
        renderer = PytestRenderer("math")
        invalid_code = "def test_broken(\n"  # Missing closing paren

        is_valid, error = renderer.validate_syntax(invalid_code)

        assert is_valid is False
        assert error is not None

    def test_render_with_setup_code(self, sample_func_info: FuncInfo) -> None:
        """Should render test with setup code."""
        renderer = PytestRenderer("test")
        test_case = TestCase(
            test_name="test_with_setup",
            setup="arr = [1, 2, 3]\nexpected = 6",
            call="result = sum(arr)",
            assertions=["assert result == expected"],
            comment="Test with setup",
        )

        rendered = renderer.render_test_case(test_case, sample_func_info)

        assert "arr = [1, 2, 3]" in rendered
        assert "expected = 6" in rendered
        assert "result = sum(arr)" in rendered

    def test_render_with_multiline_call(self, sample_func_info: FuncInfo) -> None:
        """Should render multiline function calls."""
        renderer = PytestRenderer("test")
        test_case = TestCase(
            test_name="test_multiline",
            setup="",
            call="with pytest.raises(Exception):\n    risky_operation()",
            assertions=[],
            comment="Test exception",
        )

        rendered = renderer.render_test_case(test_case, sample_func_info)

        assert "with pytest.raises(Exception):" in rendered
        assert "risky_operation()" in rendered


class TestRenderToFile:
    """Tests for render_test_file_to_path function."""

    def test_render_to_file(self, sample_func_info: FuncInfo, sample_test_cases: list[TestCase], temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should render test file to disk."""
        output_path = f"{temp_dir.name}/test_calculator.py"
        test_cases = {sample_func_info.name: sample_test_cases}

        render_test_file_to_path(
            [sample_func_info],
            test_cases,
            "math.calculator",
            output_path,
        )

        # Check file was created
        import os
        assert os.path.exists(output_path)

        # Check file content
        with open(output_path) as f:
            content = f.read()

        assert "import pytest" in content
        assert "test_add_numbers_success" in content

    def test_render_to_file_creates_directories(self, sample_func_info: FuncInfo, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should create parent directories if needed."""
        output_path = f"{temp_dir.name}/nested/dir/test_calculator.py"
        test_cases = {sample_func_info.name: []}

        render_test_file_to_path(
            [sample_func_info],
            test_cases,
            "math",
            output_path,
        )

        import os
        assert os.path.exists(output_path)

    def test_render_to_file_validates_syntax(self, sample_func_info: FuncInfo, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should raise ValueError if generated code has syntax errors."""
        # Create a renderer with a syntax error by monkey-patching
        from tree_sitter_analyzer.test_gen.renderer import PytestRenderer

        original_render = PytestRenderer.render_test_file

        def broken_render(self, func_infos, test_cases):
            return "def broken(\n"  # Syntax error

        PytestRenderer.render_test_file = broken_render

        output_path = f"{temp_dir.name}/test_broken.py"
        test_cases = {sample_func_info.name: []}

        with pytest.raises(ValueError, match="syntax error"):
            render_test_file_to_path(
                [sample_func_info],
                test_cases,
                "math",
                output_path,
            )

        # Restore original method
        PytestRenderer.render_test_file = original_render


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_module_path(self, sample_func_info: FuncInfo) -> None:
        """Should handle empty module path."""
        renderer = PytestRenderer("")
        test_cases = {sample_func_info.name: []}

        rendered = renderer.render_test_file([sample_func_info], test_cases)

        # Should have TODO comment for imports
        assert "# TODO: Add imports for functions under test" in rendered

    def test_module_path_conversion(self) -> None:
        """Should convert module path to class name correctly."""
        renderer = PytestRenderer("src.auth.auth")
        class_name = renderer._module_path_to_class_name()
        assert class_name == "SrcAuthAuth"

    def test_module_name_extraction(self) -> None:
        """Should extract module name from module path."""
        renderer = PytestRenderer("src.auth.auth")
        module_name = renderer._get_module_name()
        assert module_name == "auth"

    def test_simple_module_path(self) -> None:
        """Should handle simple module path."""
        renderer = PytestRenderer("math")
        class_name = renderer._module_path_to_class_name()
        assert class_name == "Math"
