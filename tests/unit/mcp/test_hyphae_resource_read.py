"""Regression test for RFC-0001 resources/read boundary — issue #454.

The MCP SDK's @server.read_resource() decorator matches the handler return
value against:
  str | bytes           → wraps as TextResourceContents (deprecated)
  Iterable[ReadResourceContents] → wraps each item via .content/.mime_type

Returning a raw dict hits the Iterable branch, then calls dict_key.content
→ AttributeError: 'str' object has no attribute 'content'.

This test verifies that handle_read_resource, when called with a
tsa://hyphae/ URI, returns a list of ReadResourceContents objects — NOT a
raw dict — so the MCP SDK can wrap them without crashing.

Boundary rule: the test goes through the real handle_read_resource handler
registered by register_resources(), not through read_hyphae_resource()
directly (that would miss the boundary where the crash occurs).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.server_utils.resource_registration import (
    register_resources,
)


def _capture_decorator(handlers, attr_name):
    def decorator():
        def wrapper(func):
            handlers[attr_name] = func
            return func

        return wrapper

    return decorator


def _make_instance(project_root: str = "/tmp/proj"):
    code_file_resource = MagicMock()
    code_file_resource.get_resource_info.return_value = {
        "uri_template": "code://file",
        "name": "Code File",
        "description": "Source code",
        "mime_type": "text/plain",
    }
    code_file_resource.matches_uri.return_value = False
    project_stats_resource = MagicMock()
    project_stats_resource.get_resource_info.return_value = {
        "uri_template": "project://stats",
        "name": "Project Stats",
        "description": "Statistics",
        "mime_type": "application/json",
    }
    project_stats_resource.matches_uri.return_value = False
    instance = MagicMock()
    instance.code_file_resource = code_file_resource
    instance.project_stats_resource = project_stats_resource
    instance._project_root = project_root
    return instance


class TestHyphaeResourceReadBoundary:
    """handle_read_resource must return ReadResourceContents, not a raw dict."""

    @pytest.mark.asyncio
    async def test_returns_list_of_read_resource_contents(self):
        """Issue #454: tsa://hyphae/ URIs must not return a raw dict.

        The MCP SDK iterates the return value and calls .content on each item.
        A dict is Iterable[str] (its keys), and str has no .content — crash.
        The fix: wrap the JSON payload in ReadResourceContents objects.
        """
        from mcp.server.lowlevel.helper_types import ReadResourceContents

        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance(project_root="/tmp/proj")
        register_resources(server, instance)

        fake_items = [
            {
                "name": "apply_toon",
                "file": "mcp/facade_map.py",
                "line": 1,
                "kind": "function",
            }
        ]
        fake_result = {"selector": ".function", "items": fake_items, "count": 1}

        with patch(
            "tree_sitter_analyzer.mcp.resources.hyphae_resource.read_hyphae_resource",
            new=AsyncMock(return_value=fake_result),
        ):
            result = await handlers["read_resource"](
                "tsa://hyphae/%23apply_toon_format_to_response"
            )

        # Must be a list (or iterable) of ReadResourceContents — NOT a raw dict
        assert isinstance(result, list), (
            f"Expected list[ReadResourceContents], got {type(result).__name__}. "
            "The MCP SDK crashes with 'str object has no attribute content' "
            "when a raw dict is returned (dict is Iterable[str], not Iterable[ReadResourceContents])."
        )
        assert len(result) == 1
        item = result[0]
        assert isinstance(item, ReadResourceContents), (
            f"Each item must be ReadResourceContents, got {type(item).__name__}"
        )
        # content must be a JSON string containing the selector result
        assert isinstance(item.content, str)
        parsed = json.loads(item.content)
        assert parsed["selector"] == ".function"
        assert parsed["count"] == 1
        assert item.mime_type == "application/json"

    @pytest.mark.asyncio
    async def test_read_resource_contents_survive_sdk_iteration(self):
        """Each item in the result must have .content and .mime_type attributes.

        This directly replicates what the MCP SDK does:
            contents_list = [create_content(item.content, item.mime_type) for item in result]
        If the hyphae handler returns a raw dict, this would crash.
        """

        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance(project_root="/tmp/proj")
        register_resources(server, instance)

        fake_result = {"selector": "#foo", "items": [], "count": 0}

        with patch(
            "tree_sitter_analyzer.mcp.resources.hyphae_resource.read_hyphae_resource",
            new=AsyncMock(return_value=fake_result),
        ):
            result = await handlers["read_resource"]("tsa://hyphae/%23foo")

        # Simulate exactly what the MCP SDK does — must not raise AttributeError
        contents_list = [(item.content, item.mime_type) for item in result]
        assert len(contents_list) == 1
        content_str, mime = contents_list[0]
        assert mime == "application/json"
        assert "#foo" in json.loads(content_str)["selector"]

    @pytest.mark.asyncio
    async def test_unsubscribe_cleanup_does_not_affect_resource_read(self):
        """Unsubscribe path: removing session state must not break resource reads.

        Regression check: after unsubscribe, re-reading the resource URI must
        still work (resource read is stateless — does not depend on session store).
        """
        from mcp.server.lowlevel.helper_types import ReadResourceContents

        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance(project_root="/tmp/proj")
        register_resources(server, instance)

        # Simulate: session was unsubscribed (session store cleared)
        from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst

        hst._SESSION_SESSIONS.pop("task-gone", None)
        hst._SESSION_LOOPS.pop("task-gone", None)

        # But reading the resource URI should still work via live evaluation
        fake_result = {"selector": ".class", "items": [], "count": 0}
        with patch(
            "tree_sitter_analyzer.mcp.resources.hyphae_resource.read_hyphae_resource",
            new=AsyncMock(return_value=fake_result),
        ):
            result = await handlers["read_resource"]("tsa://hyphae/.class")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ReadResourceContents)
