#!/usr/bin/env python3
"""
Info Commands - CLI Commands for Information Display

This module provides CLI commands for displaying information
about the analysis engine, supported languages, and version.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (lazy loading, caching)
- Detailed documentation

Features:
- Info command for general information
- Version command for displaying version
- Help command for displaying help
- Type-safe operations (PEP 484)
- Command pattern implementation

Architecture:
- Command pattern implementation
- Layered design with clear separation of concerns
- Performance optimization with lazy loading
- Type-safe operations (PEP 484)
- Integration with analysis engine

Usage:
    >>> from tree_sitter_analyzer.cli.commands import InfoCommand, VersionCommand
    >>> registry = get_command_registry()
    >>> registry.execute("info", args)
    >>> registry.execute("version", args)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import logging
import sys
from functools import lru_cache
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
)

# Type checking setup
if TYPE_CHECKING:
    # Core imports
    # Utility imports
    from ...utils.logging import (
        log_debug,
        log_error,
    )
    from ..core.analysis_engine import AnalysisEngine, AnalysisRequest, AnalysisResult
    from ..core.cache_service import CacheConfig, CacheService
    from ..core.parser import Parser
    from ..core.query import QueryExecutor, QueryResult
    from ..language_detector import LanguageDetector, LanguageInfo
    from ..plugins.manager import PluginInfo, PluginManager
    from ..plugins.programming_language_extractor import ProgrammingLanguageExtractor

    # CLI imports
    from .base import Command, CommandMetadata, CommandResult, ExecutionContext
else:
    # Runtime imports (when type checking is disabled)
    # Core imports
    AnalysisEngine = Any
    AnalysisRequest = Any
    AnalysisResult = Any
    Parser = Any
    QueryExecutor = Any
    QueryResult = Any
    CacheService = Any
    CacheConfig = Any
    LanguageDetector = Any
    LanguageInfo = Any
    PluginManager = Any
    PluginInfo = Any
    ProgrammingLanguageExtractor = Any

    # CLI imports
    Command = Any
    CommandResult = Any
    ExecutionContext = Any
    CommandMetadata = Any

    # Utility imports
    from ...utils.logging import (
        log_debug,
        log_error,
    )

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =====
# Type Definitions
# =====


class InfoCommandProtocol(Protocol):
    """Interface for info command creation functions."""

    def __call__(self, project_root: str) -> "InfoCommand":
        """
        Create info command instance.

        Args:
            project_root: Root directory of the project

        Returns:
            InfoCommand instance
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================


class InfoCommandError(Exception):
    """Base exception for info command errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(InfoCommandError):
    """Exception raised when info command initialization fails."""

    pass


class ExecutionError(InfoCommandError):
    """Exception raised when command execution fails."""

    pass


class ValidationError(InfoCommandError):
    """Exception raised when command validation fails."""

    pass


# ============================================================================
# Info Command
# ============================================================================


class InfoCommand(Command):
    """
    Info command for displaying analysis engine information.

    Features:
    - Display supported languages
    - Display plugin information
    - Display performance statistics
    - Display cache statistics
    - Type-safe operations (PEP 484)

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Performance optimization with lazy loading
    - Type-safe operations (PEP 484)
    - Integration with analysis engine and components

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import InfoCommand
        >>> cmd = InfoCommand()
        >>> result = cmd.execute(context)
        >>> print(result.message)
    """

    def __init__(self) -> None:
        """
        Initialize info command.

        Note:
            - Inherits from Command base class
            - Provides metadata for command registration
        """
        super().__init__(
            name="info",
            description="Display information about the analysis engine and supported features",
            category="information",
        )

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute info command.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Displays general information
            - Displays supported languages
            - Displays plugin information
            - Displays performance statistics
            - Handles errors gracefully
        """
        start_time = perf_counter()

        try:
            # Get engine from context
            engine = context.engine

            # Display general information
            info_lines = []
            info_lines.append("=== Tree-sitter Analyzer Information ===")
            info_lines.append("")

            # Display supported languages
            info_lines.append("Supported Languages:")
            if engine:
                languages = engine.get_supported_languages()
                for language in languages:
                    info_lines.append(f"  - {language}")
            else:
                info_lines.append("  (Engine not initialized)")

            info_lines.append("")

            # Display plugin information
            info_lines.append("Plugin Information:")
            if engine:
                plugin_manager = engine.plugin_manager
                plugins = plugin_manager.get_all_plugins()
                for plugin_name in plugins.keys():
                    info_lines.append(f"  - {plugin_name}")
            else:
                info_lines.append("  (Engine not initialized)")

            info_lines.append("")

            # Display performance statistics
            info_lines.append("Performance Statistics:")
            if engine:
                stats = engine.get_cache_stats()
                info_lines.append(f"  Cache Size: {stats.get('size', 0)}")
                info_lines.append(f"  Cache Hits: {stats.get('hits', 0)}")
                info_lines.append(f"  Cache Misses: {stats.get('misses', 0)}")
                info_lines.append(f"  Hit Rate: {stats.get('hit_rate', 0.0):.2%}")
            else:
                info_lines.append("  (Engine not initialized)")

            info_lines.append("")
            info_lines.append("=== End ===")

            message = "\n".join(info_lines)

            end_time = perf_counter()
            execution_time = end_time - start_time

            log_debug(f"Info command executed in {execution_time:.3f}s")

            return CommandResult(
                command_name=self._name,
                success=True,
                message=message,
                execution_time=execution_time,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Info command execution failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Info command failed: {str(e)}",
                execution_time=execution_time,
            )


