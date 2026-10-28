"""统一查询语言的类型化查询错误与 ``Result`` 类型。

RFC-0041 §4：未知输入在边界处解析，所有可预期的失败都是值而非异常。
:class:`QueryError` 用封闭集合 :data:`ERROR_CODES` 中的错误码标识失败，
指向出错的片段，并附带具体的修复建议 (通常是 agent 可原样重发的修正后
查询)。部分结果不会丢失：在若干阶段执行之后产生的错误会把它们放在
``partial`` 中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

#: 查询文本为空或不是字符串。
EMPTY_QUERY = "UQL_EMPTY_QUERY"
#: 查询长度超过解析器的上限。
QUERY_TOO_LONG = "UQL_QUERY_TOO_LONG"
#: 步骤之间用了 ``|`` (或其他分隔符) 而不是 ``.`` 连接。
WRONG_SEPARATOR = "UQL_WRONG_SEPARATOR"
#: 引号或括号不配对。
UNBALANCED = "UQL_UNBALANCED"
#: 步骤不是 ``name(args)`` 形式。
INVALID_STEP = "UQL_INVALID_STEP"
#: 步骤名不属于本语言。
UNKNOWN_STAGE = "UQL_UNKNOWN_STAGE"
#: 步骤只存在于旧版 ``chain`` 方言中。
CHAIN_ONLY_STAGE = "UQL_CHAIN_ONLY_STAGE"
#: 该阶段不接受此关键字参数。
UNKNOWN_ARGUMENT = "UQL_UNKNOWN_ARGUMENT"
#: 参数类型错误或超出范围。
INVALID_ARGUMENT = "UQL_INVALID_ARGUMENT"
#: 阶段顺序非法 (例如在任何源阶段之前出现关系阶段)。
INVALID_ORDER = "UQL_INVALID_ORDER"
#: 在需要查询的位置只给了一个裸词。
BARE_WORD = "UQL_BARE_WORD"
#: ``select(...)`` 内的 TQL 选择器 (或裸选择器) 格式错误。
SELECTOR_SYNTAX = "UQL_SELECTOR_SYNTAX"
#: 选择器使用了求值器未实现的伪类。
UNKNOWN_PSEUDO_CLASS = "UQL_UNKNOWN_PSEUDO_CLASS"
#: 步骤数过多。
TOO_MANY_STAGES = "UQL_TOO_MANY_STAGES"
#: 续页游标格式错误、属于其他查询或已过期。
INVALID_CURSOR = "UQL_INVALID_CURSOR"
#: 游标签发后源码代次 (generation) 已变化。
STALE_CURSOR = "UQL_STALE_CURSOR"
#: 项目没有可用的索引。
INDEX_UNAVAILABLE = "UQL_INDEX_UNAVAILABLE"
#: 查询文本之外的工具参数 (limit、detail 等) 非法。
INVALID_TOOL_ARGUMENT = "UQL_INVALID_TOOL_ARGUMENT"

#: 错误码的封闭集合；测试固定了其内容，新增错误码必须是有意识的变更。
ERROR_CODES = frozenset(
    {
        EMPTY_QUERY,
        QUERY_TOO_LONG,
        WRONG_SEPARATOR,
        UNBALANCED,
        INVALID_STEP,
        UNKNOWN_STAGE,
        CHAIN_ONLY_STAGE,
        UNKNOWN_ARGUMENT,
        INVALID_ARGUMENT,
        INVALID_ORDER,
        BARE_WORD,
        SELECTOR_SYNTAX,
        UNKNOWN_PSEUDO_CLASS,
        TOO_MANY_STAGES,
        INVALID_CURSOR,
        STALE_CURSOR,
        INDEX_UNAVAILABLE,
        INVALID_TOOL_ARGUMENT,
    }
)


@dataclass(frozen=True)
class QueryError:
    """一个类型化失败，附带相关片段与修复建议。"""

    code: str
    message: str
    stage_index: int | None = None
    fragment: str | None = None
    suggestion: str | None = None
    fixed_query: str | None = None
    partial: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(f"unregistered UQL error code: {self.code}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        for key in ("stage_index", "fragment", "suggestion", "fixed_query"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.partial:
            out["partial"] = self.partial
        return out


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Err:
    error: QueryError

    @property
    def ok(self) -> bool:
        return False


Result = Ok[T] | Err
