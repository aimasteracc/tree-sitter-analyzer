"""
Unit tests for analyze_scale_helpers module.

Tests all extracted helper functions from AnalyzeScaleTool:
- extract_structural_overview
- extract_structural_overview_universal
- generate_llm_guidance
- validate_scale_arguments
- create_json_file_analysis
- build_analysis_result
- build_detailed_analysis
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_helpers import (
    build_analysis_result,
    build_detailed_analysis,
    create_json_file_analysis,
    extract_structural_overview,
    extract_structural_overview_universal,
    generate_llm_guidance,
    validate_scale_arguments,
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
        method = _make_element(
            element_type="function", name="m7", complexity_score=7
        )
        result = _make_analysis_result(elements=[method])
        overview = extract_structural_overview(result)
        assert overview["complexity_hotspots"] == []

    def test_boundary_complexity_8_creates_hotspot(self):
        method = _make_element(
            element_type="function", name="m8", complexity_score=8
        )
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


class TestGenerateLlmGuidance:
    def _base_metrics(self, total_lines=100, language="python"):
        return {"total_lines": total_lines, "language": language}

    def _base_overview(self):
        return {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }

    def test_small_file_size_category(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=50), self._base_overview()
        )
        assert guidance["size_category"] == "small"
        assert "small file" in guidance["analysis_strategy"].lower()

    def test_medium_file_size_category(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=300), self._base_overview()
        )
        assert guidance["size_category"] == "medium"

    def test_large_file_size_category(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=1000), self._base_overview()
        )
        assert guidance["size_category"] == "large"

    def test_very_large_file_size_category(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=2000), self._base_overview()
        )
        assert guidance["size_category"] == "very_large"

    def test_large_file_recommends_targeted_tools(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=500), self._base_overview()
        )
        assert "extract_code_section" in guidance["recommended_tools"]
        assert "query_code" in guidance["recommended_tools"]

    def test_small_file_no_targeted_tools(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=50), self._base_overview()
        )
        assert "extract_code_section" not in guidance["recommended_tools"]

    def test_complexity_hotspots_recommends_structure_analysis(self):
        overview = self._base_overview()
        overview["complexity_hotspots"].append(
            {"name": "hot", "complexity": 10, "start_line": 1, "end_line": 5}
        )
        guidance = generate_llm_guidance(self._base_metrics(), overview)
        assert "analyze_code_structure" in guidance["recommended_tools"]
        assert "1 complexity hotspots" in guidance["complexity_assessment"]

    def test_no_hotspots_assessment(self):
        guidance = generate_llm_guidance(
            self._base_metrics(), self._base_overview()
        )
        assert "No significant complexity" in guidance["complexity_assessment"]

    def test_multiple_classes_key_area(self):
        overview = self._base_overview()
        overview["classes"] = [{"name": "A"}, {"name": "B"}]
        guidance = generate_llm_guidance(self._base_metrics(), overview)
        assert any("Multiple classes" in a for a in guidance["key_areas"])

    def test_many_methods_key_area(self):
        overview = self._base_overview()
        overview["methods"] = [{"name": f"m{i}"} for i in range(25)]
        guidance = generate_llm_guidance(self._base_metrics(), overview)
        assert any("Many methods" in a for a in guidance["key_areas"])

    def test_many_imports_key_area(self):
        overview = self._base_overview()
        overview["imports"] = [{"name": f"imp{i}"} for i in range(15)]
        guidance = generate_llm_guidance(self._base_metrics(), overview)
        assert any("Many imports" in a for a in guidance["key_areas"])

    @patch("tree_sitter_analyzer.query_loader.get_query_loader")
    def test_python_language_suggested_queries(self, mock_loader):
        mock_loader.return_value.list_queries_for_language.return_value = [
            "functions",
            "classes",
        ]
        guidance = generate_llm_guidance(
            self._base_metrics(language="python"), self._base_overview()
        )
        assert "functions" in guidance["suggested_queries"]
        assert "classes" in guidance["suggested_queries"]

    @patch("tree_sitter_analyzer.query_loader.get_query_loader")
    def test_unknown_language_no_suggested_queries(self, mock_loader):
        mock_loader.return_value.list_queries_for_language.return_value = []
        guidance = generate_llm_guidance(
            self._base_metrics(language="brainfuck"), self._base_overview()
        )
        assert guidance["suggested_queries"] == []

    def test_workflow_steps_always_start_with_check_scale(self):
        guidance = generate_llm_guidance(
            self._base_metrics(), self._base_overview()
        )
        assert guidance["workflow_steps"][0] == "check_code_scale (done)"

    def test_large_file_workflow_includes_targeted_steps(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=2000), self._base_overview()
        )
        steps = guidance["workflow_steps"]
        assert any("analyze_code_structure" in s for s in steps)

    def test_small_file_workflow_includes_full_analysis(self):
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=50), self._base_overview()
        )
        steps = guidance["workflow_steps"]
        assert any("full structure table" in s for s in steps)

    def test_many_imports_suggests_dependency_analysis(self):
        overview = self._base_overview()
        overview["imports"] = [{"name": f"i{i}"} for i in range(8)]
        guidance = generate_llm_guidance(self._base_metrics(), overview)
        steps = guidance["workflow_steps"]
        assert any("analyze_dependencies" in s for s in steps)

    def test_hotspot_in_large_file_workflow(self):
        overview = self._base_overview()
        overview["complexity_hotspots"].append(
            {
                "name": "hotFn",
                "complexity": 12,
                "start_line": 10,
                "end_line": 50,
            }
        )
        guidance = generate_llm_guidance(
            self._base_metrics(total_lines=2000), overview
        )
        steps = guidance["workflow_steps"]
        assert any("hotFn" in s and "hotspot" in s for s in steps)

    def test_missing_structural_fields_populated(self):
        overview = {}
        generate_llm_guidance(self._base_metrics(), overview)
        assert "complexity_hotspots" in overview
        assert "classes" in overview
        assert "methods" in overview
        assert "fields" in overview
        assert "imports" in overview

    @patch("tree_sitter_analyzer.query_loader.get_query_loader")
    def test_available_queries_populated_from_loader(self, mock_loader):
        mock_loader.return_value.list_queries_for_language.return_value = [
            "classes",
            "methods",
            "custom_query",
        ]
        guidance = generate_llm_guidance(
            self._base_metrics(language="java"), self._base_overview()
        )
        assert "available_queries" in guidance
        assert "classes" in guidance["available_queries"]
        assert "methods" in guidance["available_queries"]


class TestValidateScaleArguments:
    def test_single_file_valid(self):
        args = {"file_path": "test.py"}
        assert validate_scale_arguments(args) is True

    def test_single_file_with_options(self):
        args = {
            "file_path": "test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": False,
            "include_guidance": True,
        }
        assert validate_scale_arguments(args) is True

    def test_batch_mode_valid(self):
        args = {
            "file_paths": ["a.py", "b.py"],
            "metrics_only": True,
        }
        assert validate_scale_arguments(args) is True

    def test_missing_file_path_raises(self):
        with pytest.raises(ValueError, match="Required field 'file_path'"):
            validate_scale_arguments({})

    def test_empty_file_path_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_scale_arguments({"file_path": "   "})

    def test_non_string_file_path_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            validate_scale_arguments({"file_path": 123})

    def test_file_paths_mutually_exclusive(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "file_path": "b.py", "metrics_only": True}
            )

    def test_file_paths_non_list_raises(self):
        with pytest.raises(ValueError, match="non-empty list"):
            validate_scale_arguments({"file_paths": "notalist", "metrics_only": True})

    def test_file_paths_empty_list_raises(self):
        with pytest.raises(ValueError, match="non-empty list"):
            validate_scale_arguments({"file_paths": [], "metrics_only": True})

    def test_file_paths_metrics_only_false_raises(self):
        with pytest.raises(ValueError, match="metrics_only must be true"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "metrics_only": False}
            )

    def test_metrics_only_non_bool_raises(self):
        with pytest.raises(ValueError, match="metrics_only must be a boolean"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "metrics_only": "yes"}
            )

    def test_language_non_string_raises(self):
        with pytest.raises(ValueError, match="language must be a string"):
            validate_scale_arguments({"file_path": "f.py", "language": 42})

    def test_include_complexity_non_bool_raises(self):
        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_complexity": "yes"}
            )

    def test_include_details_non_bool_raises(self):
        with pytest.raises(ValueError, match="include_details must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_details": 1}
            )

    def test_include_guidance_non_bool_raises(self):
        with pytest.raises(ValueError, match="include_guidance must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_guidance": [True]}
            )


class TestCreateJsonFileAnalysis:
    def _base_metrics(self, total_lines=50, blank_lines=5, file_size_bytes=1024):
        return {
            "total_lines": total_lines,
            "blank_lines": blank_lines,
            "file_size_bytes": file_size_bytes,
            "estimated_tokens": 200,
        }

    def test_basic_analysis_structure(self):
        result = create_json_file_analysis(
            "config.json", self._base_metrics(), False
        )
        assert result["success"] is True
        assert result["file_path"] == "config.json"
        assert result["language"] == "json"
        assert result["total_lines"] == 50
        assert result["non_empty_lines"] == 45

    def test_small_scale_category(self):
        result = create_json_file_analysis(
            "s.json", self._base_metrics(total_lines=50), False
        )
        assert result["scale_category"] == "small"

    def test_medium_scale_category(self):
        result = create_json_file_analysis(
            "m.json", self._base_metrics(total_lines=500), False
        )
        assert result["scale_category"] == "medium"

    def test_large_scale_category(self):
        result = create_json_file_analysis(
            "l.json", self._base_metrics(total_lines=1500), False
        )
        assert result["scale_category"] == "large"

    def test_without_guidance(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), False
        )
        assert "llm_analysis_guidance" not in result

    def test_with_guidance(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), True
        )
        assert "llm_analysis_guidance" in result
        g = result["llm_analysis_guidance"]
        assert g["file_characteristics"] == "JSON configuration/data file"
        assert "recommended_workflow" in g

    def test_complexity_metrics_zeros(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), False
        )
        cm = result["complexity_metrics"]
        assert cm["total_elements"] == 0
        assert cm["max_depth"] == 0
        assert cm["avg_complexity"] == 0.0

    def test_structural_overview_empty(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), False
        )
        so = result["structural_overview"]
        assert so["classes"] == []
        assert so["methods"] == []
        assert so["fields"] == []

    def test_suitable_for_full_analysis_under_1000_lines(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(total_lines=500), False
        )
        assert result["analysis_recommendations"]["suitable_for_full_analysis"] is True

    def test_not_suitable_for_full_analysis_over_1000_lines(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(total_lines=1500), False
        )
        assert result["analysis_recommendations"]["suitable_for_full_analysis"] is False


class TestBuildAnalysisResult:
    def _mock_count_fn(self, elements, elem_type, label):
        return sum(1 for _ in elements)

    def test_basic_result_structure(self):
        result = build_analysis_result(
            file_path="test.py",
            language="python",
            file_metrics={"total_lines": 100},
            analysis_result=_make_analysis_result(elements=[]),
            structural_overview={"classes": [], "methods": []},
            count_elements_fn=self._mock_count_fn,
        )
        assert result["success"] is True
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["file_metrics"]["total_lines"] == 100

    def test_with_elements_summary(self):
        elements = [
            _make_element(element_type="class", name="A"),
            _make_element(element_type="function", name="fn"),
        ]
        result = build_analysis_result(
            file_path="test.py",
            language="python",
            file_metrics={},
            analysis_result=_make_analysis_result(elements=elements),
            structural_overview={},
            count_elements_fn=self._mock_count_fn,
        )
        assert result["summary"]["classes"] == 2
        assert result["summary"]["methods"] == 2

    def test_none_analysis_result(self):
        result = build_analysis_result(
            file_path="test.py",
            language="python",
            file_metrics={},
            analysis_result=None,
            structural_overview={},
            count_elements_fn=self._mock_count_fn,
        )
        assert result["success"] is True
        assert result["summary"]["classes"] == 0

    def test_package_included_when_present(self):
        pkg = MagicMock()
        pkg.name = "com.example"
        result = build_analysis_result(
            file_path="A.java",
            language="java",
            file_metrics={},
            analysis_result=_make_analysis_result(package=pkg),
            structural_overview={},
            count_elements_fn=self._mock_count_fn,
        )
        assert result["summary"]["package"] == "com.example"

    def test_package_none_when_absent(self):
        result = build_analysis_result(
            file_path="test.py",
            language="python",
            file_metrics={},
            analysis_result=_make_analysis_result(package=None),
            structural_overview={},
            count_elements_fn=self._mock_count_fn,
        )
        assert result["summary"]["package"] is None


class TestBuildDetailedAnalysis:
    def test_empty_analysis(self):
        result = _make_analysis_result(elements=[])
        result.get_statistics.return_value = {}
        detailed = build_detailed_analysis(result, "test.py")
        assert detailed["classes"] == []
        assert detailed["methods"] == []
        assert detailed["fields"] == []
        assert detailed["statistics"] == {}

    def test_none_analysis_result(self):
        detailed = build_detailed_analysis(None, "test.py")
        assert detailed["classes"] == []
        assert detailed["statistics"] == {}

    def test_detailed_class_extraction(self):
        cls = _make_element(
            element_type="class",
            name="MyClass",
            start_line=1,
            end_line=100,
            visibility="public",
            extends_class="Base",
            implements_interfaces=["I1"],
            annotations=["Deprecated"],
        )
        result = _make_analysis_result(elements=[cls])
        result.get_statistics.return_value = {"total": 1}
        detailed = build_detailed_analysis(result, "A.java")
        assert len(detailed["classes"]) == 1
        c = detailed["classes"][0]
        assert c["name"] == "MyClass"
        assert c["visibility"] == "public"
        assert c["extends"] == "Base"
        assert c["implements"] == ["I1"]
        assert c["annotations"] == ["Deprecated"]
        assert c["lines"] == "1-100"

    def test_detailed_method_extraction(self):
        method = _make_element(
            element_type="function",
            name="doWork",
            start_line=10,
            end_line=30,
            visibility="private",
            return_type="int",
            parameters=["a", "b"],
            is_constructor=False,
            is_static=True,
            complexity_score=7,
            annotations=["Test"],
        )
        result = _make_analysis_result(elements=[method])
        detailed = build_detailed_analysis(result, "test.py")
        assert len(detailed["methods"]) == 1
        m = detailed["methods"][0]
        assert m["name"] == "doWork"
        assert m["return_type"] == "int"
        assert m["parameters"] == 2
        assert m["is_static"] is True
        assert m["complexity"] == 7
        assert m["lines"] == "10-30"

    def test_detailed_field_extraction(self):
        field = _make_element(
            element_type="variable",
            name="count",
            start_line=5,
            end_line=5,
            visibility="private",
            field_type="int",
            is_static=False,
            is_final=True,
            annotations=["Volatile"],
        )
        result = _make_analysis_result(elements=[field])
        detailed = build_detailed_analysis(result, "test.py")
        assert len(detailed["fields"]) == 1
        f = detailed["fields"][0]
        assert f["name"] == "count"
        assert f["type"] == "int"
        assert f["is_final"] is True
        assert f["lines"] == "5-5"

    def test_statistics_from_analysis_result(self):
        result = _make_analysis_result(elements=[])
        result.get_statistics.return_value = {"elements": 5, "depth": 3}
        detailed = build_detailed_analysis(result, "test.py")
        assert detailed["statistics"]["elements"] == 5

    def test_mixed_elements_in_detailed(self):
        elements = [
            _make_element(element_type="class", name="C", start_line=1, end_line=10),
            _make_element(element_type="function", name="f", start_line=2, end_line=5),
            _make_element(element_type="variable", name="v", start_line=3, end_line=3),
        ]
        result = _make_analysis_result(elements=elements)
        detailed = build_detailed_analysis(result, "test.py")
        assert len(detailed["classes"]) == 1
        assert len(detailed["methods"]) == 1
        assert len(detailed["fields"]) == 1
