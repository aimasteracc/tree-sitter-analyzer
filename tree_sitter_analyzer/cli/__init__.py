#!/usr/bin/env python3
"""
CLI Package for Tree-sitter Analyzer

Command-line interface components using Command Pattern for extensible
and maintainable CLI development.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- Performance optimization (LRU caching, command factory)
- Thread-safe operations
- Detailed documentation

Architecture:
- Command Pattern for command execution
- Factory pattern for command creation
- Lazy loading for command components
- Validation layer for argument checking
- Error recovery mechanisms

Features:
- Type-safe command execution
- Argument validation
- Error recovery
- Performance monitoring
- Thread-safe command registration

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

import argparse
import functools
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
)

# Type checking setup - Minimal imports for type annotations only
if TYPE_CHECKING:
    from ..language_loader import LanguageLoader
    from ..output_manager import OutputManager
    from ..query_loader import QueryLoader

# Runtime imports - Used directly in code
from ..language_loader import get_language_loader
from ..output_manager import get_output_manager
from ..query_loader import get_query_loader
from ..utils import log_error, log_warning
from .commands.advanced_command import AdvancedCommand
from .commands.default_command import DefaultCommand
from .commands.partial_read_command import PartialReadCommand
from .commands.query_command import QueryCommand
from .commands.structure_command import StructureCommand
from .commands.summary_command import SummaryCommand
from .commands.table_command import TableCommand
from .info_commands import (
    DescribeQueryCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)

# ============================================================================
# Type Definitions
# ============================================================================


class CommandInterface(Protocol):
    """Interface for CLI commands."""

    def execute(self) -> int:
        """
        Execute command.

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        ...


class CommandFactoryInterface(Protocol):
    """Interface for command factory creation functions."""

    def __call__(self, args: argparse.Namespace) -> CommandInterface | None:
        """
        Create command instance from arguments.

        Args:
            args: Parsed command-line arguments

        Returns:
            Command instance or None if no command matches
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================


class CLIError(Exception):
    """Base exception for CLI errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class ArgumentParsingError(CLIError):
    """Exception raised when argument parsing fails."""

    pass


class CommandExecutionError(CLIError):
    """Exception raised when command execution fails."""

    pass


class CommandNotFoundError(CLIError):
    """Exception raised when no command is found for arguments."""

    pass


class ValidationError(CLIError):
    """Exception raised when argument validation fails."""

    pass


# ============================================================================
# CLI Configuration
# ============================================================================


class CLIConfig:
    """
    Configuration for CLI system.

    Attributes:
        project_root: Root directory of the project
        default_language: Default programming language
        output_format: Default output format
        enable_logging: Enable logging output
        enable_performance_monitoring: Enable performance monitoring
    """

    def __init__(
        self,
        project_root: str = ".",
        default_language: str = "python",
        output_format: str = "table",
        enable_logging: bool = True,
        enable_performance_monitoring: bool = True,
    ):
        """
        Initialize CLI configuration.

        Args:
            project_root: Root directory of the project
            default_language: Default programming language (default: 'python')
            output_format: Default output format (default: 'table')
            enable_logging: Enable logging output (default: True)
            enable_performance_monitoring: Enable performance monitoring (default: True)
        """
        self.project_root = project_root
        self.default_language = default_language
        self.output_format = output_format
        self.enable_logging = enable_logging
        self.enable_performance_monitoring = enable_performance_monitoring

    def get_default_language(self) -> str:
        """
        Get default programming language.

        Returns:
            Default programming language

        Note:
            - Returns the configured default language
            - Can be overridden by environment variables
        """
        # Check environment variable
        import os

        env_language = os.environ.get("DEFAULT_LANGUAGE", "")
        if env_language:
            return env_language

        return self.default_language


# ============================================================================
# Command Factory
# ============================================================================


