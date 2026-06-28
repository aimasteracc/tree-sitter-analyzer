#!/usr/bin/env python3
"""
Tree-sitter Analyzer Custom Exceptions

Public facade for the exception hierarchy and handling utilities. Keep imports from
``tree_sitter_analyzer.exceptions`` stable while the implementation lives in
smaller private modules.
"""

from .exceptions.core import (
    AnalysisError,
    ConfigurationError,
    FileHandlingError,
    LanguageNotSupportedError,
    MCPError,
    ParseError,
    PluginError,
    QueryError,
    TreeSitterAnalyzerError,
    ValidationError,
)
from .exceptions.execution import (
    create_error_response,
    handle_exception,
    handle_exceptions,
    safe_execute,
    safe_execute_async,
)
from .exceptions.mcp import (
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
    _sanitize_error_context,
    create_mcp_error_response,
    mcp_exception_handler,
)
from .exceptions.security import (
    FileRestrictionError,
    PathTraversalError,
    RegexSecurityError,
    SecurityError,
)

__all__ = [
    "AnalysisError",
    "ConfigurationError",
    "FileHandlingError",
    "FileRestrictionError",
    "LanguageNotSupportedError",
    "MCPError",
    "MCPResourceError",
    "MCPTimeoutError",
    "MCPToolError",
    "MCPValidationError",
    "ParseError",
    "PathTraversalError",
    "PluginError",
    "QueryError",
    "RegexSecurityError",
    "SecurityError",
    "TreeSitterAnalyzerError",
    "ValidationError",
    "_sanitize_error_context",
    "create_error_response",
    "create_mcp_error_response",
    "handle_exception",
    "handle_exceptions",
    "mcp_exception_handler",
    "safe_execute",
    "safe_execute_async",
]

for _name in __all__:
    _obj = globals()[_name]
    if hasattr(_obj, "__module__"):
        _obj.__module__ = __name__

del _name, _obj
