#!/usr/bin/env python3
"""Tests for cli/argument_parser_builder.py — epilog, core options, query/output/analysis option groups."""

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
    _add_mcp_equivalent_options,
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

    def test_list_skills_alias(self):
        parser = self._make_parser()
        _add_agent_skills_options(parser)
        args = parser.parse_args(["--list-skills"])
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


class TestFullIndexMCPEquivalentOptions:
    """Regression: CLI --full-index-mode choices must match MCP tool valid modes.

    Dogfood-found bug: argparse exposed {rebuild,stats,clear} but CodeGraphFullIndexTool
    only accepts {full,incremental}. Using TSA on TSA to discover and verify the fix.
    """

    def _make_parser(self):
        p = argparse.ArgumentParser()
        _add_mcp_equivalent_options(p)
        return p

    def test_full_index_mode_default_is_incremental(self):
        """Default mode must match MCP tool default ('incremental')."""
        parser = self._make_parser()
        args = parser.parse_args(["--full-index"])
        assert args.full_index_mode == "incremental"

    def test_full_index_mode_accepts_full(self):
        parser = self._make_parser()
        args = parser.parse_args(["--full-index", "--full-index-mode", "full"])
        assert args.full_index_mode == "full"

    def test_full_index_mode_accepts_incremental(self):
        parser = self._make_parser()
        args = parser.parse_args(["--full-index", "--full-index-mode", "incremental"])
        assert args.full_index_mode == "incremental"

    def test_full_index_mode_rejects_rebuild(self):
        """'rebuild' was the old invalid choice — must now be rejected."""
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--full-index", "--full-index-mode", "rebuild"])

    def test_full_index_mode_rejects_stats(self):
        """'stats' was an old invalid choice — must now be rejected."""
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--full-index", "--full-index-mode", "stats"])
