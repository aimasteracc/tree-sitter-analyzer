#!/usr/bin/env python3
"""Shared mixin tests for create_argument_parser options."""

import argparse

import pytest

from tree_sitter_analyzer.cli_main import (
    _normalize_agent_command_aliases,
    create_argument_parser,
)


class TestCreateArgumentParserMixin:
    """Tests for create_argument_parser function."""

    __test__ = False

    def test_parser_creation(self):
        """Test that argument parser is created successfully."""
        parser = create_argument_parser()
        assert parser is not None
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parser_accepts_agent_summary_only_for_change_impact(self):
        """Change-impact can request a compact agent-only response."""
        parser = create_argument_parser()
        args = parser.parse_args(["--change-impact", "--agent-summary-only"])

        assert args.change_impact is True
        assert args.agent_summary_only is True

    def test_parser_accepts_agent_workflow_pack(self):
        """Agent workflow can be requested without a target file."""
        parser = create_argument_parser()
        args = parser.parse_args(["--agent-workflow"])

        assert args.agent_workflow is True
        assert args.file_path is None

    def test_parser_accepts_agent_skills_inventory(self):
        """Agent skills inventory can be requested without a target file."""
        parser = create_argument_parser()
        args = parser.parse_args(["--agent-skills"])

        assert args.agent_skills is True
        assert args.file_path is None

    def test_parser_accepts_change_impact_mode_and_test_toggle(self):
        """Change-impact CLI exposes the MCP mode and include_tests controls."""
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "--change-impact",
                "--change-impact-mode",
                "staged",
                "--change-impact-no-tests",
            ]
        )

        assert args.change_impact is True
        assert args.change_impact_mode == "staged"
        assert args.change_impact_include_tests is False

    def test_parser_has_file_path_argument(self):
        """Test that parser has file_path argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["test.py"])
        assert args.file_path == "test.py"

    def test_parser_has_query_key_argument(self):
        """Test that parser has --query-key argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--query-key", "class", "test.py"])
        assert args.query_key == "class"

    def test_parser_has_query_string_argument(self):
        """Test that parser has --query-string argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--query-string", "(function)", "test.py"])
        assert args.query_string == "(function)"

    def test_parser_has_filter_argument(self):
        """Test that parser has --filter argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--filter", "name=main", "test.py"])
        assert args.filter == "name=main"

    def test_parser_has_list_queries_argument(self):
        """Test that parser has --list-queries argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--list-queries"])
        assert args.list_queries is True

    def test_parser_has_describe_query_argument(self):
        """Test that parser has --describe-query argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--describe-query", "class"])
        assert args.describe_query == "class"

    def test_parser_has_show_supported_languages_argument(self):
        """Test that parser has --show-supported-languages argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--show-supported-languages"])
        assert args.show_supported_languages is True

    def test_parser_has_show_supported_extensions_argument(self):
        """Test that parser has --show-supported-extensions argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--show-supported-extensions"])
        assert args.show_supported_extensions is True

    def test_parser_has_output_format_argument(self):
        """Test that parser has --output-format argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--output-format", "json", "test.py"])
        assert args.output_format == "json"

    def test_parser_has_format_argument(self):
        """Test that parser has --format argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--format", "toon", "test.py"])
        assert args.format == "toon"

    def test_parser_has_table_argument(self):
        """Test that parser has --table argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--table", "full", "test.py"])
        assert args.table == "full"

    def test_parser_has_include_javadoc_argument(self):
        """Test that parser has --include-javadoc argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--include-javadoc", "test.py"])
        assert args.include_javadoc is True

    def test_parser_has_advanced_argument(self):
        """Test that parser has --advanced argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--advanced", "test.py"])
        assert args.advanced is True

    def test_parser_has_summary_argument(self):
        """Test that parser has --summary argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--summary", "test.py"])
        # --summary is a flag that accepts a value
        assert args.summary == "test.py"

    def test_parser_has_structure_argument(self):
        """Test that parser has --structure argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--structure", "test.py"])
        assert args.structure is True

    def test_parser_has_statistics_argument(self):
        """Test that parser has --statistics argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--statistics", "test.py"])
        assert args.statistics is True

    def test_parser_has_language_argument(self):
        """Test that parser has --language argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--language", "python", "test.py"])
        assert args.language == "python"

    def test_parser_has_project_root_argument(self):
        """Test that parser has --project-root argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--project-root", "/path/to/project", "test.py"])
        assert args.project_root == "/path/to/project"

    def test_parser_has_quiet_argument(self):
        """Test that parser has --quiet argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--quiet", "test.py"])
        assert args.quiet is True

    def test_parser_has_partial_read_argument(self):
        """Test that parser has --partial-read argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--partial-read", "test.py"])
        assert args.partial_read is True

    def test_parser_has_start_line_argument(self):
        """Test that parser has --start-line argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--start-line", "10", "test.py"])
        assert args.start_line == 10

    def test_parser_has_end_line_argument(self):
        """Test that parser has --end-line argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--end-line", "20", "test.py"])
        assert args.end_line == 20

    def test_parser_has_start_column_argument(self):
        """Test that parser has --start-column argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--start-column", "5", "test.py"])
        assert args.start_column == 5

    def test_parser_has_end_column_argument(self):
        """Test that parser has --end-column argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--end-column", "15", "test.py"])
        assert args.end_column == 15

    def test_parser_default_output_format(self):
        """Test that default output format is json."""
        parser = create_argument_parser()
        args = parser.parse_args(["test.py"])
        assert args.output_format == "json"

    def test_parser_file_path_optional(self):
        """Test that file_path is optional."""
        parser = create_argument_parser()
        args = parser.parse_args(["--list-queries"])
        assert args.file_path is None

    def test_parser_has_safe_to_edit_edit_type_argument(self):
        """Test that --edit-type supports MCP safe_to_edit schema values."""
        parser = create_argument_parser()
        args = parser.parse_args(["test.py", "--safe-to-edit", "--edit-type", "rename"])
        assert args.safe_to_edit is True
        assert args.edit_type == "rename"

    @pytest.mark.parametrize(
        ("argv", "expected_mode", "expected_file_path"),
        [
            (["--dependencies"], "summary", None),
            (["--dependencies", "summary"], "summary", None),
            (["--dependencies", "cycles"], "cycles", None),
            (["target.py", "--dependencies", "file_deps"], "file_deps", "target.py"),
            (["--dependencies", "full"], "full", None),
        ],
    )
    def test_parser_dependencies_supports_mcp_modes_and_legacy_full(
        self,
        argv: list[str],
        expected_mode: str,
        expected_file_path: str | None,
    ):
        """Dependency CLI accepts MCP modes and the legacy full alias."""
        parser = create_argument_parser()
        args = parser.parse_args(argv)
        assert args.dependencies == expected_mode
        assert args.file_path == expected_file_path

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (
                ["file-health", "target.py", "--format", "json"],
                ["target.py", "--file-health", "--format", "json"],
            ),
            (
                ["agent-skills", "--format", "json"],
                ["--agent-skills", "--format", "json"],
            ),
            (
                ["agent-workflow", "target.py", "--format", "json"],
                ["--agent-workflow", "target.py", "--format", "json"],
            ),
            (
                ["parser-readiness", "swift", "--format", "json"],
                ["--parser-readiness", "swift", "--format", "json"],
            ),
            (
                ["safe-to-edit", "target.py", "--edit-type", "rename"],
                ["target.py", "--safe-to-edit", "--edit-type", "rename"],
            ),
            (
                ["refactor", "target.py"],
                ["target.py", "--refactor"],
            ),
            (
                ["smart-context", "target.py", "--format", "toon"],
                ["target.py", "--smart-context", "--format", "toon"],
            ),
            (
                ["project-health", "--format", "json"],
                ["--project-health", "--format", "json"],
            ),
            (
                ["change-impact", "--agent-summary-only"],
                ["--change-impact", "--agent-summary-only"],
            ),
            (
                ["target.py", "--file-health"],
                ["target.py", "--file-health"],
            ),
        ],
    )
    def test_agent_command_aliases_normalize_to_existing_flags(
        self, argv: list[str], expected: list[str]
    ):
        """Agent-friendly command aliases reuse the existing flag CLI."""
        assert _normalize_agent_command_aliases(argv) == expected

    def test_agent_file_scoped_alias_without_path_keeps_existing_error_path(
        self,
    ):
        """Missing file paths still flow to MCP command validation."""
        assert _normalize_agent_command_aliases(
            ["file-health", "--format", "json"]
        ) == [
            "--file-health",
            "--format",
            "json",
        ]
