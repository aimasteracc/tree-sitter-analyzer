"""Tool handler registration for MCP server — extracted from server.py create_server."""

from typing import Any

try:
    from mcp.types import TextContent, Tool
except ImportError:
    TextContent = Any
    Tool = Any

from ...utils import setup_logger
from ..utils.schema_strictness import enforce_strict_params
from .error_recovery import (
    build_agent_friendly_error,
    ensure_canonical_error_envelope,
    ensure_canonical_success_envelope,
)

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
    # ``Tool`` is set to ``typing.Any`` as a sentinel when the optional `mcp`
    # package isn't importable. mypy can't see that identity check through
    # its narrowing because typing.Any has no fixed runtime identity.
    if Tool is Any:  # type: ignore[comparison-overlap]
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
            # Central envelope normalization: tools that return their own
            # ``{success: False, ...}`` dicts (find_and_grep, refactoring_suggestions,
            # read_partial, query, search_content) get the canonical
            # ``agent_summary``/``summary_line``/``error_type`` keys added here
            # — without losing any tool-specific fields they already set.
            if isinstance(result, dict) and result.get("success") is False:
                result = ensure_canonical_error_envelope(
                    name, result, arguments=arguments
                )
            elif isinstance(result, dict):
                # Finding 6: success-path normalization. Mirror
                # ``agent_summary.summary_line`` to top-level for tools
                # that build an agent_summary but never set summary_line
                # (FileHealth, ProjectHealth, RefactoringSuggestions, ...).
                # Idempotent — tools that already set ``summary_line`` keep
                # their value. Applies to TOON responses too because TOON
                # mode keeps ``agent_summary``/``summary_line`` as metadata
                # alongside the ``toon_content`` blob.
                result = ensure_canonical_success_envelope(
                    name, result, arguments=arguments
                )
            return [
                TextContent(
                    type="text",
                    text=_json_dumps(result),
                )
            ]
        except Exception as e:
            _safe_log_error(f"Tool call error for {name}: {e}")
            error_body = build_agent_friendly_error(name, e, arguments=arguments)
            return [
                TextContent(
                    type="text",
                    text=_json_dumps(error_body),
                )
            ]


async def _dispatch_tool(
    server_instance: Any, name: str, arguments: dict[str, Any]
) -> Any:
    """Route a tool call to the appropriate handler.

    F5: legacy non-BaseMCPTool paths (``set_project_path``) get the
    strict-parameter check here, since they bypass the
    ``BaseMCPTool.__init_subclass__`` wrapper. BaseMCPTool-backed paths
    (everything in ``server_instance._tools``, plus ``extract_code_section``
    and ``analyze_code_structure`` which delegate to BaseMCPTool subclasses)
    are validated by that wrapper and need no extra gate here.
    """
    if name == "set_project_path":
        schema = _SET_PROJECT_PATH_TOOL["inputSchema"]
        enforce_strict_params(
            name, schema if isinstance(schema, dict) else None, arguments
        )
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
