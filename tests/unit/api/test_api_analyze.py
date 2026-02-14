#!/usr/bin/env python3
"""
Unit tests for API analyze_file and analyze_code functions.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import tree_sitter_analyzer.api as api_module


@pytest.fixture(autouse=True)
def reset_api_engine():
    """Reset api module engine singleton before and after each test."""
    api_module._engine = None
    yield
    api_module._engine = None


def make_mock_result(
    success=True,
    language="python",
    elements=None,
    query_results=None,
    error_message=None,
    node_count=42,
    line_count=10,
):
    """Create mock AnalysisResult for testing."""
    result = MagicMock()
    result.success = success
    result.language = language
    result.node_count = node_count
    result.line_count = line_count
    result.error_message = error_message
    result.elements = elements or []
    result.query_results = query_results or {}
    return result


def make_mock_element(name="func", elem_type="function", **kwargs):
    """Create mock element with controllable attributes for hasattr testing."""
    # Use a real class so type(elem).__name__.lower() works correctly
    class_name = elem_type.capitalize()
    elem_class = type(class_name, (), {"__name__": class_name})

    elem = elem_class()
    elem.name = name
    elem.start_line = kwargs.get("start_line", 1)
    elem.end_line = kwargs.get("end_line", 5)
    elem.raw_text = kwargs.get("raw_text", "def func(): pass")
    elem.language = kwargs.get("language", "python")
    optional_attrs = [
        "module_path",
        "module_name",
        "imported_names",
        "variable_type",
        "initializer",
        "is_constant",
        "parameters",
        "return_type",
        "is_async",
        "is_static",
        "is_constructor",
        "is_method",
        "complexity_score",
        "superclass",
        "class_type",
    ]
    for attr in optional_attrs:
        if attr in kwargs:
            setattr(elem, attr, kwargs[attr])
    return elem


class TestGetEngine:
    """Tests for get_engine singleton."""

    def test_get_engine_first_call_creates_instance(self):
        """First call to get_engine creates new UnifiedAnalysisEngine."""
        with patch("tree_sitter_analyzer.api.UnifiedAnalysisEngine") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            result = api_module.get_engine()
            mock_cls.assert_called_once()
            assert result is mock_instance

    def test_get_engine_subsequent_calls_return_same_instance(self):
        """Subsequent calls return the same engine instance."""
        with patch("tree_sitter_analyzer.api.UnifiedAnalysisEngine") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            result1 = api_module.get_engine()
            result2 = api_module.get_engine()
            mock_cls.assert_called_once()
            assert result1 is result2
            assert result1 is mock_instance


class TestAnalyzeFile:
    """Tests for analyze_file function."""

    def test_analyze_file_success_basic_structure(self):
        """analyze_file returns correct structure on success."""
        mock_result = make_mock_result()
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert result["success"] is True
            assert result["file_info"]["path"] == "/test.py"
            assert result["file_info"]["exists"] is True
            assert result["language_info"]["language"] == "python"
            assert result["ast_info"]["node_count"] == 42
            assert result["ast_info"]["line_count"] == 10

    def test_analyze_file_passes_path_as_string(self):
        """analyze_file converts Path to string."""
        mock_result = make_mock_result()
        path_arg = Path("relative/file.py")
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            api_module.analyze_file(path_arg)
            call_args = mock_engine.analyze_sync.call_args
            request = call_args[0][0]
            assert request.file_path == str(path_arg)

    def test_analyze_file_passes_request_params(self):
        """analyze_file passes correct AnalysisRequest parameters."""
        mock_result = make_mock_result()
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            api_module.analyze_file(
                "/test.py",
                language="javascript",
                queries=["classes", "functions"],
                include_elements=False,
                include_queries=False,
            )
            call_args = mock_engine.analyze_sync.call_args
            request = call_args[0][0]
            assert request.language == "javascript"
            assert request.queries == ["classes", "functions"]
            assert request.include_elements is False
            assert request.include_queries is False

    def test_analyze_file_detected_language_flag(self):
        """language_info.detected is True when language is auto-detected."""
        mock_result = make_mock_result(language="python")
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert result["language_info"]["detected"] is True

    def test_analyze_file_explicit_language_detected_false(self):
        """language_info.detected is False when language is explicit."""
        mock_result = make_mock_result(language="python")
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py", language="python")
            assert result["language_info"]["detected"] is False

    def test_analyze_file_failed_analysis_with_error_message(self):
        """Failed analysis with error_message adds error key."""
        mock_result = make_mock_result(
            success=False, error_message="Parse error at line 5"
        )
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert result["success"] is False
            assert result["error"] == "Parse error at line 5"

    def test_analyze_file_failed_analysis_without_error_message(self):
        """Failed analysis without error_message still returns structure."""
        mock_result = make_mock_result(success=False, error_message=None)
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert result["success"] is False
            assert "error" not in result

    def test_analyze_file_include_elements_false_removes_elements(self):
        """When include_elements=False, elements key is removed."""
        mock_result = make_mock_result(elements=[make_mock_element()])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py", include_elements=False)
            assert "elements" not in result

    def test_analyze_file_include_queries_false_removes_query_results(self):
        """When include_queries=False, query_results key is removed."""
        mock_result = make_mock_result(query_results={"classes": {"captures": []}})
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py", include_queries=False)
            assert "query_results" not in result

    def test_analyze_file_elements_empty_when_no_elements(self):
        """Empty elements list when analysis has no elements."""
        mock_result = make_mock_result(elements=[])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert result["elements"] == []

    def test_analyze_file_elements_with_type_specific_fields(self):
        """Element dict includes type-specific fields when hasattr is True."""
        elem = make_mock_element(
            module_path="mypkg",
            module_name="mypkg.utils",
            imported_names=["foo", "bar"],
            variable_type="str",
            initializer="None",
            is_constant=True,
            parameters=["x", "y"],
            return_type="int",
            is_async=True,
            is_static=True,
            is_constructor=True,
            is_method=True,
            complexity_score=5,
            superclass="BaseClass",
            class_type="class",
        )
        mock_result = make_mock_result(elements=[elem])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            elem_dict = result["elements"][0]
            assert elem_dict["module_path"] == "mypkg"
            assert elem_dict["module_name"] == "mypkg.utils"
            assert elem_dict["imported_names"] == ["foo", "bar"]
            assert elem_dict["variable_type"] == "str"
            assert elem_dict["initializer"] == "None"
            assert elem_dict["is_constant"] is True
            assert elem_dict["parameters"] == ["x", "y"]
            assert elem_dict["return_type"] == "int"
            assert elem_dict["is_async"] is True
            assert elem_dict["is_static"] is True
            assert elem_dict["is_constructor"] is True
            assert elem_dict["is_method"] is True
            assert elem_dict["complexity_score"] == 5
            assert elem_dict["superclass"] == "BaseClass"
            assert elem_dict["class_type"] == "class"

    def test_analyze_file_method_class_name_resolution(self):
        """Method element gets class_name from containing class."""
        class_elem = make_mock_element(
            name="MyClass", elem_type="class", start_line=1, end_line=10
        )
        method_elem = make_mock_element(
            name="my_method",
            elem_type="function",
            is_method=True,
            start_line=3,
            end_line=5,
        )
        mock_result = make_mock_result(elements=[class_elem, method_elem])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            method_dict = result["elements"][1]
            assert method_dict["class_name"] == "MyClass"

    def test_analyze_file_method_class_name_none_when_no_containing_class(self):
        """Method outside any class gets class_name=None."""
        method_elem = make_mock_element(
            name="standalone_func",
            elem_type="function",
            is_method=True,
            start_line=1,
            end_line=5,
        )
        mock_result = make_mock_result(elements=[method_elem])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            method_dict = result["elements"][0]
            assert method_dict["class_name"] is None

    def test_analyze_file_no_elements_when_include_elements_false(self):
        """Elements not processed when include_elements=False."""
        mock_result = make_mock_result(elements=[make_mock_element()])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py", include_elements=False)
            assert "elements" not in result

    def test_analyze_file_no_elements_if_no_hasattr_elements(self):
        """When analysis_result has no elements attr, no elements key added."""
        mock_result = make_mock_result()
        del mock_result.elements
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert "elements" not in result

    def test_analyze_file_query_results_added_when_include_queries(self):
        """query_results added when include_queries=True and available."""
        mock_result = make_mock_result(query_results={"classes": {"captures": []}})
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_sync.return_value = mock_result
            result = api_module.analyze_file("/test.py")
            assert "query_results" in result
            assert result["query_results"] == {"classes": {"captures": []}}

    def test_analyze_file_file_not_found_re_raised(self):
        """FileNotFoundError is re-raised, not caught."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.analyze_sync.side_effect = FileNotFoundError("file not found")
            mock_get_engine.return_value = mock_engine
            with pytest.raises(FileNotFoundError, match="file not found"):
                api_module.analyze_file("/nonexistent.py")

    def test_analyze_file_generic_exception_returns_error_dict(self):
        """Generic exception returns error dict, does not raise."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.analyze_sync.side_effect = RuntimeError("internal error")
            mock_get_engine.return_value = mock_engine
            result = api_module.analyze_file("/test.py")
            assert result["success"] is False
            assert result["error"] == "internal error"
            assert result["file_info"]["exists"] is False
            assert result["ast_info"]["node_count"] == 0


class TestAnalyzeCode:
    """Tests for analyze_code function."""

    def test_analyze_code_success_basic_structure(self):
        """analyze_code returns correct structure on success."""
        mock_result = make_mock_result()
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code("def foo(): pass", "python")
            assert result["success"] is True
            assert result["language_info"]["language"] == "python"
            assert result["language_info"]["detected"] is False
            assert result["ast_info"]["node_count"] == 42

    def test_analyze_code_calls_analyze_code_sync(self):
        """analyze_code calls engine.analyze_code_sync with correct args."""
        mock_result = make_mock_result()
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            api_module.analyze_code("print(1)", "python")
            mock_engine.analyze_code_sync.assert_called_once_with(
                "print(1)", "python", filename="string"
            )

    def test_analyze_code_failed_analysis_returns_error(self):
        """Failed analysis returns error dict."""
        mock_result = make_mock_result(success=False, error_message="Syntax error")
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code("invalid {", "python")
            assert result["success"] is False
            assert result["error"] == "Syntax error"

    def test_analyze_code_exception_returns_error_dict(self):
        """Exception in analyze_code returns error dict (no FileNotFoundError)."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.analyze_code_sync.side_effect = ValueError("bad input")
            mock_get_engine.return_value = mock_engine
            result = api_module.analyze_code("", "python")
            assert result["success"] is False
            assert result["error"] == "bad input"
            assert result["language_info"]["language"] == "python"

    def test_analyze_code_include_elements_false_removes_elements(self):
        """When include_elements=False, elements key is removed."""
        elem = make_mock_element()
        mock_result = make_mock_result(elements=[elem])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code(
                "def x(): pass", "python", include_elements=False
            )
            assert "elements" not in result

    def test_analyze_code_include_queries_false_removes_query_results(self):
        """When include_queries=False, query_results key is removed."""
        mock_result = make_mock_result(query_results={"functions": []})
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code(
                "def x(): pass", "python", include_queries=False
            )
            assert "query_results" not in result

    def test_analyze_code_element_with_method_class_resolution(self):
        """Method gets class_name from containing class."""
        class_elem = make_mock_element(
            name="Foo", elem_type="class", start_line=1, end_line=8
        )
        method_elem = make_mock_element(
            name="bar", elem_type="function", is_method=True, start_line=2, end_line=4
        )
        mock_result = make_mock_result(elements=[class_elem, method_elem])
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code("class Foo:\n  def bar(): pass", "python")
            method_dict = result["elements"][1]
            assert method_dict["class_name"] == "Foo"

    def test_analyze_code_no_file_info_in_result(self):
        """analyze_code result has no file_info key (code string, not file)."""
        mock_result = make_mock_result()
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.analyze_code_sync.return_value = mock_result
            result = api_module.analyze_code("x = 1", "python")
            assert "file_info" not in result
