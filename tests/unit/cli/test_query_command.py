#!/usr/bin/env python3
"""
Tests for QueryCommand
"""

from argparse import Namespace
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.query_command import QueryCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        query_key=None,
        query_string=None,
        advanced=False,
        table=None,
        structure=False,
        summary=False,
        output_format="text",
        toon_use_tabs=False,
        statistics=False,
        output_file=None,
        suppress_output=False,
        format_type="full",
        language=None,
        include_details=True,
        include_complexity=True,
        include_guidance=False,
        metrics_only=False,
        output_format_param="json",
        format_type_param="full",
        language_param=None,
        filter_expression=None,
        filter=None,
        result_format="json",
        query_key_param=None,
        query_string_param=None,
    )


@pytest.fixture
def command(mock_args):
    """Create QueryCommand instance for testing."""
    return QueryCommand(mock_args)


class TestQueryCommandInit:
    """Tests for QueryCommand initialization."""

    def test_init(self, command):
        """Test QueryCommand initialization."""
        assert command is not None
        assert isinstance(command, QueryCommand)
        assert hasattr(command, "args")
        assert hasattr(command, "query_service")

    def test_init_with_args(self, mock_args):
        """Test QueryCommand initialization with args."""
        command = QueryCommand(mock_args)
        assert command.args == mock_args
        assert command.query_service is not None


