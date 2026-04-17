#!/usr/bin/env python3
"""
Tiered Skill Loader — split SKILL.md into core (<500 token) and extended tiers.

Core tier: essential routing table for the 5 most common operations.
Extended tier: full routing table, SMART workflow, token strategies, combos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_SKILL_MD_PATH = Path(__file__).resolve().parent.parent.parent / (
    ".claude/skills/ts-analyzer-skills/SKILL.md"
)

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

# Core tools: the 5 most frequent operations (80% of queries land here)
CORE_TOOLS: frozenset[str] = frozenset({
    "analyze_code_structure",
    "query_code",
    "search_content",
    "trace_impact",
    "get_code_outline",
})

# Core routing entries: (trigger_phrase, tool, key_params)
CORE_ROUTES: list[tuple[str, str, dict[str, str]]] = [
    ("这个文件的结构", "analyze_code_structure", {"format_type": "compact"}),
    ("代码结构", "analyze_code_structure", {"format_type": "compact"}),
    ("有什么类", "query_code", {"query_key": "classes"}),
    ("所有方法", "query_code", {"query_key": "methods"}),
    ("函数列表", "query_code", {"query_key": "functions"}),
    ("搜索", "search_content", {"pattern": "QUERY"}),
    ("谁调用了", "trace_impact", {"symbol_name": "SYMBOL"}),
    ("影响范围", "trace_impact", {"symbol_name": "SYMBOL"}),
    ("大纲", "get_code_outline", {}),
    ("层级结构", "get_code_outline", {}),
]

# Core behavior rules (kept minimal)
CORE_RULES: list[str] = [
    "先分流再调用：判断用户需求属于哪个类别",
    "用绝对路径：所有 file_path 参数必须是绝对路径",
    "CJK 支持：中英文查询等价处理",
]

# Extended tools: everything beyond core
EXTENDED_TOOLS: frozenset[str] = frozenset({
    "check_code_scale",
    "extract_code_section",
    "list_files",
    "find_and_grep",
    "batch_search",
    "modification_guard",
    "get_project_summary",
    "build_project_index",
    "set_project_path",
    "check_tools",
    "dependency_query",
    "read_partial",
})


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed CJK/English."""
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    ascii_count = sum(1 for c in text if c.isascii())
    other = len(text) - cjk_count - ascii_count
    # CJK: ~2 chars/token, ASCII: ~4 chars/token, other: ~3 chars/token
    return int(cjk_count / 2 + ascii_count / 4 + other / 3)


# ---------------------------------------------------------------------------
# Skill tier data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkillTier:
    """A tier of skill content with metadata."""
    name: str
    content: str
    tools: frozenset[str]
    token_estimate: int
    char_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "char_count", len(self.content))


def _build_core_tier() -> SkillTier:
    """Build the minimal core tier (most common queries only)."""
    lines: list[str] = [
        "# ts-analyzer 核心路由",
        "",
        "当用户说... | 使用工具 | 关键参数",
        "---|---|---",
    ]
    for trigger, tool, params in CORE_ROUTES:
        param_str = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else "—"
        lines.append(f"「{trigger}」 | `{tool}` | {param_str}")
    lines.append("")
    lines.append("## 行为规则")
    for rule in CORE_RULES:
        lines.append(f"- {rule}")

    content = "\n".join(lines)
    return SkillTier(
        name="core",
        content=content,
        tools=CORE_TOOLS,
        token_estimate=_estimate_tokens(content),
    )


