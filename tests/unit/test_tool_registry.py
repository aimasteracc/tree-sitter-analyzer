"""Tests for tree_sitter_analyzer.mcp._tool_registry module."""

from __future__ import annotations

from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry


class TestCreateToolRegistry:
    def test_returns_tools_and_dict(self):
        tools, lookup = create_tool_registry(project_root=None)
        assert isinstance(tools, list)
        assert isinstance(lookup, dict)
        assert len(tools) == len(lookup)

    def test_tool_names_are_strings(self):
        tools, _ = create_tool_registry(project_root=None)
        for name, _instance in tools:
            assert isinstance(name, str)
            assert name

    def test_dict_keys_match_tool_names(self):
        tools, lookup = create_tool_registry(project_root=None)
        for name, _ in tools:
            assert name in lookup

    def test_expected_tool_count(self):
        # Wave C2: the public surface is exactly the 8 domain facades.
        tools, _ = create_tool_registry(project_root=None)
        assert len(tools) == 8, f"Expected exactly 8 facades, got {len(tools)}"

    def test_specific_tools_present(self):
        # Wave C2: the registry exposes the 8 facade names, not the legacy
        # 63 discrete tool names (which are reached via the legacy-name shim).
        _, lookup = create_tool_registry(project_root=None)
        expected = [
            "search",
            "nav",
            "structure",
            "health",
            "edit",
            "project",
            "index",
            "viz",
        ]
        for name in expected:
            assert name in lookup, f"Missing facade: {name}"

    def test_tool_instances_have_execute(self):
        tools, _ = create_tool_registry(project_root=None)
        for name, instance in tools:
            assert hasattr(instance, "execute"), f"{name} missing execute method"

    def test_project_root_passed_through(self, tmp_path):
        tools, _ = create_tool_registry(project_root=str(tmp_path))
        for _name, instance in tools:
            if hasattr(instance, "project_root"):
                assert instance.project_root == str(tmp_path)
