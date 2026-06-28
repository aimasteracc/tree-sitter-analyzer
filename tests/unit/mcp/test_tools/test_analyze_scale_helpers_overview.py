"""
Tests for extract_structural_overview and extract_structural_overview_universal.
"""

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.analyze_scale_helpers import (
    extract_structural_overview,
    extract_structural_overview_universal,
)


def _make_element(
    element_type="class",
    name="TestElement",
    start_line=1,
    end_line=10,
    class_type="class",
    visibility="public",
    extends_class=None,
    implements_interfaces=None,
    annotations=None,
    return_type="void",
    parameters=None,
    complexity_score=0,
    is_constructor=False,
    is_static=False,
    field_type="Object",
    is_final=False,
    imported_name="TestImport",
    import_statement="import TestImport",
    line_number=1,
    is_static_import=False,
    is_wildcard=False,
    file_path="test.py",
):
    e = MagicMock()
    e.element_type = element_type
    e.name = name
    e.start_line = start_line
    e.end_line = end_line
    e.class_type = class_type
    e.visibility = visibility
    e.extends_class = extends_class
    e.implements_interfaces = implements_interfaces or []
    ann_mocks = []
    if annotations:
        for a in annotations:
            m = MagicMock()
            m.name = a
            ann_mocks.append(m)
    e.annotations = ann_mocks
    e.return_type = return_type
    e.parameters = parameters or []
    e.complexity_score = complexity_score
    e.is_constructor = is_constructor
    e.is_static = is_static
    e.field_type = field_type
    e.is_final = is_final
    e.imported_name = imported_name
    e.import_statement = import_statement
    e.line_number = line_number
    e.is_static_import = is_static_import
    e.is_wildcard = is_wildcard
    e.file_path = file_path
    return e


def _make_analysis_result(elements=None, package=None, annotations=None):
    result = MagicMock()
    result.elements = elements or []
    result.package = package
    result.annotations = annotations or []
    return result


class TestExtractStructuralOverview:
    def test_empty_elements_returns_empty_overview(self):
        result = _make_analysis_result(elements=[])
        overview = extract_structural_overview(result)
        assert overview["classes"] == []
        assert overview["methods"] == []
        assert overview["fields"] == []
        assert overview["imports"] == []
        assert overview["complexity_hotspots"] == []

    def test_extracts_class_with_all_fields(self):
        cls = _make_element(
            element_type="class",
            name="MyClass",
            start_line=5,
            end_line=50,
            class_type="class",
            visibility="public",
            extends_class="BaseClass",
            implements_interfaces=["IFoo", "IBar"],
            annotations=["Deprecated"],
        )
        result = _make_analysis_result(elements=[cls])
        overview = extract_structural_overview(result)
        assert len(overview["classes"]) == 1
        c = overview["classes"][0]
        assert c["name"] == "MyClass"
        assert c["start_line"] == 5
        assert c["end_line"] == 50
        assert c["line_span"] == 46
        assert c["visibility"] == "public"
        assert c["extends"] == "BaseClass"
        assert c["implements"] == ["IFoo", "IBar"]
        assert c["annotations"] == ["Deprecated"]

    def test_extracts_method_with_all_fields(self):
        method = _make_element(
            element_type="function",
            name="doStuff",
            start_line=10,
            end_line=20,
            visibility="private",
            return_type="int",
            parameters=["a", "b", "c"],
            complexity_score=5,
            is_constructor=False,
            is_static=True,
            annotations=["Override"],
        )
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert len(overview["methods"]) == 1
        m = overview["methods"][0]
        assert m["name"] == "doStuff"
        assert m["line_span"] == 11
        assert m["parameter_count"] == 3
        assert m["complexity"] == 5
        assert m["is_static"] is True
        assert m["annotations"] == ["Override"]

    def test_high_complexity_method_creates_hotspot(self):
        method = _make_element(
            element_type="function",
            name="complexMethod",
            start_line=10,
            end_line=50,
            complexity_score=12,
        )
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert len(overview["complexity_hotspots"]) == 1
        h = overview["complexity_hotspots"][0]
        assert h["name"] == "complexMethod"
        assert h["complexity"] == 12
        assert h["type"] == "method"

    def test_low_complexity_method_no_hotspot(self):
        method = _make_element(
            element_type="function",
            name="simpleMethod",
            complexity_score=3,
        )
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert overview["complexity_hotspots"] == []

    def test_extracts_field_with_all_fields(self):
        field = _make_element(
            element_type="variable",
            name="myField",
            start_line=8,
            end_line=8,
            visibility="protected",
            field_type="String",
            is_static=True,
            is_final=True,
            annotations=["Inject"],
        )
        result = _make_analysis_result(elements=[field])
        overview = extract_structural_overview(result)
        assert len(overview["fields"]) == 1
        f = overview["fields"][0]
        assert f["name"] == "myField"
        assert f["type"] == "String"
        assert f["visibility"] == "protected"
        assert f["is_static"] is True
        assert f["is_final"] is True
        assert f["annotations"] == ["Inject"]

    def test_extracts_import_with_all_fields(self):
        imp = _make_element(
            element_type="import",
            name="os",
            imported_name="os",
            import_statement="import os",
            line_number=1,
            is_static_import=False,
            is_wildcard=False,
            start_line=1,
        )
        result = _make_analysis_result(elements=[imp])
        overview = extract_structural_overview(result)
        assert len(overview["imports"]) == 1
        i = overview["imports"][0]
        assert i["name"] == "os"
        assert i["statement"] == "import os"
        assert i["is_static"] is False
        assert i["is_wildcard"] is False

    def test_mixed_elements_all_extracted(self):
        elements = [
            _make_element(element_type="class", name="A"),
            _make_element(element_type="function", name="fn"),
            _make_element(element_type="variable", name="v"),
            _make_element(element_type="import", name="sys"),
        ]
        result = _make_analysis_result(elements=elements)
        overview = extract_structural_overview(result)
        assert len(overview["classes"]) == 1
        assert len(overview["methods"]) == 1
        assert len(overview["fields"]) == 1
        assert len(overview["imports"]) == 1

    def test_boundary_complexity_7_no_hotspot(self):
        method = _make_element(element_type="function", name="m7", complexity_score=7)
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert overview["complexity_hotspots"] == []

    def test_boundary_complexity_8_creates_hotspot(self):
        method = _make_element(element_type="function", name="m8", complexity_score=8)
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert len(overview["complexity_hotspots"]) == 1


