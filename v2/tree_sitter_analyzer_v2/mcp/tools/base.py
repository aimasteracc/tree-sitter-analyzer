"""
Base MCP Tool class.

This module provides the abstract base class for all MCP tools.

All tools must implement:
- get_name(): Return tool name
- get_description(): Return tool description
- get_schema(): Return JSON schema for arguments
- execute(): Execute the tool with given arguments
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseTool(ABC):
    """
    Abstract base class for MCP tools.

    All tools must inherit from this class and implement the required methods.

    Uses __init_subclass__ to automatically register concrete tool classes.
    MCPServer can use BaseTool.registered_tool_classes() to discover all tools
    without maintaining a separate _TOOL_SPECS list.
    """

    # Automatic subclass registry (populated by __init_subclass__)
    _tool_classes: list[type["BaseTool"]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Automatically register concrete tool subclasses."""
        super().__init_subclass__(**kwargs)
        # Only register non-abstract classes (concrete tools)
        if not getattr(cls, "__abstractmethods__", None):
            BaseTool._tool_classes.append(cls)

    @classmethod
    def registered_tool_classes(cls) -> list[type["BaseTool"]]:
        """Return all registered concrete tool classes.

        To ensure all tool modules are imported, call
        ``_import_tool_modules()`` first.
        """
        return list(cls._tool_classes)

    @abstractmethod
    def get_name(self) -> str:
        """
        Get tool name.

        Returns:
            Tool name (e.g., "analyze_code_structure")
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Get tool description.

        Returns:
            Human-readable description of what the tool does
        """
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """
        Get JSON schema for tool arguments.

        Returns:
            JSON schema dict defining the tool's input parameters
        """
        pass

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with given arguments.

        Args:
            arguments: Tool arguments matching the schema

        Returns:
            Tool execution result as a dictionary
        """
        pass

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition (standard format for all tools).

        Returns:
            Tool definition dictionary compatible with MCP server.
        """
        return {
            "name": self.get_name(),
            "description": self.get_description(),
            "inputSchema": self.get_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> list[str]:
        """Validate arguments against the tool's JSON schema.

        Performs lightweight validation of required fields and types.
        Returns a list of error messages (empty if valid).
        """
        schema = self.get_schema()
        errors: list[str] = []

        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in arguments:
                errors.append(f"Missing required argument: {field}")

        # Check property types
        properties = schema.get("properties", {})
        for key, value in arguments.items():
            if key not in properties:
                continue  # Allow extra fields (forward compatibility)
            expected_type = properties[key].get("type")
            if expected_type and not self._check_type(value, expected_type):
                errors.append(f"Argument '{key}' expected type '{expected_type}', got '{type(value).__name__}'")

        return errors

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Check if value matches expected JSON schema type."""
        _type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_types = _type_map.get(expected)
        if expected_types is None:
            return True  # Unknown type, accept
        return isinstance(value, expected_types)

    # ── Shared utility methods ──

    @staticmethod
    def _validate_path_safe(
        file_path: str,
        project_root: str | None = None,
    ) -> dict[str, Any] | None:
        """Validate a file path against traversal attacks.

        Uses SecurityValidator when *project_root* is supplied.
        Without a root, performs a basic ".." traversal check.

        Returns:
            None if the path is safe; an ``_error()`` dict otherwise.
        """
        # Quick heuristic: reject obvious traversal patterns
        normalized = str(Path(file_path).resolve())
        if ".." in file_path:
            return BaseTool._error(
                f"Path traversal detected: {file_path}",
                error_code="SECURITY_VIOLATION",
            )
        if project_root:
            root = Path(project_root).resolve()
            try:
                Path(normalized).relative_to(root)
            except ValueError:
                return BaseTool._error(
                    f"Path is outside project boundaries: {file_path}",
                    error_code="SECURITY_VIOLATION",
                )
        return None

    @staticmethod
    def _detect_language_from_path(
        file_path: str | None,
        *,
        default: str = "python",
    ) -> str:
        """Detect programming language from file extension.

        Uses parser_registry.get_ext_lang_map() as the single source of truth
        for extension→language mapping. Falls back to a minimal hardcoded map
        only if the registry is unavailable.

        Args:
            file_path: Path to a source file (may be None for directory analysis).
            default: Fallback language when detection fails.

        Returns:
            Detected language string (e.g. "python", "java").
        """
        if not file_path:
            return default
        ext = Path(file_path).suffix.lower()
        try:
            from tree_sitter_analyzer_v2.core.parser_registry import get_ext_lang_map
            ext_map = get_ext_lang_map()
        except ImportError:
            # Minimal fallback if registry is unavailable
            ext_map = {
                ".py": "python", ".pyw": "python",
                ".java": "java",
                ".ts": "typescript", ".tsx": "typescript",
                ".js": "javascript", ".jsx": "javascript",
            }
        return ext_map.get(ext, default)

    # ── Standard error response helpers ──

    @staticmethod
    def _error(
        message: str,
        *,
        error_code: str = "INTERNAL_ERROR",
    ) -> dict[str, Any]:
        """Create a standardised error response.

        Args:
            message: Human-readable error description.
            error_code: Machine-readable error code
                (e.g. FILE_NOT_FOUND, INVALID_ARGUMENT, TIMEOUT).
        """
        return {"success": False, "error": message, "error_code": error_code}
