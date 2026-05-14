"""Tool handler registration for MCP server — extracted from server.py create_server."""

from typing import Any

try:
    from mcp.types import TextContent, Tool
except ImportError:
    TextContent = Any
    Tool = Any

from ...utils import setup_logger
from .error_recovery import build_agent_friendly_error

logger = setup_logger(__name__)

_SET_PROJECT_PATH_TOOL = {
    "name": "set_project_path",
    "description": "SMART Workflow 'Set' step (FIRST): Set the project root path for security boundaries. Call this before any other tool to ensure correct file resolution and security validation.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Absolute path to the project root",
            }
        },
        "required": ["project_path"],
        "additionalProperties": False,
    },
}


def register_tools(server: Any, server_instance: Any) -> None:
    """Register tool list and call handlers on the MCP server."""
    if Tool is Any:
        return

    @server.list_tools()  # type: ignore[untyped-decorator]
    async def handle_list_tools() -> list[Any]:
        """List all available tools."""
        logger.info("Client requesting tools list")
        tools = [
            Tool(**t.get_tool_definition()) for _, t in server_instance._tool_instances
        ]
        tools.append(Tool(**_SET_PROJECT_PATH_TOOL))
        logger.info(f"Returning {len(tools)} tools: {[t.name for t in tools]}")
        return tools

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        try:
            server_instance._ensure_initialized()
            logger.info(f"MCP tool call: {name} with args: {list(arguments.keys())}")
            server_instance._validate_file_path_security(arguments)
            result = await _dispatch_tool(server_instance, name, arguments)
            return [
                TextContent(
                    type="text",
                    text=_json_dumps(result),
                )
            ]
        except Exception as e:
            _safe_log_error(f"Tool call error for {name}: {e}")
            error_body = build_agent_friendly_error(name, e)
            return [
                TextContent(
                    type="text",
                    text=_json_dumps(error_body),
                )
            ]


async def _dispatch_tool(
    server_instance: Any, name: str, arguments: dict[str, Any]
) -> Any:
    """Route a tool call to the appropriate handler."""
    if name == "set_project_path":
        return server_instance._handle_set_project_path(arguments)
    if name == "extract_code_section":
        return await server_instance._handle_extract_code_section(arguments)
    if name == "analyze_code_structure":
        return await server_instance.table_format_tool.execute(arguments)
    if name in server_instance._tools:
        return await server_instance._tools[name].execute(arguments)
    raise ValueError(f"Unknown tool: {name}")


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, ensure_ascii=False)


def _safe_log_error(msg: str) -> None:
    try:
        logger.error(msg)
    except (ValueError, OSError):
        pass
