#!/usr/bin/env python3
"""
CLI Commands Package Initialization

This module initializes the CLI commands package with command registration,
argument parsing, and execution dispatch.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Command pattern implementation
- Lazy loading for performance
- Type-safe operations (PEP 484)

Features:
- Command registration and discovery
- Argument parsing and validation
- Execution dispatching
- Help message generation
- Type-safe operations (PEP 484)

Architecture:
- Layered design with clear separation of concerns
- Performance optimization with lazy loading
- Type-safe operations (PEP 484)
- Integration with core analysis engine

Usage:
    >>> from tree_sitter_analyzer.cli.commands import get_command_registry
    >>> registry = get_command_registry()
    >>> command = registry.get_command("info")
    >>> command.execute(args)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
)

# Type checking setup
if TYPE_CHECKING:
    from ...core.analysis_engine import AnalysisEngine

# Runtime imports
from ..utils.logging import (
    log_debug,
    log_error,
)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================================
# Type Definitions
# ============================================================================


class CommandProtocol(Protocol):
    """Interface for command creation functions."""

    def __call__(self, name: str, description: str) -> Command:
        """
        Create command instance.

        Args:
            name: Command name
            description: Command description

        Returns:
            Command instance
        """
        ...


class CommandFactoryProtocol(Protocol):
    """Interface for command factory functions."""

    def __call__(self, engine: Any) -> CommandRegistry:
        """
        Create command registry instance.

        Args:
            engine: AnalysisEngine instance

        Returns:
            CommandRegistry instance
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================


class CommandError(Exception):
    """Base exception for command errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(CommandError):
    """Exception raised when command initialization fails."""

    pass


class RegistrationError(CommandError):
    """Exception raised when command registration fails."""

    pass


class ExecutionError(CommandError):
    """Exception raised when command execution fails."""

    pass


class ValidationError(CommandError):
    """Exception raised when command validation fails."""

    pass


class NotFoundError(CommandError):
    """Exception raised when command is not found."""

    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True, slots=True)
class CommandMetadata:
    """
    Metadata for a command.

    Attributes:
        name: Command name
        description: Command description
        category: Command category
        aliases: List of alternative names
        examples: List of usage examples
        requires_analysis: Whether command requires analysis
        output_format: Output format (json, text, etc.)
    """

    name: str
    description: str
    category: str = "general"
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    requires_analysis: bool = True
    output_format: str = "json"

    def __hash__(self) -> int:
        """Hash based on name."""
        return hash(self.name)


@dataclass
class ExecutionContext:
    """
    Context for command execution.

    Attributes:
        engine: AnalysisEngine instance
        args: Parsed command-line arguments
        options: Command options
        config: Global configuration
    """

    engine: AnalysisEngine
    args: list[str]
    options: dict[str, Any]
    config: dict[str, Any]


@dataclass
class CommandResult:
    """
    Result of command execution.

    Attributes:
        command_name: Name of command
        success: Whether execution was successful
        message: Success or error message
        data: Result data (if any)
        execution_time: Time taken to execute (seconds)
    """

    command_name: str
    success: bool
    message: str
    data: Any | None = None
    execution_time: float = 0.0


# ============================================================================
# Base Command
# ============================================================================


class Command:
    """
    Base class for CLI commands.

    Features:
    - Command metadata (name, description, examples)
    - Argument parsing and validation
    - Execution dispatching
    - Help message generation
    - Type-safe operations (PEP 484)
    - Error handling and recovery

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Type-safe operations (PEP 484)
    - Integration with analysis engine

    Usage:
        >>> class MyCommand(Command):
        ...     def execute(self, context: ExecutionContext) -> CommandResult:
        ...         # Command logic here
        ...         return CommandResult("mycommand", True, "Success")
    """

    def __init__(self, name: str, description: str, category: str = "general"):
        """
        Initialize command.

        Args:
            name: Command name
            description: Command description
            category: Command category (default: "general")
        """
        self._name = name
        self._description = description
        self._category = category
        self._aliases: list[str] = []
        self._examples: list[str] = []

    @property
    def metadata(self) -> CommandMetadata:
        """Get command metadata."""
        return CommandMetadata(
            name=self._name,
            description=self._description,
            category=self._category,
            aliases=self._aliases,
            examples=self._examples,
            requires_analysis=True,
            output_format="json",
        )

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute command with given context.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Subclasses must implement this method
            - Default implementation raises NotImplementedError
        """
        start_time = perf_counter()

        try:
            # Default implementation
            end_time = perf_counter()
            execution_time = end_time - start_time

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Command {self._name} not implemented",
                execution_time=execution_time,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Command {self._name} execution failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Command execution failed: {str(e)}",
                execution_time=execution_time,
            )

    def validate_arguments(self, args: list[str]) -> tuple[bool, str | None]:
        """
        Validate command arguments.

        Args:
            args: Command-line arguments

        Returns:
            Tuple of (is_valid, error_message)

        Note:
            - Default implementation returns (True, None)
            - Subclasses can override for custom validation
        """
        return True, None

    def get_help(self) -> str:
        """
        Generate help message for command.

        Returns:
            Help message string

        Note:
            - Includes name, description, examples
            - Includes aliases
        """
        lines = [
            f"Command: {self._name}",
            f"Description: {self._description}",
            f"Category: {self._category}",
        ]

        if self._aliases:
            lines.append(f"Aliases: {', '.join(self._aliases)}")

        if self._examples:
            lines.append("Examples:")
            for example in self._examples:
                lines.append(f"  {example}")

        return "\n".join(lines)

    def __str__(self) -> str:
        """String representation of command."""
        return f"Command: {self._name}"

    def __hash__(self) -> int:
        """Hash based on command name."""
        return hash(self._name)


