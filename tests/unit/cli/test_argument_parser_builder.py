#!/usr/bin/env python3
"""Tests for cli/argument_parser_builder.py"""

import argparse

import pytest

from tree_sitter_analyzer import __version__
from tree_sitter_analyzer.cli.argument_parser_builder import (
    CLI_EPILOG,
    _add_agent_skills_options,
    _add_agent_workflow_options,
    _add_analysis_options,
    _add_batch_options,
    _add_core_options,
    _add_mcp_analysis_options,
    _add_mcp_change_options,
    _add_mcp_equivalent_options,
    _add_mcp_health_options,
    _add_output_options,
    _add_partial_read_options,
    _add_project_and_logging_options,
    _add_query_options,
    _add_sql_platform_options,
    create_argument_parser,
)


class TestCLIEpilog:
    def test_epilog_is_string(self):
        assert isinstance(CLI_EPILOG, str)

    def test_epilog_contains_examples(self):
        assert "Examples:" in CLI_EPILOG

    def test_epilog_mentions_table(self):
        assert "--table=full" in CLI_EPILOG

    def test_epilog_mentions_query_key(self):
        assert "--query-key" in CLI_EPILOG

    def test_epilog_mentions_advanced(self):
        assert "--advanced" in CLI_EPILOG

    def test_epilog_mentions_structure(self):
        assert "--structure" in CLI_EPILOG

    def test_epilog_mentions_summary(self):
        assert "--summary" in CLI_EPILOG

    def test_epilog_mentions_partial_read(self):
        assert "--partial-read" in CLI_EPILOG

    def test_epilog_mentions_file_health(self):
        assert "--file-health" in CLI_EPILOG

    def test_epilog_mentions_safe_to_edit(self):
        assert "--safe-to-edit" in CLI_EPILOG

    def test_epilog_mentions_refactor(self):
        assert "--refactor" in CLI_EPILOG

    def test_epilog_mentions_smart_context(self):
        assert "--smart-context" in CLI_EPILOG

    def test_epilog_mentions_change_impact(self):
        assert "--change-impact" in CLI_EPILOG

    def test_epilog_mentions_project_health(self):
        assert "--project-health" in CLI_EPILOG

    def test_epilog_mentions_overview(self):
        assert "--overview" in CLI_EPILOG

    def test_epilog_mentions_dependencies(self):
        assert "--dependencies" in CLI_EPILOG


class TestCreateArgumentParser:
    def test_returns_argument_parser(self):
        parser = create_argument_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_description_set(self):
        parser = create_argument_parser()
        assert "Tree-sitter" in parser.description

    def test_raw_description_formatter(self):
        parser = create_argument_parser()
        assert parser.formatter_class is argparse.RawDescriptionHelpFormatter

    def test_epilog_set(self):
        parser = create_argument_parser()
        assert parser.epilog == CLI_EPILOG

    def test_version_action_present(self):
        parser = create_argument_parser()
        version_actions = [
            a for a in parser._actions if isinstance(a, argparse._VersionAction)
        ]
        assert len(version_actions) == 1
        assert __version__ in version_actions[0].version

    def test_file_path_argument(self):
        parser = create_argument_parser()
        pos_actions = [a for a in parser._actions if a.option_strings == []]
        file_path_actions = [a for a in pos_actions if a.dest == "file_path"]
        assert len(file_path_actions) == 1
        assert file_path_actions[0].nargs == "?"


class TestAddCoreOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_version_flag(self):
        parser = self._make_parser()
        _add_core_options(parser)
        version_actions = [
            a for a in parser._actions if isinstance(a, argparse._VersionAction)
        ]
        assert len(version_actions) == 1

    def test_file_path_optional(self):
        parser = self._make_parser()
        _add_core_options(parser)
        args = parser.parse_args([])
        assert args.file_path is None

    def test_file_path_provided(self):
        parser = self._make_parser()
        _add_core_options(parser)
        args = parser.parse_args(["test.py"])
        assert args.file_path == "test.py"


class TestAddQueryOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_query_key(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--query-key", "class"])
        assert args.query_key == "class"

    def test_query_key_default_none(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args([])
        assert args.query_key is None

    def test_query_string(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--query-string", "(class_declaration)"])
        assert args.query_string == "(class_declaration)"

    def test_query_key_and_string_mutually_exclusive(self):
        parser = self._make_parser()
        _add_query_options(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--query-key", "class", "--query-string", "(x)"])

    def test_filter(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--filter", "name=main"])
        assert args.filter == "name=main"

    def test_list_queries(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--list-queries"])
        assert args.list_queries is True

    def test_filter_help(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--filter-help"])
        assert args.filter_help is True

    def test_describe_query(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--describe-query", "classes"])
        assert args.describe_query == "classes"

    def test_show_supported_languages(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--show-supported-languages"])
        assert args.show_supported_languages is True

    def test_show_supported_extensions(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--show-supported-extensions"])
        assert args.show_supported_extensions is True

    def test_show_common_queries(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--show-common-queries"])
        assert args.show_common_queries is True

    def test_show_query_languages(self):
        parser = self._make_parser()
        _add_query_options(parser)
        args = parser.parse_args(["--show-query-languages"])
        assert args.show_query_languages is True


class TestAddOutputOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_output_format_default_json(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args([])
        assert args.output_format == "json"

    def test_output_format_text(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--output-format", "text"])
        assert args.output_format == "text"

    def test_output_format_toon(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--output-format", "toon"])
        assert args.output_format == "toon"

    def test_format_alias(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--format", "toon"])
        assert args.format == "toon"

    def test_toon_use_tabs(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--toon-use-tabs"])
        assert args.toon_use_tabs is True

    def test_table_full(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--table", "full"])
        assert args.table == "full"

    def test_table_compact(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--table", "compact"])
        assert args.table == "compact"

    def test_table_csv(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--table", "csv"])
        assert args.table == "csv"

    def test_include_javadoc(self):
        parser = self._make_parser()
        _add_output_options(parser)
        args = parser.parse_args(["--include-javadoc"])
        assert args.include_javadoc is True


class TestAddAnalysisOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_advanced(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--advanced"])
        assert args.advanced is True

    def test_summary_default_none(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args([])
        assert args.summary is None

    def test_summary_const(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--summary"])
        assert args.summary == "classes,methods"

    def test_summary_custom(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--summary", "functions"])
        assert args.summary == "functions"

    def test_structure(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--structure"])
        assert args.structure is True

    def test_statistics(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--statistics"])
        assert args.statistics is True

    def test_language(self):
        parser = self._make_parser()
        _add_analysis_options(parser)
        args = parser.parse_args(["--language", "python"])
        assert args.language == "python"


class TestAddSqlPlatformOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_sql_platform_info(self):
        parser = self._make_parser()
        _add_sql_platform_options(parser)
        args = parser.parse_args(["--sql-platform-info"])
        assert args.sql_platform_info is True

    def test_record_sql_profile(self):
        parser = self._make_parser()
        _add_sql_platform_options(parser)
        args = parser.parse_args(["--record-sql-profile"])
        assert args.record_sql_profile is True

    def test_compare_sql_profiles(self):
        parser = self._make_parser()
        _add_sql_platform_options(parser)
        args = parser.parse_args(["--compare-sql-profiles", "a", "b"])
        assert args.compare_sql_profiles == ["a", "b"]


class TestAddProjectAndLoggingOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_project_root(self):
        parser = self._make_parser()
        _add_project_and_logging_options(parser)
        args = parser.parse_args(["--project-root", "/tmp/project"])
        assert args.project_root == "/tmp/project"

    def test_quiet(self):
        parser = self._make_parser()
        _add_project_and_logging_options(parser)
        args = parser.parse_args(["--quiet"])
        assert args.quiet is True


class TestAddPartialReadOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_partial_read(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--partial-read"])
        assert args.partial_read is True

    def test_partial_read_requests_json(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--partial-read-requests-json", '{"requests":[]}'])
        assert args.partial_read_requests_json == '{"requests":[]}'

    def test_partial_read_requests_file(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--partial-read-requests-file", "/tmp/req.json"])
        assert args.partial_read_requests_file == "/tmp/req.json"

    def test_start_line(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--start-line", "10"])
        assert args.start_line == 10

    def test_end_line(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--end-line", "20"])
        assert args.end_line == 20

    def test_start_column(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--start-column", "0"])
        assert args.start_column == 0

    def test_end_column(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--end-column", "80"])
        assert args.end_column == 80

    def test_allow_truncate(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--allow-truncate"])
        assert args.allow_truncate is True

    def test_fail_fast(self):
        parser = self._make_parser()
        _add_partial_read_options(parser)
        args = parser.parse_args(["--fail-fast"])
        assert args.fail_fast is True


class TestAddBatchOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_health_check(self):
        parser = self._make_parser()
        _add_batch_options(parser)
        args = parser.parse_args(["--health-check"])
        assert args.health_check is True

    def test_metrics_only(self):
        parser = self._make_parser()
        _add_batch_options(parser)
        args = parser.parse_args(["--metrics-only"])
        assert args.metrics_only is True

    def test_file_paths(self):
        parser = self._make_parser()
        _add_batch_options(parser)
        args = parser.parse_args(["--file-paths", "a.py", "b.py"])
        assert args.file_paths == ["a.py", "b.py"]

    def test_files_from(self):
        parser = self._make_parser()
        _add_batch_options(parser)
        args = parser.parse_args(["--files-from", "files.txt"])
        assert args.files_from == "files.txt"


class TestAddMcpEquivalentOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_adds_all_sub_groups(self):
        parser = self._make_parser()
        _add_mcp_equivalent_options(parser)
        dests = {a.dest for a in parser._actions}
        assert "agent_skills" in dests
        assert "agent_workflow" in dests
        assert "file_health" in dests
        assert "change_impact" in dests
        assert "smart_context" in dests


class TestAddAgentSkillsOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_agent_skills(self):
        parser = self._make_parser()
        _add_agent_skills_options(parser)
        args = parser.parse_args(["--agent-skills"])
        assert args.agent_skills is True

    def test_agent_skills_root(self):
        parser = self._make_parser()
        _add_agent_skills_options(parser)
        args = parser.parse_args(["--agent-skills-root", "/custom/path"])
        assert args.agent_skills_root == "/custom/path"


class TestAddAgentWorkflowOptions:
    def _make_parser(self):
        return argparse.ArgumentParser()

    def test_agent_workflow(self):
        parser = self._make_parser()
        _add_agent_workflow_options(parser)
        args = parser.parse_args(["--agent-workflow"])
        assert args.agent_workflow is True


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
