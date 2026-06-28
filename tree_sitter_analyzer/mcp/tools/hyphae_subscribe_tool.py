"""RFC-0001 criterion 2: search action=subscribe / unsubscribe.

Agents subscribe to a Hyphae selector expression. When a file change
alters the selector's result the server pushes a resource-updated
notification so the agent can re-read without polling.

Session capture: the subscribe handler grabs ``request_context.session``
and ``asyncio.get_running_loop()`` at call time (the only moment both are
accessible). The captured refs are stored in ``SubscriptionRegistry`` and
used by the watch→push bridge (RFC-0001 criterion 4) to schedule
``send_resource_updated`` on the correct event loop.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

from tree_sitter_analyzer.registry.singleton_registry import get_subscription_registry
from ..utils.format_helper import apply_toon_format_to_response
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
        output_format = arguments.get("output_format", "toon")

        # RFC-0001: capture session + loop at subscribe time (the only moment
        # request_context is populated and the event loop is running).
        session_id = _capture_session_id()
        loop = asyncio.get_event_loop()

        registry = get_subscription_registry()
        registry.subscribe(session_id, selector)

        # Store the loop, session object, and min_interval so the bridge can use them.
        # Session is captured here because request_context is only valid during a handler.
        _SESSION_LOOPS[session_id] = loop
        _SESSION_MIN_INTERVALS[session_id] = min_interval
        _SESSION_SESSIONS[session_id] = _capture_session_obj()

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
        return apply_toon_format_to_response(response, output_format)


class HyphaeUnsubscribeTool(BaseMCPTool):
    """``search action=unsubscribe``: cancel a Hyphae subscription."""

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
        output_format = arguments.get("output_format", "toon")
        session_id = arguments.get("sub_id") or _capture_session_id()
        selector = arguments.get("selector")

        registry = get_subscription_registry()
        if selector:
            registry.unsubscribe(session_id, selector)
        else:
            registry.remove_session(session_id)

        _SESSION_LOOPS.pop(session_id, None)
        _SESSION_MIN_INTERVALS.pop(session_id, None)
        _SESSION_SESSIONS.pop(session_id, None)

        response = build_response(
            verdict="INFO",
            sub_id=session_id,
            selector=selector,
            message="Unsubscribed.",
        )
        return apply_toon_format_to_response(response, output_format)


# ---------------------------------------------------------------------------
# Session capture helpers
# ---------------------------------------------------------------------------

# Maps session_id → asyncio loop (for the bridge)
_SESSION_LOOPS: dict[str, asyncio.AbstractEventLoop] = {}
# Maps session_id → min_interval_s
_SESSION_MIN_INTERVALS: dict[str, float] = {}
# Maps session_id → MCP ServerSession object (captured at subscribe time)
_SESSION_SESSIONS: dict[str, Any] = {}


def _capture_session_id() -> str:
    """Return a stable session identifier for the current MCP request.

    Uses the asyncio task identity as a stable proxy when no explicit session
    object is available — each MCP connection runs in a dedicated task so this
    is effectively per-connection.
    """
    try:
        task = asyncio.current_task()
        if task is not None:
            return f"task-{id(task)}"
    except RuntimeError:
        pass
    return "session-default"


def _capture_session_obj() -> Any:
    """Capture the MCP ServerSession from the current request context.

    Must be called inside a tool handler (where request_context is populated).
    Returns None if unavailable — the bridge degrades gracefully.
    """
    try:
        # The current request context lives in a module-level contextvar in the
        # MCP low-level server; accessing ``Server.request_context`` on the class
        # returns the property descriptor, not the live context. Read the
        # contextvar directly (populated for the duration of a tool-call handler).
        from mcp.server.lowlevel.server import request_ctx

        return request_ctx.get().session
    except Exception:
        return None


def get_session_loop(session_id: str) -> asyncio.AbstractEventLoop | None:
    """Return the captured event loop for *session_id*, or None."""
    return _SESSION_LOOPS.get(session_id)


def get_session_obj(session_id: str) -> Any:
    """Return the captured MCP ServerSession for *session_id*, or None."""
    return _SESSION_SESSIONS.get(session_id)


def get_session_min_interval(session_id: str) -> float:
    """Return the min_interval_s for *session_id* (default 2.0)."""
    return _SESSION_MIN_INTERVALS.get(session_id, 2.0)
