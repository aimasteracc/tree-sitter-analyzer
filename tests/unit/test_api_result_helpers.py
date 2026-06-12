"""Unit tests for _api_result_helpers — result shaping and error responses."""

from unittest.mock import MagicMock

from tree_sitter_analyzer._api_result_helpers import (
    code_analysis_error,
    code_analysis_result,
    element_to_dict,
    file_analysis_error,
    file_analysis_result,
    find_class_name,
)


def _make_elem(
    name="foo",
    cls_name="Function",
    start_line=1,
    end_line=5,
    raw_text="def foo(): pass",
    language="python",
    **extra,
):
    """Create a real (non-Mock) element.

    Uses a freshly-built class so ``type(elem).__name__ == cls_name`` for the
    element-type classifier in ``_api_result_helpers``. Unlike MagicMock, this
    means ``hasattr(elem, 'parameters')`` is False unless the caller explicitly
    supplies the attribute via ``**extra``, which is what the "optional fields
    omitted when absent" tests assert.
    """
    cls = type(cls_name, (), {})
    elem = cls()
    elem.name = name
    elem.start_line = start_line
    elem.end_line = end_line
    elem.raw_text = raw_text
    elem.language = language
    for k, v in extra.items():
        setattr(elem, k, v)
    return elem


def _make_analysis_result(
    success=True,
    language="python",
    node_count=10,
    line_count=5,
    error_message=None,
    elements=None,
    query_results=None,
):
    """Create a mock analysis result."""
    result = MagicMock()
    result.success = success
    result.language = language
    result.node_count = node_count
    result.line_count = line_count
    result.error_message = error_message
    result.elements = elements if elements is not None else []
    result.query_results = query_results
    return result


class TestElementToDict:
    """Tests for element_to_dict."""

    def test_basic_fields(self):
        elem = _make_elem()
        result = element_to_dict(elem)
        assert result["name"] == "foo"
        assert result["type"] == "function"
        assert result["start_line"] == 1
        assert result["end_line"] == 5
        assert result["language"] == "python"

    def test_optional_fields_included_when_present(self):
        elem = _make_elem(parameters=["x", "y"], return_type="int")
        result = element_to_dict(elem)
        assert result["parameters"] == ["x", "y"]
        assert result["return_type"] == "int"

    def test_optional_fields_omitted_when_absent(self):
        elem = _make_elem()
        result = element_to_dict(elem)
        assert "parameters" not in result
        assert "return_type" not in result

    def test_method_gets_class_name(self):
        method = _make_elem(
            name="bar", cls_name="Function", is_method=True, start_line=3, end_line=5
        )
        cls = _make_elem(name="MyClass", cls_name="Class", start_line=1, end_line=10)
        result = element_to_dict(method, all_elements=[method, cls])
        assert result["class_name"] == "MyClass"

    def test_method_without_class_is_none(self):
        method = _make_elem(name="bar", cls_name="Function", is_method=True)
        result = element_to_dict(method, all_elements=[method])
        assert result.get("class_name") is None

    def test_class_type_lowercase(self):
        elem = _make_elem(cls_name="Class")
        result = element_to_dict(elem)
        assert result["type"] == "class"


class TestFindClassName:
    """Tests for find_class_name."""

    def test_finds_enclosing_class(self):
        method = _make_elem(start_line=5, end_line=10)
        cls = _make_elem(cls_name="Class", start_line=1, end_line=20)
        assert find_class_name(method, [cls]) == "foo"

    def test_no_enclosing_class(self):
        method = _make_elem(start_line=5, end_line=10)
        cls = _make_elem(cls_name="Class", start_line=15, end_line=20)
        assert find_class_name(method, [cls]) is None

    def test_method_at_class_boundary_start(self):
        method = _make_elem(start_line=1, end_line=5)
        cls = _make_elem(cls_name="Class", start_line=1, end_line=10)
        assert find_class_name(method, [cls]) == "foo"

    def test_multiple_classes_picks_innermost(self):
        """When method is inside two classes, the innermost (smallest span) wins."""
        method = _make_elem(start_line=8, end_line=10)
        # cls1 span=11 (outer), cls2 span=7 (inner) — cls2 must win
        cls1 = _make_elem(name="A", cls_name="Class", start_line=1, end_line=12)
        cls2 = _make_elem(name="B", cls_name="Class", start_line=3, end_line=10)
        assert find_class_name(method, [cls1, cls2]) == "B"

    # --- Issue #532: nested-container innermost-wins ---

    def test_nested_container_innermost_wins(self):
        """Method inside nested class → innermost (smallest span) class wins."""
        # Outer: lines 1-20 (span=19), Inner: lines 5-10 (span=5)
        # method on line 7 is inside BOTH — must get Inner.
        method = _make_elem(name="m", start_line=7, end_line=8)
        outer = _make_elem(name="Outer", cls_name="Class", start_line=1, end_line=20)
        inner = _make_elem(name="Inner", cls_name="Class", start_line=5, end_line=10)
        # Outer listed first (as plugins typically emit outer before inner)
        assert find_class_name(method, [outer, inner]) == "Inner"

    def test_nested_namespace_innermost_wins(self):
        """TS namespace wrapping a class: method inside class → class, not namespace."""
        # Namespace (class_type=namespace): lines 1-18
        # BatchProcessor class: lines 3-17
        # method on line 5
        method = _make_elem(name="process", start_line=5, end_line=7)
        namespace = _make_elem(
            name="DataProcessing", cls_name="Class", start_line=1, end_line=18
        )
        cls = _make_elem(
            name="BatchProcessor", cls_name="Class", start_line=3, end_line=17
        )
        # namespace listed first (as TypeScript extractor emits outer first)
        assert find_class_name(method, [namespace, cls]) == "BatchProcessor"

    def test_java_method_in_inner_class_gets_class_name(self):
        """element_to_dict sets class_name for a function inside a nested class
        even when is_method is not explicitly True (Java plugin doesn't set it)."""
        inner_class = _make_elem(
            name="InnerClass", cls_name="Class", start_line=3, end_line=7
        )
        method = _make_elem(
            name="innerMethod",
            cls_name="Function",
            start_line=4,
            end_line=6,
        )
        result = element_to_dict(method, all_elements=[inner_class, method])
        assert result["class_name"] == "InnerClass"


