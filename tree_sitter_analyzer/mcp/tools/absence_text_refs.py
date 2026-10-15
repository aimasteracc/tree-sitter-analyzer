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
