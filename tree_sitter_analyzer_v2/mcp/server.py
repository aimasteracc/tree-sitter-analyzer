"""
MCP Server implementation for tree-sitter-analyzer v2.

Provides a full-featured MCP server with auto-registered tools.
Includes Code Graph tools for AI-powered code analysis.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions, ServerCapabilities
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool, ToolsCapability

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None  # type: ignore
    InitializationOptions = None  # type: ignore
    ServerCapabilities = None  # type: ignore
    stdio_server = None  # type: ignore
    TextContent = None  # type: ignore
    Tool = None  # type: ignore
    ToolsCapability = None  # type: ignore

from tree_sitter_analyzer_v2.mcp.tools import (
    AnalyzeCodeGraphTool,
    AnalyzeTool,
    BatchOperationsTool,
    CheckCodeScaleTool,
    CodeQualityTool,
    DeleteFileTool,
    ExtractCodeSectionTool,
    FindAndGrepTool,
    FindFilesTool,
    FindFunctionCallersTool,
    FormatterTool,
    LinterTool,
    QueryCallChainTool,
    QueryTool,
    RefactorRenameTool,
    ReplaceInFileTool,
    SearchContentTool,
    TestRunnerTool,
    VisualizeCodeGraphTool,
    WriteFileTool,
)
from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry


class MCPServer:
    """
    Full-featured MCP server for tree-sitter-analyzer v2.

    This implements the MCP protocol specification with:
    - initialize: Server initialization
    - ping: Health check
    - shutdown: Graceful shutdown
    - tools/list: List available tools
    - tools/call: Execute tool

    Tools are auto-registered on initialization including Code Graph tools.
    """

    def __init__(self, project_root: str) -> None:
        """
        Initialize MCP server with auto-registered tools.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = Path(project_root).resolve()
        self.name = "tree-sitter-analyzer-v2"
        self.version = "2.0.0-alpha.1"
        self.is_initialized = False

        # Initialize tool registry and auto-register all tools
        self.tool_registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        """Auto-register all available MCP tools."""
        # Core analysis tools
        self.tool_registry.register(AnalyzeTool())
        self.tool_registry.register(QueryTool())
        self.tool_registry.register(CheckCodeScaleTool())
        self.tool_registry.register(ExtractCodeSectionTool())

        # Search tools
        self.tool_registry.register(FindFilesTool())
        self.tool_registry.register(SearchContentTool())
        self.tool_registry.register(FindAndGrepTool())

        # File operation tools
        self.tool_registry.register(WriteFileTool())
        self.tool_registry.register(ReplaceInFileTool())
        self.tool_registry.register(DeleteFileTool())
        self.tool_registry.register(BatchOperationsTool())

        # Refactoring tools
        self.tool_registry.register(RefactorRenameTool())

        # Quality tools
        self.tool_registry.register(CodeQualityTool())
        self.tool_registry.register(LinterTool())
        self.tool_registry.register(FormatterTool())
        self.tool_registry.register(TestRunnerTool())

        # Code Graph tools (NEW in Phase 9!)
        self.tool_registry.register(AnalyzeCodeGraphTool())
        self.tool_registry.register(FindFunctionCallersTool())
        self.tool_registry.register(QueryCallChainTool())
        self.tool_registry.register(VisualizeCodeGraphTool())  # NEW in E4!

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
            result = tool.execute(tool_arguments)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
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


class TreeSitterAnalyzerMCPServer:
    """
    MCP Server wrapper using the official MCP SDK.

    This wraps the MCPServer class to provide stdio-based communication
    compatible with Claude Desktop, Cursor, and other MCP clients.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize MCP server with project root.

        Args:
            project_root: Root directory of the project to analyze.
                         If None, uses TREE_SITTER_PROJECT_ROOT env var or current directory.
        """
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP SDK not installed. Install with: uv pip install -e '.[mcp]'"
            )

        # Determine project root
        if project_root is None:
            project_root = os.getenv("TREE_SITTER_PROJECT_ROOT", os.getcwd())

        self.project_root = Path(project_root).resolve()
        self.mcp_server = Server("tree-sitter-analyzer-v2")
        self.core_server = MCPServer(str(self.project_root))

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""

        @self.mcp_server.list_tools()
        async def list_tools() -> list[Tool]:
            """List all available tools."""
            tools_data = self.core_server.tool_registry.get_all_schemas()
            return [
                Tool(
                    name=tool["name"],
                    description=tool["description"],
                    inputSchema=tool["inputSchema"],
                )
                for tool in tools_data
            ]

        @self.mcp_server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Execute a tool and return results."""
            try:
                tool = self.core_server.tool_registry.get(name)
                result = tool.execute(arguments)

                # Format result as TextContent
                if isinstance(result, dict):
                    text = json.dumps(result, indent=2)
                else:
                    text = str(result)

                return [TextContent(type="text", text=text)]
            except Exception as e:
                error_msg = f"Tool execution failed: {str(e)}"
                return [TextContent(type="text", text=error_msg)]

    async def run(self) -> None:
        """Run the MCP server with stdio transport."""
        # Create server capabilities
        capabilities = ServerCapabilities(
            tools=ToolsCapability(listChanged=True),
        )

        # Create initialization options
        options = InitializationOptions(
            server_name="tree-sitter-analyzer-v2",
            server_version="2.0.0-alpha.1",
            capabilities=capabilities,
        )

        # Run server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await self.mcp_server.run(read_stream, write_stream, options)


async def main() -> None:
    """Main entry point for MCP server."""
    if not MCP_AVAILABLE:
        print(
            "Error: MCP SDK not installed. Install with: uv pip install -e '.[mcp]'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Get project root from environment or use current directory
        project_root = os.getenv("TREE_SITTER_PROJECT_ROOT", os.getcwd())

        # Create and run server
        server = TreeSitterAnalyzerMCPServer(project_root)
        await server.run()

        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Server failed: {e}", file=sys.stderr)
        sys.exit(1)


def main_sync() -> None:
    """Synchronous entry point for setuptools scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
