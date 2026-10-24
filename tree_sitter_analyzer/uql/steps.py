"""两种方言共用的词法层：切分 ``a(..).b(..)`` 并解析参数。

这是步骤级解析的唯一负责者 (RFC-0041 §2)。旧版 ``chain`` DSL
(``mcp/tools/_codegraph_query_dsl.py``) 与统一管道语法都调用它，二者都不会
自行重新切分查询文本。参数只允许字面量 (``ast.literal_eval`` 加上 JS 风格的
``true/false/null``)，用户输入绝不会被求值。

错误消息与 RFC-0041 之前的 chain 解析器保持逐字节一致，因为现有调用方和
测试会按消息内容匹配。
"""

from __future__ import annotations

import ast
import re
from typing import Any

from .errors import (
    INVALID_ARGUMENT,
    INVALID_STEP,
    UNBALANCED,
    WRONG_SEPARATOR,
    Err,
    Ok,
    QueryError,
    Result,
)
from .ir import RawStep

MAX_STRING_ARG_LENGTH = 160
MAX_LIST_ARGS = 8

_STEP_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", flags=re.S)

# LLM agent 在这种 jQuery 风格 DSL 中会自然写出 JS/JSON 风格的裸词。
# Python 的 ast.literal_eval 只认识 True/False/None，否则 ``answer(compact=true)``
# 会报出晦涩的 "malformed node or string" 错误，把 agent 从低成本的单次 chain
# 调用逼回缓慢的多次调用路径。
_JS_BARE_LITERALS: dict[str, Any] = {
    "true": True,
    "false": False,
    "null": None,
    "none": None,
}

PIPE_MESSAGE = (
    "chain steps are separated by '.', not '|' — e.g. "
    "search('IndexShard').callers().  To search for a literal '|' "
    "(e.g. a type union), quote it: search('string | number')."
)


def has_unquoted_pipe(query: str) -> bool:
    """当 ``query`` 在单/双引号范围之外含有 ``|`` 时返回 True。

    顶层的管道符是误用分隔符 (#574)；引号参数内的管道符
    (如 ``search('string | number')``) 则是合法的搜索文本。
    """
    in_single = in_double = escaped = False
    for ch in query:
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "|" and not in_single and not in_double:
            return True
    return False


def pipe_error(query: str) -> QueryError:
    fixed = _replace_unquoted_pipes(query)
    return QueryError(
        WRONG_SEPARATOR,
        PIPE_MESSAGE,
        fragment="|",
        suggestion="Join steps with '.'",
        fixed_query=fixed,
    )


def _replace_unquoted_pipes(query: str) -> str:
    """把引号外的 ``|`` 换成 ``.`` 并去掉它两侧的空白；引号内的字面量原样保留。"""
    out: list[str] = []
    in_single = in_double = escaped = skip_space = False
    for ch in query:
        quoted = in_single or in_double
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "|" and not quoted:
            while out and out[-1].isspace():
                out.pop()
            out.append(".")
            skip_space = True
            continue
        elif skip_space and not quoted and ch.isspace():
            continue
        skip_space = False
        out.append(ch)
    return "".join(out)


def split_steps(query: str) -> Result[list[str]]:
    """按顶层 ``.`` (引号与括号之外) 切分。"""
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False
    for idx, ch in enumerate(query):
        if escape:
            escape = False
            continue
        if ch == "\\" and quote:
            escape = True
            continue
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return Err(
                    QueryError(
                        UNBALANCED,
                        "unbalanced ')' in query chain",
                        fragment=query[max(0, idx - 20) : idx + 1],
                        suggestion="Remove the extra ')' or add the matching '('.",
                    )
                )
        elif ch == "." and depth == 0:
            parts.append(query[start:idx].strip())
            start = idx + 1
    if quote or depth != 0:
        return Err(
            QueryError(
                UNBALANCED,
                "unbalanced quote or parentheses in query chain",
                suggestion="Close every quote and parenthesis.",
            )
        )
    parts.append(query[start:].strip())
    return Ok([part for part in parts if part])


