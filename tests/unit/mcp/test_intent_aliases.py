#!/usr/bin/env python3
"""
Unit tests for Intent Aliases system.

Intent Aliases provide user-friendly, intent-based names for MCP tools,
mapping from "what the user wants to do" to the underlying tool implementation.

Test Coverage:
- Alias resolution (intent name → tool name)
- Parameter transformation
- Backward compatibility (original names still work)
- Invalid alias handling
- Case sensitivity
- Multiple aliases for same tool
"""

import pytest

from tree_sitter_analyzer.mcp.intent_aliases import (
    IntentAliasResolver,
    get_tool_name_from_alias,
    get_all_aliases,
    is_valid_alias,
)


class TestIntentAliasResolution:
    """测试 Intent Alias 解析逻辑"""

    def test_resolve_locate_usage_to_search_content(self):
        """locate_usage 应该解析为 search_content"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("locate_usage")

        assert result == "search_content"

    def test_resolve_map_structure_to_list_files(self):
        """map_structure 应该解析为 list_files"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("map_structure")

        assert result == "list_files"

    def test_resolve_find_impacted_code_to_find_and_grep(self):
        """find_impacted_code 应该解析为 find_and_grep"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("find_impacted_code")

        assert result == "find_and_grep"

    def test_resolve_extract_structure_to_analyze_code_structure(self):
        """extract_structure 应该解析为 analyze_code_structure"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("extract_structure")

        assert result == "analyze_code_structure"

    def test_resolve_navigate_structure_to_get_code_outline(self):
        """navigate_structure 应该解析为 get_code_outline"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("navigate_structure")

        assert result == "get_code_outline"

    def test_resolve_discover_files_to_list_files(self):
        """discover_files 应该解析为 list_files (multiple aliases)"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("discover_files")

        assert result == "list_files"

    def test_resolve_find_usage_to_search_content(self):
        """find_usage 应该解析为 search_content (multiple aliases)"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("find_usage")

        assert result == "search_content"


class TestBackwardCompatibility:
    """测试向后兼容性 - 原始工具名仍然有效"""

    def test_original_tool_name_returns_itself(self):
        """原始工具名应该返回自己（不变）"""
        resolver = IntentAliasResolver()

        result = resolver.resolve("search_content")

        assert result == "search_content"

    def test_all_original_tool_names_pass_through(self):
        """所有原始工具名都应该 pass through"""
        resolver = IntentAliasResolver()
        original_tools = [
            "list_files",
            "search_content",
            "find_and_grep",
            "analyze_code_structure",
            "get_code_outline",
        ]

        for tool in original_tools:
            result = resolver.resolve(tool)
            assert result == tool


class TestInvalidAliases:
    """测试无效 alias 处理"""

    def test_unknown_alias_raises_error(self):
        """未知的 alias 应该抛出 ValueError"""
        resolver = IntentAliasResolver()

        with pytest.raises(ValueError, match="Unknown tool or alias"):
            resolver.resolve("invalid_tool_name")

    def test_empty_alias_raises_error(self):
        """空字符串应该抛出 ValueError"""
        resolver = IntentAliasResolver()

        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            resolver.resolve("")

    def test_none_alias_raises_error(self):
        """None 应该抛出 TypeError"""
        resolver = IntentAliasResolver()

        with pytest.raises(TypeError):
            resolver.resolve(None)


class TestCaseSensitivity:
    """测试大小写敏感性"""

    def test_alias_is_case_sensitive(self):
        """Alias 应该区分大小写"""
        resolver = IntentAliasResolver()

        # 小写应该工作
        assert resolver.resolve("locate_usage") == "search_content"

        # 大写应该失败
        with pytest.raises(ValueError):
            resolver.resolve("LOCATE_USAGE")

    def test_original_tool_name_is_case_sensitive(self):
        """原始工具名应该区分大小写"""
        resolver = IntentAliasResolver()

        # 小写应该工作
        assert resolver.resolve("search_content") == "search_content"

        # 大写应该失败
        with pytest.raises(ValueError):
            resolver.resolve("SEARCH_CONTENT")


class TestAliasMetadata:
    """测试 Alias 元数据和查询功能"""

    def test_get_all_aliases_returns_dict(self):
        """get_all_aliases 应该返回完整的 alias 映射"""
        aliases = get_all_aliases()

        assert isinstance(aliases, dict)
        assert len(aliases) > 0
        assert "locate_usage" in aliases
        assert aliases["locate_usage"] == "search_content"

    def test_is_valid_alias_for_known_alias(self):
        """is_valid_alias 对已知 alias 返回 True"""
        assert is_valid_alias("locate_usage") is True
        assert is_valid_alias("map_structure") is True

    def test_is_valid_alias_for_original_tool(self):
        """is_valid_alias 对原始工具名返回 True"""
        assert is_valid_alias("search_content") is True
        assert is_valid_alias("list_files") is True

    def test_is_valid_alias_for_unknown_name(self):
        """is_valid_alias 对未知名称返回 False"""
        assert is_valid_alias("invalid_name") is False
        assert is_valid_alias("") is False


class TestHelperFunction:
    """测试辅助函数 get_tool_name_from_alias"""

    def test_get_tool_name_from_alias_with_alias(self):
        """get_tool_name_from_alias 应该解析 alias"""
        result = get_tool_name_from_alias("locate_usage")

        assert result == "search_content"

    def test_get_tool_name_from_alias_with_original(self):
        """get_tool_name_from_alias 对原始名称返回自身"""
        result = get_tool_name_from_alias("search_content")

        assert result == "search_content"

    def test_get_tool_name_from_alias_with_invalid(self):
        """get_tool_name_from_alias 对无效名称抛出错误"""
        with pytest.raises(ValueError):
            get_tool_name_from_alias("invalid_name")
