"""Core exception hierarchy for tree-sitter-analyzer."""

from pathlib import Path
from typing import Any


class TreeSitterAnalyzerError(Exception):
    """Base exception for all tree-sitter analyzer errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary format."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
        }


class AnalysisError(TreeSitterAnalyzerError):
    """Raised when file analysis fails."""

    def __init__(
        self,
        message: str,
        file_path: str | Path | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if file_path:
            context["file_path"] = str(file_path)
        if language:
            context["language"] = language
        super().__init__(message, context=context, **kwargs)


class ParseError(TreeSitterAnalyzerError):
    """Raised when parsing fails."""

    def __init__(
        self,
        message: str,
        language: str | None = None,
        source_info: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if language:
            context["language"] = language
        if source_info:
            context.update(source_info)
        super().__init__(message, context=context, **kwargs)


class LanguageNotSupportedError(TreeSitterAnalyzerError):
    """Raised when a language is not supported."""

    def __init__(
        self, language: str, supported_languages: list[str] | None = None, **kwargs: Any
    ) -> None:
        message = f"Language '{language}' is not supported"
        context = kwargs.get("context", {})
        context["language"] = language
        if supported_languages:
            context["supported_languages"] = supported_languages
            message += f". Supported languages: {', '.join(supported_languages)}"
        super().__init__(message, context=context, **kwargs)


class PluginError(TreeSitterAnalyzerError):
    """Raised when plugin operations fail."""

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if plugin_name:
            context["plugin_name"] = plugin_name
        if operation:
            context["operation"] = operation
        super().__init__(message, context=context, **kwargs)


class QueryError(TreeSitterAnalyzerError):
    """Raised when query execution fails."""

    def __init__(
        self,
        message: str,
        query_name: str | None = None,
        query_string: str | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if query_name:
            context["query_name"] = query_name
        if query_string:
            context["query_string"] = query_string
        if language:
            context["language"] = language
        super().__init__(message, context=context, **kwargs)


class FileHandlingError(TreeSitterAnalyzerError):
    """Raised when file operations fail."""

    def __init__(
        self,
        message: str,
        file_path: str | Path | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if file_path:
            context["file_path"] = str(file_path)
        if operation:
            context["operation"] = operation
        super().__init__(message, context=context, **kwargs)


class ConfigurationError(TreeSitterAnalyzerError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        config_value: Any | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if config_key:
            context["config_key"] = config_key
        if config_value is not None:
            context["config_value"] = config_value
        super().__init__(message, context=context, **kwargs)


class ValidationError(TreeSitterAnalyzerError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        validation_type: str | None = None,
        invalid_value: Any | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if validation_type:
            context["validation_type"] = validation_type
        if invalid_value is not None:
            context["invalid_value"] = invalid_value
        super().__init__(message, context=context, **kwargs)


class MCPError(TreeSitterAnalyzerError):
    """Raised when MCP operations fail."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        resource_uri: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if tool_name:
            context["tool_name"] = tool_name
        if resource_uri:
            context["resource_uri"] = resource_uri
        super().__init__(message, context=context, **kwargs)
