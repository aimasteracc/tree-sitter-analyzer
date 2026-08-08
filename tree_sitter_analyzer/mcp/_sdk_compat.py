"""Compatibility adapter for the public low-level MCP 1.x and 2.x APIs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class MCP2ServerAdapter:
    """Expose the 1.x decorator registration surface over MCP 2.x handlers."""

    def __init__(self, server: Any) -> None:
        self._server = server

    def __getattr__(self, name: str) -> Any:
        return getattr(self._server, name)

    def list_tools(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                return types.ListToolsResult(tools=await handler())

            self._server.add_request_handler(
                "tools/list", types.PaginatedRequestParams, adapted
            )
            return handler

        return decorate

    def call_tool(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                return types.CallToolResult(
                    content=await handler(params.name, params.arguments or {})
                )

            self._server.add_request_handler(
                "tools/call", types.CallToolRequestParams, adapted
            )
            return handler

        return decorate

    def list_resources(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                return types.ListResourcesResult(resources=await handler())

            self._server.add_request_handler(
                "resources/list", types.PaginatedRequestParams, adapted
            )
            return handler

        return decorate

    def read_resource(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                raw = await handler(params.uri)
                contents: list[types.TextResourceContents | types.BlobResourceContents]
                if isinstance(raw, (str, bytes)):
                    text = raw.decode() if isinstance(raw, bytes) else raw
                    contents = [types.TextResourceContents(uri=params.uri, text=text)]
                else:
                    contents = [
                        types.TextResourceContents(
                            uri=params.uri,
                            text=(
                                item.content.decode()
                                if isinstance(item.content, bytes)
                                else item.content
                            ),
                            mimeType=getattr(item, "mime_type", None),
                        )
                        for item in raw
                    ]
                return types.ReadResourceResult(contents=contents)

            self._server.add_request_handler(
                "resources/read", types.ReadResourceRequestParams, adapted
            )
            return handler

        return decorate

    def list_prompts(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                return types.ListPromptsResult(prompts=await handler())

            self._server.add_request_handler(
                "prompts/list", types.PaginatedRequestParams, adapted
            )
            return handler

        return decorate

    def get_prompt(self) -> Callable[[Any], Any]:
        from mcp import types

        def decorate(handler: Any) -> Any:
            async def adapted(context: Any, params: Any) -> Any:
                return await handler(params.name, params.arguments)

            self._server.add_request_handler(
                "prompts/get", types.GetPromptRequestParams, adapted
            )
            return handler

        return decorate


def adapt_server(server: Any) -> Any:
    """Return the native 1.x server or a decorator-compatible 2.x adapter."""
    return server if hasattr(server, "list_tools") else MCP2ServerAdapter(server)
