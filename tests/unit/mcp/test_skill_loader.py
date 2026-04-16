#!/usr/bin/env python3
"""
Tests for the layered SkillLoader.

Verifies:
- Core routes cover all 16 MCP tools
- Core tier token cost < 500 tokens
- Extended tier provides additional coverage
- Route resolution for core and extended queries
- SKILL.md generation produces valid content
"""

from __future__ import annotations

import re

import pytest

from tree_sitter_analyzer.mcp.skill_loader import (
    CORE_ROUTES,
    EXTENDED_CJK_MAP,
    EXTENDED_FUZZY_MAP,
    TOKEN_OPTIMIZATION,
    TOOL_PATTERNS,
    SkillLoader,
    get_skill_loader,
)

ALL_MCP_TOOLS = {
    "check_code_scale",
    "analyze_code_structure",
    "get_code_outline",
    "query_code",
    "extract_code_section",
    "list_files",
    "search_content",
    "find_and_grep",
    "batch_search",
    "trace_impact",
    "modification_guard",
    "get_project_summary",
    "build_project_index",
    "set_project_path",
    "check_tools",
    "dependency_query",
}


class TestCoreCoverage:
    """Verify core routes cover all 16 MCP tools."""

    def test_core_covers_all_tools(self) -> None:
        loader = SkillLoader()
        covered = loader.core_tools_covered()
        missing = ALL_MCP_TOOLS - covered
        assert not missing, f"Core routes miss tools: {missing}"

    def test_core_coverage_100_pct(self) -> None:
        loader = SkillLoader()
        assert loader.core_coverage_pct() == 100.0

    def test_core_route_count(self) -> None:
        assert len(CORE_ROUTES) >= 16

    def test_all_core_tools_are_real(self) -> None:
        for route in CORE_ROUTES:
            assert route.tool in ALL_MCP_TOOLS, f"Unknown tool: {route.tool}"

    def test_no_duplicate_core_tools(self) -> None:
        tools = [r.tool for r in CORE_ROUTES]
        assert len(tools) == len(set(tools)), "Duplicate tools in core routes"


class TestTokenCost:
    """Verify core tier stays under 500 tokens."""

    def test_core_under_500_tokens(self) -> None:
        loader = SkillLoader()
        assert loader.core_token_cost() < 500, (
            f"Core tier costs {loader.core_token_cost()} tokens, target <500"
        )

    def test_core_much_smaller_than_full(self) -> None:
        loader = SkillLoader()
        core = loader.core_token_cost()
        full = loader.full_token_cost()
        assert core < full * 0.5, (
            f"Core ({core}) should be <50% of full ({full})"
        )

    def test_full_includes_extended_data(self) -> None:
        loader = SkillLoader()
        full = loader.full_token_cost()
        core = loader.core_token_cost()
        assert full > core, "Full cost should exceed core"

    def test_generated_core_md_under_target(self) -> None:
        loader = SkillLoader()
        content = loader.generate_core_skill_md()
        tokens = loader.estimate_tokens(content)
        assert tokens < 500, (
            f"Generated core SKILL.md costs {tokens} tokens, target <500"
        )

    def test_estimate_tokens_reasonable(self) -> None:
        loader = SkillLoader()
        assert loader.estimate_tokens("hello world test") > 0
        assert loader.estimate_tokens("代码结构分析方法") > 0
        # Longer text should estimate more tokens
        assert loader.estimate_tokens("a" * 100) > loader.estimate_tokens("a" * 10)


class TestRouteResolution:
    """Verify query-to-route resolution."""

    @pytest.mark.parametrize(
        "query,expected_tool",
        [
            ("这个文件的结构", "analyze_code_structure"),
            ("code structure", "analyze_code_structure"),
            ("有什么类", "analyze_code_structure"),
            ("大纲", "get_code_outline"),
            ("层级结构", "get_code_outline"),
            ("所有方法", "query_code"),
            ("函数列表", "query_code"),
            ("第 10 行的代码", "extract_code_section"),
            ("谁调用了 processOrder", "trace_impact"),
            ("影响范围", "trace_impact"),
            ("修改安全吗", "modification_guard"),
            ("搜索 TODO", "search_content"),
            ("找到 .java 文件中的 deprecated", "find_and_grep"),
            ("同时搜 error 和 warning", "batch_search"),
            ("找文件", "list_files"),
            ("文件多大", "check_code_scale"),
            ("项目概览", "get_project_summary"),
            ("构建索引", "build_project_index"),
            ("设置项目路径", "set_project_path"),
            ("检查工具", "check_tools"),
            ("谁依赖 UserService", "dependency_query"),
        ],
        ids=lambda x: x[:20] if isinstance(x, str) else str(x),
    )
    def test_core_resolves_common_queries(
        self, query: str, expected_tool: str
    ) -> None:
        loader = SkillLoader()
        route = loader.resolve(query)
        assert route is not None, f"No route for query: {query}"
        assert route.tool == expected_tool, (
            f"Query '{query}' resolved to {route.tool}, expected {expected_tool}"
        )

    def test_extended_cjk_resolves(self) -> None:
        loader = SkillLoader()
        route = loader.resolve("所有函数", use_extended=True)
        assert route is not None
        assert route.tool == "query_code"

    def test_extended_fuzzy_resolves(self) -> None:
        loader = SkillLoader()
        route = loader.resolve("struct", use_extended=True)
        assert route is not None
        assert route.tool == "analyze_code_structure"

    def test_extended_off_returns_none_for_cjk(self) -> None:
        loader = SkillLoader()
        route = loader.resolve("所有函数", use_extended=False)
        assert route is None

    def test_empty_query_returns_none(self) -> None:
        loader = SkillLoader()
        assert loader.resolve("") is None

    def test_unmatched_query_returns_none(self) -> None:
        loader = SkillLoader()
        assert loader.resolve("xyzzy12345") is None


