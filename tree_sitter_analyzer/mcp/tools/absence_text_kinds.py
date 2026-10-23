"""#1633：JSON、Notebook 与模板文件中的名字——绝对否定不得弱于 grep。

dogfood 第 6 轮实测：以下 grep 能找到的引用仍让 ``nav callers`` 答
``complete, 0``，本模块把它们纳入 #1624 的非调用引用扫描（命中只会把答案降级为
``unknown`` 并列出位置，从不升级）：

* JSON（serverless ``function.json``、工具配置）里的 ``"pkg.mod:fn"``；
* ``.ipynb`` 代码单元里对函数的调用或引用；
* ``.html`` / ``.jinja`` / ``.j2`` / ``.jinja2`` 模板的 ``{{ fn() }}`` /
  ``{% ... %}`` 表达式。

设计取舍（宁可保守，但不让大量真正无人使用的函数失去 ``complete``）：

* JSON 只认“恰为引用”的字符串**值**：整串等于名字，或无空白的点号/冒号路径以
  该名字结尾（``"pkg.mod:fn"``、``"pkg.mod.fn"``）。键与含空白的散文串不计。
  大于 ``JSON_MAX_BYTES`` 的文件视为数据（golden 输出、lockfile、快照）不扫描。
  本仓库实测（git 跟踪 116 个 .json，共 587 KB；p99 42 KB，最大 68 KB 的
  ``grammar_snapshot.json`` 是快照数据）：64 KiB 上限保留 115 个、519 KB。
* Notebook 只扫描 ``cell_type == "code"`` 的单元，按 Python 源码处理（剔除注释与
  散文串，调用与名字引用都计入）；命中行映射回 ``.ipynb`` 文件中的源码行。
  无法解析的 Notebook 按原文整词扫描（只会更保守）。
* 模板只保留 ``{{ ... }}`` / ``{% ... %}`` 内的表达式，按整词扫描；HTML 散文不计。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from .absence_text_refs import CONFIG_LANGUAGE, is_config_file

#: 扫描列表中的“语言”标记。
JSON_LANGUAGE = "json"
NOTEBOOK_LANGUAGE = "notebook"
TEMPLATE_LANGUAGE = "template"
#: 超过此大小的 JSON 视为数据而非配置（见模块文档中的实测）。
JSON_MAX_BYTES = 64 * 1024
_TEMPLATE_SUFFIXES = frozenset({".html", ".jinja", ".j2", ".jinja2"})
#: JSON 字符串字面量（不跨行）。
_JSON_STRING = re.compile(r'"((?:\\.|[^"\\\n])*)"')
#: 模板表达式：``{{ ... }}`` 与 ``{% ... %}``。
_TEMPLATE_EXPRESSION = re.compile(r"\{\{([\s\S]*?)\}\}|\{%([\s\S]*?)%\}")

#: ``(text, language, bare) -> 剔除注释与散文后的代码文本``（Python 剥离器）。
Stripper = Callable[[str, str, "str | None"], str]


def text_language(rel_path: str) -> str | None:
    """``rel_path`` 需要做文本引用扫描时的语言标记；不扫描为 None。"""
    suffix = os.path.splitext(rel_path)[1].lower()
    if suffix == ".json":
        return JSON_LANGUAGE
    if suffix == ".ipynb":
        return NOTEBOOK_LANGUAGE
    if suffix in _TEMPLATE_SUFFIXES:
        return TEMPLATE_LANGUAGE
    return CONFIG_LANGUAGE if is_config_file(rel_path) else None


def wanted(abs_path: str) -> bool:
    """是否扫描该文件：语言受支持，且 JSON 不超过 ``JSON_MAX_BYTES``。"""
    return wanted_as(abs_path, text_language(abs_path))


def wanted_as(abs_path: str, language: str | None) -> bool:
    """:func:`wanted`，但 ``language`` 已由 :func:`text_language` 算出。

    语言只取决于路径字符串，可以随目录遍历结果一起记忆；JSON 的大小每次重新读取。
    """
    if language != JSON_LANGUAGE:
        return language is not None
    try:
        return os.path.getsize(abs_path) <= JSON_MAX_BYTES
    except OSError:
        # 读不到大小时照常列入：随后读取失败会让答案为 unknown，只会更保守。
        return True


def reference_text(text: str, language: str, bare: str | None, strip: Stripper) -> str:
    """把非源码文件化为“只剩可能引用”的文本，保留行号；配置文件原文返回。"""
    if language == JSON_LANGUAGE and bare:
        return _json_references(text, bare)
    if language == NOTEBOOK_LANGUAGE:
        return _notebook_code(text, bare, strip)
    if language == TEMPLATE_LANGUAGE:
        return _template_expressions(text)
    return text


def _line_of(text: str, offset: int) -> int:
    """``offset`` 所在的行号（从 0 起）。"""
    return text.count("\n", 0, offset)


def _json_references(text: str, bare: str) -> str:
    """只在“值恰为引用”的 JSON 字符串所在行留下名字。"""
    reference = re.compile(r"(?:[\w$.:-]*[.:])?" + re.escape(bare))
    lines = [""] * (text.count("\n") + 1)
    for match in _JSON_STRING.finditer(text):
        if text[match.end() :].lstrip(" \t\r\n").startswith(":"):
            continue  # 对象的键，不是值。
        if reference.fullmatch(match.group(1)):
            lines[_line_of(text, match.start())] = f" {bare} "
    return "\n".join(lines)


def _notebook_code(text: str, bare: str | None, strip: Stripper) -> str:
    """代码单元按 Python 剥离后放回其在 ``.ipynb`` 中的行；其余行留空。"""
    try:
        cells = json.loads(text).get("cells")
    except (ValueError, AttributeError):
        return text
    if not isinstance(cells, list):
        return text
    out = [""] * (text.count("\n") + 1)
    cursor = 0
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        items = source.splitlines(keepends=True) if isinstance(source, str) else source
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            return text
        if not items:
            continue
        line_of: list[int] = []
        row = _line_of(text, cursor)
        for item in items:
            # 源码行在文件中以 JSON 字符串出现；找不到（如压缩格式）时沿用上一行。
            encoded = json.dumps(item, ensure_ascii=False)
            found = text.find(encoded, cursor)
            if found >= 0:
                row, cursor = _line_of(text, found), found + len(encoded)
            line_of.extend([row] * item.count("\n"))
        line_of.append(row)
        stripped = strip("".join(items), "python", bare).split("\n")
        for index, code in enumerate(stripped):
            if code.strip():
                row = line_of[min(index, len(line_of) - 1)]
                out[row] = f"{out[row]} {code}" if out[row] else code
    return "\n".join(out)


def _template_expressions(text: str) -> str:
    """只保留模板表达式内容；其余文本替换为等量换行。"""
    pieces: list[str] = []
    last = 0
    for match in _TEMPLATE_EXPRESSION.finditer(text):
        pieces.append("\n" * text.count("\n", last, match.start()))
        pieces.append(f" {match.group(1) or match.group(2) or ''} ")
        last = match.end()
    pieces.append("\n" * text.count("\n", last))
    return "".join(pieces)