class TestFileAnalysisResult:
    """Tests for file_analysis_result."""

    def test_success_with_elements(self):
        ar = _make_analysis_result(elements=[_make_elem()])
        result = file_analysis_result(
            ar, "/test.py", None, include_elements=True, include_queries=False
        )
        assert result["success"] is True
        assert result["file_info"]["path"] == "/test.py"
        assert result["file_info"]["exists"] is True
        assert "elements" in result
        assert len(result["elements"]) == 1

    def test_success_without_elements(self):
        ar = _make_analysis_result(elements=[_make_elem()])
        result = file_analysis_result(
            ar, "/test.py", "python", include_elements=False, include_queries=False
        )
        assert "elements" not in result
        assert result["language_info"]["detected"] is False

    def test_success_with_query_results(self):
        ar = _make_analysis_result(query_results={"q1": []})
        result = file_analysis_result(
            ar, "/test.py", None, include_elements=False, include_queries=True
        )
        assert "query_results" in result

    def test_failed_analysis_with_error(self):
        ar = _make_analysis_result(success=False, error_message="Parse failed")
        result = file_analysis_result(
            ar, "/test.py", None, include_elements=True, include_queries=True
        )
        assert result["success"] is False
        assert result["error"] == "Parse failed"
        assert "elements" not in result

    def test_failed_analysis_without_error_message(self):
        ar = _make_analysis_result(success=False, error_message=None)
        result = file_analysis_result(
            ar, "/test.py", None, include_elements=True, include_queries=True
        )
        assert result["success"] is False
        assert "error" not in result
        assert "elements" not in result

    def test_auto_detected_language(self):
        ar = _make_analysis_result()
        result = file_analysis_result(
            ar, "/test.py", None, include_elements=False, include_queries=False
        )
        assert result["language_info"]["detected"] is True


class TestCodeAnalysisResult:
    """Tests for code_analysis_result."""

    def test_success_response(self):
        ar = _make_analysis_result()
        result = code_analysis_result(
            ar, "python", include_elements=False, include_queries=False
        )
        assert result["success"] is True
        assert result["language_info"]["detected"] is False
        assert "file_info" not in result

    def test_failed_analysis(self):
        ar = _make_analysis_result(success=False, error_message="Syntax error")
        result = code_analysis_result(
            ar, "python", include_elements=True, include_queries=True
        )
        assert result["error"] == "Syntax error"


class TestFileAnalysisError:
    """Tests for file_analysis_error."""

    def test_basic_error(self):
        result = file_analysis_error(
            "/missing.py", "python", FileNotFoundError("not found")
        )
        assert result["success"] is False
        assert "not found" in result["error"]
        assert result["file_info"]["exists"] is False
        assert result["ast_info"]["node_count"] == 0

    def test_none_language(self):
        result = file_analysis_error("/file.py", None, RuntimeError("err"))
        assert result["language_info"]["language"] == "unknown"


class TestCodeAnalysisError:
    """Tests for code_analysis_error."""

    def test_basic_error(self):
        result = code_analysis_error("python", ValueError("bad input"))
        assert result["success"] is False
        assert "bad input" in result["error"]
        assert result["language_info"]["language"] == "python"

    def test_empty_language(self):
        result = code_analysis_error("", RuntimeError("fail"))
        assert result["language_info"]["language"] == "unknown"


class TestLocalFunctionStaysUnowned:
    """Codex P2 on #570: a function nested inside another FUNCTION's span
    (local helper) is deliberately unowned — line containment in a class
    must not ownerize it."""

    def test_local_function_gets_no_class_name(self):
        cls = _make_elem("Outer", cls_name="Class", start_line=1, end_line=30)
        method = _make_elem("doWork", cls_name="Function", start_line=5, end_line=20)
        local = _make_elem("inner", cls_name="Function", start_line=8, end_line=12)
        elements = [cls, method, local]
        d = element_to_dict(local, elements)
        assert "class_name" not in d
        d2 = element_to_dict(method, elements)
        assert d2["class_name"] == "Outer"
