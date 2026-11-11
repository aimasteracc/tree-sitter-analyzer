"""RFC-0043 Phase C: the shape words of a Python text decide exactly what the
header / rename expressions decide, and are kept per content digest."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_class_index as class_index
from tree_sitter_analyzer.mcp.tools import callers_py_shapes as shapes
from tree_sitter_analyzer.resident import parse_facts

_TEXTS = [
    "class A(Base, metaclass=Meta):\n    pass\n",
    "class B(\n    mix(Base),\n    Other[int],  # comment Base2\n):\n    x: int = 1\n",
    "class C(D)  # no colon ever",
    "@class E(F): pass\nsubclass G(H): pass\n_class I(J): pass\n",
    "class K (L): pass\nclass M(N, class_(O)): pass\n",
    "Alias = mix(Base)\nOther: Type[Base] = Base\nx == y\nz = a = b\n",
    "  indented = Base\nT: X = Y = Z\nlast=Q",
    "import a.b as c\nfrom m import X as Y, Z  as  W\nfrom n import (P as\n    R)\n",
    "x as as y\na as b as c\nfoo as\n",
    "Y = X\nY = m.n.X  # re-export\nY = X # c\nY = X.\nY = .X\nY=X\t\n",
    "Y = X\r\nZ = W # c\r\nclass S(T):\r\n    pass\r\n",
    "\u00e9 = \u00fcber\nclass \u00c9t\u00e9(Bas\u00e9): pass\nV = \u00e9t\u00e9 as \u00fc\n",
    "class U(V,\n      W): x = 1\nclass Q(R) -> None: S\n",
    "",
    "class\nA(B): pass\nclass A(): pass\nclass A: pass\n",
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


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text)) | {"absent", "as", "class"}


@pytest.mark.parametrize("shape", shapes.SHAPES)
@pytest.mark.parametrize("text", _TEXTS)
def test_words_decide_like_the_expression(text: str, shape: str) -> None:
    spelled = shapes.spelled_words(text, shape)

    for word in sorted(_words(text)):
        expected = shapes.shape_pattern([word], shape).search(text) is not None
        assert (word in spelled) is expected, (word, shape)


@pytest.mark.parametrize("shape", shapes.SHAPES)
def test_several_names_match_when_one_does(shape: str) -> None:
    text = "".join(_TEXTS)
    words = sorted(_words(text))
    for first, second in zip(words, words[1:], strict=False):
        expected = shapes.shape_pattern([first, second], shape).search(text)
        assert shapes.mentions(text, [first, second], shape) is (expected is not None)


def test_memo_on_and_off_agree_and_compute_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real = shapes.spelled_words

    def counting(text: str, shape: str) -> frozenset[str]:
        calls.append(shape)
        return real(text, shape)

    monkeypatch.setattr(shapes, "spelled_words", counting)
    text = _TEXTS[1]
    names = [["Base"], ["Other"], ["int", "absent"], ["absent"], ["mix"]]
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    off = [shapes.mentions(text, n, "header") for n in names]
    assert calls == []  # off: the expression, as before
    monkeypatch.delenv(parse_facts.ENV_VAR)
    on = [shapes.mentions(text, n, "header") for n in names]
    again = [shapes.mentions(text, n, "header") for n in names]

    assert off == on == again == [True, True, True, False, True]
    assert calls == ["header"]
    assert shapes.mentions(text, [], "header") is False


def test_shapes_and_texts_are_separate_entries() -> None:
    shapes.mentions("Y = X\n", ["X"], "header")
    shapes.mentions("Y = X\n", ["X"], "rename")
    shapes.mentions("Y = Z\n", ["X"], "rename")

    assert parse_facts.stats()["entries"] == 3


def test_files_with_follows_an_edit(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("class A(Base):\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = Base\n", encoding="utf-8")
    index = class_index.build(str(tmp_path), ["a.py", "b.py"])
    assert index.files_with(["Base"]) == ["a.py", "b.py"]
    assert index.files_with(["Base"], "rename") == ["b.py"]
    # A different size: the evidence file cache's stamp changes and it reads again.
    (tmp_path / "a.py").write_text("class A:\n    base = Base()\n", encoding="utf-8")

    assert index.files_with(["Base"]) == ["b.py"]
