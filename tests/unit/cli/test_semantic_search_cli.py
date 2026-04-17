"""
Unit tests for Semantic Search CLI.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.semantic_search_cli import _build_parser


class TestBuildParser:
    """Test argument parser building."""

    def test_build_parser(self) -> None:
        """Test parser construction."""
        parser = _build_parser()

        # Check that description contains key phrases (prog name varies by test runner)
        assert "semantic code search" in parser.description.lower()
        assert "query classification" in parser.description.lower()

    def test_required_query_argument(self) -> None:
        """Test that --query is required."""
        parser = _build_parser()

        # Should fail without --query
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_query_argument(self) -> None:
        """Test --query argument."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test query"])

        assert args.query == "test query"

    def test_format_argument_default(self) -> None:
        """Test --format default value."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test"])

        assert args.format == "text"

    def test_format_argument_choices(self) -> None:
        """Test --format choices."""
        parser = _build_parser()

        for fmt in ["text", "json", "toon"]:
            args = parser.parse_args(["--query", "test", "--format", fmt])
            assert args.format == fmt

    def test_project_root_argument(self) -> None:
        """Test --project-root argument."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--project-root", "/path/to/project"])

        assert args.project_root == "/path/to/project"

    def test_cache_ttl_argument(self) -> None:
        """Test --cache-ttl argument."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--cache-ttl", "120"])

        assert args.cache_ttl == 120

    def test_llm_provider_argument(self) -> None:
        """Test --llm-provider argument."""
        parser = _build_parser()

        args = parser.parse_args(["--query", "test", "--llm-provider", "openai"])
        assert args.llm_provider == "openai"

        args = parser.parse_args(["--query", "test", "--llm-provider", "anthropic"])
        assert args.llm_provider == "anthropic"

    def test_no_cache_argument(self) -> None:
        """Test --no-cache flag."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--no-cache"])

        assert args.no_cache is True

    def test_show_cache_stats_argument(self) -> None:
        """Test --show-cache-stats flag."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--show-cache-stats"])

        assert args.show_cache_stats is True

    def test_clear_cache_argument(self) -> None:
        """Test --clear-cache flag."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--clear-cache"])

        assert args.clear_cache is True

    def test_quiet_argument(self) -> None:
        """Test --quiet flag."""
        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--quiet"])

        assert args.quiet is True


class TestSemanticSearchCli:
    """Test semantic search CLI functionality."""

    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.detect_project_root")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.QueryClassifier")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.FastPathExecutor")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.LLMIntegration")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.QueryCache")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.SearchResultFormatter")
    async def test_simple_query_execution(
        self,
        mock_formatter_class,
        mock_cache_class,
        mock_llm_class,
        mock_executor_class,
        mock_classifier_class,
        mock_detect_root,
    ) -> None:
        """Test simple query execution."""
        # Setup mocks
        mock_detect_root.return_value = "/fake/root"

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = MagicMock(
            query_type=MagicMock(value="simple"),
            params={"handler": "grep_by_name", "params": {"name": "test"}},
            confidence=0.9,
        )
        mock_classifier_class.return_value = mock_classifier

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            success=True,
            results=[{"file": "test.py", "line": 10}],
            execution_time=0.5,
            tool_used="ripgrep",
        )
        mock_executor_class.return_value = mock_executor

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        mock_formatter = MagicMock()
        mock_formatter.format.return_value = "Results: test.py:10"
        mock_formatter_class.return_value = mock_formatter

        # Run the CLI
        parser = _build_parser()
        args = parser.parse_args(["--query", "functions named test", "--quiet"])

        from tree_sitter_analyzer.cli.commands.semantic_search_cli import _run

        exit_code = await _run(args)

        assert exit_code == 0
        mock_classifier.classify.assert_called_once()
        mock_executor.execute.assert_called_once()

    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.detect_project_root")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.QueryCache")
    async def test_show_cache_stats(
        self,
        mock_cache_class,
        mock_detect_root,
    ) -> None:
        """Test showing cache statistics."""
        mock_detect_root.return_value = "/fake/root"

        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = MagicMock(
            total_queries=100,
            cache_hits=60,
            cache_misses=40,
            hit_rate=lambda: 0.6,
            invalidations=5,
        )
        mock_cache_class.return_value = mock_cache

        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--show-cache-stats"])

        from tree_sitter_analyzer.cli.commands.semantic_search_cli import _run

        exit_code = await _run(args)

        assert exit_code == 0
        mock_cache.get_stats.assert_called_once()

    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.detect_project_root")
    @patch("tree_sitter_analyzer.cli.commands.semantic_search_cli.QueryCache")
    async def test_clear_cache(
        self,
        mock_cache_class,
        mock_detect_root,
    ) -> None:
        """Test clearing the cache."""
        mock_detect_root.return_value = "/fake/root"

        mock_cache = MagicMock()
        mock_cache_class.return_value = mock_cache

        parser = _build_parser()
        args = parser.parse_args(["--query", "test", "--clear-cache"])

        from tree_sitter_analyzer.cli.commands.semantic_search_cli import _run

        exit_code = await _run(args)

        assert exit_code == 0
        mock_cache.clear.assert_called_once()