def _build_extended_tier() -> SkillTier:
    """Build the extended tier (all tools + advanced patterns)."""
    lines: list[str] = [
        "# ts-analyzer 扩展路由",
        "",
        "当用户说... | 使用工具 | 关键参数",
        "---|---|---",
    ]
    # Extended routing entries
    extended_routes: list[tuple[str, str, dict[str, str]]] = [
        ("文件多大", "check_code_scale", {}),
        ("复杂度", "check_code_scale", {}),
        ("第 X 行的代码", "extract_code_section", {"start_line": "X"}),
        ("找文件", "list_files", {"pattern": "*.ext"}),
        ("哪些文件", "list_files", {}),
        ("找到 .java 中的 XXX", "find_and_grep", {"file_pattern": "*.java"}),
        ("同时搜多个模式", "batch_search", {"patterns": "[...]"}),
        ("修改安全吗", "modification_guard", {"symbol_name": "X"}),
        ("项目概览", "get_project_summary", {}),
        ("构建索引", "build_project_index", {}),
        ("设置项目路径", "set_project_path", {"project_path": "/path"}),
        ("检查工具", "check_tools", {}),
        ("谁依赖 X", "dependency_query", {"query_type": "dependents"}),
        ("blast radius", "dependency_query", {"query_type": "blast_radius"}),
        ("健康评分", "dependency_query", {"query_type": "health_scores"}),
    ]
    for trigger, tool, params in extended_routes:
        param_str = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else "—"
        lines.append(f"「{trigger}」 | `{tool}` | {param_str}")

    lines.append("")
    lines.append("## SMART 工作流")
    lines.append("Set → Map(check_code_scale, get_code_outline) → "
                 "Analyze(query_code, analyze_code_structure) → "
                 "Retrieve(extract_code_section) → "
                 "Trace(trace_impact, modification_guard)")
    lines.append("")
    lines.append("## Token 优化策略")
    lines.append("- 大文件(>500行): format_type=compact 或 TOON")
    lines.append("- 大量结果(>50条): output_file + suppress_output")
    lines.append("- 只需特定元素: query_code + filter 而非全量分析")
    lines.append("- 项目级了解: get_project_summary (有缓存)")

    content = "\n".join(lines)
    return SkillTier(
        name="extended",
        content=content,
        tools=EXTENDED_TOOLS,
        token_estimate=_estimate_tokens(content),
    )


def _load_full_skill_md() -> str:
    """Load the full SKILL.md content from disk."""
    if _SKILL_MD_PATH.exists():
        return _SKILL_MD_PATH.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_core_tier() -> SkillTier:
    """Return the lightweight core tier (<500 tokens)."""
    return _build_core_tier()


def get_extended_tier() -> SkillTier:
    """Return the extended tier with all tools and patterns."""
    return _build_extended_tier()


def get_full_tier() -> SkillTier:
    """Return the full SKILL.md content as a tier."""
    content = _load_full_skill_md()
    return SkillTier(
        name="full",
        content=content,
        tools=CORE_TOOLS | EXTENDED_TOOLS,
        token_estimate=_estimate_tokens(content),
    )


def get_tier_by_tool(tool_name: str) -> SkillTier:
    """Return the tier that contains the given tool.

    If the tool is in the core set, return core tier.
    Otherwise return the extended tier.
    If neither matches, return full tier.
    """
    if tool_name in CORE_TOOLS:
        return get_core_tier()
    if tool_name in EXTENDED_TOOLS:
        return get_extended_tier()
    return get_full_tier()


def get_combined_tier(*tiers: str) -> SkillTier:
    """Combine multiple tiers by name into one SkillTier.

    Args:
        tiers: One or more of "core", "extended".

    Returns:
        A combined SkillTier with merged content and tools.
    """
    tier_map: dict[str, SkillTier] = {
        "core": get_core_tier(),
        "extended": get_extended_tier(),
    }
    selected = [tier_map[t] for t in tiers if t in tier_map]
    if not selected:
        return get_core_tier()

    merged_content = "\n\n".join(t.content for t in selected)
    merged_tools: frozenset[str] = frozenset()
    for t in selected:
        merged_tools = merged_tools | t.tools
    return SkillTier(
        name="+".join(tiers),
        content=merged_content,
        tools=merged_tools,
        token_estimate=_estimate_tokens(merged_content),
    )


# ---------------------------------------------------------------------------
# Benchmark utilities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierBenchmark:
    """Benchmark results comparing tiers."""
    core_tokens: int
    extended_tokens: int
    full_tokens: int
    core_tools_count: int
    extended_tools_count: int
    full_tools_count: int
    core_savings_pct: float = 0.0
    extended_savings_pct: float = 0.0

    def __post_init__(self) -> None:
        if self.full_tokens > 0:
            object.__setattr__(
                self, "core_savings_pct",
                round((1 - self.core_tokens / self.full_tokens) * 100, 1),
            )
            object.__setattr__(
                self, "extended_savings_pct",
                round((1 - self.extended_tokens / self.full_tokens) * 100, 1),
            )


