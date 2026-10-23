"""把一次 ``nav action=callers`` 回答与判定器结果比对。

核心不变量（RFC-0028 §1、#1740 / #1758 / #1772）：回答为 ``complete`` 时，
判定器找到的每个 ``target`` / ``possible`` 调用点都必须被某个已列出的调用方
覆盖（同一文件、调用点行号落在调用方定义的行区间内，或调用方为模块级）。
否则即为一次**错误的 complete**。

非 ``complete`` 回答不会是错误 complete，但仍按“已列出 / 有证据 / 静默丢失”
分类，供报告与召回棘轮使用。
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.wrong_complete.sites import Site
from scripts.wrong_complete.token_text import brace_span_end

#: 回答里带 ``(file, line)`` 调用点证据的字段。
EVIDENCE_FIELDS = (
    "name_only_sites",
    "unresolved_sites",
    "unresolved_inbound_sites",
    "excluded_sites",
    "non_call_reference_sites",
)
_MODULE_CALLERS = frozenset({"<module>", "<toplevel>", ""})


@dataclass(frozen=True)
class ListedCaller:
    """回答里列出的一个调用方（定义区间）。"""

    file: str
    name: str
    line: int
    end_line: int

    def covers(self, site: Site) -> bool:
        """本调用方是否覆盖 ``site``。"""
        if self.file != site.file:
            return False
        if self.name in _MODULE_CALLERS and self.line <= 0:
            # 没有行号的模块级调用方：覆盖该文件里的模块级调用点。
            return site.caller == "<module>"
        # 函数调用方与带调用行的 ``<module>`` 调用方（``module_scope_caller``）都按行区间。
        return self.line <= site.line <= self.end_line


@dataclass(frozen=True)
class Score:
    """一次回答的评分。"""

    completeness: str
    listed: tuple[Site, ...]
    evidenced: tuple[Site, ...]
    silent: tuple[Site, ...]

    @property
    def is_complete(self) -> bool:
        """回答是否声称 ``complete``。"""
        return self.completeness == "complete"

    @property
    def wrong_complete(self) -> tuple[Site, ...]:
        """``complete`` 回答漏掉的必须覆盖点；非 ``complete`` 回答恒为空。"""
        return (*self.evidenced, *self.silent) if self.is_complete else ()

    def as_dict(self) -> dict[str, Any]:
        """JSON 友好的摘要。"""
        return {
            "completeness": self.completeness,
            "listed": [_site_dict(s) for s in self.listed],
            "evidenced": [_site_dict(s) for s in self.evidenced],
            "silent": [_site_dict(s) for s in self.silent],
            "wrong_complete": [_site_dict(s) for s in self.wrong_complete],
        }


def _site_dict(site: Site) -> dict[str, Any]:
    return {
        "file": site.file,
        "line": site.line,
        "kind": site.kind,
        "verdict": site.verdict,
        "reason": site.reason,
        "caller": site.caller,
    }


def normalize_path(path: object) -> str:
    """统一成正斜杠相对路径。"""
    return str(path or "").replace("\\", "/").removeprefix("./")


def listed_callers(
    answer: Mapping[str, Any], sources: Mapping[str, str] | None = None
) -> list[ListedCaller]:
    """解析回答里的 ``callers``。

    缺失 ``end_line`` 时：C 系文件且给了 ``sources`` 则按花括号配对补出区间，
    否则退化为单行区间（只会让覆盖判定更严格）。
    """
    out: list[ListedCaller] = []
    for row in answer.get("callers") or []:
        file = normalize_path(row.get("file"))
        line = int(row.get("line") or 0)
        end = int(row.get("end_line") or 0)
        if not end:
            end = _span_end(file, line, (sources or {}).get(file))
        out.append(ListedCaller(file, str(row.get("name") or ""), line, end))
    return out


def _span_end(file: str, line: int, text: str | None) -> int:
    """定义从 `line` 开始的函数的结束行。"""
    if text is None:
        return line
    if not file.endswith(".py"):
        return brace_span_end(text, line)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return line
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            if line in (node.lineno, first):
                return int(node.end_lineno or line)
    return line


def evidence_keys(answer: Mapping[str, Any]) -> set[tuple[str, int]]:
    """回答各证据字段里的 ``(file, line)``。"""
    keys: set[tuple[str, int]] = set()
    for field in EVIDENCE_FIELDS:
        for row in answer.get(field) or []:
            if isinstance(row, Mapping) and row.get("line") is not None:
                keys.add((normalize_path(row.get("file")), int(row["line"])))
    return keys


def score(
    answer: Mapping[str, Any],
    sites: Iterable[Site],
    sources: Mapping[str, str] | None = None,
) -> Score:
    """按必须覆盖点给回答评分；``sources`` 用于补出缺失的调用方区间。"""
    callers = listed_callers(answer, sources)
    evidence = evidence_keys(answer)
    listed: list[Site] = []
    evidenced: list[Site] = []
    silent: list[Site] = []
    for site in sites:
        if not site.must_cover:
            continue
        if any(caller.covers(site) for caller in callers):
            listed.append(site)
        elif site.key() in evidence:
            evidenced.append(site)
        else:
            silent.append(site)
    return Score(
        completeness=str(answer.get("completeness")),
        listed=tuple(listed),
        evidenced=tuple(evidenced),
        silent=tuple(silent),
    )


def caller_keys(answer: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    """``(file, caller name)`` 集合，用于比较两次回答的调用方是否相同。"""
    return frozenset((c.file, c.name) for c in listed_callers(answer))
