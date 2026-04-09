#!/usr/bin/env python3
"""Property-based tests for models module.

Uses Hypothesis to verify CodeElement and AnalysisResult properties.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.models import (
    AnalysisResult,
    Class,
    Function,
    Import,
    Variable,
)

# Strategies for generating test data
valid_name_strategy = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(min_codepoint=32, max_codepoint=126, exclude_characters="\n\r\t"),
)

line_number_strategy = st.integers(min_value=1, max_value=100000)

language_strategy = st.sampled_from(
    ["python", "java", "javascript", "typescript", "go", "rust", "ruby", "php", "c", "cpp", "sql"]
)


class TestFunctionProperties:
    """Property tests for Function model."""

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
        end_line=line_number_strategy,
        language=language_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_function_creation(self, name: str, start_line: int, end_line: int, language: str) -> None:
        """Function should be created with valid parameters."""
        # Ensure end_line >= start_line
        end_line = max(start_line, end_line)

        func = Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            language=language,
        )

        assert func.name == name
        assert func.start_line == start_line
        assert func.end_line == end_line
        assert func.language == language
        assert func.element_type == "function"

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
        end_line=line_number_strategy,
    )
    @settings(max_examples=30)
    def test_function_line_span(self, name: str, start_line: int, end_line: int) -> None:
        """Function line span should be non-negative."""
        end_line = max(start_line, end_line)
        func = Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            language="python",
        )
        assert func.end_line >= func.start_line

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_function_to_summary_item_contains_required_keys(self, name: str) -> None:
        """Function.to_summary_item should contain required keys."""
        func = Function(name=name, start_line=1, end_line=10, language="python")
        result = func.to_summary_item()

        required_keys = ["name", "type", "lines"]
        for key in required_keys:
            assert key in result

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_function_default_visibility(self, name: str) -> None:
        """Function should have default public visibility."""
        func = Function(name=name, start_line=1, end_line=10, language="python")
        assert func.visibility == "public"
        assert func.is_public is True


class TestClassProperties:
    """Property tests for Class model."""

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
        end_line=line_number_strategy,
        language=language_strategy,
    )
    @settings(max_examples=50)
    def test_class_creation(self, name: str, start_line: int, end_line: int, language: str) -> None:
        """Class should be created with valid parameters."""
        end_line = max(start_line, end_line)

        cls = Class(
            name=name,
            start_line=start_line,
            end_line=end_line,
            language=language,
        )

        assert cls.name == name
        assert cls.element_type == "class"

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_class_with_methods(self, name: str) -> None:
        """Class can have methods added."""
        cls = Class(name=name, start_line=1, end_line=100, language="java")

        method = Function(
            name="testMethod",
            start_line=10,
            end_line=20,
            language="java",
        )

        cls.methods.append(method)
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "testMethod"

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_class_to_summary_item(self, name: str) -> None:
        """Class.to_summary_item should work correctly."""
        cls = Class(name=name, start_line=1, end_line=100, language="java")
        result = cls.to_summary_item()

        assert result["name"] == name
        assert result["type"] == "class"


class TestVariableProperties:
    """Property tests for Variable model."""

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
    )
    @settings(max_examples=50)
    def test_variable_creation(self, name: str, start_line: int) -> None:
        """Variable should be created with valid parameters."""
        var = Variable(
            name=name,
            start_line=start_line,
            end_line=start_line,
            language="python",
        )

        assert var.name == name
        assert var.element_type == "variable"
        assert var.start_line == start_line

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_variable_to_summary_item(self, name: str) -> None:
        """Variable.to_summary_item should work correctly."""
        var = Variable(name=name, start_line=1, end_line=1, language="python")
        result = var.to_summary_item()

        assert result["name"] == name
        assert result["type"] == "variable"


class TestImportProperties:
    """Property tests for Import model."""

    @given(
        module_name=valid_name_strategy,
        start_line=line_number_strategy,
    )
    @settings(max_examples=50)
    def test_import_creation(self, module_name: str, start_line: int) -> None:
        """Import should be created with valid parameters."""
        imp = Import(
            name=module_name,
            start_line=start_line,
            end_line=start_line,
            language="python",
        )

        assert imp.name == module_name
        assert imp.element_type == "import"

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_import_to_summary_item(self, name: str) -> None:
        """Import.to_summary_item should work correctly."""
        imp = Import(name=name, start_line=1, end_line=1, language="python")
        result = imp.to_summary_item()

        assert result["name"] == name
        assert result["type"] == "import"


class TestAnalysisResultProperties:
    """Property tests for AnalysisResult model."""

    @given(
        file_path=st.text(min_size=1, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
        language=language_strategy,
    )
    @settings(max_examples=30)
    def test_analysis_result_creation(self, file_path: str, language: str) -> None:
        """AnalysisResult should be created with valid parameters."""
        result = AnalysisResult(
            file_path=file_path,
            language=language,
        )

        assert result.file_path == file_path
        assert result.language == language
        assert result.elements == []

    @given(
        file_path=st.text(min_size=1, max_size=100),
        num_functions=st.integers(min_value=0, max_value=10),
        num_classes=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=30)
    def test_analysis_result_with_elements(
        self, file_path: str, num_functions: int, num_classes: int
    ) -> None:
        """AnalysisResult can hold multiple elements."""
        result = AnalysisResult(file_path=file_path, language="python")

        for i in range(num_functions):
            result.elements.append(
                Function(
                    name=f"func_{i}",
                    start_line=i * 10 + 1,
                    end_line=i * 10 + 5,
                    language="python",
                )
            )

        for i in range(num_classes):
            result.elements.append(
                Class(
                    name=f"Class_{i}",
                    start_line=i * 100 + 1,
                    end_line=i * 100 + 50,
                    language="python",
                )
            )

        assert len(result.elements) == num_functions + num_classes

    @given(
        file_path=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=30)
    def test_analysis_result_to_dict(self, file_path: str) -> None:
        """AnalysisResult.to_dict should contain required keys."""
        result = AnalysisResult(file_path=file_path, language="python")
        result_dict = result.to_dict()

        required_keys = ["file_path", "success", "analysis_time"]
        for key in required_keys:
            assert key in result_dict


class TestElementSerializationProperties:
    """Property tests for element serialization."""

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
        end_line=line_number_strategy,
    )
    @settings(max_examples=30)
    def test_function_summary_serialization(
        self, name: str, start_line: int, end_line: int
    ) -> None:
        """Function summary serialization should preserve data."""
        end_line = max(start_line, end_line)
        func = Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            language="python",
        )

        # Serialize via to_summary_item
        summary = func.to_summary_item()

        # Check serialization preserves key data
        assert summary["name"] == name
        assert summary["lines"]["start"] == start_line
        assert summary["lines"]["end"] == end_line
        assert summary["type"] == "function"

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_class_summary_serialization(self, name: str) -> None:
        """Class summary serialization should work correctly."""
        cls = Class(name=name, start_line=1, end_line=100, language="java")
        cls.methods.append(
            Function(name="method1", start_line=10, end_line=20, language="java")
        )

        summary = cls.to_summary_item()
        assert summary["name"] == name
        assert summary["type"] == "class"


class TestElementEqualityProperties:
    """Property tests for element equality and hashing."""

    @given(
        name=valid_name_strategy,
        start_line=line_number_strategy,
    )
    @settings(max_examples=30)
    def test_same_name_elements_can_differ(self, name: str, start_line: int) -> None:
        """Elements with same name but different lines are different."""
        func1 = Function(name=name, start_line=start_line, end_line=start_line + 10, language="python")
        func2 = Function(name=name, start_line=start_line + 100, end_line=start_line + 110, language="python")

        # They have the same name
        assert func1.name == func2.name
        # But different line positions
        assert func1.start_line != func2.start_line

    @given(name=valid_name_strategy)
    @settings(max_examples=30)
    def test_element_attributes_preserved(self, name: str) -> None:
        """Element attributes should be preserved after creation."""
        func = Function(
            name=name,
            start_line=1,
            end_line=10,
            language="python",
            return_type="str",
            is_async=True,
            parameters=["x", "y"],
        )

        assert func.name == name
        assert func.return_type == "str"
        assert func.is_async is True
        assert func.parameters == ["x", "y"]
