"""#1942: ``call_path`` with ``Class.method`` endpoints.

Minimal repro of the rich v13.9.4 finding: ``Progress.start`` calls
``self.live.start()`` (bound to ``Live.start``), which calls
``self.console.set_live(self)``. With qualified endpoints the tool answered
``NO_PATH`` / ``NOT_FOUND``, resolved ``Progress.start`` to another ``start``,
attributed ``LiveError`` to the wrong file and reported definition lines as hop
lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

pytestmark = pytest.mark.slow_ok  # a real index build is the behaviour under test

PROGRESS = """\
from live import Live


class Progress:
    def __init__(self) -> None:
        self.live: Live = Live(None)

    def start(self) -> None:
        self.live.start()


class Task:
    def start(self) -> int:
        return 1
"""

LIVE = """\
class Live:
    def __init__(self, console) -> None:
        self.console = console

    def start(self) -> None:
        if self.console is None:
            return
        self.console.set_live(self)
"""

ERRORS = """\
class LiveError(Exception):
    pass
"""

CONSOLE = """\
from errors import LiveError


class Console:
    def set_live(self, live) -> None:
        if live is None:
            raise LiveError("no live")
        self._live = live
"""

OTHER = """\
class Task:
    def start(self) -> int:
        return 2
"""


async def _indexed(tmp_path: Path) -> Path:
    from tests.unit._index_refresh_support import _refresh_index

    project = tmp_path / "proj"
    project.mkdir()
    for name, text in (
        ("progress.py", PROGRESS),
        ("live.py", LIVE),
        ("errors.py", ERRORS),
        ("console.py", CONSOLE),
        ("other.py", OTHER),
    ):
        (project / name).write_text(text, encoding="utf-8")
    await _refresh_index(project)
    return project


async def _path(project: Path, **arguments: str) -> dict:
    return await CodeGraphCallPathTool(str(project)).execute(arguments)


def _chain(path: dict) -> list[tuple[str, str, str, int]]:
    return [
        (hop["caller"], hop["callee"], hop["callee_file"], hop["call_site_line"])
        for hop in path["hops"]
    ]


@pytest.mark.asyncio
async def test_qualified_endpoints_find_the_path(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project, source_function="Progress.start", target_function="Console.set_live"
    )

    assert result["path_status"] == "PATH_FOUND", result
    assert result["endpoints"]["source"]["resolved"] == {
        "name": "Progress.start",
        "file": "progress.py",
        "line": 8,
    }
    first = result["paths"][0]
    assert _chain(first) == [
        ("Progress.start", "Live.start", "live.py", 9),
        ("Live.start", "Console.set_live", "console.py", 8),
    ]
    # The last hop goes through an untyped receiver: say so, never hide it.
    assert first["hops"][0]["callee_resolution"] == "resolved"
    assert first["hops"][1]["callee_resolution"] == "name_only"
    assert first["hops"][1]["line"] == 8  # the call site, not `def start` (5)


@pytest.mark.asyncio
async def test_qualified_source_is_the_named_class_method(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project,
        source_function="Live.start",
        target_function="Console.set_live",
    )

    assert result["path_status"] == "PATH_FOUND", result
    assert _chain(result["paths"][0]) == [
        ("Live.start", "Console.set_live", "console.py", 8)
    ]


@pytest.mark.asyncio
async def test_unknown_class_fails_closed_with_candidates(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project, source_function="Nope.start", target_function="Console.set_live"
    )

    assert result["path_status"] == "ENDPOINT_NOT_RESOLVED"
    assert result["verdict"] == "WARN"
    names = {c["name"] for c in result["endpoints"]["source"]["candidates"]}
    assert names == {"Progress.start", "Task.start", "Live.start"}
    assert "Live.start" in result["next_step"]


@pytest.mark.asyncio
async def test_ambiguous_class_method_names_retry_commands(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project, source_function="Task.start", target_function="Console.set_live"
    )

    assert result["path_status"] == "ENDPOINT_AMBIGUOUS"
    files = {c["file"] for c in result["endpoints"]["source"]["candidates"]}
    assert files == {"progress.py", "other.py"}
    assert "source_file" in result["next_step"]

    pinned = await _path(
        project,
        source_function="Task.start",
        source_file="other.py",
        target_function="Console.set_live",
    )
    assert pinned["path_status"] == "NO_PATH"
    assert pinned["dead_end"]["source_endpoint"]["callees"] == []


@pytest.mark.asyncio
async def test_dead_end_neighbours_use_definition_coordinates(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project,
        source_function="Task.start",
        source_file="progress.py",
        target_function="Console.set_live",
    )

    assert result["path_status"] == "NO_PATH"
    assert result["completeness"] == "complete"
    callees = result["dead_end"]["target_endpoint"]["callees"]
    error = next(c for c in callees if c["name"] == "LiveError")
    assert error["file"] == "errors.py"
    assert error["line"] == 1
    assert (error["call_site_file"], error["call_site_line"]) == ("console.py", 7)


@pytest.mark.asyncio
async def test_bare_name_hops_report_call_site_lines(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project,
        source_function="start",
        source_file="progress.py",
        target_function="set_live",
    )

    assert result["path_status"] == "PATH_FOUND"
    for path in result["paths"]:
        for hop in path["hops"]:
            assert hop["line"] == hop["call_site_line"]
    lines = {hop["call_site_line"] for hop in result["paths"][0]["hops"]}
    assert 5 not in lines  # `def start` in live.py is no call site


@pytest.mark.asyncio
async def test_no_path_with_unbound_frontier_is_not_complete(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await _path(
        project,
        source_function="Live.start",
        target_function="Task.start",
        target_file="other.py",
    )

    assert result["path_status"] == "NO_PATH"
    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["UNBOUND_FRONTIER_CALLS"]
    assert [(s["file"], s["line"]) for s in result["open_sites"]] == [("live.py", 8)]
    assert "live.py:8" in result["next_step"]
