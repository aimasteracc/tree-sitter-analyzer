import json
from pathlib import Path as PathClass
from typing import Any

try:
    from mcp.types import TextContent
except ImportError:

    class TextContent:  # type: ignore
        def __init__(self, type: str, text: str) -> None:
            self.type = type
            self.text = text


from ..utils import setup_logger
from .utils.shared_cache import get_shared_cache

logger = setup_logger(__name__)


class ToolHandler:
    """Handles MCP tool execution logic."""

    def __init__(self, server: Any) -> None:
        """
        Initialize ToolHandler.

        Args:
            server: The TreeSitterAnalyzerMCPServer instance containing tool instances
        """
        self.server = server

    async def handle_tool_call(
        self, name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        """
        Handle a tool call request.

        Args:
            name: The name of the tool to call
            arguments: The arguments for the tool

        Returns:
            List of TextContent responses
        """
        try:
            # Ensure server is fully initialized
            self.server._ensure_initialized()

            # Log tool call
            logger.info(f"MCP tool call: {name} with args: {list(arguments.keys())}")

            # Validate file path security
            await self._validate_file_path(arguments)

            # Handle tool calls
            result = await self._dispatch_tool(name, arguments)

            # Return result
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, ensure_ascii=False),
                )
            ]

        except Exception as e:
            try:
                logger.error(f"Tool call error for {name}: {e}")
            except (ValueError, OSError):
                pass
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": str(e), "tool": name, "arguments": arguments},
                        indent=2,
                    ),
                )
            ]

    async def _validate_file_path(self, arguments: dict[str, Any]) -> None:
        """Validate file path security if present in arguments."""
        if "file_path" in arguments:
            file_path = arguments["file_path"]

            # Best-effort resolve against project root for boundary enforcement
            base_root = getattr(
                getattr(self.server.security_validator, "boundary_manager", None),
                "project_root",
                None,
            )

            if not PathClass(file_path).is_absolute() and base_root:
                resolved_candidate = str((PathClass(base_root) / file_path).resolve())
            else:
                resolved_candidate = file_path

            shared_cache = get_shared_cache()
            cached = shared_cache.get_security_validation(
                resolved_candidate, project_root=base_root
            )
            if cached is None:
                cached = self.server.security_validator.validate_file_path(
                    resolved_candidate
                )
                shared_cache.set_security_validation(
                    resolved_candidate, cached, project_root=base_root
                )

            if cached is not None:
                is_valid, error_msg = cached
                if not is_valid:
                    raise ValueError(
                        f"Invalid or unsafe file path: {error_msg or file_path}"
                    )

    async def _dispatch_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Dispatch tool call to appropriate handler."""
        if name == "check_code_scale":
            return await self.server.analyze_scale_tool.execute(arguments)

        elif name == "analyze_code_structure":
            if "file_path" not in arguments:
                raise ValueError("file_path parameter is required")
            return await self.server.table_format_tool.execute(arguments)

        elif name == "extract_code_section":
            if "requests" in arguments and arguments["requests"] is not None:
                return await self.server.read_partial_tool.execute(arguments)
            else:
                if "file_path" not in arguments or "start_line" not in arguments:
                    raise ValueError("file_path and start_line parameters are required")

                full_args = {
                    "file_path": arguments["file_path"],
                    "start_line": arguments["start_line"],
                    "end_line": arguments.get("end_line"),
                    "start_column": arguments.get("start_column"),
                    "end_column": arguments.get("end_column"),
                    "format": arguments.get("format", "text"),
                    "output_file": arguments.get("output_file"),
                    "suppress_output": arguments.get("suppress_output", False),
                    "output_format": arguments.get("output_format", "toon"),
                    "allow_truncate": arguments.get("allow_truncate", False),
                    "fail_fast": arguments.get("fail_fast", False),
                }
                return await self.server.read_partial_tool.execute(full_args)

        elif name == "set_project_path":
            project_path = arguments.get("project_path")
            if not project_path or not isinstance(project_path, str):
                raise ValueError(
                    "project_path parameter is required and must be a string"
                )
            if not PathClass(project_path).is_dir():
                raise ValueError(f"Project path does not exist: {project_path}")
            self.server.set_project_path(project_path)
            return {"status": "success", "project_root": project_path}

        elif name == "query_code":
            return await self.server.query_tool.execute(arguments)

        elif name == "list_files":
            return await self.server.list_files_tool.execute(arguments)

        elif name == "search_content":
            return await self.server.search_content_tool.execute(arguments)

        elif name == "find_and_grep":
            return await self.server.find_and_grep_tool.execute(arguments)

        else:
            raise ValueError(f"Unknown tool: {name}")
