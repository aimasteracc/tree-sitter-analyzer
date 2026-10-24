"""统一查询语言唯一的中间表示 (IR)。

RFC-0041 §2：TQL 选择器与 chain 管道都解析为这一个 IR，由
:mod:`tree_sitter_analyzer.uql.parser` 负责。MCP 适配器 (``search
action=uql`` / ``tql_execute`` / ``chain``) 与 CLI 参数都消费它，
没有任何一方会重新解释查询文本。

:class:`Query` 是一个有序的阶段元组：

* **源** (:class:`Select`、:class:`SymbolSource`) 开启管道；
* **关系** (:class:`Relate`) 用相关符号替换当前集合，并开启一个新的输出分组；
* **精炼** (:class:`Refine`、:class:`HasTests`、:class:`Take`、
  :class:`Sort`) 在原地收窄或排序当前分组。

所有节点都是 frozen 的，因此解析后的查询是可哈希、无副作用的值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..hyphae.ast import SelectorList

RelationName = Literal["callers", "callees", "tests", "impact"]


@dataclass(frozen=True)
class RawStep:
    """按原样记录的一个 ``name(args)`` 步骤 (chain 方言的 IR)。"""

    name: str
    args: list[Any]
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class Select:
    """源：在符号索引上求值的 TQL 选择器。"""

    text: str
    selector: SelectorList


@dataclass(frozen=True)
class SymbolSource:
    """源：名称精确匹配的定义 (允许 ``Class.method`` 形式)。"""

    names: tuple[str, ...]
    file: str | None = None


@dataclass(frozen=True)
class Relate:
    """关系：当前集合的 callers / callees / tests / impact。"""

    relation: RelationName
    depth: int = 1


@dataclass(frozen=True)
class Refine:
    """精炼：按属性保留 (``filter``) 或剔除 (``exclude``)。"""

    op: Literal["filter", "exclude"]
    predicates: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class HasTests:
    """精炼：保留有测试 (``tested``) 或无测试 (``untested``) 的符号。"""

    want_tests: bool


@dataclass(frozen=True)
class Take:
    """精炼：保留当前分组的前 ``n`` 个符号。"""

    n: int


@dataclass(frozen=True)
class Sort:
    """精炼：对当前分组排序。"""

    by: Literal["name", "file", "line"]
    desc: bool = False


Stage = Select | SymbolSource | Relate | Refine | HasTests | Take | Sort
SOURCE_STAGES = (Select, SymbolSource)
REFINEMENT_STAGES = (Refine, HasTests, Take, Sort)


@dataclass(frozen=True)
class Query:
    """一个已解析、已校验的查询。"""

    text: str
    stages: tuple[Stage, ...]
    dialect: Literal["uql", "tql"] = "uql"


def stage_name(stage: Stage) -> str:
    """阶段的表层名称，用于输出键与 reason 前缀。"""
    if isinstance(stage, Select):
        return "select"
    if isinstance(stage, SymbolSource):
        return "symbol"
    if isinstance(stage, Relate):
        return stage.relation
    if isinstance(stage, Refine):
        return stage.op
    if isinstance(stage, HasTests):
        return "tested" if stage.want_tests else "untested"
    if isinstance(stage, Take):
        return "take"
    return "sort"
