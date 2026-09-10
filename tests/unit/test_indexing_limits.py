"""Contract tests for the shared project-index file limit."""

from __future__ import annotations

import argparse

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cli.argument_groups._analysis import _add_analysis_options
from tree_sitter_analyzer.cli.argument_groups._mcp import (
    _add_mcp_index_management_options,
)
from tree_sitter_analyzer.indexing_limits import (
    DEFAULT_INDEX_MAX_FILES,
    normalize_index_max_files,
    parse_index_max_files,
)


def test_omitted_index_limit_uses_the_documented_default() -> None:
    assert normalize_index_max_files(None) == DEFAULT_INDEX_MAX_FILES


@pytest.mark.parametrize("value", [17, 17.0, "17"])
def test_positive_index_limit_is_normalized(value: object) -> None:
    assert normalize_index_max_files(value) == 17


@pytest.mark.parametrize("value", [True, False, 0, -1, 0.0, "0", "invalid"])
def test_non_positive_or_non_integer_index_limit_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="max_files must be a positive integer"):
        normalize_index_max_files(value)


def test_cli_index_limit_parser_uses_the_same_contract() -> None:
    assert parse_index_max_files("17") == 17
    with pytest.raises(ValueError, match="max_files must be a positive integer"):
        parse_index_max_files("0")


@pytest.mark.parametrize(
    "option",
    [
        "--autoindex-max-files",
        "--full-index-max-files",
        "--incremental-sync-max-files",
        "--knowledge-graph-max-files",
    ],
)
def test_index_management_cli_rejects_zero(option: str) -> None:
    parser = argparse.ArgumentParser()
    _add_mcp_index_management_options(parser)

    with pytest.raises(SystemExit):
        parser.parse_args([option, "0"])


def test_ast_cache_cli_rejects_zero() -> None:
    parser = argparse.ArgumentParser()
    _add_analysis_options(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["--ast-cache-max-files", "0"])


def test_invalid_force_limit_is_rejected_before_cache_mutation(tmp_path) -> None:
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=1, workers=0)

        with pytest.raises(ValueError, match="max_files must be a positive integer"):
            cache.index_project(max_files=0, force=True, workers=0)

        assert cache.get_stats()["total_files"] == 1
    finally:
        cache.close()
