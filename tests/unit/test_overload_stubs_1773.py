"""#1773：``@overload`` 存根的识别与构图时的合并（单元）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_symbols_json_enrichment import _symbols_for
from tree_sitter_analyzer.call_graph import CallGraph
from tree_sitter_analyzer.overload_stubs import drop_overload_stubs

_SRC = (
    "import typing\n"
    "import typing_extensions as te\n"
    "from typing import overload\n\n\n"
    "class P:\n"
    "    @overload\n"
    "    def m(self, a: int) -> int: ...\n"
    "    @typing.overload\n"
    "    def m(self, a: str) -> str: ...\n"
    "    @te.overload\n"
    "    def m(self, a: bytes) -> bytes: ...\n"
    "    def m(self, a):\n"
    "        return a\n\n"
    "    @staticmethod\n"
    "    def plain(): ...\n\n"
    "    @overload_factory()\n"
    "    def called(self): ...\n"
)


def _flags(source: str) -> list[tuple[str, int, bool]]:
    return [
        (sym["name"], sym["line"], bool(sym.get("overload")))
        for sym in _symbols_for(source, "python")
        if sym.get("kind") in ("function", "method")
    ]


def test_overload_decorators_are_marked_in_symbols() -> None:
    assert _flags(_SRC) == [
        ("m", 8, True),
        ("m", 10, True),
        ("m", 12, True),
        ("m", 13, False),
        ("plain", 17, False),
        ("called", 20, False),
    ]


def test_other_languages_are_never_marked() -> None:
    symbols = _symbols_for("@overload\nfunction m() {}\n", "javascript")
    assert not any(sym.get("overload") for sym in symbols)


def _entry(name: str, line: int, *, cls: str | None = "P", stub: bool = False) -> dict:
    entry: dict = {"file": "a.py", "name": name, "line": line, "class": cls}
    if stub:
        entry["overload"] = True
    return entry


def test_stubs_with_one_implementation_are_dropped() -> None:
    entries = [
        _entry("m", 1, stub=True),
        _entry("m", 2, stub=True),
        _entry("m", 3),
        _entry("other", 4),
    ]

    assert drop_overload_stubs(entries) == [_entry("m", 3), _entry("other", 4)]
    assert len(entries) == 4  # 输入不被改写。


@pytest.mark.parametrize(
    "entries",
    [
        # 只有存根（.pyi / Protocol）：没有实现可代表它们。
        [_entry("m", 1, stub=True), _entry("m", 2, stub=True)],
        # 两个未标记的定义（条件定义）：哪一个生效无法确定。
        [_entry("m", 1, stub=True), _entry("m", 2), _entry("m", 3)],
        # 实现属于另一个类 / 模块级：不是同一个方法。
        [_entry("m", 1, stub=True), _entry("m", 2, cls="Q")],
        [_entry("m", 1, stub=True), _entry("m", 2, cls=None)],
    ],
    ids=["stubs-only", "two-implementations", "other-class", "module-level"],
)
def test_stubs_are_kept_without_a_unique_implementation(entries: list[dict]) -> None:
    assert drop_overload_stubs(entries) == entries


def test_stubs_in_another_file_are_kept() -> None:
    stub = {**_entry("m", 1, stub=True), "file": "a.pyi"}
    assert drop_overload_stubs([stub, _entry("m", 2)]) == [stub, _entry("m", 2)]


def test_the_parse_path_graph_binds_self_calls_to_the_implementation(
    tmp_path: Path,
) -> None:
    (tmp_path / "pipe.py").write_text(
        "from typing import overload\n\n\n"
        "class Pipeline:\n"
        "    @overload\n"
        "    def constrain(self, c: int) -> int: ...\n"
        "    @overload\n"
        "    def constrain(self, c: str) -> str: ...\n"
        "    def constrain(self, c):\n"
        "        return c\n\n"
        "    def gt(self, v):\n"
        "        return self.constrain(v)\n",
        encoding="utf-8",
    )
    graph = CallGraph(str(tmp_path))

    targets = graph.resolve_targets("Pipeline.constrain", "pipe.py")
    callers = graph.callers_of("Pipeline.constrain", "pipe.py")

    assert [ref.start_line for ref in targets] == [9]
    assert [caller["name"] for caller in callers] == ["gt"]