def benchmark_tiers() -> TierBenchmark:
    """Run a benchmark comparing all tiers."""
    core = get_core_tier()
    ext = get_extended_tier()
    full = get_full_tier()
    return TierBenchmark(
        core_tokens=core.token_estimate,
        extended_tokens=ext.token_estimate,
        full_tokens=full.token_estimate,
        core_tools_count=len(core.tools),
        extended_tools_count=len(ext.tools),
        full_tools_count=len(full.tools),
    )


def resolve_query_to_tier(query: str) -> SkillTier:
    """Match a user query to the appropriate tier.

    Checks if the query matches a core tool pattern first,
    then falls back to extended, then full.
    """
    query_lower = query.lower()

    # Core patterns — longer/more-specific phrases first
    core_keywords: dict[str, str] = {
        "影响范围": "trace_impact",
        "影响": "trace_impact",
        "结构": "analyze_code_structure",
        "structure": "analyze_code_structure",
        "方法": "query_code",
        "methods": "query_code",
        "类": "query_code",
        "class": "query_code",
        "函数": "query_code",
        "functions": "query_code",
        "搜索": "search_content",
        "search": "search_content",
        "调用": "trace_impact",
        "impact": "trace_impact",
        "大纲": "get_code_outline",
        "outline": "get_code_outline",
    }
    for keyword, tool in core_keywords.items():
        if keyword in query_lower:
            if tool in CORE_TOOLS:
                return get_core_tier()

    # Extended patterns
    ext_keywords: dict[str, str] = {
        "依赖": "dependency_query",
        "dependency": "dependency_query",
        "blast": "dependency_query",
        "健康": "dependency_query",
        "health": "dependency_query",
        "修改": "modification_guard",
        "modify": "modification_guard",
        "安全": "modification_guard",
        "项目": "get_project_summary",
        "project": "get_project_summary",
        "索引": "build_project_index",
        "index": "build_project_index",
        "文件": "list_files",
        "files": "list_files",
        "多大": "check_code_scale",
        "scale": "check_code_scale",
    }
    for keyword, tool in ext_keywords.items():
        if keyword in query_lower:
            if tool in EXTENDED_TOOLS:
                return get_extended_tier()

    return get_full_tier()


# ---------------------------------------------------------------------------
# On-demand loading manager with caching
# ---------------------------------------------------------------------------

class SkillLoadManager:
    """On-demand skill loader with lazy loading and caching.

    Usage:
        mgr = SkillLoadManager()
        tier = mgr.load_for_query("代码结构")
        tier = mgr.load_for_tool("query_code")
        stats = mgr.stats()
    """

    def __init__(self) -> None:
        self._cache: dict[str, SkillTier] = {}
        self._hit_counts: dict[str, int] = {"core": 0, "extended": 0, "full": 0}
        self._miss_counts: dict[str, int] = {"core": 0, "extended": 0, "full": 0}

    def _get_or_build(self, tier_name: str) -> SkillTier:
        if tier_name in self._cache:
            self._hit_counts[tier_name] += 1
            return self._cache[tier_name]
        self._miss_counts[tier_name] += 1
        builders: dict[str, Callable[[], SkillTier]] = {
            "core": get_core_tier,
            "extended": get_extended_tier,
            "full": get_full_tier,
        }
        tier = builders[tier_name]()
        self._cache[tier_name] = tier
        return tier

    def load_for_query(self, query: str) -> SkillTier:
        """Load the appropriate tier for a user query."""
        resolved = resolve_query_to_tier(query)
        return self._get_or_build(resolved.name)

    def load_for_tool(self, tool_name: str) -> SkillTier:
        """Load the tier that contains a specific tool."""
        resolved = get_tier_by_tool(tool_name)
        return self._get_or_build(resolved.name)

    def preload_core(self) -> SkillTier:
        """Eagerly load the core tier."""
        return self._get_or_build("core")

    def preload_all(self) -> None:
        """Eagerly load all tiers into cache."""
        for name in ("core", "extended", "full"):
            self._get_or_build(name)

    def invalidate(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def stats(self) -> dict[str, dict[str, int]]:
        """Return cache hit/miss statistics."""
        result: dict[str, dict[str, int]] = {}
        for name in ("core", "extended", "full"):
            result[name] = {
                "hits": self._hit_counts[name],
                "misses": self._miss_counts[name],
                "cached": 1 if name in self._cache else 0,
            }
        return result
