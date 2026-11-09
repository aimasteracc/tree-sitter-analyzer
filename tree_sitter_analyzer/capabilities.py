"""机器可读的能力清单（agent 的规划面，dogfood §12.4）。

help 是给人读的；agent 规划需要的是：**有哪些动作、前置条件是什么、大概花多少、
最小可用调用长什么样**。本模块从注册表派生这份清单，一次给出 8 个 facade 的
全部 action，不读索引、不扫源码，可在任何回合便宜地调用。
"""

from __future__ import annotations

from typing import Any

#: 零索引即可作答的 action（instant tier）；其余需要先建索引。
_INSTANT_ACTIONS: frozenset[str] = frozenset(
    {
        "text",  # search: 原生字面量检索（grep 替代）
        "symbol",  # search: BM25 符号检索（无索引时退化）
        "outline",  # structure: 单文件大纲
        "analyze",  # structure: 结构分析
        "signatures",  # structure: 签名列表
        "ast_path",  # structure: AST 路径
        "read",  # structure: 局部读取
        "explore",  # structure: 文件探索
        "sitemap",  # structure: 目录地图
        "file",  # health: 单文件健康度
        "scale",  # health: 规模检查
        "patterns",  # health: 模式统计
        "imports",  # health: 导入清单
        "help",  # 所有 facade: 自描述 schema
    }
)

#: 每个 facade 的最小可用调用示例（占位符用 ``<...>``）。
_EXAMPLES: dict[str, dict[str, Any]] = {
    "nav": {"action": "callers", "function_name": "<symbol>"},
    "search": {"action": "text", "query": "<literal>"},
    "structure": {"action": "outline", "file_path": "<file>"},
    "health": {"action": "file", "file_path": "<file>"},
    "index": {"action": "cache", "mode": "index"},
    "project": {"action": "overview"},
    "edit": {"action": "safe", "file_path": "<file>"},
    "viz": {"action": "graph", "scope": "call_graph"},
}


def build_capability_manifest(project_root: str) -> dict[str, Any]:
    """返回 ``{tools: {name: {actions: {...}}}, tiers: {...}}`` 的规划清单。

    每个 action 条目包含：

    - ``tier``：``instant``（零索引）或 ``indexed``（需要索引）；
    - ``preconditions``：``[]`` 或 ``["index"]``；
    - ``cost_class``：与 tier 同值（保留独立字段，方便以后细化为 p50/p95）；
    - ``example``：该 facade 的最小可用调用（占位符 ``<...>``）；
    - ``self_describing``：``action=help`` 恒为真，其余为假。
    """
    from .mcp._tool_registry import create_tool_registry

    tools: dict[str, Any] = {}
    for name, tool in create_tool_registry(project_root)[0]:
        definition = tool.get_tool_definition()
        schema = definition.get("inputSchema") or definition
        actions = list(
            (schema.get("properties") or {}).get("action", {}).get("enum", ())
        )
        entries: dict[str, Any] = {}
        for action in actions:
            tier = "instant" if action in _INSTANT_ACTIONS else "indexed"
            entries[action] = {
                "tier": tier,
                "preconditions": [] if tier == "instant" else ["index"],
                "cost_class": tier,
                "example": _EXAMPLES.get(name, {"action": action}),
                "self_describing": action == "help",
            }
        tools[name] = {
            "purpose": definition.get("description", ""),
            "actions": entries,
        }
    return {
        "tools": tools,
        "tiers": {
            "instant": sorted(_INSTANT_ACTIONS),
            "indexed": sorted(
                {
                    action
                    for tool in tools.values()
                    for action in tool["actions"]
                    if action not in _INSTANT_ACTIONS
                }
            ),
        },
    }