def parse_step(
    part: str,
    *,
    index: int,
    allowed_kwargs: dict[str, frozenset[str]],
    unknown_step: Any,
) -> Result[RawStep]:
    """解析一个 ``name(args)`` 步骤。

    对不在 ``allowed_kwargs`` 中的名称，由 ``unknown_step(name, index, part)``
    构造该方言的错误 (两种方言的措辞不同)。
    """
    match = _STEP_RE.fullmatch(part)
    if not match:
        return Err(
            QueryError(
                INVALID_STEP,
                f"invalid chain step: {part!r}",
                stage_index=index,
                fragment=part,
                suggestion="Write each step as name(args), e.g. callers().",
            )
        )
    name = match.group(1)
    if name not in allowed_kwargs:
        error: QueryError = unknown_step(name, index, part)
        return Err(error)
    try:
        expr = ast.parse(f"_f({match.group(2)})", mode="eval")
    except SyntaxError as exc:
        return Err(
            QueryError(
                INVALID_STEP,
                f"invalid chain step args: {part!r} ({exc.msg})",
                stage_index=index,
                fragment=part,
                suggestion="Arguments must be literals: 'text', 3, true, ['a', 'b'].",
            )
        )
    call = expr.body
    if not isinstance(call, ast.Call):
        return Err(
            QueryError(INVALID_STEP, f"invalid chain step args: {part!r}", index, part)
        )
    try:
        args = [literal(node) for node in call.args]
        kwargs: dict[str, Any] = {}
        for kw in call.keywords:
            if kw.arg is None:
                raise _ArgError(f"{name}() does not support **kwargs", None)
            if kw.arg not in allowed_kwargs[name]:
                allowed = ", ".join(sorted(allowed_kwargs[name])) or "(none)"
                raise _ArgError(
                    f"{name}() does not support keyword {kw.arg!r}",
                    f"Accepted keywords for {name}(): {allowed}.",
                    unknown=True,
                )
            kwargs[kw.arg] = literal(kw.value)
    except _ArgError as exc:
        from .errors import UNKNOWN_ARGUMENT

        return Err(
            QueryError(
                UNKNOWN_ARGUMENT if exc.unknown else INVALID_ARGUMENT,
                exc.message,
                stage_index=index,
                fragment=part,
                suggestion=exc.suggestion,
            )
        )
    except ValueError as exc:
        return Err(
            QueryError(
                INVALID_ARGUMENT,
                str(exc),
                stage_index=index,
                fragment=part,
                suggestion="Arguments must be literals: 'text', 3, true, ['a', 'b'].",
            )
        )
    return Ok(RawStep(name=name, args=args, kwargs=kwargs))


class _ArgError(Exception):
    def __init__(self, message: str, suggestion: str | None, unknown: bool = False):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.unknown = unknown


def literal(node: ast.AST) -> Any:
    """返回字面量参数值；非字面量一律抛出 ``ValueError``。"""
    # 在 literal_eval 之前接受裸 true/false/null (不区分大小写)，
    # 否则 literal_eval 会把它们当作未定义的名称拒绝。
    if isinstance(node, ast.Name) and node.id.lower() in _JS_BARE_LITERALS:
        return _JS_BARE_LITERALS[node.id.lower()]
    value = ast.literal_eval(node)
    if isinstance(value, str):
        if len(value) > MAX_STRING_ARG_LENGTH:
            raise ValueError(f"string arguments must be <= {MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ARGS:
            raise ValueError(f"list arguments must contain <= {MAX_LIST_ARGS} items")
        if not all(isinstance(item, str) for item in value):
            raise ValueError("list arguments must contain only strings")
        if any(len(item) > MAX_STRING_ARG_LENGTH for item in value):
            raise ValueError(f"string arguments must be <= {MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, int | bool | float) or value is None:
        return value
    raise ValueError("chain arguments must be scalar literals")
