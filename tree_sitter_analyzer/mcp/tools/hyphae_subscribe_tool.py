"""RFC-0001 criterion 2: search action=subscribe / unsubscribe.

Agents subscribe to a Hyphae selector expression. When a file change
alters the selector's result the server pushes a resource-updated
notification so the agent can re-read without polling.

Session capture: the subscribe handler grabs ``request_context.session``
请求处理器在唯一可访问两者的调用期间捕获 ``ServerSession`` 与
``asyncio.get_running_loop()``。每应用生命周期 manager 持有这些引用，以及
watch→push bridge 使用的不可变发送 ticket。
"""

from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

from ..utils.format_helper import apply_output_format_to_response
from ._response_builder import build_response
from .base_tool import BaseMCPTool

_RESOURCE_SCHEME = "tsa://hyphae/"


def _selector_to_uri(selector: str) -> str:
    return _RESOURCE_SCHEME + urllib.parse.quote(selector, safe="")


def _uri_to_selector(uri: str) -> str:
    if uri.startswith(_RESOURCE_SCHEME):
        return urllib.parse.unquote(uri[len(_RESOURCE_SCHEME) :])
    return uri


class HyphaeSubscribeTool(BaseMCPTool):
    """``search action=subscribe``: register a Hyphae selector for push updates.

    Returns ``{ sub_id, resource_uri }`` on success so the agent knows which
    URI to read when notified and can unsubscribe later.
    """

    def __init__(
        self, project_root: str | None = None, lifecycle_manager: Any = None
    ) -> None:
        self._lifecycle_manager = lifecycle_manager
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_hyphae_subscribe",
            "description": (
                "Subscribe to a Hyphae selector — receive resource-updated "
                "notifications when a file change alters the result. "
                "Returns { sub_id, resource_uri }. "
                "Read resource_uri after the notification to get the new set. "
                "Unsubscribe via search action=unsubscribe."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Hyphae DSL selector to watch.",
                },
                "min_interval": {
                    "type": "number",
                    "default": 2.0,
                    "description": "Minimum seconds between re-evaluations (burst coalescing).",
                },
                "output_format": {"type": "string", "default": "json"},
            },
            "required": ["selector"],
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("selector"):
            raise ValueError("selector is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        selector = arguments["selector"]
        min_interval = float(arguments.get("min_interval", 2.0))
        output_format = arguments.get("output_format", "json")

        # RFC-0001：请求期间只捕获一次真实连接，并绑定其运行循环。
        session, owner = _capture_request_ownership()
        if session is None or self._lifecycle_manager is None:
            raise ValueError("MCP request context is required to subscribe")
        loop = asyncio.get_running_loop()
        owner = self._lifecycle_manager.require_owner(owner)
        ticket = self._lifecycle_manager.subscribe(
            owner, session, loop, selector, min_interval
        )
        session_id = ticket.session_id

        resource_uri = _selector_to_uri(selector)
        response = build_response(
            verdict="INFO",
            sub_id=session_id,
            selector=selector,
            resource_uri=resource_uri,
            message=(
                f"Subscribed. Re-read {resource_uri!r} after notifications. "
                "Unsubscribe via search action=unsubscribe."
            ),
        )
        return apply_output_format_to_response(response, output_format)


class HyphaeUnsubscribeTool(BaseMCPTool):
    """``search action=unsubscribe``: cancel a Hyphae subscription."""

    def __init__(
        self, project_root: str | None = None, lifecycle_manager: Any = None
    ) -> None:
        self._lifecycle_manager = lifecycle_manager
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_hyphae_unsubscribe",
            "description": "Cancel a Hyphae selector subscription by sub_id.",
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sub_id": {"type": "string", "description": "sub_id from subscribe."},
                "selector": {
                    "type": "string",
                    "description": "Selector to remove (alternative).",
                },
                "output_format": {"type": "string", "default": "json"},
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("sub_id") and not arguments.get("selector"):
            raise ValueError("sub_id or selector is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "json")
        session, owner = _capture_request_ownership()
        if session is None or self._lifecycle_manager is None:
            raise ValueError("MCP request context is required to unsubscribe")
        owner = self._lifecycle_manager.require_owner(owner)
        caller_session_id = _capture_session_id(session)
        requested_session_id = arguments.get("sub_id")
        if requested_session_id and requested_session_id != caller_session_id:
            raise ValueError("sub_id does not belong to the current MCP connection")
        session_id = caller_session_id
        selector = arguments.get("selector")

        self._lifecycle_manager.unsubscribe(
            owner, session, sub_id=requested_session_id, selector=selector
        )

        response = build_response(
            verdict="INFO",
            sub_id=session_id,
            selector=selector,
            message="Unsubscribed.",
        )
        return apply_output_format_to_response(response, output_format)


# ---------------------------------------------------------------------------
# Session capture helpers
# ---------------------------------------------------------------------------

# Maps session_id → asyncio loop (for the bridge)
_SESSION_LOOPS: dict[str, asyncio.AbstractEventLoop] = {}
# Maps session_id → min_interval_s
_SESSION_MIN_INTERVALS: dict[str, float] = {}
# Maps session_id → MCP ServerSession object (captured at subscribe time)
_SESSION_SESSIONS: dict[str, Any] = {}


def _capture_session_id(session: Any) -> str:
    """从已捕获的 ServerSession 生成连接级不透明句柄。"""
    return f"session-{id(session)}"


def _capture_session_obj() -> Any:
    """从当前请求上下文捕获 MCP ServerSession；上下文缺失时返回 None。"""
    try:
        # 低层 server 在工具处理期间填充此 contextvar。
        from mcp.server.lowlevel.server import request_ctx

        return request_ctx.get().session
    except Exception:
        return None


def _capture_request_ownership() -> tuple[Any, Any]:
    """一次读取 SDK 请求上下文中的 session 与 lifespan owner。"""
    try:
        from mcp.server.lowlevel.server import request_ctx

        context = request_ctx.get()
        return context.session, context.lifespan_context
    except Exception:
        return None, None


def get_session_loop(session_id: str) -> asyncio.AbstractEventLoop | None:
    """Return the captured event loop for *session_id*, or None."""
    return _SESSION_LOOPS.get(session_id)


def get_session_obj(session_id: str) -> Any:
    """Return the captured MCP ServerSession for *session_id*, or None."""
    return _SESSION_SESSIONS.get(session_id)


def get_session_min_interval(session_id: str) -> float:
    """Return the min_interval_s for *session_id* (default 2.0)."""
    return _SESSION_MIN_INTERVALS.get(session_id, 2.0)