class TestExtractStructuralOverviewUniversal:
    def test_none_analysis_result_returns_empty(self):
        overview = extract_structural_overview_universal(None)
        assert overview["classes"] == []
        assert overview["methods"] == []

    def test_no_elements_attr_returns_empty(self):
        overview = extract_structural_overview_universal(MagicMock(spec=[]))
        assert overview["classes"] == []

    def test_empty_elements_returns_empty(self):
        result = _make_analysis_result(elements=[])
        overview = extract_structural_overview_universal(result)
        assert overview["classes"] == []

    def test_extracts_class_element(self):
        e = MagicMock()
        e.element_type = "class"
        e.name = "MyClass"
        e.start_line = 1
        e.end_line = 50
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["classes"]) == 1
        assert overview["classes"][0]["name"] == "MyClass"
        assert overview["classes"][0]["line_span"] == 50

    def test_extracts_function_element(self):
        e = MagicMock()
        e.element_type = "function"
        e.name = "myFunc"
        e.start_line = 5
        e.end_line = 15
        e.complexity_score = 3
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["methods"]) == 1
        assert overview["methods"][0]["complexity"] == 3

    def test_extracts_method_element(self):
        e = MagicMock()
        e.element_type = "method"
        e.name = "myMethod"
        e.start_line = 10
        e.end_line = 20
        e.complexity_score = 2
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["methods"]) == 1

    def test_extracts_variable_element(self):
        e = MagicMock()
        e.element_type = "variable"
        e.name = "myVar"
        e.start_line = 3
        e.end_line = 3
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["fields"]) == 1
        assert overview["fields"][0]["name"] == "myVar"

    def test_extracts_import_element(self):
        e = MagicMock()
        e.element_type = "import"
        e.name = "os"
        e.start_line = 1
        e.end_line = 1
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["imports"]) == 1
        assert overview["imports"][0]["name"] == "os"

    def test_high_complexity_creates_hotspot(self):
        e = MagicMock()
        e.element_type = "function"
        e.name = "complexFn"
        e.start_line = 1
        e.end_line = 100
        e.complexity_score = 15
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert len(overview["complexity_hotspots"]) == 1
        assert overview["complexity_hotspots"][0]["complexity"] == 15

    def test_missing_attr_uses_defaults(self):
        e = MagicMock(spec=[])
        e.element_type = "class"
        result = _make_analysis_result(elements=[e])
        overview = extract_structural_overview_universal(result)
        assert overview["classes"][0]["name"] == "unnamed"
        assert overview["classes"][0]["start_line"] == 0
