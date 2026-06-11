"""
Tests for create_json_file_analysis, build_analysis_result, and build_detailed_analysis.
"""

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.analyze_scale_helpers import (
    build_analysis_result,
    build_detailed_analysis,
    create_json_file_analysis,
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


class TestCreateJsonFileAnalysis:
    def _base_metrics(self, total_lines=50, blank_lines=5, file_size_bytes=1024):
        return {
            "total_lines": total_lines,
            "blank_lines": blank_lines,
            "file_size_bytes": file_size_bytes,
            "estimated_tokens": 200,
        }

    def test_basic_analysis_structure(self):
        result = create_json_file_analysis("config.json", self._base_metrics(), False)
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
        result = create_json_file_analysis("a.json", self._base_metrics(), False)
        assert "llm_analysis_guidance" not in result

    def test_with_guidance(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), True, output_format="json"
        )
        assert "llm_analysis_guidance" in result
        g = result["llm_analysis_guidance"]
        assert g["file_characteristics"] == "JSON configuration/data file"
        assert "recommended_workflow" in g

    def test_complexity_metrics_zeros(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), False, output_format="json"
        )
        cm = result["complexity_metrics"]
        assert cm["total_elements"] == 0
        assert cm["max_depth"] == 0
        assert cm["avg_complexity"] == 0.0

    def test_structural_overview_empty(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(), False, output_format="json"
        )
        so = result["structural_overview"]
        assert so["classes"] == []
        assert so["methods"] == []
        assert so["fields"] == []

    def test_suitable_for_full_analysis_under_1000_lines(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(total_lines=500), False, output_format="json"
        )
        assert result["analysis_recommendations"]["suitable_for_full_analysis"] is True

    def test_not_suitable_for_full_analysis_over_1000_lines(self):
        result = create_json_file_analysis(
            "a.json", self._base_metrics(total_lines=1500), False, output_format="json"
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


class TestF12FormatKeyConsistency:
    """Regression tests for F12 — round-16b dogfood found that the JSON
    envelope returned ``output_format`` while the TOON envelope returned
    ``format``, so callers that key off either name silently dropped fields.
    The canonical key is ``output_format``; ``format`` survives as a
    back-compat alias that MUST equal ``output_format`` whenever it
    appears.
    """

    def _metrics(self, total_lines: int = 50) -> dict:
        return {
            "total_lines": total_lines,
            "code_lines": 40,
            "comment_lines": 5,
            "blank_lines": 5,
            "file_size_bytes": 1024,
            "estimated_tokens": 200,
        }

    def test_create_json_file_analysis_exposes_output_format_in_json(self):
        """JSON-file path on JSON output must expose ``output_format`` and
        a matching ``format`` alias — round-16b saw the JSON envelope drop
        ``format`` entirely."""
        result = create_json_file_analysis(
            "config.json", self._metrics(), include_guidance=False, output_format="json"
        )
        assert result["output_format"] == "json"
        assert result["format"] == "json"
        assert result["format"] == result["output_format"]

    def test_create_json_file_analysis_exposes_output_format_in_toon(self):
        """JSON-file path on TOON output must still expose ``output_format``
        even after the TOON wrapper rewrites ``format`` to ``toon``."""
        result = create_json_file_analysis(
            "config.json", self._metrics(), include_guidance=False, output_format="toon"
        )
        # The TOON wrapper stomps ``format`` to "toon" but preserves the
        # canonical ``output_format`` key from the inner dict.
        assert result["output_format"] == "toon"
        assert result["format"] == "toon"
        assert result["format"] == result["output_format"]

    def test_format_alias_matches_output_format_for_both_paths(self):
        """Whichever format the caller asks for, ``format`` and
        ``output_format`` MUST agree — never one set without the other,
        never different values."""
        for fmt in ("json", "toon"):
            result = create_json_file_analysis(
                "data.json", self._metrics(), include_guidance=False, output_format=fmt
            )
            assert "format" in result, f"format missing for output_format={fmt}"
            assert "output_format" in result, (
                f"output_format missing for output_format={fmt}"
            )
            assert result["format"] == result["output_format"], (
                f"format/output_format disagree for {fmt}"
            )
