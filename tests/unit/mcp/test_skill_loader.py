#!/usr/bin/env python3
"""
Tests for tiered skill loading — verify core/extended/full tiers.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.skill_loader import (
    CORE_TOOLS,
    EXTENDED_TOOLS,
    SkillLoadManager,
    TierBenchmark,
    benchmark_tiers,
    get_combined_tier,
    get_core_tier,
    get_extended_tier,
    get_full_tier,
    get_tier_by_tool,
    resolve_query_to_tier,
)


class TestCoreTier:
    """Verify core tier properties."""

    def test_core_token_estimate_under_500(self) -> None:
        tier = get_core_tier()
        assert tier.token_estimate < 500, (
            f"Core tier too large: {tier.token_estimate} tokens"
        )

    def test_core_covers_5_tools(self) -> None:
        tier = get_core_tier()
        assert len(tier.tools) == 5
        assert "analyze_code_structure" in tier.tools
        assert "query_code" in tier.tools
        assert "search_content" in tier.tools
        assert "trace_impact" in tier.tools
        assert "get_code_outline" in tier.tools

    def test_core_content_not_empty(self) -> None:
        tier = get_core_tier()
        assert len(tier.content) > 100
        assert "核心路由" in tier.content
        assert "行为规则" in tier.content

    def test_core_char_count_matches(self) -> None:
        tier = get_core_tier()
        assert tier.char_count == len(tier.content)


class TestExtendedTier:
    """Verify extended tier properties."""

    def test_extended_covers_remaining_tools(self) -> None:
        tier = get_extended_tier()
        assert "check_code_scale" in tier.tools
        assert "modification_guard" in tier.tools
        assert "dependency_query" in tier.tools
        assert "list_files" in tier.tools
        assert "get_project_summary" in tier.tools

    def test_extended_has_smart_workflow(self) -> None:
        tier = get_extended_tier()
        assert "SMART" in tier.content

    def test_extended_has_token_optimization(self) -> None:
        tier = get_extended_tier()
        assert "Token" in tier.content or "优化" in tier.content

    def test_no_overlap_between_core_and_extended(self) -> None:
        core = get_core_tier()
        ext = get_extended_tier()
        overlap = core.tools & ext.tools
        assert not overlap, f"Tools in both tiers: {overlap}"


class TestFullTier:
    """Verify full tier loads the actual SKILL.md."""

    def test_full_tier_has_content(self) -> None:
        tier = get_full_tier()
        assert len(tier.content) > 0

    def test_full_tier_name(self) -> None:
        tier = get_full_tier()
        assert tier.name == "full"

    def test_full_tier_covers_all_tools(self) -> None:
        tier = get_full_tier()
        all_tools = CORE_TOOLS | EXTENDED_TOOLS
        assert all_tools.issubset(tier.tools)


class TestTierByTool:
    """Verify tier lookup by tool name."""

    @pytest.mark.parametrize("tool", sorted(CORE_TOOLS))
    def test_core_tool_returns_core_tier(self, tool: str) -> None:
        tier = get_tier_by_tool(tool)
        assert tier.name == "core"
        assert tool in tier.tools

    @pytest.mark.parametrize("tool", sorted(EXTENDED_TOOLS))
    def test_extended_tool_returns_extended_tier(self, tool: str) -> None:
        tier = get_tier_by_tool(tool)
        assert tier.name == "extended"

    def test_unknown_tool_returns_full(self) -> None:
        tier = get_tier_by_tool("nonexistent_tool")
        assert tier.name == "full"


class TestCombinedTier:
    """Verify tier combination."""

    def test_core_plus_extended(self) -> None:
        combined = get_combined_tier("core", "extended")
        all_tools = CORE_TOOLS | EXTENDED_TOOLS
        assert combined.tools == all_tools

    def test_core_only(self) -> None:
        combined = get_combined_tier("core")
        assert combined.tools == CORE_TOOLS

    def test_empty_tiers_returns_core(self) -> None:
        combined = get_combined_tier()
        assert combined.name == "core"


class TestQueryResolution:
    """Verify query-to-tier resolution."""

    @pytest.mark.parametrize("query", [
        "这个文件的结构",
        "代码结构",
        "有什么类",
        "所有方法",
        "函数列表",
        "搜索 TODO",
        "谁调用了 processOrder",
        "影响范围",
        "大纲",
        "层级结构",
        "code structure",
        "find methods",
        "search pattern",
        "trace impact",
        "get outline",
    ])
    def test_core_queries_resolve_to_core(self, query: str) -> None:
        tier = resolve_query_to_tier(query)
        assert tier.name == "core", f"'{query}' resolved to {tier.name}"

    @pytest.mark.parametrize("query", [
        "文件多大",
        "修改安全吗",
        "谁依赖 UserService",
        "blast radius",
        "健康评分",
        "项目概览",
        "构建索引",
        "找文件",
    ])
    def test_extended_queries_resolve_to_extended(self, query: str) -> None:
        tier = resolve_query_to_tier(query)
        assert tier.name == "extended", f"'{query}' resolved to {tier.name}"

    def test_unknown_query_resolves_to_full(self) -> None:
        tier = resolve_query_to_tier("完全随机的问题 xyz")
        assert tier.name == "full"


class TestBenchmark:
    """Verify benchmark results."""

    def test_benchmark_returns_results(self) -> None:
        result = benchmark_tiers()
        assert isinstance(result, TierBenchmark)
        assert result.core_tokens > 0
        assert result.extended_tokens > 0
        assert result.full_tokens > 0

    def test_core_smaller_than_full(self) -> None:
        result = benchmark_tiers()
        assert result.core_tokens < result.full_tokens

    def test_extended_smaller_than_full(self) -> None:
        result = benchmark_tiers()
        assert result.extended_tokens < result.full_tokens

    def test_core_savings_significant(self) -> None:
        result = benchmark_tiers()
        if result.full_tokens > 0:
            assert result.core_savings_pct > 30, (
                f"Core savings too low: {result.core_savings_pct}%"
            )

    def test_tool_counts_add_up(self) -> None:
        result = benchmark_tiers()
        total = result.core_tools_count + result.extended_tools_count
        assert total == result.full_tools_count


class TestSkillLoadManager:
    """Verify on-demand loading with caching."""

    def test_load_for_query_core(self) -> None:
        mgr = SkillLoadManager()
        tier = mgr.load_for_query("代码结构")
        assert tier.name == "core"

    def test_load_for_query_extended(self) -> None:
        mgr = SkillLoadManager()
        tier = mgr.load_for_query("谁依赖 UserService")
        assert tier.name == "extended"

    def test_load_for_tool_core(self) -> None:
        mgr = SkillLoadManager()
        tier = mgr.load_for_tool("query_code")
        assert tier.name == "core"

    def test_load_for_tool_extended(self) -> None:
        mgr = SkillLoadManager()
        tier = mgr.load_for_tool("dependency_query")
        assert tier.name == "extended"

    def test_caching_hit_counts(self) -> None:
        mgr = SkillLoadManager()
        mgr.load_for_query("代码结构")
        mgr.load_for_query("代码结构")
        mgr.load_for_query("代码结构")
        stats = mgr.stats()
        assert stats["core"]["hits"] == 2
        assert stats["core"]["misses"] == 1
        assert stats["core"]["cached"] == 1

    def test_caching_extended_hit_counts(self) -> None:
        mgr = SkillLoadManager()
        mgr.load_for_tool("dependency_query")
        mgr.load_for_tool("list_files")
        stats = mgr.stats()
        assert stats["extended"]["hits"] == 1
        assert stats["extended"]["misses"] == 1

    def test_preload_core(self) -> None:
        mgr = SkillLoadManager()
        mgr.preload_core()
        stats = mgr.stats()
        assert stats["core"]["cached"] == 1
        assert stats["extended"]["cached"] == 0
        assert stats["full"]["cached"] == 0

    def test_preload_all(self) -> None:
        mgr = SkillLoadManager()
        mgr.preload_all()
        stats = mgr.stats()
        assert stats["core"]["cached"] == 1
        assert stats["extended"]["cached"] == 1
        assert stats["full"]["cached"] == 1

    def test_invalidate_clears_cache(self) -> None:
        mgr = SkillLoadManager()
        mgr.preload_all()
        mgr.invalidate()
        stats = mgr.stats()
        assert stats["core"]["cached"] == 0
        assert stats["extended"]["cached"] == 0
        assert stats["full"]["cached"] == 0

    def test_stats_structure(self) -> None:
        mgr = SkillLoadManager()
        stats = mgr.stats()
        for name in ("core", "extended", "full"):
            assert name in stats
            assert "hits" in stats[name]
            assert "misses" in stats[name]
            assert "cached" in stats[name]

    def test_multiple_tiers_independent(self) -> None:
        mgr = SkillLoadManager()
        mgr.load_for_query("代码结构")  # core
        mgr.load_for_query("谁依赖 X")  # extended
        stats = mgr.stats()
        assert stats["core"]["misses"] == 1
        assert stats["extended"]["misses"] == 1
        assert stats["full"]["misses"] == 0
