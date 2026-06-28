"""MCP-specific exception facade."""

from .mcp_response import create_mcp_error_response, mcp_exception_handler
from .mcp_types import (
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
)
from .sanitization import _sanitize_error_context

__all__ = [
    "MCPResourceError",
    "MCPTimeoutError",
    "MCPToolError",
    "MCPValidationError",
    "_sanitize_error_context",
    "create_mcp_error_response",
    "mcp_exception_handler",
]