class TestExtendedData:
    """Verify extended data completeness."""

    def test_cjk_map_has_entries(self) -> None:
        assert len(EXTENDED_CJK_MAP) >= 10

    def test_cjk_map_tools_are_real(self) -> None:
        for _pattern, (tool, _params) in EXTENDED_CJK_MAP.items():
            assert tool in ALL_MCP_TOOLS, f"Unknown tool in CJK map: {tool}"

    def test_fuzzy_map_has_entries(self) -> None:
        assert len(EXTENDED_FUZZY_MAP) >= 8

    def test_fuzzy_map_tools_are_real(self) -> None:
        for _key, tool in EXTENDED_FUZZY_MAP.items():
            assert tool in ALL_MCP_TOOLS, f"Unknown tool in fuzzy map: {tool}"

    def test_token_optimization_has_entries(self) -> None:
        assert len(TOKEN_OPTIMIZATION) >= 4

    def test_tool_patterns_has_entries(self) -> None:
        assert len(TOOL_PATTERNS) >= 4

    def test_pattern_tools_are_real(self) -> None:
        for _name, _flow, _desc, tools_csv in TOOL_PATTERNS:
            for tool in tools_csv.split(","):
                assert tool in ALL_MCP_TOOLS, f"Unknown tool in pattern: {tool}"


class TestSkillMdGeneration:
    """Verify SKILL.md generation."""

    def test_core_md_has_all_tools(self) -> None:
        loader = SkillLoader()
        content = loader.generate_core_skill_md()
        for tool in ALL_MCP_TOOLS:
            assert tool in content, f"Core SKILL.md missing tool: {tool}"

    def test_core_md_has_rules(self) -> None:
        loader = SkillLoader()
        content = loader.generate_core_skill_md()
        assert "TOON" in content
        assert "modification_guard" in content
        assert "absolute paths" in content

    def test_core_md_has_smart(self) -> None:
        loader = SkillLoader()
        content = loader.generate_core_skill_md()
        assert "SMART" in content

    def test_extended_md_has_cjk_map(self) -> None:
        loader = SkillLoader()
        content = loader.generate_extended_md()
        assert "CJK" in content
        for cjk_pattern in EXTENDED_CJK_MAP:
            assert cjk_pattern in content

    def test_extended_md_has_fuzzy(self) -> None:
        loader = SkillLoader()
        content = loader.generate_extended_md()
        assert "Fuzzy" in content

    def test_extended_md_has_optimization(self) -> None:
        loader = SkillLoader()
        content = loader.generate_extended_md()
        assert "Optimization" in content


class TestSingleton:
    """Verify singleton behavior."""

    def test_get_skill_loader_returns_instance(self) -> None:
        loader = get_skill_loader()
        assert isinstance(loader, SkillLoader)

    def test_get_skill_loader_returns_same(self) -> None:
        loader1 = get_skill_loader()
        loader2 = get_skill_loader()
        assert loader1 is loader2


class TestRouteDataclass:
    """Verify Route dataclass behavior."""

    def test_route_creation(self) -> None:
        from tree_sitter_analyzer.mcp.skill_loader import Route

        route = Route("test pattern", "test_tool", {"key": "val"})
        assert route.pattern == "test pattern"
        assert route.tool == "test_tool"
        assert route.params == {"key": "val"}

    def test_route_frozen(self) -> None:
        from tree_sitter_analyzer.mcp.skill_loader import Route

        route = Route("p", "t")
        with pytest.raises(AttributeError):
            route.tool = "other"  # type: ignore[misc]

    def test_route_default_params(self) -> None:
        from tree_sitter_analyzer.mcp.skill_loader import Route

        route = Route("p", "t")
        assert route.params == {}
