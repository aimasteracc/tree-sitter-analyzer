"""#1813：nav 答复中的路径只有一种形式——仓库相对、正斜杠，与 OS 和索引状态无关。

Windows 上无索引时，内存调用图、符号查找与 trace 按 OS 分隔符拼路径
（``app\\doc.py``，trace 甚至是绝对路径），有索引时则是 ``app/doc.py``：同一个问题
随索引状态给出不同的路径，agent 跨调用比较、复用这些路径，答案缓存也以它们为键。
"""

from __future__ import annotations

import sys
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph as call_graph_module
from tree_sitter_analyzer import source_lines
from tree_sitter_analyzer.mcp.tools import (
    query_symbol_search,
    symbol_lineage_tool,
    trace_impact_tool,
)
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _response_path

_FILES = {
    "app/__init__.py": "",
    "app/doc.py": (
        "from app.util import helper\n"
        "\n"
        "\n"
        "class Doc:\n"
        "    def render(self):\n"
        "        return helper(1)\n"
        "\n"
        "\n"
        "def main():\n"
        "    return Doc().render()\n"
    ),
    "app/util.py": "def helper(x):\n    return x + 1\n",
    "tests/__init__.py": "",
    "tests/test_doc.py": (
        "from app.doc import main\n\n\ndef test_main():\n    assert main() == 2\n"
    ),
}

_CALLS: list[dict[str, Any]] = [
    {"action": "callers", "function_name": "helper"},
    {"action": "callers", "function_name": "helper", "file_path": "app/util.py"},
    {"action": "callees", "function_name": "main"},
    {"action": "callees", "function_name": "main", "file_path": "app/doc.py"},
    {"action": "navigate", "symbol": "helper"},
    {"action": "lineage", "symbol": "Doc"},
    {"action": "impact", "symbol": "helper"},
    {"action": "callee_tree", "symbol": "main"},
    {"action": "caller_tree", "symbol": "helper"},
    {"action": "test_map", "symbol": "main"},
    {"action": "trace", "symbol": "helper"},
]


class _WindowsRelative(type(Path())):  # type: ignore[misc]
    """真实路径，但相对路径按 Windows 分隔符给出——在任何 OS 上重现 #1813 的输入。"""

    def relative_to(self, *other: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        return PureWindowsPath(*super().relative_to(*other, **kwargs).parts)


def _write(root: Path) -> str:
    for rel, text in _FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


async def _index(root: str) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    indexed = await CodeGraphFullIndexTool(root).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [value] if isinstance(value, str) else []


def _backslash_paths(response: Any, root: str) -> list[str]:
    """答复里任何带反斜杠的项目路径，或项目根下的绝对路径。"""
    root_forms = {root, root.replace("\\", "/")}
    return [
        s
        for s in _strings(response)
        if any(f"{top}\\" in s for top in ("app", "tests"))
        or any(form in s for form in root_forms)
    ]


@pytest.fixture(autouse=True)
def _in_process_trace_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """trace 默认在新起的工作进程里扫描；这里只关心路径形式，在进程内扫描。"""

    def scan(symbol: str, roots: list[str], **options: Any) -> list[dict[str, Any]]:
        options.pop("classify_source", None)
        return source_lines.scan_symbol_lines(symbol, roots, **options)

    monkeypatch.setattr(trace_impact_tool, "scan_symbol_lines", scan)


def _ids(args: dict[str, Any]) -> str:
    return "-".join(str(v) for v in args.values()).replace("/", "_")


async def _ask(root: str, args: dict[str, Any]) -> list[str]:
    response = await build_nav_facade(root).execute(dict(args))
    assert response.get("success") is not False, response
    return _backslash_paths(response, root)


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="OS separator is '\\' on Windows")
@pytest.mark.parametrize("indexed", [False, True], ids=["no_index", "index"])
@pytest.mark.parametrize("args", _CALLS, ids=_ids)
async def test_windows_nav_answers_use_forward_slash_paths(
    tmp_path: Path, indexed: bool, args: dict[str, Any]
) -> None:
    root = _write(tmp_path)
    if indexed:
        await _index(root)

    assert await _ask(root, args) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [False, True], ids=["no_index", "index"])
@pytest.mark.parametrize("args", _CALLS, ids=_ids)
async def test_nav_answers_use_forward_slash_paths_with_a_windows_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, indexed: bool, args: dict[str, Any]
) -> None:
    root = _write(tmp_path)
    if indexed:
        await _index(root)
    # Every producer that walks the tree sees paths whose relative form uses '\\'.
    original_iter = call_graph_module.CallGraph._iter_source_files

    def iter_windows(self: Any, exts: Any) -> list[Path]:
        return [_WindowsRelative(p) for p in original_iter(self, exts)]

    original_collect = query_symbol_search._collect_source_files

    def collect_windows(base: Path) -> list[Path]:
        return [_WindowsRelative(p) for p in original_collect(base)]

    monkeypatch.setattr(call_graph_module.CallGraph, "_iter_source_files", iter_windows)
    monkeypatch.setattr(query_symbol_search, "_collect_source_files", collect_windows)

    assert await _ask(root, args) == []


@pytest.mark.asyncio
async def test_no_index_answers_name_the_same_paths_as_indexed_answers(
    tmp_path: Path,
) -> None:
    root = _write(tmp_path)
    facade = build_nav_facade(root)
    args = {"action": "callers", "function_name": "helper", "file_path": "app/util.py"}

    cold = await facade.execute(dict(args))
    await _index(root)
    warm = await build_nav_facade(root).execute(dict(args))

    def files(response: dict[str, Any]) -> set[str]:
        return {c["file"] for c in response.get("callers") or []}

    assert files(cold) == files(warm) == {"app/doc.py"}


@pytest.mark.asyncio
async def test_trace_usages_are_repository_relative(tmp_path: Path) -> None:
    root = _write(tmp_path)

    response = await build_nav_facade(root).execute(
        {"action": "trace", "symbol": "helper", "max_results": 50}
    )

    assert {u["file"] for u in response["usages"]} == {"app/doc.py", "app/util.py"}
    assert all(u["file"] == u["file_path"] for u in response["usages"])


def test_response_path_outside_the_project_keeps_an_absolute_forward_slash_path(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "other" / "lib.py"

    assert _response_path(str(project / "app" / "doc.py"), str(project)) == "app/doc.py"
    assert _response_path(str(outside), str(project)) == str(outside).replace("\\", "/")
    assert _response_path("C:\\elsewhere\\lib.py", None) == "C:/elsewhere/lib.py"


def test_grep_fallback_definitions_use_forward_slash_paths(tmp_path: Path) -> None:
    import re

    root = Path(_write(tmp_path))
    hits: list[dict[str, Any]] = []

    symbol_lineage_tool._scan_file_for_definitions(
        _WindowsRelative(root / "app" / "doc.py"),
        root,
        "Doc",
        re.compile(r"\bDoc\b"),
        re.compile(r"^\s*class\s+Doc\b"),
        hits,
        set(),
    )

    assert [(h["file"], h["start_line"]) for h in hits] == [("app/doc.py", 4)]
