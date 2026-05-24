"""
Tests for generate_llm_guidance and validate_scale_arguments.
"""

from unittest.mock import patch

from tree_sitter_analyzer.mcp.tools.analyze_scale_helpers import (
    generate_llm_guidance,
    validate_scale_arguments,
)


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
        import pytest

        with pytest.raises(ValueError, match="Required field 'file_path'"):
            validate_scale_arguments({})

    def test_empty_file_path_raises(self):
        import pytest

        with pytest.raises(ValueError, match="cannot be empty"):
            validate_scale_arguments({"file_path": "   "})

    def test_non_string_file_path_raises(self):
        import pytest

        with pytest.raises(ValueError, match="must be a string"):
            validate_scale_arguments({"file_path": 123})

    def test_file_paths_mutually_exclusive(self):
        import pytest

        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "file_path": "b.py", "metrics_only": True}
            )

    def test_file_paths_non_list_raises(self):
        import pytest

        with pytest.raises(ValueError, match="non-empty list"):
            validate_scale_arguments({"file_paths": "notalist", "metrics_only": True})

    def test_file_paths_empty_list_raises(self):
        import pytest

        with pytest.raises(ValueError, match="non-empty list"):
            validate_scale_arguments({"file_paths": [], "metrics_only": True})

    def test_file_paths_metrics_only_false_raises(self):
        import pytest

        with pytest.raises(ValueError, match="metrics_only must be true"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "metrics_only": False}
            )

    def test_metrics_only_non_bool_raises(self):
        import pytest

        with pytest.raises(ValueError, match="metrics_only must be a boolean"):
            validate_scale_arguments(
                {"file_paths": ["a.py"], "metrics_only": "yes"}
            )

    def test_language_non_string_raises(self):
        import pytest

        with pytest.raises(ValueError, match="language must be a string"):
            validate_scale_arguments({"file_path": "f.py", "language": 42})

    def test_include_complexity_non_bool_raises(self):
        import pytest

        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_complexity": "yes"}
            )

    def test_include_details_non_bool_raises(self):
        import pytest

        with pytest.raises(ValueError, match="include_details must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_details": 1}
            )

    def test_include_guidance_non_bool_raises(self):
        import pytest

        with pytest.raises(ValueError, match="include_guidance must be a boolean"):
            validate_scale_arguments(
                {"file_path": "f.py", "include_guidance": [True]}
            )
