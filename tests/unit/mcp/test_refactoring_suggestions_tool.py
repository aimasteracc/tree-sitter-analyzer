"""Unit tests for RefactoringSuggestionsTool."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools._refactoring_plan_builder import (
    _build_plan_for_func,
    _infer_returns,
)
from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,
)
from tree_sitter_analyzer.mcp.tools.utils.refactoring_suggestions_classes import (
    find_class_extractions,
    group_methods_by_responsibility,
)
from tree_sitter_analyzer.mcp.tools.utils.refactoring_suggestions_helpers import (
    make_agent_summary,
)

# Use project files for testing (within project boundary)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SAMPLE_PYTHON = str(
    PROJECT_ROOT / "tree_sitter_analyzer" / "languages" / "java_plugin.py"
)
SAMPLE_GENERIC = str(PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "server.py")
SAMPLE_CLI_MAIN = str(PROJECT_ROOT / "tree_sitter_analyzer" / "cli_main.py")
SAMPLE_PLAN_BUILDER = str(
    PROJECT_ROOT
    / "tree_sitter_analyzer"
    / "mcp"
    / "tools"
    / "_refactoring_plan_builder.py"
)
SAMPLE_SAFE_TO_EDIT = str(
    PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools" / "safe_to_edit_tool.py"
)


@pytest.fixture
def tool():
    t = RefactoringSuggestionsTool(".")
    t.set_project_path(".")
    return t


def _run(coro):
    return asyncio.run(coro)


def _first_precise_plan(result):
    plans = [s["precise_plan"] for s in result["suggestions"] if "precise_plan" in s]
    assert plans
    return plans[0]


class TestRefactoringSuggestionsTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "refactoring_suggestions"
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "max_suggestions" in defn["inputSchema"]["properties"]

    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_python_analysis_works(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        assert result["success"] is True
        assert "total_suggestions" in result
        assert "summary" in result
        assert "suggestions" in result

    def test_success_result_preserves_refactor_output_fields(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "output_format": "json"})
        )
        assert result["success"] is True
        assert "file" in result
        assert "total_suggestions" in result
        assert "summary" in result
        assert "agent_summary" in result
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)

    def test_python_detects_long_function(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        long_funcs = [s for s in suggestions if s["name"] == "long_function"]
        assert len(long_funcs) >= 1

    def test_python_detects_deep_nesting(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        deep = [s for s in suggestions if s["name"] == "deep_nesting"]
        assert len(deep) >= 1

    def test_python_detects_large_class(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        large_classes = [s for s in suggestions if s["name"] == "reduce_class_size"]
        assert len(large_classes) >= 1
        assert "recipe" in large_classes[0]
        assert "move_methods" in large_classes[0]["recipe"]

    def test_max_suggestions_limit(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON, "max_suggestions": 3}))
        assert result["total_suggestions"] <= 3

    def test_file_not_found(self, tool):
        result = _run(tool.execute({"file_path": "nonexistent_file.py"}))
        assert "error" in result

    def test_summary_format(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        summary = result["summary"]
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_agent_summary_surfaces_next_action(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "output_format": "json"})
        )

        agent_summary = result["agent_summary"]

        assert agent_summary["risk"] == "medium"
        assert "analyze_file" in agent_summary["next_step"]
        assert agent_summary["target_owner"] == "analyze_file"
        assert agent_summary["target_module"].endswith("_java_plugin_helpers.py")
        assert any(
            "--change-impact-scope" in command
            for command in agent_summary["suggested_tests"]
        )

    def test_suggestions_have_priority(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        for s in suggestions:
            assert "priority_score" in s
            assert isinstance(s["priority_score"], int)

    def test_suggestions_sorted_by_priority(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        scores = [s["priority_score"] for s in suggestions]
        assert scores == sorted(scores, reverse=True)

    def test_suggestions_have_line_ranges(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        for s in suggestions:
            if "line_range" in s:
                lr = s["line_range"]
                assert "start" in lr
                assert "end" in lr
                assert lr["start"] <= lr["end"]

    def test_include_extractions_false(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "include_extractions": False})
        )
        extractions = [s for s in result["suggestions"] if s["type"] == "extraction"]
        assert len(extractions) == 0

    def test_server_file_analysis(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_GENERIC}))
        assert result["total_suggestions"] >= 0

    def test_default_no_skeleton(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        if with_plans:
            for ext in with_plans[0]["precise_plan"]["extractions"]:
                assert "skeleton" not in ext

    def test_include_skeleton_true(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "include_skeleton": True})
        )
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        if with_plans:
            assert "skeleton" in with_plans[0]["precise_plan"]["extractions"][0]

    def test_output_format_toon(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "output_format": "toon"})
        )
        assert result.get("format") == "toon"

    def test_long_function_has_precise_plan(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        assert len(with_plans) >= 1
        plan = with_plans[0]["precise_plan"]
        assert "function" in plan
        assert "function_lines" in plan
        assert "helper_module" in plan
        assert "extractions" in plan
        assert len(plan["extractions"]) >= 1

    def test_precise_plan_extraction_fields(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "include_skeleton": True})
        )
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        assert len(with_plans) >= 1
        ext = with_plans[0]["precise_plan"]["extractions"][0]
        assert "helper_name" in ext
        assert "extract_lines" in ext
        assert "params" in ext
        assert "returns" in ext
        assert "skeleton" in ext
        assert isinstance(ext["params"], list)
        assert isinstance(ext["returns"], list)
        assert isinstance(ext["skeleton"], str)

    def test_precise_plan_has_steps(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        assert len(with_plans) >= 1
        plan = with_plans[0]["precise_plan"]
        assert "steps" in plan
        assert len(plan["steps"]) >= 3

    def test_precise_plan_helper_module_name(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        assert len(with_plans) >= 1
        helper_mod = with_plans[0]["precise_plan"]["helper_module"]
        assert helper_mod.endswith("_helpers.py")
        assert "_java_plugin_helpers.py" in helper_mod

    def test_precise_plan_uses_relative_import_for_package_module(self, tmp_path):
        source = (
            "def sample(flag):\n"
            "    total = 0\n"
            "    if flag:\n"
            "        total += 1\n"
            "        total += 2\n"
            "        total += 3\n"
            "        total += 4\n"
            "    return total\n"
        )
        lines = source.splitlines()
        package = tmp_path / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        file_path = str(package / "sample_module.py")

        plan = _build_plan_for_func(
            file_path,
            lines,
            {"line": 1, "end_line": len(lines), "name": "sample"},
            source,
        )

        assert plan is not None
        assert "from ._sample_module_helpers import " in plan["steps"][1]

    def test_precise_plan_normalizes_private_module_helper_names(self, tmp_path):
        source = (
            "def _main(flag):\n"
            "    total = 0\n"
            "    if flag:\n"
            "        total += 1\n"
            "        total += 2\n"
            "        total += 3\n"
            "        total += 4\n"
            "    return total\n"
        )
        lines = source.splitlines()
        package = tmp_path / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")

        plan = _build_plan_for_func(
            str(package / "_private_module.py"),
            lines,
            {"line": 1, "end_line": len(lines), "name": "_main"},
            source,
        )

        assert plan is not None
        assert "__private_module_helpers.py" not in plan["helper_module"]
        assert plan["helper_module"].endswith("_private_module_helpers.py")
        assert all(
            not extraction["helper_name"].startswith("__")
            for extraction in plan["extractions"]
        )
        assert "from ._private_module_helpers import " in plan["steps"][1]

    def test_precise_plan_keeps_absolute_import_for_non_package_file(self, tmp_path):
        source = (
            "def main(flag):\n"
            "    total = 0\n"
            "    if flag:\n"
            "        total += 1\n"
            "        total += 2\n"
            "        total += 3\n"
            "        total += 4\n"
            "    return total\n"
        )
        lines = source.splitlines()

        plan = _build_plan_for_func(
            str(tmp_path / "standalone.py"),
            lines,
            {"line": 1, "end_line": len(lines), "name": "main"},
            source,
        )

        assert plan is not None
        assert "from _standalone_helpers import " in plan["steps"][1]
        assert "from ._standalone_helpers import " not in plan["steps"][1]

    def test_mcp_tool_hooks_are_not_move_to_helpers(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_SAFE_TO_EDIT}))

        messages = [suggestion["message"] for suggestion in result["suggestions"]]

        assert not any("get_tool_schema" in message for message in messages)
        assert not any("validate_arguments" in message for message in messages)

    def test_class_recipe_groups_private_methods_by_responsibility(self):
        groups = group_methods_by_responsibility(
            [
                "_extract_import_info",
                "_parse_import_statement",
                "_extract_export_info",
                "_parse_export_statement",
                "_calculate_complexity",
            ]
        )

        assert groups[:2] == [
            {
                "responsibility": "import",
                "methods": ["_extract_import_info", "_parse_import_statement"],
                "count": 2,
            },
            {
                "responsibility": "export",
                "methods": ["_extract_export_info", "_parse_export_statement"],
                "count": 2,
            },
        ]

    def test_large_class_suggestion_includes_agent_recipe(self, tmp_path):
        source = tmp_path / "extractor.py"
        source.write_text("", encoding="utf-8")
        suggestions = find_class_extractions(
            [
                {
                    "name": "WidgetExtractor",
                    "line": 1,
                    "end_line": 200,
                    "method_count": 18,
                    "method_names": [
                        "_extract_import_info",
                        "_parse_import_statement",
                        "_extract_export_info",
                        "_parse_export_statement",
                        "_calculate_complexity",
                        "_calculate_score",
                    ],
                }
            ],
            {"id": "E004", "name": "reduce_class_size", "threshold": 5, "message": ""},
            {
                "id": "E002",
                "name": "extract_class",
                "message": "Methods {methods} in '{class_name}' share prefix '{prefix}'. Extract a new class.",
            },
            str(source),
        )

        recipe = suggestions[0]["recipe"]
        assert recipe["target_owner"] == "WidgetImportMixin"
        assert recipe["target_module"].endswith("_extractor_import_mixin.py")
        assert recipe["move_methods"] == [
            "_extract_import_info",
            "_parse_import_statement",
        ]
        assert "import_update" in recipe
        assert recipe["candidate_groups"][0]["responsibility"] == "import"

    def test_agent_summary_can_summarize_class_recipe(self):
        summary = make_agent_summary(
            "pkg/extractor.py",
            [
                {
                    "name": "reduce_class_size",
                    "priority_score": 50,
                    "recipe": {
                        "target_owner": "WidgetImportMixin",
                        "move_methods": [
                            "_extract_import_info",
                            "_parse_import_statement",
                        ],
                        "tests": [
                            "uv run python -m tree_sitter_analyzer <file> --refactor --format json"
                        ],
                        "stop_condition": "WidgetExtractor is below the class-size threshold.",
                    },
                    "line_range": {"start": 10, "end": 80},
                }
            ],
        )

        assert summary["next_step"] == (
            "Extract _extract_import_info, _parse_import_statement "
            "into WidgetImportMixin."
        )
        assert summary["target_owner"] == "WidgetImportMixin"
        assert summary["move_methods"] == [
            "_extract_import_info",
            "_parse_import_statement",
        ]
        assert summary["target_lines"] == "10-80"
        assert summary["stop_condition"] == (
            "WidgetExtractor is below the class-size threshold."
        )

    def test_prefix_group_skips_existing_responsibility_mixin(self, tmp_path):
        source = tmp_path / "find_and_grep_response.py"
        source.write_text("", encoding="utf-8")
        suggestions = find_class_extractions(
            [
                {
                    "name": "FindAndGrepRespondMixin",
                    "line": 1,
                    "end_line": 90,
                    "method_count": 3,
                    "method_names": [
                        "_respond_grouped",
                        "_respond_summary",
                        "_respond_full",
                    ],
                }
            ],
            {"id": "E004", "name": "reduce_class_size", "threshold": 5, "message": ""},
            {
                "id": "E002",
                "name": "extract_class",
                "message": "Methods {methods} in '{class_name}' share prefix '{prefix}'. Extract a new class.",
            },
            str(source),
        )

        assert suggestions == []

    def test_infer_returns_collects_direct_and_guard_body_assignments(self):
        block = """
        total = 0
        left, right = pair
        if flag:
            guarded = total + left
        try:
            loaded = read()
        except OSError:
            ignored = None
        """

        assert _infer_returns(block) == ["total", "left", "right", "guarded"]

    def test_precise_plan_skeleton_is_valid_python(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "include_skeleton": True})
        )
        with_plans = [s for s in result["suggestions"] if "precise_plan" in s]
        assert len(with_plans) >= 1
        for ext in with_plans[0]["precise_plan"]["extractions"]:
            import ast

            skeleton = ext["skeleton"]
            assert skeleton.startswith("def ")
            try:
                ast.parse(skeleton)
            except SyntaxError:
                pass  # Some skeletons may have incomplete bodies — that's ok


class TestR37tStructuralSuggestionsTopLabel:
    """r37t (dogfood): structural suggestions (P001 god_file, P002
    long_function, ...) carry their kind in ``name`` — they do NOT set
    a ``pattern`` field. The summary_line helper used to read
    ``top.get('pattern', 'unknown')`` so structural-only files always
    rendered ``top=unknown`` in the headline. The fix reads ``name``
    first with ``pattern`` and ``type`` as fallbacks.

    Caught by dogfooding ``--refactor`` on our own
    ``trace_impact_tool.py`` (806 lines, god_file + long_function +
    deep_nesting). Headline previously said:
        ``... suggestions=4 top=unknown major=3 critical=1``
    Now correctly says:
        ``... suggestions=4 top=long_function major=3 critical=1``
    """

    def test_structural_long_function_renders_name(self):
        suggestions = [
            {
                "id": "P002",
                "name": "long_function",
                "severity": "major",
                "message": "fn x is 90 lines",
            }
        ]
        result = make_agent_summary("foo.py", suggestions)
        assert "top=long_function" in result["summary_line"]
        assert "top=unknown" not in result["summary_line"]

    def test_anti_pattern_bridge_still_works(self):
        """Anti-pattern bridge sets BOTH name and pattern → still resolves."""
        suggestions = [
            {
                "id": "AP002",
                "name": "bare_except",
                "pattern": "bare_except",
                "severity": "major",
                "message": "bare except",
            }
        ]
        result = make_agent_summary("foo.py", suggestions)
        assert "top=bare_except" in result["summary_line"]

    def test_legacy_pattern_only_still_resolves(self):
        """Old fixtures with only ``pattern`` (no ``name``) still resolve."""
        suggestions = [
            {
                "id": "X",
                "pattern": "legacy_kind",
                "severity": "major",
                "message": "legacy",
            }
        ]
        result = make_agent_summary("foo.py", suggestions)
        assert "top=legacy_kind" in result["summary_line"]

    def test_type_fallback_when_no_name_no_pattern(self):
        """Final fallback to ``type`` before ``unknown``."""
        suggestions = [
            {
                "id": "Y",
                "type": "synthetic_kind",
                "severity": "major",
                "message": "no name no pattern",
            }
        ]
        result = make_agent_summary("foo.py", suggestions)
        assert "top=synthetic_kind" in result["summary_line"]

    def test_unknown_only_when_truly_missing(self):
        """``top=unknown`` reserved for entries with no kind metadata at all."""
        suggestions = [{"severity": "major", "message": "no kind info"}]
        result = make_agent_summary("foo.py", suggestions)
        assert "top=unknown" in result["summary_line"]
