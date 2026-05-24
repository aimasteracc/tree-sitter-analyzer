"""Tests for mcp.server_utils.resource_registration — MCP resource handler registration."""

from unittest.mock import AsyncMock, MagicMock

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


def _make_instance():
    code_file_resource = MagicMock()
    code_file_resource.get_resource_info.return_value = {
        "uri_template": "code://file",
        "name": "Code File",
        "description": "Source code",
        "mime_type": "text/plain",
    }
    project_stats_resource = MagicMock()
    project_stats_resource.get_resource_info.return_value = {
        "uri_template": "project://stats",
        "name": "Project Stats",
        "description": "Statistics",
        "mime_type": "application/json",
    }
    instance = MagicMock()
    instance.code_file_resource = code_file_resource
    instance.project_stats_resource = project_stats_resource
    return instance


class TestRegisterResources:
    def test_registers_list_and_read_handlers(self):
        server = MagicMock()
        instance = _make_instance()
        register_resources(server, instance)
        assert server.list_resources.called
        assert server.read_resource.called

    @pytest.mark.asyncio
    async def test_handle_read_resource_code_file(self):
        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance()
        instance.code_file_resource.matches_uri.return_value = True
        instance.code_file_resource.read_resource = AsyncMock(
            return_value="file content"
        )
        instance.project_stats_resource.matches_uri.return_value = False

        register_resources(server, instance)

        result = await handlers["read_resource"]("code://file/path.py")
        assert result == "file content"

    @pytest.mark.asyncio
    async def test_handle_read_resource_project_stats(self):
        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance()
        instance.code_file_resource.matches_uri.return_value = False
        instance.project_stats_resource.matches_uri.return_value = True
        instance.project_stats_resource.read_resource = AsyncMock(return_value="stats")

        register_resources(server, instance)

        result = await handlers["read_resource"]("project://stats")
        assert result == "stats"

    @pytest.mark.asyncio
    async def test_handle_read_resource_unknown_raises(self):
        handlers = {}
        server = MagicMock()
        server.list_resources.side_effect = _capture_decorator(
            handlers, "list_resources"
        )
        server.read_resource.side_effect = _capture_decorator(handlers, "read_resource")

        instance = _make_instance()
        instance.code_file_resource.matches_uri.return_value = False
        instance.project_stats_resource.matches_uri.return_value = False

        register_resources(server, instance)

        with pytest.raises(ValueError, match="Resource not found"):
            await handlers["read_resource"]("unknown://thing")
