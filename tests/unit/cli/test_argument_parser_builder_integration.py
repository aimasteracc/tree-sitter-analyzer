#!/usr/bin/env python3
"""Tests for cli/argument_parser_builder.py — health/change/analysis option groups and full-parser integration."""

import argparse

from tree_sitter_analyzer.cli.argument_parser_builder import (
    _add_mcp_analysis_options,
    _add_mcp_change_options,
    _add_mcp_health_options,
    create_argument_parser,
)


class TestAddMcpHealthOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_file_health(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--file-health"])
        assert args.file_health is True

    def test_project_health(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--project-health"])
        assert args.project_health is True

    def test_max_files_default(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args([])
        assert args.max_files == 30

    def test_max_files_custom(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--max-files", "50"])
        assert args.max_files == 50

    def test_overview(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--overview"])
        assert args.overview is True

    def test_safe_to_edit(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--safe-to-edit"])
        assert args.safe_to_edit is True

    def test_edit_type_default(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args([])
        assert args.edit_type == "refactor"

    def test_edit_type_choices(self):
        parser = self._make_parser()
        _add_mcp_health_options(parser)
        args = parser.parse_args(["--edit-type", "fix_bug"])
        assert args.edit_type == "fix_bug"


class TestAddMcpChangeOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_change_impact(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--change-impact"])
        assert args.change_impact is True

    def test_change_impact_mode_default(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args([])
        assert args.change_impact_mode == "diff"

    def test_change_impact_mode_staged(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--change-impact-mode", "staged"])
        assert args.change_impact_mode == "staged"

    def test_change_impact_resource_profile_default(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args([])
        assert args.change_impact_resource_profile == "default"

    def test_change_impact_resource_profile_local_low_impact(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(
            ["--change-impact-resource-profile", "local_low_impact"]
        )
        assert args.change_impact_resource_profile == "local_low_impact"

    def test_change_impact_scope(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--change-impact-scope", "src/", "tests/"])
        assert args.change_impact_scope == ["src/", "tests/"]

    def test_change_impact_no_tests(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--change-impact-no-tests"])
        assert args.change_impact_include_tests is False

    def test_change_impact_include_tests_default(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args([])
        assert args.change_impact_include_tests is True

    def test_agent_summary_only(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--agent-summary-only"])
        assert args.agent_summary_only is True

    def test_agent_summary_only_default_is_true(self):
        """v1.12 default flip: trimmed surface is the default."""
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args([])
        assert args.agent_summary_only is True

    def test_change_impact_full_default_is_false(self):
        """v1.12: --change-impact-full is the explicit opt-out."""
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args([])
        assert args.change_impact_full is False

    def test_change_impact_full_can_be_set(self):
        parser = self._make_parser()
        _add_mcp_change_options(parser)
        args = parser.parse_args(["--change-impact-full"])
        assert args.change_impact_full is True


class TestAddMcpAnalysisOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_parser_readiness(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--parser-readiness"])
        assert args.parser_readiness is True

    def test_parser_readiness_language(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--parser-readiness-language", "swift"])
        assert args.parser_readiness_language == "swift"

    def test_parser_readiness_include_supported(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--parser-readiness-include-supported"])
        assert args.parser_readiness_include_supported is True

    def test_dependencies_default_none(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args([])
        assert args.dependencies is None

    def test_dependencies_const(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--dependencies"])
        assert args.dependencies == "summary"

    def test_dependencies_file_deps(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--dependencies", "file_deps"])
        assert args.dependencies == "file_deps"

    def test_refactor(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--refactor"])
        assert args.refactor is True

    def test_smart_context(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--smart-context"])
        assert args.smart_context is True

    def test_symbol_lineage(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--symbol-lineage", "MyClass"])
        assert args.symbol_lineage == "MyClass"

    def test_max_depth_default(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args([])
        assert args.max_depth == 3

    def test_max_depth_custom(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--max-depth", "5"])
        assert args.max_depth == 5

    def test_code_patterns(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--code-patterns"])
        assert args.code_patterns is True

    def test_min_grade_default(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args([])
        assert args.min_grade == "D"

    def test_min_grade_custom(self):
        parser = self._make_parser()
        _add_mcp_analysis_options(parser)
        args = parser.parse_args(["--min-grade", "B"])
        assert args.min_grade == "B"


class TestFullParserIntegration:
    def test_parse_common_combination(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--query-key",
                "class",
                "--output-format",
                "json",
            ]
        )
        assert args.file_path == "test.py"
        assert args.query_key == "class"
        assert args.output_format == "json"

    def test_parse_advanced_structure(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.java",
                "--advanced",
                "--structure",
            ]
        )
        assert args.file_path == "test.java"
        assert args.advanced is True
        assert args.structure is True

    def test_parse_file_health(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--file-health",
            ]
        )
        assert args.file_path == "test.py"
        assert args.file_health is True

    def test_parse_change_impact(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "--change-impact",
                "--change-impact-mode",
                "staged",
                "--change-impact-resource-profile",
                "local_low_impact",
            ]
        )
        assert args.change_impact is True
        assert args.change_impact_mode == "staged"
        assert args.change_impact_resource_profile == "local_low_impact"

    def test_parse_pr_review_url_mode(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "--pr-review",
                "pr",
                "--pr-review-url",
                "https://github.com/owner/repo/pull/42",
            ]
        )
        assert args.pr_review == "pr"
        assert args.pr_review_url == "https://github.com/owner/repo/pull/42"

    def test_parse_dependencies_blast_radius(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--dependencies",
                "blast_radius",
            ]
        )
        assert args.dependencies == "blast_radius"

    def test_parse_smart_context(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--smart-context",
            ]
        )
        assert args.smart_context is True

    def test_parse_refactor(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--refactor",
            ]
        )
        assert args.refactor is True

    def test_parse_partial_read_range(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--partial-read",
                "--start-line",
                "10",
                "--end-line",
                "20",
            ]
        )
        assert args.partial_read is True
        assert args.start_line == 10
        assert args.end_line == 20

    def test_parse_project_health(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "--project-health",
                "--max-files",
                "100",
            ]
        )
        assert args.project_health is True
        assert args.max_files == 100

    def test_parse_overview(self):
        parser = create_argument_parser()
        args = parser.parse_args(["--overview"])
        assert args.overview is True

    def test_parse_symbol_lineage_with_depth(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--symbol-lineage",
                "MyClass",
                "--max-depth",
                "5",
            ]
        )
        assert args.symbol_lineage == "MyClass"
        assert args.max_depth == 5

    def test_parse_code_patterns(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--code-patterns",
            ]
        )
        assert args.code_patterns is True

    def test_parse_safe_to_edit(self):
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "test.py",
                "--safe-to-edit",
                "--edit-type",
                "add_feature",
            ]
        )
        assert args.safe_to_edit is True
        assert args.edit_type == "add_feature"

    def test_no_args_file_path_none(self):
        parser = create_argument_parser()
        args = parser.parse_args([])
        assert args.file_path is None

    def test_defaults_all_correct(self):
        parser = create_argument_parser()
        args = parser.parse_args([])
        assert args.output_format == "json"
        assert args.change_impact_mode == "diff"
        assert args.change_impact_include_tests is True
        assert args.edit_type == "refactor"
        assert args.max_files == 30
        assert args.max_depth == 3
        assert args.min_grade == "D"
        assert args.dependencies is None
        assert args.summary is None


class TestCodeGraphImpactCliParity:
    """P3 — CLI parity for codegraph_impact include_tests flag.

    These tests ensure:
    1. The argparse dest is exactly ``codegraph_impact_include_tests`` (so a
       flag rename can't silently revert the feature to False).
    2. _specs_extended.build_tool_args reads that dest and passes it through as
       ``include_tests`` in the tool-args dict.
    """

    def test_flag_dest_is_codegraph_impact_include_tests(self):
        """--codegraph-impact-include-tests stores to dest codegraph_impact_include_tests."""
        from tree_sitter_analyzer.cli.argument_parser_builder import (
            create_argument_parser,
        )

        parser = create_argument_parser()
        args = parser.parse_args([])
        # Default must be False (store_true flag, not set → False)
        assert args.codegraph_impact_include_tests is False

    def test_flag_can_be_set_true(self):
        """Passing --codegraph-impact-include-tests sets dest to True."""
        from tree_sitter_analyzer.cli.argument_parser_builder import (
            create_argument_parser,
        )

        parser = create_argument_parser()
        args = parser.parse_args(
            ["--codegraph-impact", "my_fn", "--codegraph-impact-include-tests"]
        )
        assert args.codegraph_impact_include_tests is True

    def test_build_tool_args_threads_include_tests_false(self):
        """build_tool_args reads codegraph_impact_include_tests=False → include_tests=False."""
        import argparse

        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_extended import (
            _EXTENDED_SPECS,
        )

        spec = next(s for s in _EXTENDED_SPECS if s.flag_name == "codegraph_impact")
        # Simulate argparse namespace with include_tests=False (the default)
        ns = argparse.Namespace(
            codegraph_impact="my_fn",
            codegraph_impact_mode="function_impact",
            codegraph_impact_functions=None,
            codegraph_impact_file=None,
            codegraph_impact_depth=5,
            codegraph_impact_include_tests=False,
        )
        tool_args = spec.build_tool_args(ns, "json")
        assert tool_args["include_tests"] is False

    def test_build_tool_args_threads_include_tests_true(self):
        """build_tool_args reads codegraph_impact_include_tests=True → include_tests=True.

        If the argparse dest were renamed and getattr fell back to False,
        this assertion would catch the regression.
        """
        import argparse

        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_extended import (
            _EXTENDED_SPECS,
        )

        spec = next(s for s in _EXTENDED_SPECS if s.flag_name == "codegraph_impact")
        ns = argparse.Namespace(
            codegraph_impact="my_fn",
            codegraph_impact_mode="risk_score",
            codegraph_impact_functions=None,
            codegraph_impact_file=None,
            codegraph_impact_depth=5,
            codegraph_impact_include_tests=True,
        )
        tool_args = spec.build_tool_args(ns, "json")
        assert tool_args["include_tests"] is True


class TestCodeGraphPRReviewCliParity:
    def test_build_tool_args_threads_pr_url(self):
        import argparse

        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_extended import (
            _EXTENDED_SPECS,
        )

        spec = next(s for s in _EXTENDED_SPECS if s.flag_name == "pr_review")
        ns = argparse.Namespace(
            pr_review="pr",
            pr_review_url="https://github.com/owner/repo/pull/42",
        )
        tool_args = spec.build_tool_args(ns, "json")
        assert tool_args["mode"] == "pr"
        assert tool_args["pr_url"] == "https://github.com/owner/repo/pull/42"


def _choices_for_flag(flag: str) -> set[str]:
    """Return the argparse ``choices`` set for a long flag on the full parser."""
    parser = create_argument_parser()
    for action in parser._actions:
        if flag in action.option_strings:
            assert action.choices is not None, f"{flag} has no choices"
            return set(action.choices)
    raise AssertionError(f"flag {flag} not found on the parser")


class TestEditKindEnumParity:
    """Issue #985 — --edit-type and --modification-guard-type must share one
    canonical edit-kind vocabulary so they can never diverge again."""

    def test_edit_type_and_modification_guard_type_enums_agree(self):
        """The two flags' argparse choices sets must be exactly equal."""
        edit_types = _choices_for_flag("--edit-type")
        mg_types = _choices_for_flag("--modification-guard-type")
        assert edit_types == mg_types

    def test_canonical_edit_kinds_set_is_pinned(self):
        """Lock the canonical set membership exactly so future drift goes red."""
        from tree_sitter_analyzer.constants import EDIT_KINDS

        assert set(EDIT_KINDS) == {
            "add_feature",
            "behavior_change",
            "delete",
            "fix_bug",
            "refactor",
            "rename",
            "signature_change",
        }
        # No duplicates, and both flags expose exactly this set.
        assert len(EDIT_KINDS) == 7
        assert _choices_for_flag("--edit-type") == set(EDIT_KINDS)
        assert _choices_for_flag("--modification-guard-type") == set(EDIT_KINDS)
