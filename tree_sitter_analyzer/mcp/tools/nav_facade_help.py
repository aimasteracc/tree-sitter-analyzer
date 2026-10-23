"""nav 门面 bespoke 动作的 help schema（#1562）。

``callers`` / ``callees`` / ``context`` 走 bespoke 闭包，此前 ``nav action=help``
对它们返回 ``ACTION_SCHEMA_UNAVAILABLE``。这里集中声明闭包真实转发的参数，
路由与 schema 共用同一份清单，二者不会漂移。
"""

from __future__ import annotations

from typing import Any

from .facade_discovery import build_bespoke_action_schema

# callers/callees scope=point 路由转发给 inner 的参数。
POINT_RELATION_KEYS = (
    "function_name",
    "file_path",
    "limit",
    "include_bodies",
    "output_format",
)
# callers/callees scope=graph 路由转发给 call_graph inner 的参数。
GRAPH_RELATION_KEYS = ("function_name", "file_path", "depth", "output_format")
# context 路由转发给 CodeGraphContextTool 的参数。
CONTEXT_KEYS = (
    "task",
    "max_nodes",
    "max_code_blocks",
    "output_format",
    "include_graph",
    "access_mode",
    "snapshot_id",
    "source_generation",
)

_SCOPE_PROPERTY: dict[str, Any] = {
    "type": "string",
    "enum": ["point", "graph"],
    "default": "point",
    "description": (
        "point = direct 1-hop relation (fast); graph = full call-graph traversal."
    ),
}
_CONTEXT_ALIAS_PROPERTIES: dict[str, Any] = {
    "symbol": {
        "type": "string",
        "description": "Symbol name; used as task when task is omitted.",
    },
    "query": {
        "type": "string",
        "description": (
            "Free-text query; used as task when task and symbol are omitted."
        ),
    },
}


def register_nav_help_schemas(
    facade: Any, callers_inner: Any, callees_inner: Any, context_inner: Any
) -> None:
    """为 callers/callees/context 登记 help schema。"""
    for action, inner in (("callers", callers_inner), ("callees", callees_inner)):
        facade.register_bespoke_schema(
            action,
            build_bespoke_action_schema(
                action,
                inner,
                keep=POINT_RELATION_KEYS,
                extra_properties={"scope": _SCOPE_PROPERTY},
            ),
        )
    facade.register_bespoke_schema(
        "context",
        build_bespoke_action_schema(
            "context",
            context_inner,
            keep=CONTEXT_KEYS,
            extra_properties=_CONTEXT_ALIAS_PROPERTIES,
            required_any_of=("task", "symbol", "query"),
        ),
    )