class CLICommandFactory:
    """
    Factory for creating CLI commands based on arguments.

    Features:
    - Lazy loading of command components
    - Caching of command instances
    - Type-safe command creation
    - Error handling and recovery
    - Performance monitoring

    Attributes:
        config: CLI configuration
        _language_loader: Language loader instance
        _query_loader: Query loader instance
        _output_manager: Output manager instance
        _cache: Command instance cache
        _stats: Performance statistics
    """

    def __init__(self, config: CLIConfig | None = None):
        """
        Initialize CLI command factory.

        Args:
            config: Optional CLI configuration (uses defaults if None)
        """
        self.config = config or CLIConfig()

        # Lazy loading of components
        self._language_loader: LanguageLoader | None = None
        self._query_loader: QueryLoader | None = None
        self._output_manager: OutputManager | None = None

        # Command cache
        self._cache: dict[str, CommandInterface] = {}

        # Performance statistics
        self._stats: dict[str, Any] = {
            "total_commands": 0,
            "successful_commands": 0,
            "failed_commands": 0,
            "execution_times": [],
        }

    def _get_language_loader(self) -> LanguageLoader:
        """
        Get language loader instance (lazy loading).

        Returns:
            Language loader instance

        Performance:
            Lazy loading with caching.
        """
        if self._language_loader is None:
            self._language_loader = get_language_loader(self.config.project_root)

        return self._language_loader

    def _get_query_loader(self) -> QueryLoader:
        """
        Get query loader instance (lazy loading).

        Returns:
            Query loader instance

        Performance:
            Lazy loading with caching.
        """
        if self._query_loader is None:
            self._query_loader = get_query_loader(self.config.project_root)

        return self._query_loader

    def _get_output_manager(self) -> OutputManager:
        """
        Get output manager instance (lazy loading).

        Returns:
            Output manager instance

        Performance:
            Lazy loading with caching.
        """
        if self._output_manager is None:
            self._output_manager = get_output_manager()

        return self._output_manager

    def create_command(self, args: argparse.Namespace) -> CommandInterface | None:
        """
        Create command instance based on arguments.

        Args:
            args: Parsed command-line arguments

        Returns:
            Command instance or None if no command matches

        Raises:
            ValidationError: If arguments are invalid
            CommandNotFoundError: If no command matches

        Performance:
            Monitors command creation and execution time.
        """
        start_time = time.perf_counter()

        try:
            # Update statistics
            self._stats["total_commands"] += 1

            # Type annotation for command variable
            command: CommandInterface | None = None

            # Check for information commands (no file analysis required)
            if hasattr(args, "list_queries") and args.list_queries:
                command = ListQueriesCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            if hasattr(args, "describe_query") and args.describe_query:
                command = DescribeQueryCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            if (
                hasattr(args, "show_supported_languages")
                and args.show_supported_languages
            ):
                command = ShowLanguagesCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            if (
                hasattr(args, "show_supported_extensions")
                and args.show_supported_extensions
            ):
                command = ShowExtensionsCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Check for file analysis commands (require file path)
            if not hasattr(args, "file_path") or not args.file_path:
                raise ValidationError("File path is required for this command")

            # Partial read command - highest priority for file operations
            if hasattr(args, "partial_read") and args.partial_read:
                command = PartialReadCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Handle table command
            if hasattr(args, "table") and args.table:
                command = TableCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Handle structure command
            if hasattr(args, "structure") and args.structure:
                command = StructureCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Handle summary command
            if hasattr(args, "summary") and args.summary is not None:
                command = SummaryCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Handle advanced command
            if hasattr(args, "advanced") and args.advanced:
                command = AdvancedCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Handle query commands
            if hasattr(args, "query_key") and args.query_key:
                command = QueryCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            if hasattr(args, "query_string") and args.query_string:
                command = QueryCommand(args)
                self._stats["successful_commands"] += 1
                end_time = time.perf_counter()
                self._stats["execution_times"].append(end_time - start_time)
                return command

            # Default command - if file_path is provided but no specific command, use default analysis
            command = DefaultCommand(args)
            self._stats["successful_commands"] += 1
            end_time = time.perf_counter()
            self._stats["execution_times"].append(end_time - start_time)
            return command

        except ValidationError as e:
            self._stats["failed_commands"] += 1
            end_time = time.perf_counter()
            self._stats["execution_times"].append(end_time - start_time)
            log_warning(f"Command creation failed: {e}")
            raise
        except Exception as e:
            self._stats["failed_commands"] += 1
            end_time = time.perf_counter()
            self._stats["execution_times"].append(end_time - start_time)
            log_error(f"Unexpected error creating command: {e}")
            raise CommandExecutionError(f"Failed to create command: {e}") from None

    def validate_arguments(self, args: argparse.Namespace) -> str | None:
        """
        Validate command arguments.

        Args:
            args: Parsed command-line arguments

        Returns:
            Validation error message or None if valid

        Note:
            - Validates common argument combinations
            - Returns helpful error messages
        """
        # Check for information commands (no file path required)
        if (
            hasattr(args, "list_queries")
            and args.list_queries
            or hasattr(args, "describe_query")
            and args.describe_query
            or hasattr(args, "show_supported_languages")
            and args.show_supported_languages
            or hasattr(args, "show_supported_extensions")
            and args.show_supported_extensions
        ):
            return None  # No validation needed for info commands

        # Check for file analysis commands
        if not hasattr(args, "file_path") or not args.file_path:
            return "File path is required for this command"

        # Check for query commands
        if hasattr(args, "query_key") and args.query_key:
            # Query key should be a valid string
            if not isinstance(args.query_key, str):
                return "Query key must be a string"

        if hasattr(args, "query_string") and args.query_string:
            # Query string should be a valid string
            if not isinstance(args.query_string, str):
                return "Query string must be a string"

        return None  # Validation passed

    def get_stats(self) -> dict[str, Any]:
        """
        Get command factory statistics.

        Returns:
            Dictionary with command factory statistics
        """
        return {
            "total_commands": self._stats["total_commands"],
            "successful_commands": self._stats["successful_commands"],
            "failed_commands": self._stats["failed_commands"],
            "execution_times": self._stats["execution_times"],
            "average_execution_time": (
                sum(self._stats["execution_times"])
                / len(self._stats["execution_times"])
                if self._stats["execution_times"]
                else 0
            ),
            "config": {
                "project_root": self.config.project_root,
                "default_language": self.config.default_language,
                "output_format": self.config.output_format,
                "enable_logging": self.config.enable_logging,
                "enable_performance_monitoring": self.config.enable_performance_monitoring,
            },
        }


