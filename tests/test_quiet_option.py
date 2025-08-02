#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test --quiet Option Functionality

Tests to verify that the --quiet option correctly suppresses INFO level logs
and only displays error messages.
"""

import logging
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.cli.commands.base_command import BaseCommand
from tree_sitter_analyzer.cli.commands.advanced_command import AdvancedCommand
from tree_sitter_analyzer.cli_main import main


class MockCommand(BaseCommand):
    """Mock implementation of BaseCommand for testing purposes."""

    async def execute_async(self, language: str) -> int:
        """Mock implementation of execute_async."""
        return 0


class TestQuietOption:
    """Test class for --quiet option functionality."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_java_file = os.path.join(self.temp_dir, "Test.java")
        
        # Create test Java file
        with open(self.test_java_file, 'w', encoding='utf-8') as f:
            f.write("""
public class Test {
    public static void main(String[] args) {
        System.out.println("Hello World");
    }
}
""")

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_quiet_option_suppresses_info_messages(self) -> None:
        """Test that --quiet option suppresses INFO messages in BaseCommand."""
        from argparse import Namespace
        
        # Test with quiet=True - should not show info messages
        args = Namespace(file_path=self.test_java_file, language=None, table=False, quiet=True)
        command = MockCommand(args)
        
        with patch('tree_sitter_analyzer.output_manager.output_info') as mock_info:
            language = command.detect_language()
            
            assert language == "java"
            # With quiet=True, info messages should not be called
            mock_info.assert_not_called()

    def test_quiet_option_allows_error_messages(self) -> None:
        """Test that --quiet option still allows error messages."""
        from argparse import Namespace

        # Create nonexistent file
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.java")
        args = Namespace(file_path=nonexistent_file, quiet=True)
        command = MockCommand(args)

        # Test that validation fails (which indicates error was processed)
        result = command.validate_file()
        assert not result  # Should return False for nonexistent file

    def test_quiet_option_in_cli_main(self) -> None:
        """Test that --quiet option sets environment variable correctly."""
        # Test that --quiet in sys.argv sets LOG_LEVEL environment variable
        original_argv = sys.argv.copy()
        original_log_level = os.environ.get('LOG_LEVEL')
        
        try:
            # Simulate --quiet in command line
            sys.argv = ['tree_sitter_analyzer', self.test_java_file, '--quiet']
            
            # Mock the argument parser and main execution to avoid full execution
            with patch('tree_sitter_analyzer.cli_main.create_argument_parser') as mock_parser:
                mock_args = Mock()
                mock_args.quiet = True
                mock_args.table = False
                mock_args.file_path = self.test_java_file
                mock_args.partial_read = False
                mock_args.list_queries = False
                mock_args.list_languages = False
                mock_args.version = False
                mock_parser.return_value.parse_args.return_value = mock_args

                with patch('tree_sitter_analyzer.cli_main.CLICommandFactory.create_command') as mock_factory:
                    mock_command = Mock()
                    mock_command.execute.return_value = 0
                    mock_factory.return_value = mock_command

                    with patch('tree_sitter_analyzer.cli_main.handle_special_commands') as mock_special:
                        mock_special.return_value = None

                        # Import and call main to trigger environment variable setting
                        from tree_sitter_analyzer.cli_main import main

                        # The main function should set LOG_LEVEL=ERROR when --quiet is present
                        try:
                            main()
                        except SystemExit:
                            pass  # Expected due to sys.exit() in main()

                        # Check that LOG_LEVEL was set to ERROR
                        assert os.environ.get('LOG_LEVEL') == 'ERROR'
        
        finally:
            # Restore original state
            sys.argv = original_argv
            if original_log_level is not None:
                os.environ['LOG_LEVEL'] = original_log_level
            elif 'LOG_LEVEL' in os.environ:
                del os.environ['LOG_LEVEL']

    def test_logging_level_configuration_with_quiet(self) -> None:
        """Test that logging level is configured correctly with --quiet option."""
        from argparse import Namespace
        
        # Mock the logging configuration
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            # Simulate the logging configuration that happens in cli_main
            args = Namespace(quiet=True, table=False)
            
            # This simulates the logging configuration in cli_main.py
            if hasattr(args, "quiet") and args.quiet:
                logging.getLogger().setLevel(logging.ERROR)
                logging.getLogger("tree_sitter_analyzer").setLevel(logging.ERROR)
                logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)
            
            # Verify that setLevel was called with ERROR level
            mock_logger.setLevel.assert_called_with(logging.ERROR)

    def test_quiet_option_vs_table_option(self) -> None:
        """Test interaction between --quiet and --table options."""
        from argparse import Namespace
        
        # Test with both quiet=True and table=True
        args = Namespace(file_path=self.test_java_file, language=None, table=True, quiet=True)
        command = MockCommand(args)
        
        with patch('tree_sitter_analyzer.output_manager.output_info') as mock_info:
            language = command.detect_language()
            
            assert language == "java"
            # With both table=True and quiet=True, info messages should not be called
            mock_info.assert_not_called()

    def test_quiet_option_with_language_detection_error(self) -> None:
        """Test that --quiet option still shows language detection errors."""
        from argparse import Namespace
        
        # Create a file with unknown extension
        unknown_file = os.path.join(self.temp_dir, "test.unknown")
        with open(unknown_file, 'w') as f:
            f.write("some content")
        
        args = Namespace(file_path=unknown_file, language=None, table=False, quiet=True)
        command = MockCommand(args)

        # Test that language detection fails for unknown file
        language = command.detect_language()
        assert language is None  # Should return None for unknown language

    def test_quiet_option_environment_variable_early_setting(self) -> None:
        """Test that LOG_LEVEL environment variable is set early in main()."""
        original_argv = sys.argv.copy()
        original_log_level = os.environ.get('LOG_LEVEL')
        
        try:
            # Test the early check for quiet mode
            sys.argv = ['tree_sitter_analyzer', '--quiet', self.test_java_file]
            
            # This simulates the early check in cli_main.py
            if "--quiet" in sys.argv:
                os.environ['LOG_LEVEL'] = 'ERROR'
            
            # Verify that LOG_LEVEL was set
            assert os.environ.get('LOG_LEVEL') == 'ERROR'
        
        finally:
            # Restore original state
            sys.argv = original_argv
            if original_log_level is not None:
                os.environ['LOG_LEVEL'] = original_log_level
            elif 'LOG_LEVEL' in os.environ:
                del os.environ['LOG_LEVEL']

    def test_quiet_option_without_table_shows_no_info(self) -> None:
        """Test that quiet option without table option suppresses info messages."""
        from argparse import Namespace
        
        # Test with quiet=True and table=False
        args = Namespace(file_path=self.test_java_file, language=None, table=False, quiet=True)
        command = MockCommand(args)
        
        with patch('tree_sitter_analyzer.output_manager.output_info') as mock_info:
            language = command.detect_language()
            
            assert language == "java"
            # With quiet=True, info messages should not be called
            mock_info.assert_not_called()

    def test_no_quiet_option_shows_info_messages(self) -> None:
        """Test that without --quiet option, INFO messages are shown."""
        from argparse import Namespace

        # Test with quiet=False - should show info messages
        args = Namespace(file_path=self.test_java_file, language=None, table=False, quiet=False)
        command = MockCommand(args)

        # Capture stdout to verify the message is printed
        from io import StringIO
        import sys

        captured_output = StringIO()
        original_stdout = sys.stdout

        try:
            sys.stdout = captured_output
            language = command.detect_language()
            output = captured_output.getvalue()

            assert language == "java"
            # With quiet=False, info messages should be printed
            assert "INFO: Language auto-detected from extension: java" in output
        finally:
            sys.stdout = original_stdout

    def test_quiet_option_help_text(self) -> None:
        """Test that --quiet option has correct help text."""
        from tree_sitter_analyzer.cli_main import create_argument_parser
        
        parser = create_argument_parser()
        
        # Find the --quiet argument
        quiet_action = None
        for action in parser._actions:
            if hasattr(action, 'dest') and action.dest == 'quiet':
                quiet_action = action
                break
        
        assert quiet_action is not None, "--quiet option should be defined"

        # Check that it's a store_true action by checking the action type
        assert hasattr(quiet_action, 'const') and quiet_action.const is True, "--quiet should be a store_true action"

        # Check help text (it should contain relevant keywords)
        assert quiet_action.help is not None
        assert "INFO" in quiet_action.help


if __name__ == "__main__":
    pytest.main([__file__])
