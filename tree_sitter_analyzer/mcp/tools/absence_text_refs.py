"""#1624：绝对否定不得弱于 grep——代码字符串与配置文件中的名字。

#1598 的扫描只看同语言的已索引源码，并丢弃一切不“恰为标识符”的字符串，于是
下列 grep 能找到的引用都被漏掉，``0 callers, complete`` 比 grep 更弱：

* 入口点与 ``importlib`` 解析串：``"pkg.mod:func"``、``"pkg.mod.func"``；
* 字符串里的代码：``exec("defs.f()")``、``python -c "...f()"``；
* 配置 / 脚本文件：``pyproject.toml``、``setup.cfg``、``.github/workflows/*.yml``。

设计取舍（宁可保守：命中只会把答案降级为 ``unknown`` 并列出位置）：

* 代码字符串：名字以整词出现，且（串内无空白——单个 token，如点号/冒号路径）
  或（紧邻 ``.`` / ``:`` 之后，或紧跟 ``(``——代码形态）时计为引用。散文串
  （``"the size is fine"``）与独立成句的三引号串（文档字符串，运行时无作用）
  不计，以免真正无人使用的方法被大量误降级。
* 配置文件：只扫描会“调用”名字的配置与脚本（toml/cfg/ini/yml/yaml、shell /
  PowerShell / batch、Makefile、Dockerfile 等），其中的整词出现全部计入。
  Markdown/rst/txt 等散文文档与 JSON（多为测试数据 / golden 输出）不扫描：
  它们点名方法只是描述，计入会让几乎所有方法都无法答 ``complete``。
  （#1633 起 JSON 改为只认“恰为引用”的字符串值，见 ``absence_text_kinds``。）

#1633（dogfood 第 6 轮）补上两种仍弱于 grep 的代码串：

* ``exec`` / ``eval`` / ``compile`` 的字符串实参本身就是代码：整个串体按代码保留，
  裸名引用（``exec("h = fn\\nh()")``）也计入；``re.compile(...)`` 等方法调用不算。
* 文档字符串中的 doctest 行（``>>> `` / ``... `` 之后的内容）会被 doctest 执行，
  按代码保留；文档字符串的其余散文仍不计。

JSON、Notebook 与模板文件见 ``absence_text_kinds``。
"""

from __future__ import annotations

import os
import re

#: 配置文件在扫描列表中的“语言”标记：原文扫描，不剔除注释与字符串。
CONFIG_LANGUAGE = "config"
#: 会调用名字的配置 / 脚本文件后缀。
_CONFIG_SUFFIXES = frozenset(
    {
        ".toml",
        ".cfg",
        ".ini",
        ".yml",
        ".yaml",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".bat",
        ".cmd",
        ".mk",
    }
)
#: 无后缀（或以名字区分）的构建文件。
_CONFIG_NAMES = frozenset({"makefile", "gnumakefile", "justfile", "procfile"})
#: 允许名字之前紧邻的代码形态分隔符（点号路径、入口点冒号）。
_CODE_PREFIXES = frozenset(".:")
#: 字符串前紧邻的“把串当代码执行”的调用（不含 ``re.compile`` 等方法调用）。
_CODE_CALL = re.compile(r"(?<![\w.$])(?:exec|eval|compile)\s*\(\s*[rRbBuU]*$")
#: 回看调用名的字符数上限。
_CODE_CALL_LOOKBACK = 64
#: doctest 的提示符。
_DOCTEST_PROMPTS = (">>>", "...")


def is_config_file(rel_path: str) -> bool:
    """``rel_path`` 是否属于需要扫描的配置 / 脚本文件。"""
    name = os.path.basename(rel_path).lower()
    if name in _CONFIG_NAMES or name.startswith("dockerfile"):
        return True
    return os.path.splitext(name)[1] in _CONFIG_SUFFIXES


def is_docstring(text: str, start: int, end: int) -> bool:
    """``text[start:end]`` 处的三引号串是否独立成句（文档字符串，运行时无作用）。"""
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    # 去掉 r/b/u 等前缀字母后，前面只剩缩进才算独立成句。
    if prefix.rstrip("rRbBuU").strip():
        return False
    line_end = text.find("\n", end)
    rest = text[end : len(text) if line_end < 0 else line_end].strip()
    return not rest or rest.startswith("#")


def string_code(
    text: str, span: tuple[int, int], body: str, docstring: bool, bare: str | None
) -> str | None:
    """非标识符字符串中须按代码保留的部分（保留行号）；可整体剔除时为 None。

    ``docstring`` 表示这是 Python 三引号串，需再判断是否独立成句。
    """
    start, end = span
    if _CODE_CALL.search(text, max(0, start - _CODE_CALL_LOOKBACK), start):
        return f" {body} "
    if docstring and is_docstring(text, start, end):
        return doctest_code(body)
    return string_mention(body, bare) if bare else None


def doctest_code(body: str) -> str:
    """文档字符串中 doctest 提示符之后的代码；其余行留空（保留行号）。"""
    lines: list[str] = []
    for line in body.split("\n"):
        stripped = line.lstrip()
        code = stripped.startswith(_DOCTEST_PROMPTS)
        lines.append(f" {stripped[3:]}" if code else "")
    return "\n".join(lines)


def string_mention(body: str, bare: str) -> str | None:
    """代码形态地提到 ``bare`` 的串：命中行替换为名字，其余行留空（保留行号）。

    没有任何代码形态的命中时返回 None（调用方按普通字符串剔除）。
    """
    pattern = re.compile(r"(?<![\w$])" + re.escape(bare) + r"(?![\w$])")
    single_token = not any(char.isspace() for char in body)
    hit = False
    lines: list[str] = []
    for line in body.split("\n"):
        if any(
            _code_like(line, match, single_token) for match in pattern.finditer(line)
        ):
            lines.append(f" {bare} ")
            hit = True
        else:
            lines.append("")
    return "\n".join(lines) if hit else None


def _code_like(line: str, match: re.Match[str], single_token: bool) -> bool:
    if single_token:
        return True
    before = line[match.start() - 1] if match.start() else ""
    return before in _CODE_PREFIXES or line[match.end() :].lstrip().startswith("(")
