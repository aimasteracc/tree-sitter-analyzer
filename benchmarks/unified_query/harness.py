"""统一查询基准测试的测量客户端 (RFC-0041)。

每次 TSA 调用都经过与 MCP 服务器相同的接缝：facade 的 ``execute``、规范化
envelope 处理，再经线上序列化 (``json.dumps(indent=2)``)，因此记录下的字节数
就是 agent 上下文实际收到的字节数。grep 组的调用执行真实的 ``git grep`` /
文件读取，并记录其 stdout。

token 稍后由 ``tokens.py`` 根据记录的请求与响应文本统计；本模块只负责记录。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CallRecord:
    tool: str
    request: str
    response: str
    seconds: float


@dataclass
class Trace:
    calls: list[CallRecord] = field(default_factory=list)

    @property
    def response_bytes(self) -> int:
        return sum(len(c.response.encode("utf-8")) for c in self.calls)

    @property
    def request_bytes(self) -> int:
        return sum(len(c.request.encode("utf-8")) for c in self.calls)

    @property
    def seconds(self) -> float:
        return sum(c.seconds for c in self.calls)


class TsaClient:
    """进程内 facade 客户端，序列化方式与 MCP 服务器完全一致。"""

    def __init__(self, root: str) -> None:
        from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
        from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

        self.root = root
        self.facades = {
            "search": build_search_facade(root),
            "nav": build_nav_facade(root),
        }
        self.trace = Trace()

    def call(self, facade: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_error_envelope,
            ensure_canonical_success_envelope,
        )

        start = time.perf_counter()
        result = asyncio.run(self.facades[facade].execute(dict(arguments)))
        if isinstance(result, dict) and result.get("success") is False:
            result = ensure_canonical_error_envelope(
                facade, result, arguments=arguments
            )
        elif isinstance(result, dict):
            result = ensure_canonical_success_envelope(
                facade, result, arguments=arguments
            )
        elapsed = time.perf_counter() - start
        text = json.dumps(result, indent=2, ensure_ascii=False)
        request = json.dumps({"name": facade, "arguments": arguments})
        self.trace.calls.append(CallRecord(facade, request, text, elapsed))
        return result  # type: ignore[no-any-return]


class GrepClient:
    """``git grep`` + 文件读取组，记录 agent 会读到的文本。"""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.trace = Trace()

    def _record(self, tool: str, request: str, response: str, start: float) -> str:
        self.trace.calls.append(
            CallRecord(tool, request, response, time.perf_counter() - start)
        )
        return response

    def grep(self, pattern: str, *paths: str) -> list[tuple[str, int, str]]:
        start = time.perf_counter()
        cmd = ["git", "grep", "-n", "-E", pattern, "--", *(paths or ("*.py",))]
        out = subprocess.run(
            cmd, cwd=self.root, capture_output=True, text=True, encoding="utf-8"
        ).stdout
        self._record("grep", " ".join(cmd), out, start)
        hits: list[tuple[str, int, str]] = []
        for line in out.splitlines():
            file, _, rest = line.partition(":")
            num, _, text = rest.partition(":")
            if num.isdigit():
                hits.append((file, int(num), text))
        return hits

    def read(self, file: str, start: int, end: int) -> list[str]:
        """一次 ``Read``：读取第 ``start..end`` 行 (从 1 起、闭区间) 并加行号。"""
        begin = time.perf_counter()
        lines = (self.root / file).read_text(encoding="utf-8").splitlines()
        chunk = lines[start - 1 : min(end, len(lines))]
        numbered = "\n".join(f"{start + i}\t{t}" for i, t in enumerate(chunk))
        self._record("read", f"{file}:{start}-{end}", numbered, begin)
        return chunk

    def outline(self, file: str) -> list[tuple[int, int, str]]:
        """agent 把行号映射到函数的最低成本方式：grep 所有 def。"""
        hits = self.grep(r"^\s*(async\s+)?def \w+", file)
        rows: list[tuple[int, int, str]] = []
        for _, line, text in hits:
            indent = len(text) - len(text.lstrip())
            name = text.strip().split("def ", 1)[1].split("(", 1)[0]
            rows.append((line, indent, name))
        return rows


def enclosing(outline: list[tuple[int, int, str]], line: int, text: str) -> str:
    """之前最近的、缩进更小的 def；没有则返回 ``<module>``。"""
    indent = len(text) - len(text.lstrip())
    best = "<module>"
    for def_line, def_indent, name in outline:
        if def_line > line:
            break
        if def_indent < indent:
            best = name
    return best
