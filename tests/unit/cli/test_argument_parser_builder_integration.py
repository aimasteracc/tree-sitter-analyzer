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
            ]
        )
        assert args.change_impact is True
        assert args.change_impact_mode == "staged"

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
