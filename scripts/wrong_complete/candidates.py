"""真实仓库扫描的目标抽样（不使用 TSA，移植自 dogfood ``bare_sweep.py`` / ``defs_regex.py``）。

候选：类方法，名字至少 4 个字符、不是 dunder、名字里不含 ``test``，且该名字在
整个仓库里**只有一个定义**；再要求至少 1 行、至多 40 行“看起来像调用”的行
（``.name(``，与 dogfood 的 ``git grep -w`` 过滤相同）。按种子打乱后取前 ``count`` 个。
"""

from __future__ import annotations

import ast
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.wrong_complete.sites import Target

_JAVA_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "new",
        "synchronized",
        "else",
        "throw",
        "super",
        "this",
    }
)
_JAVA_METHOD = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|protected|private|static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:<[^>]+>\s+)?[\w.$<>\[\]?, ]+?\s+(\w+)\s*\([^;{]*\)?\s*(?:throws\s+[\w.$, ]+)?\s*\{?\s*$"
)
_JAVA_CLASS = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|sealed|non-sealed|strictfp)\s+)*"
    r"(?:class|interface|enum|record|@interface)\s+(\w+)"
)
MAX_CALL_LINES = 40


@dataclass(frozen=True)
class Candidate:
    """一个抽中的目标与它的 ``git grep`` 调用行数。"""

    target: Target
    call_lines: int


def tracked_files(repo: Path) -> list[str]:
    """``git ls-files``（正斜杠相对路径）。"""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def python_methods(repo: Path, files: list[str]) -> list[Target]:
    """``ast`` 枚举的全部类方法定义。"""
    found: list[Target] = []
    for rel in files:
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        found.append(Target(rel, item.name, node.name, item.lineno))
    return found


def java_methods(repo: Path, files: list[str]) -> list[Target]:
    """正则枚举的 Java 方法定义（外层类取最近的类声明行）。"""
    found: list[Target] = []
    for rel in files:
        if not rel.endswith(".java"):
            continue
        owner: str | None = None
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            match = _JAVA_CLASS.search(line)
            if match and not stripped.startswith(("//", "*")):
                owner = match.group(1)
            method = _JAVA_METHOD.match(line)
            if method is None or method.group(1) in _JAVA_KEYWORDS:
                continue
            if "=" in line.split("(")[0] or stripped.startswith(
                ("//", "*", "return", "new ", "throw", "else", "@")
            ):
                continue
            if owner and method.group(1) == owner:
                continue
            found.append(Target(rel, method.group(1), owner, number))
    return found


def grep_call_lines(texts: dict[str, str], target: Target) -> int:
    """与 ``git grep -w`` 等价的逐行扫描：形如 ``.name(`` 的行数（不含定义行）。"""
    call = re.compile(r"\." + re.escape(target.name) + r"\s*\(")
    count = 0
    for path, text in texts.items():
        if target.name not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if (path, number) != (target.file, target.line) and call.search(line):
                count += 1
    return count


def _read_texts(repo: Path, files: list[str]) -> dict[str, str]:
    """跟踪文件里的文本文件（含 NUL 的二进制文件跳过，对应 ``git grep -I``）。"""
    texts: dict[str, str] = {}
    for rel in files:
        try:
            data = (repo / rel).read_bytes()
        except OSError:
            continue
        if b"\0" not in data:
            texts[rel] = data.decode("utf-8", errors="replace")
    return texts


def sample(
    repo: Path, lang: str, seed: int, count: int, files: list[str] | None = None
) -> list[Candidate]:
    """按种子抽样 ``count`` 个单一定义的方法目标；``files`` 缺省为 ``git ls-files``。"""
    files = tracked_files(repo) if files is None else files
    texts = _read_texts(repo, files)
    defs = python_methods(repo, files) if lang == "py" else java_methods(repo, files)
    by_name: dict[str, int] = {}
    for target in defs:
        by_name[target.name] = by_name.get(target.name, 0) + 1
    pool = [
        t
        for t in defs
        if t.owner
        and len(t.name) >= 4
        and not t.name.startswith("__")
        and "test" not in t.name.lower()
        and by_name[t.name] == 1
    ]
    random.Random(seed).shuffle(pool)
    picked: list[Candidate] = []
    for target in pool:
        if len(picked) >= count:
            break
        lines = grep_call_lines(texts, target)
        if 1 <= lines <= MAX_CALL_LINES:
            picked.append(Candidate(target, lines))
    return picked
