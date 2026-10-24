"""把逐个调用方手工展开的 ``nav`` 调用序列引向一次 ``search action=uql`` (RFC-0041)。

``nav action=callers`` 之后对其列出的调用方再调 ``test_map`` (或再调 ``callers``)
是 agent 手工拼多跳问题的典型做法：基准 (``benchmarks/unified_query``) 中
"谁调用 X、哪些测试覆盖这些调用方" 需要 13 次调用，而一条 UQL 查询只需 1 次，
并且逐阶段报告完整性。

提示只在检测到这种序列时出现，单跳查询的响应保持不变，不为它付出字节。
记忆是进程内、有界的：只保留最近几次 callers 答案列出的调用方名称。
"""

from __future__ import annotations

import re
from collections import deque
from typing import Any

#: 记住最近多少次 ``nav callers`` 答案。
_MAX_ANSWERS = 4
#: 每次答案最多记住多少个调用方名称 (与 callers 的 limit 上限一致)。
_MAX_NAMES = 500
#: 能安全放进 UQL 字符串字面量的符号名 (含 ``Cls.method`` 形式)。
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def uql_literal(name: str) -> str | None:
    return f"'{name}'" if _SAFE_NAME.match(name) else None


def _caller_names(result: Any) -> set[str]:
    """一次 callers 答案中列出的调用方名称 (裸名与 ``Cls.name`` 两种形式)。"""
    if not isinstance(result, dict):
        return set()
    names: set[str] = set()
    for entry in result.get("callers") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name or name.startswith("<"):
            continue
        names.add(name)
        cls = entry.get("class")
        if isinstance(cls, str) and cls:
            names.add(f"{cls}.{name}")
        if len(names) >= _MAX_NAMES:
            break
    return names


class CallerFollowUps:
    """记住最近的 callers 答案，识别对其调用方的逐个追问。"""

    def __init__(self) -> None:
        self._answers: deque[tuple[str, frozenset[str]]] = deque(maxlen=_MAX_ANSWERS)

    def record(self, symbol: Any, result: Any) -> None:
        if not isinstance(symbol, str) or not symbol:
            return
        names = _caller_names(result)
        if names:
            self._answers.append((symbol, frozenset(names)))

    def source_of(self, name: Any) -> str | None:
        """若 ``name`` 是最近某次 callers 答案列出的调用方，返回被查询的符号。"""
        if not isinstance(name, str) or not name:
            return None
        bare = name.rpartition(".")[2]
        for symbol, names in reversed(self._answers):
            if symbol != name and (name in names or bare in names):
                return symbol
        return None


def hint_after_test_map(source: str) -> str | None:
    """在 callers 之后对其调用方逐个调 test_map 时的提示。"""
    literal = uql_literal(source)
    if literal is None:
        return None
    next_step = (
        f"Mapping tests caller by caller? One call answers it with per-stage "
        f'completeness: search action=uql query="symbol({literal}).callers().tests()" '
        "(or .untested() for callers without tests)."
    )
    return next_step


def hint_after_callers(source: str) -> str | None:
    """在 callers 之后对其调用方再逐个调 callers 时的提示。"""
    literal = uql_literal(source)
    if literal is None:
        return None
    next_step = (
        f"Walking callers hop by hop? One call: search action=uql "
        f'query="symbol({literal}).callers(depth=2)" (depth up to 5; add '
        ".filter(path='src/') to restrict), with per-stage completeness."
    )
    return next_step


def hint_for_caller_tree(symbol: str, depth: int) -> str:
    """caller_tree 不声明完整性；需要影响集 (含测试与文件) 时指向 uql impact()。"""
    literal = uql_literal(symbol)
    if literal is None:
        return ""
    bounded = min(max(depth, 1), 10)
    next_step = (
        " The tree makes no completeness claim; for the impact set with its "
        "tests, files and completeness: search action=uql "
        f'query="symbol({literal}).impact(depth={bounded})".'
    )
    return next_step


def append_next_step(result: Any, hint: str | None) -> Any:
    """把提示追加到答案的 ``agent_summary.next_step`` (不存在时创建)。"""
    if hint is None or not isinstance(result, dict) or result.get("success") is False:
        return result
    summary = result.get("agent_summary")
    summary = dict(summary) if isinstance(summary, dict) else {}
    current = summary.get("next_step")
    summary["next_step"] = f"{current} {hint}" if current else hint
    return {**result, "agent_summary": summary}
