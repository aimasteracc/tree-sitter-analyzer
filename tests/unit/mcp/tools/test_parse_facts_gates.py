"""RFC-0043 Phase B: the declaration-header table and the Python class facts are
memoized by content digest and give the same answers as a live parse."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import callers_declaration_header as header
from tree_sitter_analyzer.mcp.tools import callers_py_class_index as class_index
from tree_sitter_analyzer.resident import parse_facts

_JAVA = (
    "class A {\n"
    '    @SuppressWarnings("x")\n'
    "    private void beforeValue()\n"
    "        throws Exception {}\n"
    "    void other() { beforeValue(); }\n"
    "    @Deprecated\n"
    "    A() {}\n"
    "}\n"
)
_TS = (
    "export class A {\n"
    "  @Get()\n"
    "  target() { return 1; }\n"
    "}\n"
    "@Component({})\n"
    "export class\n"
    "  target {}\n"
)
_PY = (
    "@register(\n"
    "    'x',\n"
    ")\n"
    "def target():\n"
    "    pass\n"
    "class C:\n"
    "    @property\n"
    "    def target(self):\n"
    "        return 1\n"
)
_CASES = [
    (_JAVA, "java", "beforeValue"),
    (_TS, "typescript", "target"),
    (_PY, "python", "target"),
]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(parse_facts.ENV_VAR, raising=False)
    monkeypatch.delenv("TSA_RESIDENT", raising=False)
    parse_facts.clear()
    class_index.clear_indexes()
    yield
    parse_facts.clear()
    class_index.clear_indexes()


def _every_recorded(text: str, language: str, bare: str) -> list[frozenset[int]]:
    lines = range(0, text.count("\n") + 2)
    return [header.name_lines(text, [line], language, bare) for line in lines] + [
        header.name_lines(text, list(lines), language, bare)
    ]


@pytest.mark.parametrize(
    ("text", "language", "bare"), _CASES, ids=["java", "typescript", "python"]
)
def test_name_lines_equal_the_live_parse(
    monkeypatch: pytest.MonkeyPatch, text: str, language: str, bare: str
) -> None:
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    live = _every_recorded(text, language, bare)
    monkeypatch.delenv(parse_facts.ENV_VAR)
    first = _every_recorded(text, language, bare)
    again = _every_recorded(text, language, bare)

    assert first == live == again
    assert any(live), "fixture must exercise a header name line"
    assert parse_facts.stats()["misses"] == 1  # one parse; every other call hits


def test_tree_sitter_declarations_parsed_once_per_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    real = header._build_tree_sitter_declarations

    def counting(text: str, language: str):
        calls.append(language)
        return real(text, language)

    monkeypatch.setattr(header, "_build_tree_sitter_declarations", counting)
    _every_recorded(_JAVA, "java", "beforeValue")

    assert calls == ["java"]


def test_unparsable_text_adds_nothing() -> None:
    assert header.name_lines("x", [1], "no-such-lang", "x") == frozenset()
    assert header.name_lines("def f(:\n", [1], "python", "f") == frozenset()


def test_grammar_fault_adds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import tree_sitter_analyzer.language_loader as loader

    def broken(language: str):
        raise RuntimeError("grammar fault")

    monkeypatch.setattr(loader, "create_parser_safely", broken)

    assert header.name_lines(_JAVA, [2], "java", "beforeValue") == frozenset()


_MODULE = (
    "import base as b\n"
    "from pkg import Thing as Other\n"
    "Alias = Other\n"
    "class A(b.Base, metaclass=Meta):\n"
    "    x = 1\n"
    "    def m(self):\n"
    "        pass\n"
    "class B(A):\n"
    "    pass\n"
)


def _facts(root: Path, rel: str):
    return class_index._read_file_facts(str(root), rel)


def test_class_facts_equal_the_live_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(_MODULE, encoding="utf-8")
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    live = _facts(tmp_path, "pkg/m.py")
    monkeypatch.delenv(parse_facts.ENV_VAR)
    first = _facts(tmp_path, "pkg/m.py")
    again = _facts(tmp_path, "pkg/m.py")

    assert live is not None
    assert first == live == again
    assert [c.name for c in live.classes] == ["A", "B"]
    assert ("Thing", "Other") in live.renames
    assert parse_facts.stats()["hits"] == 1


def test_class_facts_follow_an_edit(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    path.write_text("class A:\n    pass\n", encoding="utf-8")
    before = _facts(tmp_path, "m.py")
    # A different size: the evidence file cache's stamp changes and it reads again.
    path.write_text("class A:\n    pass\nclass Z(A):\n    pass\n", encoding="utf-8")
    after = _facts(tmp_path, "m.py")

    assert before is not None and [c.name for c in before.classes] == ["A"]
    assert after is not None and [c.name for c in after.classes] == ["A", "Z"]


def test_class_facts_of_the_same_bytes_in_another_file_are_separate(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("class A:\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class A:\n    pass\n", encoding="utf-8")

    first = _facts(tmp_path, "a.py")
    second = _facts(tmp_path, "b.py")

    assert first is not None and second is not None
    assert first.classes[0].rel == "a.py"
    assert second.classes[0].rel == "b.py"


def test_unreadable_or_unparsable_file_has_no_facts(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("class (:\n", encoding="utf-8")

    assert _facts(tmp_path, "missing.py") is None
    assert _facts(tmp_path, "bad.py") is None


def test_index_file_uses_the_memoized_facts(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(_MODULE, encoding="utf-8")
    first = class_index.build(str(tmp_path), ["m.py"]).file("m.py")
    second = class_index.build(str(tmp_path), ["m.py"]).file("m.py")

    assert first is second