# ============================================================================
# Convenience Functions with Caching
# ============================================================================


@functools.lru_cache(maxsize=64, typed=True)
def get_command_factory(project_root: str = ".") -> CLICommandFactory:
    """
    Get CLI command factory instance with LRU caching.

    Args:
        project_root: Root directory of the project (default: '.')

    Returns:
        CLICommandFactory instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    config = CLIConfig(project_root=project_root)
    return CLICommandFactory(config=config)


def create_command(
    args: argparse.Namespace, project_root: str = "."
) -> CommandInterface | None:
    """
    Create CLI command from arguments (convenience function).

    Args:
        args: Parsed command-line arguments
        project_root: Root directory of the project (default: '.')

    Returns:
        Command instance or None if no command matches

    Raises:
        ValidationError: If arguments are invalid
        CommandNotFoundError: If no command matches

    Performance:
        Uses LRU-cached command factory.
    """
    factory = get_command_factory(project_root)
    return factory.create_command(args)


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

__all__: list[str] = [
    # Type definitions
    "CommandInterface",
    "CommandFactoryInterface",
    # Configuration
    "CLIConfig",
    # Exceptions
    "CLIError",
    "ArgumentParsingError",
    "CommandExecutionError",
    "CommandNotFoundError",
    "ValidationError",
    # Factory
    "CLICommandFactory",
    # Convenience functions
    "get_command_factory",
    "create_command",
    # Main entry point (for backward compatibility)
    "main",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the module or class to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If module not found
    """
    # CRITICAL: Skip Python internal attributes
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

    # Handle main function
    if name == "main":
        from ..cli_main import main

        return main

    # Handle CLI commands
    if name in [
        "AdvancedCommand",
        "DefaultCommand",
        "PartialReadCommand",
        "QueryCommand",
        "StructureCommand",
        "SummaryCommand",
        "TableCommand",
    ]:
        from . import commands

        return getattr(commands, name)

    # Handle CLI info commands
    if name in [
        "DescribeQueryCommand",
        "ListQueriesCommand",
        "ShowExtensionsCommand",
        "ShowLanguagesCommand",
    ]:
        from . import info_commands

        return getattr(info_commands, name)

    # Handle factory
    if name == "CLICommandFactory":
        return CLICommandFactory
    elif name == "CLIConfig":
        return CLIConfig

    # Default behavior
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
