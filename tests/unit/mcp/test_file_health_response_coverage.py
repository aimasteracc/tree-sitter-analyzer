"""Tests for uncovered paths in file_health_response.py (63% -> 85%+)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from tree_sitter_analyzer.mcp.tools.utils.file_health_response import (
    _build_agent_next_action,
    _build_agent_summary,
    _build_extraction_plan,
    _build_extraction_target,
    _build_optional_extraction_fields,
    _build_recommendation,
    _build_signal,
    _find_function_end_line,
    _first_actionable_smell,
    _has_refactor_target_smell,
    _long_method_names,
    _suggest_next_action,
    _weakest_dimension_score,
    build_file_health_result,
)


def _make_health(grade: str, total: float, dimensions: dict[str, float]):
    return SimpleNamespace(grade=grade, total=total, dimensions=dimensions)


class TestBuildOptionalExtractionFields:
    def test_d_grade_returns_next_action_and_plan(self):
        smells = [
            {"smell": "long_method", "detail": "'run' is 80 lines (L12)", "severity": "warning"}
        ]
        fields = _build_optional_extraction_fields("src/x.py", "D", smells, "/tmp/x.py", None)
        assert "next_action" in fields
        assert "extraction_plan" in fields

    def test_f_grade_returns_fields(self):
        smells = [
            {"smell": "long_method", "detail": "'process' is 100 lines (L5)", "severity": "critical"}
        ]
        fields = _build_optional_extraction_fields("src/y.py", "F", smells, "/tmp/y.py", None)
        assert "next_action" in fields

    def test_a_grade_returns_empty(self):
        fields = _build_optional_extraction_fields("src/a.py", "A", [], "/tmp/a.py", None)
        assert fields == {}

    def test_no_long_methods_returns_no_extraction_plan(self):
        smells = [{"smell": "oversized_file", "detail": "500 lines", "severity": "warning"}]
        fields = _build_optional_extraction_fields("src/z.py", "D", smells, "/tmp/z.py", None)
        assert "next_action" in fields
        assert "extraction_plan" not in fields


class TestBuildSignal:
    def test_empty_dimensions_returns_no_data(self):
        assert _build_signal({}) == "no_data"

    def test_high_score_returns_healthy(self):
        assert _build_signal({"complexity": 80.0, "size": 90.0}) == "healthy"

    def test_mid_score_uses_signal_map(self):
        signal = _build_signal({"complexity": 50.0})
        assert signal == "moderate_cc"

    def test_low_score_uses_signal_map(self):
        signal = _build_signal({"dependencies": 20.0})
        assert signal == "high_coupling"

    def test_unknown_dimension_uses_fallback(self):
        signal = _build_signal({"custom_dim": 30.0})
        assert signal == "custom_dim_high"


class TestBuildRecommendation:
    def test_good_grade_no_smells(self):
        rec = _build_recommendation("A", {"complexity": 90.0}, [])
        assert "good shape" in rec

    def test_no_smells_with_grade_c(self):
        rec = _build_recommendation("C", {"complexity": 40.0}, [])
        assert "weakest dimension" in rec
        assert "complexity" in rec

    def test_critical_smells_included(self):
        smells = [
            {"smell": "long_method", "detail": "'x'", "severity": "critical"},
            {"smell": "deep_nesting", "detail": "nesting", "severity": "warning"},
        ]
        rec = _build_recommendation("D", {"complexity": 30.0}, smells)
        assert "1 critical" in rec
        assert "1 warning" in rec

    def test_long_method_names_in_extraction(self):
        smells = [
            {"smell": "long_method", "detail": "'process_data' is huge", "severity": "warning"},
            {"smell": "long_method", "detail": "'run_pipeline' is big", "severity": "critical"},
        ]
        rec = _build_recommendation("D", {"complexity": 20.0}, smells)
        assert "process_data" in rec
        assert "run_pipeline" in rec


class TestLongMethodNames:
    def test_extracts_names_from_detail(self):
        smells = [
            {"smell": "long_method", "detail": "'my_func' is 50 lines", "severity": "warning"},
        ]
        assert _long_method_names(smells) == ["my_func"]

    def test_skips_non_long_method_smells(self):
        smells = [{"smell": "god_class", "detail": "big class", "severity": "warning"}]
        assert _long_method_names(smells) == []

    def test_skips_detail_without_quote(self):
        smells = [{"smell": "long_method", "detail": "no quotes here", "severity": "warning"}]
        assert _long_method_names(smells) == []


class TestSuggestNextAction:
    def test_long_method_smell(self):
        smells = [{"smell": "long_method", "detail": "", "severity": "warning"}]
        action = _suggest_next_action("src/x.py", smells)
        assert "refactoring_suggestions" in action

    def test_oversized_file_smell(self):
        smells = [{"smell": "oversized_file", "detail": "", "severity": "warning"}]
        action = _suggest_next_action("src/x.py", smells)
        assert "split into focused modules" in action

    def test_generic_smell(self):
        smells = [{"smell": "high_complexity", "detail": "", "severity": "warning"}]
        action = _suggest_next_action("src/x.py", smells)
        assert "re-run check_file_health" in action


class TestBuildAgentNextAction:
    def test_healthy_file_returns_noop(self):
        action = _build_agent_next_action("src/a.py", "A", {"complexity": 95.0}, [])
        assert action["priority"] == "none"

    def test_b_grade_with_smell_returns_medium(self):
        action = _build_agent_next_action(
            "src/b.py", "B", {"complexity": 60.0},
            [{"smell": "high_complexity", "severity": "warning"}]
        )
        assert action["priority"] == "medium"

    def test_d_grade_returns_high_priority(self):
        action = _build_agent_next_action(
            "src/d.py", "D", {"complexity": 20.0},
            [{"smell": "long_method", "severity": "warning"}]
        )
        assert action["priority"] == "high"

    def test_c_grade_with_smells_returns_medium(self):
        action = _build_agent_next_action(
            "src/c.py", "C", {"complexity": 40.0},
            [{"smell": "deep_nesting", "severity": "warning"}]
        )
        assert action["priority"] == "medium"

    def test_critical_smell_returns_high(self):
        action = _build_agent_next_action(
            "src/e.py", "C", {"complexity": 50.0},
            [{"smell": "long_method", "severity": "critical"}]
        )
        assert action["priority"] == "high"

    def test_action_reason_without_smells(self):
        action = _build_agent_next_action("src/x.py", "C", {"size": 30.0}, [])
        assert "weakest dimension" in action["reason"]


class TestBuildAgentSummary:
    def test_empty_dimensions_returns_unknown(self):
        health = _make_health("A", 95.0, {})
        action = {"priority": "none", "cli_command": ""}
        summary = _build_agent_summary("src/a.py", health, [], action)
        assert summary["weakest_dimension"] == "unknown"
        assert summary["weakest_score"] is None

    def test_critical_smell_preferred_over_warning(self):
        health = _make_health("C", 70.0, {"complexity": 30.0})
        smells = [
            {"smell": "high_complexity", "severity": "warning"},
            {"smell": "long_method", "severity": "critical", "detail": "big"},
        ]
        action = _build_agent_next_action("src/c.py", "C", health.dimensions, smells)
        summary = _build_agent_summary("src/c.py", health, smells, action)
        assert summary["target_smell"] == "long_method"


class TestWeakestDimensionScore:
    def test_empty_dimensions(self):
        dim, score = _weakest_dimension_score({})
        assert dim == "unknown"
        assert score is None

    def test_returns_lowest(self):
        dim, score = _weakest_dimension_score({"complexity": 80.0, "size": 30.0, "deps": 90.0})
        assert dim == "size"
        assert score == 30.0


class TestFirstActionableSmell:
    def test_empty_returns_none(self):
        assert _first_actionable_smell([]) is None

    def test_critical_preferred(self):
        smells = [
            {"smell": "a", "severity": "warning"},
            {"smell": "b", "severity": "critical"},
        ]
        result = _first_actionable_smell(smells)
        assert result["smell"] == "b"

    def test_first_when_no_critical(self):
        smells = [
            {"smell": "x", "severity": "warning"},
            {"smell": "y", "severity": "info"},
        ]
        result = _first_actionable_smell(smells)
        assert result["smell"] == "x"


class TestHasRefactorTargetSmell:
    def test_long_method_is_target(self):
        assert _has_refactor_target_smell([{"smell": "long_method"}]) is True

    def test_oversized_file_is_target(self):
        assert _has_refactor_target_smell([{"smell": "oversized_file"}]) is True

    def test_god_class_is_target(self):
        assert _has_refactor_target_smell([{"smell": "god_class"}]) is True

    def test_deep_nesting_is_target(self):
        assert _has_refactor_target_smell([{"smell": "deep_nesting"}]) is True

    def test_other_smell_is_not_target(self):
        assert _has_refactor_target_smell([{"smell": "high_complexity"}]) is False


class TestBuildExtractionPlan:
    def test_returns_none_when_no_long_methods(self):
        smells = [{"smell": "god_class", "detail": "big", "severity": "warning"}]
        assert _build_extraction_plan("src/x.py", smells, "/tmp/x.py", None) is None

    def test_builds_plan_with_targets(self, tmp_path):
        target_file = tmp_path / "big_module.py"
        target_file.write_text("def run():\n    pass\n\ndef helper():\n    pass\n")
        smells = [
            {"smell": "long_method", "detail": "'run' is 50 lines (L1)", "severity": "critical"},
        ]
        plan = _build_extraction_plan(
            "big_module.py", smells, str(target_file), None
        )
        assert plan is not None
        assert plan["target_file"] == "big_module.py"
        assert len(plan["methods_to_extract"]) == 1
        assert plan["methods_to_extract"][0]["method"] == "run"
        assert len(plan["steps"]) == 5

    def test_limits_to_three_targets(self, tmp_path):
        target_file = tmp_path / "many.py"
        target_file.write_text("def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\ndef d():\n    pass\n")
        smells = [
            {"smell": "long_method", "detail": f"'{n}' is 50 lines (L{i})", "severity": "warning"}
            for i, n in enumerate(["a", "b", "c", "d"], 1)
        ]
        plan = _build_extraction_plan("many.py", smells, str(target_file), None)
        assert plan is not None
        assert len(plan["methods_to_extract"]) == 3


class TestBuildExtractionTarget:
    def test_parses_detail_with_line_number(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def run():\n    x = 1\n    return x\n\ndef other():\n    pass\n")
        smell = {"smell": "long_method", "detail": "'run' is 50 lines (L1)", "severity": "warning"}
        result = _build_extraction_target(smell, str(target), None)
        assert result["method"] == "run"
        assert result["start_line"] == 1
        assert result["priority"] == "normal"

    def test_critical_severity_target(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def run():\n    pass\n")
        smell = {"smell": "long_method", "detail": "'run' is 50 lines (L1)", "severity": "critical"}
        result = _build_extraction_target(smell, str(target), None)
        assert result["priority"] == "critical"

    def test_unknown_method_name(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def x():\n    pass\n")
        smell = {"smell": "long_method", "detail": "no quotes", "severity": "warning"}
        result = _build_extraction_target(smell, str(target), None)
        assert result["method"] == "unknown"


class TestFindFunctionEndLine:
    def test_uses_analysis_functions(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def run():\n    x = 1\n    return x\n\ndef other():\n    pass\n")
        analysis = SimpleNamespace(elements=[])
        with patch("tree_sitter_analyzer.mcp.tools.utils.file_health_response.get_functions") as mock_gf:
            mock_gf.return_value = [{"line": 1, "end_line": 4}]
            result = _find_function_end_line(str(target), 1, analysis)
        assert result == 4

    def test_falls_back_to_file_read(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def run():\n    x = 1\n    return x\n\ndef other():\n    pass\n")
        result = _find_function_end_line(str(target), 1, None)
        assert result > 1

    def test_handles_missing_file(self):
        result = _find_function_end_line("/nonexistent/file.py", 5, None)
        assert result == 5

    def test_handles_start_beyond_file(self, tmp_path):
        target = tmp_path / "small.py"
        target.write_text("x = 1\n")
        result = _find_function_end_line(str(target), 100, None)
        assert result == 100


class TestBuildFileHealthResultIntegration:
    def test_full_d_grade_flow(self, tmp_path):
        target = tmp_path / "big.py"
        target.write_text("def run():\n    x = 1\n    return x\n\ndef other():\n    pass\n")
        health = _make_health("D", 40.0, {"complexity": 20.0, "size": 50.0})
        smells = [
            {"smell": "long_method", "detail": "'run' is 50 lines (L1)", "severity": "critical"},
        ]
        result = build_file_health_result("big.py", health, smells, str(target), None)
        assert result["success"] is True
        assert result["grade"] == "D"
        assert result["smell_count"] == 1
        assert "next_action" in result
        assert "extraction_plan" in result
        assert result["signal"] == "high_cc"
