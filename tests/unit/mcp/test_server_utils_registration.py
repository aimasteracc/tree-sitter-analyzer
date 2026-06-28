"""Tests for mcp.server_utils.prompt_registration — SMART prompt registration."""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.server_utils.prompt_registration import (
    register_prompts,
)


def _capture_decorator(handlers, attr_name):
    def decorator():
        def wrapper(func):
            handlers[attr_name] = func
            return func

        return wrapper

    return decorator


class TestRegisterPrompts:
    def test_registration_applies_decorators(self):
        server = MagicMock()
        register_prompts(server)
        assert server.list_prompts.called
        assert server.get_prompt.called

    @pytest.mark.asyncio
    async def test_smart_analyze_prompt(self):
        handlers = {}
        server = MagicMock()
        server.list_prompts.side_effect = _capture_decorator(handlers, "list_prompts")
        server.get_prompt.side_effect = _capture_decorator(handlers, "get_prompt")

        register_prompts(server)

        result = await handlers["get_prompt"](
            "smart_analyze", {"file_path": "src/main.py"}
        )
        assert isinstance(result, dict) and "messages" in result

    @pytest.mark.asyncio
    async def test_smart_explore_prompt(self):
        handlers = {}
        server = MagicMock()
        server.list_prompts.side_effect = _capture_decorator(handlers, "list_prompts")
        server.get_prompt.side_effect = _capture_decorator(handlers, "get_prompt")

        register_prompts(server)

        result = await handlers["get_prompt"](
            "smart_explore", {"project_root": "/home/user/project"}
        )
        assert isinstance(result, dict) and "messages" in result

    @pytest.mark.asyncio
    async def test_unknown_prompt_raises(self):
        handlers = {}
        server = MagicMock()
        server.list_prompts.side_effect = _capture_decorator(handlers, "list_prompts")
        server.get_prompt.side_effect = _capture_decorator(handlers, "get_prompt")

        register_prompts(server)

        with pytest.raises(ValueError, match="Unknown prompt"):
            await handlers["get_prompt"]("nonexistent", {})

    @pytest.mark.asyncio
    async def test_smart_analyze_with_no_arguments(self):
        handlers = {}
        server = MagicMock()
        server.list_prompts.side_effect = _capture_decorator(handlers, "list_prompts")
        server.get_prompt.side_effect = _capture_decorator(handlers, "get_prompt")

        register_prompts(server)

        result = await handlers["get_prompt"]("smart_analyze", None)
        assert isinstance(result, dict) and "messages" in result
