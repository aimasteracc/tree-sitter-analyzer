#!/usr/bin/env python3
"""
Tests for TableCommand — core init, execute, toon format, package name.
"""

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.table_command import TableCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        query_key=None,
        query_string=None,
        advanced=False,
        table="full",
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
        include_javadoc=False,
    )


@pytest.fixture
def command(mock_args):
    """Create TableCommand instance for testing."""
    return TableCommand(mock_args)


class TestTableCommandInit:
    """Tests for TableCommand initialization."""

    def test_init(self, command):
        """Test TableCommand initialization."""
        assert command is not None
        assert isinstance(command, TableCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test TableCommand initialization with args."""
        command = TableCommand(mock_args)
        assert command.args == mock_args


class TestTableCommandExecuteAsync:
    """Tests for TableCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self, command):
        """Test execute_async returns 0 on success."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch.object(command, "_output_table"):
                result = await command.execute_async("python")
                assert result == 0
                mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_no_analysis_result(self, command):
        """Test execute_async returns 1 when no analysis result."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = None
            result = await command.execute_async("python")
            assert result == 1
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_exception(self, command):
        """Test execute_async handles exceptions."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.side_effect = Exception("Test error")
            with patch("tree_sitter_analyzer.cli.commands.table_command.output_error"):
                result = await command.execute_async("python")
                assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_full_format(self, command):
        """Test execute_async with full table type."""
        command.args.table = "full"
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch(
                "tree_sitter_analyzer.formatters.formatter_registry.FormatterRegistry"
            ) as mock_registry:
                mock_formatter = MagicMock()
                mock_formatter.format_structure.return_value = "table_output"
                mock_registry.get_formatter_for_language.return_value = mock_formatter
                with patch.object(command, "_output_table"):
                    result = await command.execute_async("python")
                    assert result == 0
                    mock_registry.get_formatter_for_language.assert_called_once()
