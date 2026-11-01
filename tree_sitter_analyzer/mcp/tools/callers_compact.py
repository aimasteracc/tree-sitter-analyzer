"""``nav action=callers format=compact``：一行一个调用方 + 一行完整性判定（#1853）。

紧凑答复是完整答复的**投影**，不是另一次计算：调用方取自完整答复的 ``callers``
列表（顺序、截断都相同），判定取自同一 RFC-0040 证明结果 ``completeness`` /
``completeness_reasons``。因此紧凑判定不可能比完整判定更乐观——只有完整答复
说 ``complete`` 时才输出 ``complete``；任何无法识别的值一律按 ``unknown`` 输出。

格式（以两个空格分隔，便于逐行读取）::

    callers of <function>: <caller_count>
    <name>  <file>:<line>  <resolution_kind>
    ...
    +<hidden> more (raise limit)                 # 仅在截断时
    verdict: complete
    verdict: incomplete (<top reasons>); details: format=verbose
    verdict: unknown (<top reasons>); details: format=verbose

本模块只依赖标准库，可在离线脚本里对已存的完整答复做同一投影（用于测量）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

COMPACT_FORMAT = "compact"
VERBOSE_FORMAT = "verbose"
#: ``nav action=callers`` 接受的 ``format`` 值；默认 ``verbose`` 即原有完整答复。
CALLERS_FORMATS = (COMPACT_FORMAT, VERBOSE_FORMAT)
#: 判定行列出的原因码个数，其余以 ``+N`` 计数。
TOP_REASONS = 3

_NOT_COMPLETE_LABELS = frozenset({"incomplete"})
_DETAILS = "; details: format=verbose"

FORMAT_PROPERTY: dict[str, Any] = {
    "type": "string",
    "enum": list(CALLERS_FORMATS),
    "default": VERBOSE_FORMAT,
    "description": (
        "verbose (default) = full answer with evidence; compact = one line per "
        "caller (name  file:line  resolution_kind) plus one completeness verdict "
        "line, derived from the same RFC-0040 result."
    ),
}


def _reasons(answer: Mapping[str, Any]) -> list[str]:
    reasons = answer.get("completeness_reasons")
    if isinstance(reasons, list | tuple) and reasons:
        return [str(reason) for reason in reasons]
    single = answer.get("completeness_reason")
    return [str(single)] if single else []


def verdict_label(answer: Mapping[str, Any]) -> str:
    """``complete`` 仅当完整答复本身为 ``complete``；其余不可识别值为 ``unknown``。"""
    completeness = answer.get("completeness")
    if isinstance(completeness, str):
        if completeness == "complete":
            return "complete"
        if completeness in _NOT_COMPLETE_LABELS:
            return completeness
    return "unknown"


def compact_verdict(answer: Mapping[str, Any]) -> str:
    """判定行正文：标签，非 complete 时附前 ``TOP_REASONS`` 个原因码。"""
    label = verdict_label(answer)
    if label == "complete":
        return label
    reasons = _reasons(answer)
    shown = reasons[:TOP_REASONS]
    if len(reasons) > len(shown):
        shown.append(f"+{len(reasons) - len(shown)}")
    return f"{label} ({', '.join(shown)})" if shown else label


def caller_line(caller: Mapping[str, Any]) -> str:
    """一个调用方：``name  file:line  resolution_kind``。"""
    name = caller.get("name") or "?"
    file = caller.get("file") or "?"
    line = caller.get("line") or 0
    kind = caller.get("resolution_kind") or caller.get("callee_resolution") or "unknown"
    return f"{name}  {file}:{line}  {kind}"


def compact_callers(answer: Any) -> Any:
    """把完整 callers 答复投影为紧凑答复；失败答复原样返回。"""
    if not isinstance(answer, dict) or answer.get("success") is False:
        return answer
    callers = [c for c in answer.get("callers") or [] if isinstance(c, Mapping)]
    total = answer.get("caller_count")
    total = total if isinstance(total, int) and total >= 0 else len(callers)
    lines = [f"callers of {answer.get('function') or '?'}: {total}"]
    lines.extend(caller_line(caller) for caller in callers)
    hidden = total - len(callers)
    if hidden > 0:
        lines.append(f"+{hidden} more (raise limit)")
    verdict = compact_verdict(answer)
    label = verdict_label(answer)
    lines.append(f"verdict: {verdict}{'' if label == 'complete' else _DETAILS}")
    compact: dict[str, Any] = {"success": True}
    if isinstance(answer.get("verdict"), str):
        compact["verdict"] = answer["verdict"]
    # 机器可读的判定与完整答复相同（信封契约：非 complete 必须给出原因码）。
    compact.update(
        {
            "format": COMPACT_FORMAT,
            "completeness": label,
            "completeness_reasons": [] if label == "complete" else _reasons(answer),
            "answer": "\n".join(lines),
        }
    )
    return compact


def invalid_format(value: Any) -> dict[str, Any] | None:
    """``format`` 不在允许值内时的错误答复；合法时为 ``None``。"""
    if value in CALLERS_FORMATS:
        return None
    return {
        "success": False,
        "error_code": "INVALID_ARGUMENT",
        "error": (
            f"format={value!r} is not supported for action=callers; "
            f"use one of: {', '.join(CALLERS_FORMATS)}"
        ),
    }


def compact_scope_error() -> dict[str, Any]:
    """``format=compact`` 只适用于 ``scope=point`` 的直接调用方答复。"""
    return {
        "success": False,
        "error_code": "INVALID_ARGUMENT",
        "error": (
            "format=compact applies to scope=point (direct callers) only; "
            "drop format or use scope=point"
        ),
    }


def with_hint(compact: Any, hint: str | None) -> Any:
    """RFC-0041 跟进提示：紧凑答复以顶层 ``next_step`` 携带。"""
    if hint is None or not isinstance(compact, dict) or compact.get("success") is False:
        return compact
    return {**compact, "next_step": hint}
