"""
MCP Server implementation for tree-sitter-analyzer v2.

Provides a minimal MCP server that responds to initialize, ping, and shutdown.
This is Phase 0 - just the protocol skeleton. Tools will be added in Phase 3.
"""

from pathlib import Path
from typing import Any


class MCPServer:
    """
    Minimal MCP server for tree-sitter-analyzer v2.

    This implements the MCP protocol specification with:
    - initialize: Server initialization
    - ping: Health check
    - shutdown: Graceful shutdown

    Tools will be added in Phase 3.
    """

    def __init__(self, project_root: str) -> None:
        """
        Initialize MCP server.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = Path(project_root).resolve()
        self.name = "tree-sitter-analyzer-v2"
        self.version = "2.0.0-alpha.1"
        self.is_initialized = False

    def get_capabilities(self) -> dict[str, Any]:
        """
        Get server capabilities.

        Returns:
            Dictionary of server capabilities
        """
        return {
            "tools": [],  # No tools yet - Phase 0
        }

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Handle MCP JSON-RPC request.

        Args:
            request: JSON-RPC request object

        Returns:
            JSON-RPC response object
        """
        # Validate JSON-RPC structure
        if "jsonrpc" not in request:
            return self._error_response(
                request.get("id"), -32600, "Invalid Request: missing jsonrpc field"
            )

        if request["jsonrpc"] != "2.0":
            return self._error_response(
                request.get("id"),
                -32600,
                f"Invalid Request: unsupported jsonrpc version {request['jsonrpc']}",
            )

        method = request.get("method")
        request_id = request.get("id")

        # Define known methods
        known_methods = {"initialize", "ping", "shutdown"}

        # Check if method is known
        if method not in known_methods:
            return self._error_response(
                request_id, -32601, f"Method not found: {method}"
            )

        # Initialize is always allowed
        if method == "initialize":
            return self._handle_initialize(request_id, request.get("params", {}))

        # Shutdown is always allowed
        if method == "shutdown":
            return self._handle_shutdown(request_id)

        # Other known methods require initialization
        if not self.is_initialized:
            return self._error_response(
                request_id,
                -32002,
                "Server not initialized. Call initialize first.",
            )

        # Handle methods after initialization
        if method == "ping":
            return self._handle_ping(request_id)

        # Should never reach here (all known methods handled above)
        return self._error_response(
            request_id, -32601, f"Method not found: {method}"
        )

    def _handle_initialize(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle initialize request."""
        self.is_initialized = True

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "0.1.0",
                "capabilities": self.get_capabilities(),
                "serverInfo": {
                    "name": self.name,
                    "version": self.version,
                },
            },
        }

    def _handle_ping(self, request_id: Any) -> dict[str, Any]:
        """Handle ping request."""
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    def _handle_shutdown(self, request_id: Any) -> dict[str, Any]:
        """Handle shutdown request."""
        self.is_initialized = False
        return {"jsonrpc": "2.0", "id": request_id, "result": None}

    def _error_response(
        self, request_id: Any, code: int, message: str
    ) -> dict[str, Any]:
        """
        Create JSON-RPC error response.

        Args:
            request_id: Request ID
            code: Error code
            message: Error message

        Returns:
            Error response object
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