class TestQueryCommandExecuteQuery:
    """Tests for QueryCommand.execute_query method."""

    @pytest.mark.asyncio
    async def test_execute_query_with_query_key(self, command):
        """Test execute_query with predefined query key."""
        with patch.object(
            command.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [{"name": "test"}]
            results = await command.execute_query("python", "test_query", "methods")
            assert results is not None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_with_custom_query(self, command):
        """Test execute_query with custom query string."""
        with patch.object(
            command.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [{"name": "test"}]
            results = await command.execute_query("python", "(function)", "custom")
            assert results is not None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_with_filter(self, command):
        """Test execute_query with filter expression."""
        with patch.object(
            command.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [{"name": "test"}]
            command.args.filter = "name=main"
            results = await command.execute_query("python", "test_query", "methods")
            assert results is not None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_failure(self, command):
        """Test execute_query handles exceptions."""
        with patch.object(
            command.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.side_effect = Exception("Test error")
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_error"
            ) as mock_error:
                results = await command.execute_query("python", "test_query", "methods")
                assert results is None
                mock_error.assert_called_once()


class TestQueryCommandExecuteAsync:
    """Tests for QueryCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_with_query_key(self, command):
        """Test execute_async with query_key parameter."""
        command.args.query_key = "methods"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [
                {
                    "capture_name": "test",
                    "node_type": "function",
                    "start_line": 1,
                    "end_line": 5,
                    "content": "def test(): pass",
                }
            ]
            with patch("tree_sitter_analyzer.cli.commands.query_command.output_data"):
                result = await command.execute_async("python")
                assert result == 0
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_with_query_string(self, command):
        """Test execute_async with query_string parameter."""
        command.args.query_string = "(function)"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [
                {
                    "capture_name": "test",
                    "node_type": "function",
                    "start_line": 1,
                    "end_line": 5,
                    "content": "def test(): pass",
                }
            ]
            with patch("tree_sitter_analyzer.cli.commands.query_command.output_data"):
                result = await command.execute_async("python")
                assert result == 0
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_no_query(self, command):
        """Test execute_async with no query specified."""
        with patch(
            "tree_sitter_analyzer.cli.commands.query_command.output_error"
        ) as mock_error:
            result = await command.execute_async("python")
            assert result == 1
            mock_error.assert_called_once_with("No query specified.")

    @pytest.mark.asyncio
    async def test_execute_async_invalid_query_key(self, command):
        """Test execute_async with invalid query key."""
        command.args.query_key = "invalid_query"
        with patch.object(
            command.query_service, "get_available_queries"
        ) as mock_available:
            mock_available.return_value = ["methods", "classes"]
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_error"
            ) as mock_error:
                result = await command.execute_async("python")
                assert result == 1
                mock_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_unsafe_query_string(self, command):
        """Test execute_async with unsafe query string."""
        command.args.query_string = "(.*)(.*)(.*)(.*)(.*)(.*)"
        with patch.object(
            command.security_validator.regex_checker, "validate_pattern"
        ) as mock_validate:
            mock_validate.return_value = (False, "Catastrophic backtracking detected")
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_error"
            ) as mock_error:
                result = await command.execute_async("python")
                assert result == 1
                mock_error.assert_called_once()


class TestQueryCommandOutput:
    """Tests for QueryCommand output."""

    @pytest.mark.asyncio
    async def test_execute_async_outputs_json(self, command):
        """Test execute_async outputs JSON format."""
        command.args.query_key = "methods"
        command.args.output_format = "json"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [{"name": "test"}]
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_json"
            ) as mock_json:
                result = await command.execute_async("python")
                assert result == 0
                mock_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_outputs_toon(self, command):
        """Test execute_async outputs TOON format."""
        command.args.query_key = "methods"
        command.args.output_format = "toon"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [{"name": "test"}]
            with patch("builtins.print") as mock_print:
                result = await command.execute_async("python")
                assert result == 0
                mock_print.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_outputs_text(self, command):
        """Test execute_async outputs text format."""
        command.args.query_key = "methods"
        command.args.output_format = "text"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [
                {
                    "capture_name": "test",
                    "node_type": "function",
                    "start_line": 1,
                    "end_line": 5,
                    "content": "def test(): pass",
                }
            ]
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_data"
            ) as mock_data:
                result = await command.execute_async("python")
                assert result == 0
                assert mock_data.call_count > 0

    @pytest.mark.asyncio
    async def test_execute_async_no_results(self, command):
        """Test execute_async with no results."""
        command.args.query_key = "methods"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = []
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_info"
            ) as mock_info:
                result = await command.execute_async("python")
                assert result == 0
                mock_info.assert_called_once()


class TestQueryCommandBehavior:
    """Tests for QueryCommand behavior."""

    @pytest.mark.asyncio
    async def test_execute_query_sanitizes_input(self, command):
        """Test execute_query sanitizes query key input."""
        command.args.query_key = "methods"
        with patch.object(
            command.security_validator, "sanitize_input"
        ) as mock_sanitize:
            mock_sanitize.return_value = "methods"
            with patch.object(
                command, "execute_query", new_callable=AsyncMock
            ) as mock_execute:
                mock_execute.return_value = [
                    {
                        "capture_name": "test",
                        "node_type": "function",
                        "start_line": 1,
                        "end_line": 5,
                        "content": "def test(): pass",
                    }
                ]
                with patch(
                    "tree_sitter_analyzer.cli.commands.query_command.output_data"
                ):
                    await command.execute_async("python")
                    mock_sanitize.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_query_failure_returns_1(self, command):
        """Test execute_async returns 1 when query fails."""
        command.args.query_key = "methods"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = None
            result = await command.execute_async("python")
            assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_multiple_results(self, command):
        """Test execute_async handles multiple results."""
        command.args.query_key = "methods"
        command.args.output_format = "text"
        with patch.object(
            command, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = [
                {
                    "capture_name": "test1",
                    "node_type": "function",
                    "start_line": 1,
                    "end_line": 5,
                    "content": "def test1(): pass",
                },
                {
                    "capture_name": "test2",
                    "node_type": "function",
                    "start_line": 6,
                    "end_line": 10,
                    "content": "def test2(): pass",
                },
            ]
            with patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_data"
            ) as mock_data:
                result = await command.execute_async("python")
                assert result == 0
                # Should output multiple results
                assert mock_data.call_count >= 6  # 3 lines per result
