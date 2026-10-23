"""C 系语言（Java / TypeScript / JavaScript）源码的纯文本预处理。

``code_view`` 把注释与字符串内容替换为空格（保留引号与换行），使后续正则
只看到代码 token，行号保持不变。``class_spans`` 用花括号配对找出类体区间。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CLASS_HEADER = re.compile(
    r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
    r"(?:\s*<[^{]*?>)?"
    r"(?:\s+extends\s+([^{]*?))?"
    r"(?:\s+implements\s+([^{]*?))?\s*\{"
)


def code_view(text: str) -> str:
    """去掉注释与字符串内容，长度与换行不变。"""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(_blank(text[i:j]))
            i = j
        elif ch in "\"'`":
            j = _string_end(text, i, ch)
            out.append(ch + _blank(text[i + 1 : j - 1]) + (ch if j - 1 > i else ""))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _blank(chunk: str) -> str:
    return "".join("\n" if c == "\n" else " " for c in chunk)


def _string_end(text: str, start: int, quote: str) -> int:
    """字符串字面量结束后的下标（含结束引号）；单/双引号不跨行。"""
    i = start + 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        if c == "\n" and quote != "`":
            return i
        i += 1
    return len(text)


def brace_span_end(text: str, line: int) -> int:
    """从第 ``line`` 行开始的定义体（花括号配对）结束行；找不到时返回 ``line``。

    TS / JS 的 ``callers`` 行可能不带 ``end_line``，评分器用它补出调用方区间
    （与 dogfood ``bare_sweep.py`` 的 ``span_end`` 同一规则，但先去掉注释与字符串）。
    """
    code = code_view(text)
    lines = code.splitlines()
    depth = 0
    seen = False
    for index in range(max(line - 1, 0), len(lines)):
        depth += lines[index].count("{") - lines[index].count("}")
        seen = seen or "{" in lines[index]
        if seen and depth <= 0:
            return index + 1
    return line


def line_of(text: str, offset: int) -> int:
    """偏移 → 1 起始行号。"""
    return text.count("\n", 0, offset) + 1


@dataclass(frozen=True)
class ClassSpan:
    """一个类 / 接口体的位置与直接父类型名。"""

    name: str
    start: int
    end: int
    supers: tuple[str, ...]


def _type_names(clause: str | None) -> tuple[str, ...]:
    if not clause:
        return ()
    without_generics = re.sub(r"<[^<>]*>", "", re.sub(r"<[^<>]*>", "", clause))
    return tuple(
        part.strip().split(".")[-1]
        for part in without_generics.split(",")
        if part.strip()
    )


def class_spans(code: str) -> list[ClassSpan]:
    """``code``（已去注释字符串）里的类体区间。"""
    spans: list[ClassSpan] = []
    for match in _CLASS_HEADER.finditer(code):
        open_at = match.end() - 1
        depth = 0
        end = len(code)
        for j in range(open_at, len(code)):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        supers = _type_names(match.group(2)) + _type_names(match.group(3))
        spans.append(ClassSpan(match.group(1), open_at, end, supers))
    return spans


def enclosing_class(spans: list[ClassSpan], offset: int) -> ClassSpan | None:
    """包含 ``offset`` 的最内层类。"""
    inside = [s for s in spans if s.start <= offset <= s.end]
    return max(inside, key=lambda s: s.start) if inside else None