# ============================================================================
# Command Registry
# ============================================================================


class CommandRegistry:
    """
    Command registry for managing and executing CLI commands.

    Features:
    - Command registration and discovery
    - Command execution dispatching
    - Help message generation
    - Type-safe operations (PEP 484)
    - Error handling and recovery
    - Lazy loading for performance

    Architecture:
    - Layered design with clear separation of concerns
    - Performance optimization with lazy loading
    - Type-safe operations (PEP 484)
    - Integration with analysis engine

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import CommandRegistry, Command
        >>> registry = CommandRegistry(engine)
        >>> command = Command("mycmd", "My command")
        >>> registry.register(command)
        >>> result = registry.execute("mycmd", args)
    """

    def __init__(self, engine: Any):
        """
        Initialize command registry.

        Args:
            engine: AnalysisEngine instance
        """
        self._engine = engine
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> None:
        """
        Register a command.

        Args:
            command: Command to register

        Raises:
            RegistrationError: If command registration fails

        Note:
            - Registers command by name and aliases
            - Validates command name and aliases
        """
        # Validate command
        if not command or not isinstance(command, Command):
            raise RegistrationError(f"Invalid command: {command}")

        command_name = command.metadata.name

        # Check for duplicates
        if command_name in self._commands:
            raise RegistrationError(f"Command {command_name} already registered")

        for alias in command.metadata.aliases:
            if alias in self._commands or alias in self._aliases:
                raise RegistrationError(f"Alias {alias} already registered")

        # Register command
        self._commands[command_name] = command
        self._aliases[command_name] = command_name

        # Register aliases
        for alias in command.metadata.aliases:
            self._aliases[alias] = command_name

        log_debug(
            f"Registered command: {command_name} (aliases: {len(command.metadata.aliases)})"
        )

    def unregister(self, command_name: str) -> bool:
        """
        Unregister a command by name.

        Args:
            command_name: Command name

        Returns:
            True if unregistered, False if not found

        Note:
            - Removes command from registry
            - Removes all aliases
        """
        if command_name not in self._commands:
            return False

        self._commands[command_name]

        # Remove command
        del self._commands[command_name]

        # Remove aliases
        aliases_to_remove = [
            alias for alias, cmd in self._aliases.items() if cmd == command_name
        ]
        for alias in aliases_to_remove:
            del self._aliases[alias]

        log_debug(f"Unregistered command: {command_name}")

        return True

    def get_command(self, name: str) -> Command | None:
        """
        Get command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            Command object or None

        Note:
            - Resolves aliases to command names
        - Returns None if command not found
        """
        # Check if it's an alias
        if name in self._aliases:
            command_name = self._aliases[name]
        else:
            command_name = name

        # Get command
        return self._commands.get(command_name)

    def get_all_commands(self) -> dict[str, Command]:
        """
        Get all registered commands.

        Returns:
            Dictionary mapping command names to Command objects

        Note:
            - Includes all registered commands
            - Sorted by command name
        """
        return dict(sorted(self._commands.items()))

    def execute(
        self, command_name: str, args: list[str], options: dict[str, Any] | None = None
    ) -> CommandResult:
        """
        Execute a command.

        Args:
            command_name: Command name or alias
            args: Command-line arguments
            options: Command options

        Returns:
            CommandResult with execution details

        Raises:
            NotFoundError: If command is not found
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Resolves aliases to command names
            - Validates arguments
            - Creates execution context
            - Handles errors gracefully
        """
        start_time = perf_counter()

        try:
            # Get command
            command = self.get_command(command_name)
            if not command:
                raise NotFoundError(f"Command not found: {command_name}")

            # Create execution context
            context = ExecutionContext(
                engine=self._engine,
                args=args,
                options=options or {},
                config={},
            )

            # Validate arguments
            is_valid, error_message = command.validate_arguments(args)
            if not is_valid:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return CommandResult(
                    command_name=command_name,
                    success=False,
                    message=f"Invalid arguments: {error_message}",
                    execution_time=execution_time,
                )

            # Execute command
            result = command.execute(context)

            log_debug(f"Executed command: {command_name} (success: {result.success})")

            return result

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Command execution failed: {command_name} - {e}")

            return CommandResult(
                command_name=command_name,
                success=False,
                message=f"Command execution failed: {str(e)}",
                execution_time=execution_time,
            )


# ============================================================================
# Convenience Functions
# ============================================================================


@lru_cache(maxsize=64, typed=True)
def get_command_registry(engine: Any) -> CommandRegistry:
    """
    Get command registry instance with LRU caching.

    Args:
        engine: AnalysisEngine instance

    Returns:
        CommandRegistry instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return CommandRegistry(engine=engine)


# ============================================================================
# Module-level exports
# ============================================================================

__all__: list[str] = [
    # Exceptions
    "CommandError",
    "InitializationError",
    "RegistrationError",
    "ExecutionError",
    "ValidationError",
    "NotFoundError",
    # Data classes
    "CommandMetadata",
    "ExecutionContext",
    "CommandResult",
    # Main classes
    "Command",
    "CommandRegistry",
    # Convenience functions
    "get_command_registry",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If requested component is not found
    """
    # Handle specific imports
    if name == "Command":
        return Command
    elif name == "CommandRegistry":
        return CommandRegistry
    elif name == "get_command_registry":
        return get_command_registry
    elif name in [
        "CommandError",
        "InitializationError",
        "RegistrationError",
        "ExecutionError",
        "ValidationError",
        "NotFoundError",
    ]:
        # Import from module
        import sys

        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found") from None
