"""tree-sitter-analyzer 的统一、携带证据的查询语言 (RFC-0041)。

一套语法 (TQL 选择器 + 管道阶段)、一个 IR (:mod:`.ir`)、一个解析器
(:mod:`.parser`)。执行引擎、各阶段实现以及 ``search action=uql`` 适配器
将在后续 PR 中提供。
"""

from __future__ import annotations

from .parser import parse_chain, parse_query

__all__ = ["parse_chain", "parse_query"]
