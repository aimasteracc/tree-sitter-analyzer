#!/usr/bin/env python3
"""把工具实例上记忆化的调用图绑定到索引身份（#1611）。

#1564 只为 callers/callees 的内存调用图绑定了 ``index_identity``；impact、
navigate、overview、pr_review 与可视化 hub 仍在首次使用时构建
``CachedCallGraph`` 并永久复用。同一 MCP 服务器内刷新索引后，它们继续用
旧图回答，且没有任何过期信号；impact / pr_review 的 SAFE/CAUTION 判定和
测试选择都依赖这张图，因此这是信任问题。

本模块提供唯一的共享入口，避免五份拷贝：记录构建时的索引身份，身份变化时
丢弃旧图并重建。身份检查只做几条聚合 SQL（见 ``relation_freshness``），
不遍历源码树。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from .relation_freshness import index_identity

#: 记录构建时索引身份的属性名；与 #1564 的 relation mixin 同名同义。
IDENTITY_ATTR = "_graph_index_identity"

_GraphT = TypeVar("_GraphT")


def index_bound_graph(
    owner: Any,
    project_root: str | None,
    build: Callable[[], _GraphT],
    *,
    attr: str = "_call_graph",
    on_discard: Callable[[], None] | None = None,
) -> _GraphT:
    """返回 ``owner.<attr>`` 上的调用图；索引身份变化时先丢弃再重建。

    - 尚无图：调用 ``build`` 构建，并记录构建前的身份（构建期间若有写入，
      下一次调用最多多重建一次，与 #1564 相同）。
    - 已有图且记录的身份与当前不同：丢弃旧图，先调用 ``on_discard``
      （供共享缓存的持有者一并释放），再重建。
    - 未记录身份的图（例如测试直接注入的替身）原样保留：无法判断其来源，
      也就无从判定过期。
    - 未绑定项目根时没有索引身份可比：已有图原样返回，否则交给 ``build``
      （由它报告缺少项目根）。
    """
    graph = getattr(owner, attr, None)
    if not project_root:
        if graph is None:
            graph = build()
            setattr(owner, attr, graph)
        return graph
    identity = index_identity(project_root)
    recorded = getattr(owner, IDENTITY_ATTR, None)
    if graph is not None and recorded is not None and recorded != identity:
        setattr(owner, attr, None)
        setattr(owner, IDENTITY_ATTR, None)
        graph = None
        if on_discard is not None:
            on_discard()
    if graph is None:
        graph = build()
        setattr(owner, attr, graph)
        setattr(owner, IDENTITY_ATTR, identity)
    return graph


def reset_index_bound_graph(owner: Any, *, attr: str = "_call_graph") -> None:
    """清空记忆化的调用图及其身份（项目根切换时调用）。"""
    setattr(owner, attr, None)
    setattr(owner, IDENTITY_ATTR, None)
