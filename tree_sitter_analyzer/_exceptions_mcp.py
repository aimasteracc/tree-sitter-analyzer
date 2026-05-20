"""MCP-specific exception facade."""

from ._exceptions_mcp_response import create_mcp_error_response, mcp_exception_handler
from ._exceptions_mcp_types import (
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
)
from ._exceptions_sanitization import _sanitize_error_context

__all__ = [
    "MCPResourceError",
    "MCPTimeoutError",
    "MCPToolError",
    "MCPValidationError",
    "_sanitize_error_context",
    "create_mcp_error_response",
    "mcp_exception_handler",
]
