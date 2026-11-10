"""#1941: dead-code surfaces list a function only where callers certifies it.

Minimal repro of the rich v13.9.4 finding: ``Console.set_live`` is called as
``self.console.set_live(self)`` (an attribute receiver whose type is not
inferred), so no resolved edge reaches it, and ``codegraph_overview`` listed it
as dead while ``nav action=callers`` answered ``unknown`` and named the site.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools import dead_code_certify as certify_mod
from tree_sitter_analyzer.mcp.tools.codegraph_overview_tool import (
    CodeGraphOverviewTool,
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool

pytestmark = pytest.mark.slow_ok  # a real index build is the behaviour under test

CONSOLE = """\
class Console:
    def __init__(self):
        self._live = None

    def set_live(self, live):
        self._live = live

    def _svg_hash(self):
        return 1

    def _repr_html_(self):
        return "<b/>"
"""

LIVE = """\
class Live:
    def __init__(self, console):
        self.console = console

    def begin(self):
        self.console.set_live(self)
"""

READER = """\
import io


class Reader(io.RawIOBase):
    def writable(self):
        return False


class Plain:
    def unused_helper(self):
        return 2
"""

TESTS = """\
def test_console():
    assert True
"""


async def _indexed(tmp_path: Path) -> Path:
    from tests.unit._index_refresh_support import _refresh_index

    project = tmp_path / "proj"
    (project / "tests").mkdir(parents=True)
    (project / "console.py").write_text(CONSOLE, encoding="utf-8")
    (project / "live.py").write_text(LIVE, encoding="utf-8")
    (project / "reader.py").write_text(READER, encoding="utf-8")
    (project / "tests" / "test_console.py").write_text(TESTS, encoding="utf-8")
    await _refresh_index(project)
    return project


def _names(entries: list[dict]) -> set[str]:
    return {entry.get("qualified_name") or entry["name"] for entry in entries}


@pytest.mark.asyncio
async def test_overview_lists_only_certified_dead_code(tmp_path: Path) -> None:
    project = await _indexed(tmp_path)

    result = await CodeGraphOverviewTool(str(project)).execute({"max_dead": 50})

    dead = _names(result["dead_code"])
    assert "Console.set_live" not in dead  # called through self.console
    assert "Reader.writable" not in dead  # io.RawIOBase calls it
    assert "Console._repr_html_" not in dead  # IPython calls it by name
    assert "test_console" not in dead  # the test runner calls it
    assert {"Console._svg_hash", "Plain.unused_helper"} <= dead
    assert result["dead_code_status"] == "certified"
    assert result["summary"]["dead_code_count"] == len(result["dead_code"])

    possibly = {entry["qualified_name"]: entry for entry in result["possibly_dead"]}
    assert "NAME_ONLY_INBOUND" in possibly["Console.set_live"]["reasons"]
    assert possibly["Console.set_live"]["open_sites"] == ["live.py:6"]
    assert possibly["Reader.writable"]["reasons"] == ["EXTERNAL_SUPERTYPE"]
    assert "io.RawIOBase" in possibly["Reader.writable"]["detail"]


@pytest.mark.asyncio
async def test_dead_code_tool_lists_only_certified_dead_functions(
    tmp_path: Path,
) -> None:
    project = await _indexed(tmp_path)

    result = await CodeGraphDeadCodeTool(str(project)).execute(
        {"mode": "dead_functions", "max_dead": 50}
    )

    dead = _names(result["dead_functions"])
    assert "Reader.writable" not in dead
    assert "Console._repr_html_" not in dead
    assert "Console.set_live" not in dead
    assert {"Console._svg_hash", "Plain.unused_helper"} <= dead
    assert result["stats"]["dead_functions_status"] == "certified"
    uncertified = _names(result["possibly_dead_functions"])
    assert "Reader.writable" in uncertified


def test_transitive_dead_needs_every_caller_dead() -> None:
    a = FunctionRef("m.py", "a", 1, "python")
    b = FunctionRef("m.py", "b", 5, "python")
    c = FunctionRef("m.py", "c", 9, "python")
    cert = certify_mod.Certification(
        verdicts={
            # a has no callers; b is called by a (dead) and by an unknown site.
            a: certify_mod.Verdict(True),
            b: certify_mod.Verdict(True, callers=(("m.py", 1), ("n.py", 3))),
            c: certify_mod.Verdict(True, callers=(("m.py", 5),)),
        }
    )

    dead = certify_mod.resolve_dead([a, b, c], cert)

    # n.py:3 is no candidate: b is alive, so c (called only by b) is alive too.
    assert dead == {a}


def test_unchecked_candidates_are_never_dead() -> None:
    a = FunctionRef("m.py", "a", 1, "python")
    cert = certify_mod.Certification(unchecked=[a])

    assert certify_mod.resolve_dead([a], cert) == set()
    entry = certify_mod.uncertified_entry(a, cert, set())
    assert entry["reasons"] == [certify_mod.BUDGET_REASON]


def test_incomplete_answer_is_not_certified() -> None:
    verdict = certify_mod._verdict(
        {
            "success": True,
            "completeness": "unknown",
            "completeness_reasons": ["NAME_ONLY_INBOUND"],
            "caller_count": 0,
            "callers": [],
        }
    )
    assert verdict.certified is False
    assert verdict.reasons == ("NAME_ONLY_INBOUND",)


def test_method_of_another_language_is_never_certified() -> None:
    method = FunctionRef("A.java", "run", 3, "java", receiver="Task")

    verdict = certify_mod._override_gate("/nowhere", method, lambda: None)

    assert verdict is not None and verdict.certified is False
    assert verdict.reasons == ("OVERRIDE_UNCHECKED",)
    assert (
        certify_mod._override_gate(
            "/nowhere", FunctionRef("a.py", "f", 1, "python"), lambda: None
        )
        is None
    )


def test_external_override_walks_project_bases(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.dead_code_overrides import external_override

    (tmp_path / "m.py").write_text(
        "import abc\n\n\n"
        "class Base(abc.ABC):\n    def hook(self):\n        return 1\n\n\n"
        "class Child(Base):\n    def hook(self):\n        return 2\n\n\n"
        "class Stream(dict):\n    def keys(self):\n        return []\n\n\n"
        "def free():\n    return 3\n",
        encoding="utf-8",
    )
    tops = lambda: frozenset({"m"})  # noqa: E731

    assert external_override(str(tmp_path), "m.py", 10, "hook", tops) is None
    found = external_override(str(tmp_path), "m.py", 15, "keys", tops)
    assert found is not None and "external base `dict`" in found
    assert external_override(str(tmp_path), "m.py", 19, "free", tops) is None
    assert external_override(str(tmp_path), "notes.txt", 1, "x", tops) is None
    unreadable = external_override(str(tmp_path), "gone.py", 1, "x", tops)
    assert unreadable is not None and "could not be read" in unreadable


def test_mismatched_batch_answers_certify_nothing() -> None:
    funcs = [
        FunctionRef("m.py", "a", 1, "python"),
        FunctionRef("m.py", "b", 5, "python"),
    ]

    assert certify_mod._answers_for(funcs, [{}]) == [None, None]
    assert certify_mod._verdict(None).reasons == (certify_mod.NO_ANSWER_REASON,)


def test_listed_caller_that_is_not_dead_keeps_the_callee_alive() -> None:
    a = FunctionRef("m.py", "a", 1, "python")
    b = FunctionRef("m.py", "b", 5, "python")
    cert = certify_mod.Certification(
        verdicts={
            a: certify_mod.Verdict(
                False, ("NAME_ONLY_INBOUND",), open_sites=("x.py:3",)
            ),
            b: certify_mod.Verdict(True, callers=(("m.py", 1),)),
        }
    )

    dead = certify_mod.resolve_dead([a, b], cert)

    assert dead == set()
    assert certify_mod.uncertified_entry(b, cert, dead)["reasons"] == ["LIVE_CALLER"]
    entry = certify_mod.uncertified_entry(a, cert, dead)
    assert entry["open_sites"] == ["x.py:3"]


@pytest.mark.asyncio
async def test_budget_leaves_candidates_unchecked(tmp_path: Path) -> None:
    funcs = [FunctionRef("m.py", f"f{i}", i + 1, "python") for i in range(3)]

    cert = await certify_mod.certify(str(tmp_path), funcs, budget_seconds=0.0)

    assert cert.unchecked == funcs
    assert cert.verdicts == {}
