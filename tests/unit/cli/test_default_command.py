#!/usr/bin/env python3
"""
Tests for DefaultCommand
"""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.default_command import DefaultCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
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
        result_format="json",
        query_key_param=None,
        query_string_param=None,
    )


@pytest.fixture
def command(mock_args):
    """Create DefaultCommand instance for testing."""
    return DefaultCommand(mock_args)


class TestDefaultCommandInit:
    """Tests for DefaultCommand initialization."""

    def test_init(self, command):
        """Test DefaultCommand initialization."""
        assert command is not None
        assert isinstance(command, DefaultCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test DefaultCommand initialization with args."""
        command = DefaultCommand(mock_args)
        assert command.args == mock_args


class TestDefaultCommandExecuteAsync:
    """Tests for DefaultCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_returns_1(self, command):
        """Test execute_async returns error code 1."""
        result = await command.execute_async("python")
        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_with_language(self, command):
        """Test execute_async with language parameter."""
        result = await command.execute_async("java")
        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_with_none_language(self, command):
        """Test execute_async with None language."""
        result = await command.execute_async(None)
        assert result == 1


class TestDefaultCommandOutput:
    """Tests for DefaultCommand output."""

    @pytest.mark.asyncio
    async def test_execute_async_outputs_error_message(self, command):
        """Test execute_async outputs error message."""
        with patch(
            "tree_sitter_analyzer.cli.commands.default_command.output_error"
        ) as mock_error:
            await command.execute_async("python")
            mock_error.assert_called_once_with(
                "Please specify a query or --advanced option"
            )

    @pytest.mark.asyncio
    async def test_execute_async_outputs_usage_examples(self, command):
        """Test execute_async outputs usage examples."""
        with patch(
            "tree_sitter_analyzer.cli.commands.default_command.output_info"
        ) as mock_info:
            await command.execute_async("python")
            # Check that output_info was called multiple times
            assert mock_info.call_count > 0
            # Check that usage examples are included
            calls = [str(call) for call in mock_info.call_args_list]
            assert any("--query-key" in call for call in calls)
            assert any("--advanced" in call for call in calls)
            assert any("--table" in call for call in calls)

    @pytest.mark.asyncio
    async def test_execute_async_outputs_examples(self, command):
        """Test execute_async outputs example commands."""
        with patch(
            "tree_sitter_analyzer.cli.commands.default_command.output_info"
        ) as mock_info:
            await command.execute_async("python")
            calls = [str(call) for call in mock_info.call_args_list]
            # Check that example commands are included
            assert any("tree-sitter-analyzer" in call for call in calls)
            assert any("file.java" in call for call in calls)


class TestDefaultCommandBehavior:
    """Tests for DefaultCommand behavior."""

    @pytest.mark.asyncio
    async def test_execute_async_does_not_call_analyze_file(self, command):
        """Test execute_async does not call analyze_file."""
        with patch.object(
            command, "analyze_file", new_callable=MagicMock
        ) as mock_analyze:
            await command.execute_async("python")
            mock_analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_async_always_returns_error(self, command):
        """Test execute_async always returns error regardless of language."""
        languages = ["python", "java", "javascript", "typescript", "go", "rust"]
        for lang in languages:
            result = await command.execute_async(lang)
            assert result == 1, f"Expected 1 for language {lang}, got {result}"
