"""
MCP Server implementation for tree-sitter-analyzer v2.

Provides a full-featured MCP server with auto-registered tools.
Includes Code Graph tools for AI-powered code analysis.
"""

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from tree_sitter_analyzer_v2 import __version__
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

# ── Tool module paths for auto-import ──
# Importing these modules triggers __init_subclass__ registration on BaseTool.
# To add a new tool: create a class inheriting BaseTool in a new module
# and add the module path here. No class name needed!
_TOOL_MODULES: list[str] = [
    "tree_sitter_analyzer_v2.mcp.tools.analyze",
    "tree_sitter_analyzer_v2.mcp.tools.query",
    "tree_sitter_analyzer_v2.mcp.tools.scale",
    "tree_sitter_analyzer_v2.mcp.tools.extract",
    "tree_sitter_analyzer_v2.mcp.tools.search",
    "tree_sitter_analyzer_v2.mcp.tools.find_and_grep",
    "tree_sitter_analyzer_v2.mcp.tools.code_graph",
    "tree_sitter_analyzer_v2.mcp.tools.intelligence",
]


class MCPServer:
    """
    Full-featured MCP server for tree-sitter-analyzer v2.

    This implements the MCP protocol specification with:
    - initialize: Server initialization
    - ping: Health check
    - shutdown: Graceful shutdown
    - tools/list: List available tools
    - tools/call: Execute tool

    Tools are auto-discovered via __init_subclass__ on BaseTool.
    To add a new tool, create a concrete BaseTool subclass and add
    its module to _TOOL_MODULES.
    """

    def __init__(self, project_root: str) -> None:
        """
        Initialize MCP server with auto-discovered tools.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = Path(project_root).resolve()
        self.name = "tree-sitter-analyzer-v2"
        self.version = __version__
        self.is_initialized = False

        # Initialize tool registry and auto-discover all tools
        self.tool_registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        """Auto-discover and register all MCP tools via __init_subclass__.

        Step 1: Import all tool modules (triggers __init_subclass__ registration).
        Step 2: Instantiate every registered concrete BaseTool subclass.
        """
        import importlib

        # Step 1: ensure all tool modules are imported
        for module_path in _TOOL_MODULES:
            try:
                importlib.import_module(module_path)
            except Exception as exc:
                logger.warning("Failed to import tool module %s: %s", module_path, exc)

        # Step 2: instantiate all auto-registered tool classes
        for tool_cls in BaseTool.registered_tool_classes():
            try:
                tool_instance: BaseTool = tool_cls()
                self.tool_registry.register(tool_instance)
            except Exception as exc:
                logger.warning("Failed to instantiate tool %s: %s", tool_cls.__name__, exc)

    def get_capabilities(self) -> dict[str, Any]:
        """
        Get server capabilities.

        Returns:
            Dictionary of server capabilities including all registered tools
        """
        return {
            "tools": self.tool_registry.get_all_schemas(),
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
        known_methods = {"initialize", "ping", "shutdown", "tools/list", "tools/call"}

        # Check if method is known
        if method not in known_methods:
            return self._error_response(request_id, -32601, f"Method not found: {method}")

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

        if method == "tools/list":
            return self._handle_tools_list(request_id)

        if method == "tools/call":
            return self._handle_tools_call(request_id, request.get("params", {}))

        # Should never reach here (all known methods handled above)
        return self._error_response(request_id, -32601, f"Method not found: {method}")

    def _handle_initialize(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
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

    def _handle_tools_list(self, request_id: Any) -> dict[str, Any]:
        """Handle tools/list request."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": self.tool_registry.get_all_schemas()},
        }

    def _handle_tools_call(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """
        Handle tools/call request.

        Args:
            request_id: Request ID
            params: Tool call parameters containing:
                - name: Tool name
                - arguments: Tool-specific arguments

        Returns:
            Tool execution result or error
        """
        if "name" not in params:
            return self._error_response(request_id, -32602, "Missing required parameter: name")

        tool_name = params["name"]
        tool_arguments = params.get("arguments", {})

        try:
            tool = self.tool_registry.get(tool_name)

            # S4-1: validate arguments against the tool's JSON schema
            validation_errors = tool.validate_arguments(tool_arguments)
            if validation_errors:
                return self._error_response(
                    request_id, -32602, f"Invalid arguments: {'; '.join(validation_errors)}"
                )

            t0 = time.perf_counter()
            result = tool.execute(tool_arguments)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "tool_execution",
                extra={"tool": tool_name, "elapsed_ms": round(elapsed_ms, 1),
                       "success": result.get("success") if isinstance(result, dict) else None},
            )
            # S4-2: timing metadata in _meta envelope (not in business result)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
                "_meta": {"timing_ms": round(elapsed_ms, 1)},
            }
        except ValueError as e:
            # Tool not found
            return self._error_response(request_id, -32602, str(e))
        except Exception as e:
            # Tool execution error
            return self._error_response(request_id, -32603, f"Tool execution failed: {e}")

    def _error_response(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
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
