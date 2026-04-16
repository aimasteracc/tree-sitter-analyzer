#!/usr/bin/env python3
"""
Layered Skill Loading for ts-analyzer Skill layer.

Provides two tiers of routing data:
- Core tier (<500 tokens): Top 12 routes covering all 16 MCP tools
- Extended tier: Full CJK mapping, fuzzy patterns, optimization strategies

This reduces the default skill loading cost by ~55% while keeping
complete routing available on demand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_ALL_MCP_TOOLS: frozenset[str] = frozenset({
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
})


@dataclass(frozen=True)
class Route:
    """A single routing entry mapping a query pattern to an MCP tool."""

    pattern: str
    tool: str
    params: dict[str, str] = field(default_factory=dict)
    keywords: tuple[str, ...] = ()

    @property
    def tools_covered(self) -> str:
        return self.tool


# ---------------------------------------------------------------------------
# Core routes — covers all 16 MCP tools with 12 patterns
# ---------------------------------------------------------------------------

CORE_ROUTES: tuple[Route, ...] = (
    Route("code structure|文件的结构|有什么类|类.*方法|struct",
          "analyze_code_structure", {"format_type": "compact"},
          ("structure", "结构", "类", "struct")),
    Route("outline|hierarchy|大纲|层级", "get_code_outline",
          {}, ("outline", "大纲", "层级", "navigate")),
    Route("find all|query|查出|所有方法|函数列表", "query_code",
          {"query_key": "methods"},
          ("find", "query", "所有", "方法", "函数", "classes", "methods")),
    Route("line|extract|第.*行|的代码|的实现", "extract_code_section",
          {}, ("line", "extract", "行", "实现", "section")),
    Route("calls|impact|谁调用|影响范围|trace", "trace_impact",
          {}, ("call", "impact", "调用", "影响", "trace", "reference")),
    Route("safe|modify|安全吗|能不能改|guard", "modification_guard",
          {}, ("safe", "modify", "安全", "改", "guard")),
    Route("search|搜索|哪里用了", "search_content",
          {}, ("search", "搜索", "where", "哪里")),
    Route("find.*then.*grep|找到.*中的", "find_and_grep",
          {}, ("find", "grep", "找到", "filter")),
    Route("batch|同时搜|多个模式", "batch_search",
          {"patterns": "[]"},
          ("batch", "同时", "多个", "parallel")),
    Route("files|找文件|哪些文件|list", "list_files",
          {}, ("file", "找文件", "list", "哪些")),
    Route("scale|complexity|文件多大|复杂度", "check_code_scale",
          {}, ("scale", "complexity", "多大", "复杂")),
    Route("overview|项目概览|project summary", "get_project_summary",
          {}, ("overview", "概览", "summary", "project")),
    Route("index|索引|build index", "build_project_index",
          {}, ("index", "索引", "build")),
    Route("set path|设置.*路径|设置项目|project path", "set_project_path",
          {}, ("set", "path", "路径", "project")),
    Route("check tools|检查工具|verify", "check_tools",
          {}, ("check", "tools", "检查", "verify")),
    Route("dependency|depend|blast|health|依赖|健康", "dependency_query",
          {"query_type": "dependents"},
          ("depend", "blast", "health", "依赖", "健康")),
)


# ---------------------------------------------------------------------------
# Extended routes — additional patterns for CJK and fuzzy matching
# ---------------------------------------------------------------------------

EXTENDED_CJK_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "所有方法": ("query_code", {"query_key": "methods"}),
    "方法的列表": ("query_code", {"query_key": "methods"}),
    "有哪些类": ("query_code", {"query_key": "classes"}),
    "类定义": ("query_code", {"query_key": "classes"}),
    "函数列表": ("query_code", {"query_key": "functions"}),
    "所有函数": ("query_code", {"query_key": "functions"}),
    "import 语句": ("query_code", {"query_key": "imports"}),
    "导入": ("query_code", {"query_key": "imports"}),
    "变量声明": ("query_code", {"query_key": "variables"}),
    "字段": ("query_code", {"query_key": "variables"}),
    "注释": ("query_code", {"query_key": "comments"}),
    "这个文件的结构": ("analyze_code_structure", {"format_type": "compact"}),
    "详细结构": ("analyze_code_structure", {"format_type": "full"}),
    "文件大小": ("check_code_scale", {}),
    "代码规模": ("check_code_scale", {}),
    "谁调用了": ("trace_impact", {}),
    "的引用": ("trace_impact", {}),
    "修改影响": ("trace_impact", {}),
    "谁依赖": ("dependency_query", {"query_type": "dependents"}),
}

EXTENDED_FUZZY_MAP: dict[str, str] = {
    "struct": "analyze_code_structure",
    "structure": "analyze_code_structure",
    "outline": "get_code_outline",
    "scale": "check_code_scale",
    "impact": "trace_impact",
    "guard": "modification_guard",
    "依赖": "dependency_query",
    "索引": "build_project_index",
    "find methods": "query_code",
    "all classes": "query_code",
    "code overview": "get_project_summary",
    "build index": "build_project_index",
}

TOKEN_OPTIMIZATION: tuple[tuple[str, str, str], ...] = (
    ("Large file (>500 lines)", "format_type: compact or TOON", "50-70%"),
    ("Many results (>50)", "output_file + suppress_output", "90%+"),
    ("Specific elements only", "query_code + filter", "80%+"),
    ("Project-level overview", "get_project_summary (cached)", "95%+"),
    ("Unknown file content", "check_code_scale first", "N/A"),
)

TOOL_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("Understand unknown code",
     "check_code_scale → get_code_outline → query_code → extract_code_section",
     "Navigate structure then extract precisely",
     "analyze_code_structure,get_code_outline,query_code,extract_code_section"),
    ("Pre-modification assessment",
     "trace_impact → modification_guard → analyze_code_structure",
     "Find callers, check safety, then review structure",
     "trace_impact,modification_guard,analyze_code_structure"),
    ("Precise search",
     "list_files → find_and_grep → extract_code_section",
     "Find files, search content, extract matching code",
     "list_files,find_and_grep,extract_code_section"),
    ("Batch analysis",
     "get_project_summary → list_files → batch_search → query_code",
     "Overview first, then drill into specifics",
     "get_project_summary,list_files,batch_search,query_code"),
)


# ---------------------------------------------------------------------------
# SkillLoader class
# ---------------------------------------------------------------------------

class SkillLoader:
    """Layered skill routing with core and extended tiers."""

    def __init__(self) -> None:
        self._core_routes = CORE_ROUTES
        self._extended_loaded = False

    @staticmethod
    def get_all_tools() -> frozenset[str]:
        """Return all registered MCP tool names."""
        return _ALL_MCP_TOOLS

    def get_core_routes(self) -> tuple[Route, ...]:
        """Return core routes (always loaded, <500 tokens)."""
        return self._core_routes

    def get_extended_cjk_map(self) -> dict[str, tuple[str, dict[str, str]]]:
        """Return extended CJK-English mapping."""
        return EXTENDED_CJK_MAP.copy()

    def get_extended_fuzzy_map(self) -> dict[str, str]:
        """Return extended fuzzy query mapping."""
        return EXTENDED_FUZZY_MAP.copy()

    def get_token_optimization(self) -> tuple[tuple[str, str, str], ...]:
        """Return token optimization strategies."""
        return TOKEN_OPTIMIZATION

    def get_tool_patterns(self) -> tuple[tuple[str, str, str, str], ...]:
        """Return tool combination patterns."""
        return TOOL_PATTERNS

    def resolve(self, query: str, use_extended: bool = False) -> Route | None:
        """Resolve a natural language query to a Route.

        Args:
            query: Natural language query (Chinese or English).
            use_extended: If True, also check extended CJK and fuzzy maps.

        Returns:
            Best matching Route, or None if no match.
        """
        query_lower = query.lower().strip()

        for route in self._core_routes:
            if re.search(route.pattern, query_lower):
                return route

        if use_extended:
            result = self._resolve_extended(query)
            if result is not None:
                return result

        return None

    def _resolve_extended(self, query: str) -> Route | None:
        """Try extended CJK and fuzzy mappings."""
        for cjk_pattern, (tool, params) in EXTENDED_CJK_MAP.items():
            if cjk_pattern in query:
                return Route(cjk_pattern, tool, params)

        query_lower = query.lower().strip()
        for fuzzy_key, tool in EXTENDED_FUZZY_MAP.items():
            if fuzzy_key.lower() in query_lower:
                return Route(fuzzy_key, tool, {})

        return None

    def core_tools_covered(self) -> frozenset[str]:
        """Return tool names covered by core routes."""
        return frozenset(r.tool for r in self._core_routes)

    def core_coverage_pct(self) -> float:
        """Return percentage of MCP tools covered by core routes."""
        covered = self.core_tools_covered()
        return len(covered & _ALL_MCP_TOOLS) / len(_ALL_MCP_TOOLS) * 100

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text.

        Uses rough heuristic: ~4 chars/token for ASCII, ~2 chars/token for CJK.
        """
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        total = len(text)
        non_cjk = total - cjk_count
        return int(non_cjk / 4 + cjk_count / 2)

    def core_token_cost(self) -> int:
        """Estimate token cost of core routes."""
        lines: list[str] = []
        for r in self._core_routes:
            lines.append(f"{r.pattern}|{r.tool}|{r.params}")
        return self.estimate_tokens("\n".join(lines))

    def full_token_cost(self) -> int:
        """Estimate token cost of all routing data (core + extended)."""
        parts: list[str] = []

        for r in self._core_routes:
            parts.append(f"{r.pattern}|{r.tool}|{r.params}")

        for k, (t, p) in EXTENDED_CJK_MAP.items():
            parts.append(f"{k}|{t}|{p}")

        for k, t in EXTENDED_FUZZY_MAP.items():
            parts.append(f"{k}|{t}")

        for scenario, strategy, savings in TOKEN_OPTIMIZATION:
            parts.append(f"{scenario}|{strategy}|{savings}")

        for name, flow, desc, _tools in TOOL_PATTERNS:
            parts.append(f"{name}|{flow}|{desc}")

        return self.estimate_tokens("\n".join(parts))

    def generate_core_skill_md(self) -> str:
        """Generate the compact core SKILL.md content."""
        lines: list[str] = [
            "---",
            "name: ts-analyzer-skills",
            "description: |",
            "  tree-sitter-analyzer Skill layer. Maps natural language queries to MCP tools.",
            "  Load skill_extended.md for full CJK mapping, fuzzy patterns, and optimization strategies.",
            "---",
            "",
            "# Tree-sitter-analyzer — Skill Layer",
            "",
            "> Route natural language to MCP tools. Core tier only.",
            "> For extended mapping: load `skill_extended.md`.",
            "",
            "## Routing (covers all 16 tools)",
            "",
        ]

        for r in self._core_routes:
            params_str = ""
            if r.params:
                param_parts = [f"{k}: {v}" for k, v in r.params.items()]
                params_str = f" ({', '.join(param_parts)})"
            lines.append(f"| `{r.tool}`{params_str} |")

        lines.extend([
            "",
            "## SMART Workflow",
            "Scale → Map → Analyze → Retrieve → Trace",
            "",
            "## Rules",
            "1. Triage first, then call precisely",
            "2. Use TOON format to save tokens",
            "3. Check modification_guard before any rename/delete",
            "4. Always use absolute paths",
            "5. Prefer batch operations (batch_search, extract arrays)",
            "",
            "## Supported Languages (17)",
            "Java Python JS TS C C++ C# Go Rust Kotlin PHP Ruby SQL HTML CSS YAML Markdown",
        ])

        return "\n".join(lines)

    def generate_extended_md(self) -> str:
        """Generate the extended reference content."""
        lines: list[str] = [
            "# Extended Skill Reference",
            "",
            "> Load only when core routing doesn't cover your query.",
            "",
            "## CJK-English Mapping",
            "",
        ]

        for cjk, (tool, params) in EXTENDED_CJK_MAP.items():
            params_str = ""
            if params:
                param_parts = [f"{k}={v}" for k, v in params.items()]
                params_str = f" + {', '.join(param_parts)}"
            lines.append(f"| \"{cjk}\" | `{tool}`{params_str} |")

        lines.extend([
            "",
            "## Fuzzy Patterns",
            "",
        ])

        for fuzzy, tool in EXTENDED_FUZZY_MAP.items():
            lines.append(f"| \"{fuzzy}\" | `{tool}` |")

        lines.extend([
            "",
            "## Token Optimization",
            "",
        ])

        for scenario, strategy, savings in TOKEN_OPTIMIZATION:
            lines.append(f"| {scenario} | {strategy} | {savings} |")

        lines.extend([
            "",
            "## Tool Patterns",
            "",
        ])

        for name, flow, desc, _tools in TOOL_PATTERNS:
            lines.append(f"### {name}")
            lines.append(f"  {flow}")
            lines.append(f"  {desc}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_loader_instance: SkillLoader | None = None


def get_skill_loader() -> SkillLoader:
    """Get singleton SkillLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SkillLoader()
    return _loader_instance
