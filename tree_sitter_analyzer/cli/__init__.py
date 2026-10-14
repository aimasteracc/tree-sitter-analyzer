#!/usr/bin/env python3
"""
CLI Package

Command-line interface components using the Command Pattern.

导出名称通过 PEP 562 ``__getattr__`` 延迟解析：导入任意 ``cli.*`` 子模块
（例如 ``--version`` 路径上的 ``cli.argument_validator``）时，不再连带
加载 info_commands / 分析引擎等重型模块。
"""

import importlib
from typing import Any

# 名称 -> (相对模块, 属性名)；首次访问时导入并缓存到模块全局。
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "InfoCommand": (".info_commands", "InfoCommand"),
    "ListQueriesCommand": (".info_commands", "ListQueriesCommand"),
    "DescribeQueryCommand": (".info_commands", "DescribeQueryCommand"),
    "ShowLanguagesCommand": (".info_commands", "ShowLanguagesCommand"),
    "ShowExtensionsCommand": (".info_commands", "ShowExtensionsCommand"),
    "main": ("..cli_main", "main"),
    "get_analysis_engine": ("..core.analysis_engine", "get_analysis_engine"),
}

# 这些框架导出在依赖不可导入时回退为 None（与旧版 try/except 行为一致）。
_OPTIONAL_EXPORTS = frozenset({"main", "get_analysis_engine", "query_loader"})


def _resolve_export(name: str) -> Any:
    """导入并返回导出名称对应的对象。"""
    if name == "query_loader":
        from ..query_loader import QueryLoader

        return QueryLoader()
    module_name, attr = _LAZY_EXPORTS[name]
    return getattr(importlib.import_module(module_name, __name__), attr)


def __getattr__(name: str) -> Any:
    """按需解析包级导出，并缓存结果以保证后续访问返回同一对象。"""
    if name not in _LAZY_EXPORTS and name != "query_loader":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        value = _resolve_export(name)
    except ImportError:
        if name not in _OPTIONAL_EXPORTS:
            raise
        value = None
    globals()[name] = value
    return value


__all__ = [
    "InfoCommand",
    "ListQueriesCommand",
    "DescribeQueryCommand",
    "ShowLanguagesCommand",
    "ShowExtensionsCommand",
    # Core framework exports
    "query_loader",
    "get_analysis_engine",
    "main",
]