# ============================================================================
# Version Command
# ============================================================================


class VersionCommand(Command):
    """
    Version command for displaying version information.

    Features:
    - Display version information
    - Display build information
    - Display dependency information
    - Type-safe operations (PEP 484)

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Type-safe operations (PEP 484)

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import VersionCommand
        >>> cmd = VersionCommand()
        >>> result = cmd.execute(context)
        >>> print(result.message)
    """

    VERSION = "1.10.5"
    BUILD_DATE = "2026-01-28"
    PYTHON_VERSION = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    def __init__(self):  # type: ignore
        """
        Initialize version command.

        Note:
            - Inherits from Command base class
            - Provides metadata for command registration
        """
        super().__init__(
            name="version",
            description="Display version and build information",
            category="information",
        )

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute version command.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Displays version information
            - Displays build information
            - Displays Python version
            - Displays dependency information
            - Handles errors gracefully
        """
        start_time = perf_counter()

        try:
            # Build version information lines
            version_lines = []
            version_lines.append("=== Version Information ===")
            version_lines.append("")
            version_lines.append(f"Version: {self.VERSION}")
            version_lines.append(f"Build Date: {self.BUILD_DATE}")
            version_lines.append(f"Python Version: {self.PYTHON_VERSION}")
            version_lines.append("")

            # Display dependency information
            version_lines.append("Dependencies:")
            version_lines.append("  - tree-sitter: (bundled)")
            version_lines.append("  - tree-sitter-languages: (bundled)")
            version_lines.append("")

            version_lines.append("=== End ===")

            message = "\n".join(version_lines)

            end_time = perf_counter()
            execution_time = end_time - start_time

            log_debug(f"Version command executed in {execution_time:.3f}s")

            return CommandResult(
                command_name=self._name,
                success=True,
                message=message,
                execution_time=execution_time,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Version command execution failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Version command failed: {str(e)}",
                execution_time=execution_time,
            )


# ============================================================================
# Help Command
# ============================================================================


class HelpCommand(Command):
    """
    Help command for displaying help information.

    Features:
    - Display general help
    - Display command-specific help
    - Display usage examples
    - Type-safe operations (PEP 484)

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Type-safe operations (PEP 484)
    - Integration with command registry

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import HelpCommand
        >>> cmd = HelpCommand()
        >>> result = cmd.execute(context)
        >>> print(result.message)
    """

    def __init__(self):  # type: ignore
        """
        Initialize help command.

        Note:
            - Inherits from Command base class
            - Provides metadata for command registration
        """
        super().__init__(
            name="help",
            description="Display help information for commands",
            category="information",
        )

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute help command.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Displays general help
            - Displays command-specific help
            - Displays usage examples
            - Handles errors gracefully
        """
        start_time = perf_counter()

        try:
            # Get command registry
            command_registry = context.config.get("command_registry")

            # Build help lines
            help_lines = []
            help_lines.append("=== Help Information ===")
            help_lines.append("")
            help_lines.append("Usage: tree-sitter-analyzer <command> [options]")
            help_lines.append("")
            help_lines.append("Available Commands:")

            if command_registry:
                commands = command_registry.get_all_commands()
                for cmd_name, command in commands.items():
                    help_lines.append(f"  {cmd_name} - {command.description}")
            else:
                help_lines.append("  (Command registry not available)")

            help_lines.append("")
            help_lines.append("Options:")
            help_lines.append("  --help, -h        Display this help message")
            help_lines.append("  --version, -v    Display version information")
            help_lines.append("  --verbose         Enable verbose output")
            help_lines.append("")
            help_lines.append("For more information on a specific command, use:")
            help_lines.append("  tree-sitter-analyzer <command> --help")

            help_lines.append("")
            help_lines.append("=== End ===")

            message = "\n".join(help_lines)

            end_time = perf_counter()
            execution_time = end_time - start_time

            log_debug(f"Help command executed in {execution_time:.3f}s")

            return CommandResult(
                command_name=self._name,
                success=True,
                message=message,
                execution_time=execution_time,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Help command execution failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Help command failed: {str(e)}",
                execution_time=execution_time,
            )


# ============================================================================
# Convenience Functions with LRU Caching
# ============================================================================


@lru_cache(maxsize=64, typed=True)
def get_info_command() -> InfoCommand:
    """
    Get info command instance with LRU caching.

    Returns:
        InfoCommand instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return InfoCommand()


@lru_cache(maxsize=64, typed=True)
def get_version_command() -> VersionCommand:
    """
    Get version command instance with LRU caching.

    Returns:
        VersionCommand instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return VersionCommand()


@lru_cache(maxsize=64, typed=True)
def get_help_command() -> HelpCommand:
    """
    Get help command instance with LRU caching.

    Returns:
        HelpCommand instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return HelpCommand()


# ============================================================================
# Module-level exports
# ============================================================================

__all__: list[str] = [
    # Main classes
    "InfoCommand",
    "VersionCommand",
    "HelpCommand",
    # Convenience functions
    "get_info_command",
    "get_version_command",
    "get_help_command",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If requested component is not found
    """
    # Handle specific imports
    if name == "InfoCommand":
        return InfoCommand
    elif name == "VersionCommand":
        return VersionCommand
    elif name == "HelpCommand":
        return HelpCommand
    elif name == "get_info_command":
        return get_info_command
    elif name == "get_version_command":
        return get_version_command
    elif name == "get_help_command":
        return get_help_command
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found") from None
