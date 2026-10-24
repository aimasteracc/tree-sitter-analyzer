"""旧版 ``search action=chain`` DSL —— RFC-0041 解析器之上的薄适配层。

RFC-0041 §2 规定步骤级解析只有一个负责者：
:mod:`tree_sitter_analyzer.uql.steps` / :mod:`tree_sitter_analyzer.uql.parser`。
本模块保留 chain 方言的历史接口 —— 以相同消息抛出 ``ValueError`` 的
``parse_chain``、``_ChainStep`` 以及各参数辅助函数 —— 使
``codegraph_query_tool`` 及其调用方无需改动。
"""

from __future__ import annotations

from typing import Any

from ...uql.errors import Err
from ...uql.ir import RawStep
from ...uql.parser import CHAIN_KWARGS
from ...uql.parser import parse_chain as _parse_chain_result

#: chain 步骤类型即统一 IR 的原始步骤 (只有一种表示)。
_ChainStep = RawStep

_SUPPORTED_STEPS = frozenset(CHAIN_KWARGS)
_ALLOWED_KWARGS = CHAIN_KWARGS


def parse_chain(query: str) -> list[_ChainStep]:
    """把安全的链式查询解析为步骤列表 (输入非法时抛出 ``ValueError``)。"""
    result = _parse_chain_result(query)
    if isinstance(result, Err):
        raise ValueError(result.error.message)
    return result.value


def step_to_dict(step: _ChainStep) -> dict[str, Any]:
    return {"name": step.name, "args": step.args, "kwargs": step.kwargs}


def first_str(step: _ChainStep, *, required: bool) -> str:
    if step.args and isinstance(step.args[0], str):
        return step.args[0]
    query = step.kwargs.get("query")
    if isinstance(query, str):
        return query
    if required:
        raise ValueError(f"{step.name}() requires a string query")
    return ""


def string_args(step: _ChainStep, *, required: bool) -> list[str]:
    values: list[str] = []
    if step.args:
        first = step.args[0]
        if isinstance(first, str):
            values = [first]
        elif isinstance(first, list):
            values = first
    query = step.kwargs.get("query")
    if isinstance(query, str):
        values = [query]
    elif isinstance(query, list):
        values = query
    values = [value for value in values if isinstance(value, str) and value.strip()]
    if required and not values:
        raise ValueError(f"{step.name}() requires a string query")
    return values


def first_int(step: _ChainStep, default: int) -> int:
    if step.args and isinstance(step.args[0], int):
        return step.args[0]
    limit_value = step.kwargs.get("limit")
    if isinstance(limit_value, int):
        return limit_value
    return default


def int_kw(step: _ChainStep, name: str, default: int, cap: int) -> int:
    value = step.kwargs.get(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, cap))


def bool_kw(step: _ChainStep, name: str, default: bool) -> bool:
    value = step.kwargs.get(name, default)
    return bool(value)


__all__ = [
    "_ChainStep",
    "bool_kw",
    "first_int",
    "first_str",
    "int_kw",
    "parse_chain",
    "step_to_dict",
    "string_args",
]
