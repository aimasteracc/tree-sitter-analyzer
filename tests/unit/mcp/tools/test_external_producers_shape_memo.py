"""RFC-0042 P2b: the literal-container shape is memoized by the source text's digest.

The text is read live on every request; only the parse of identical text is
reused, so an edit is always seen and the verdict equals the unmemoized one.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_external_producers as producers
from tree_sitter_analyzer.resident import loader

_TEXTS = {
    "literal": "def f():\n    pass\n\n\nTABLE = {'a': f}\n",
    "empty": "TABLE = {}\n",
    "mutated": "def f():\n    pass\n\n\nTABLE = {'a': f}\nTABLE['b'] = f\n",
    "updated": "TABLE = [1]\nTABLE.append(2)\n",
    "twice": "TABLE = (1,)\nTABLE = (2,)\n",
    "dynamic": "TABLE = {'a': getattr(x, 'y')}\n",
    "global": "TABLE = {1}\n\n\ndef g():\n    global TABLE\n",
    "rebound": "TABLE = {1: 2}\n\n\ndef g():\n    TABLE = None\n",
    "not_literal": "TABLE = dict(a=1)\n",
    "syntax": "TABLE = {\n",
}
_EXPECTED = {
    "literal": (True, True),
    "empty": (False, False),
    "mutated": (True, False),
    "updated": (True, False),
    "twice": (False, False),
    "dynamic": (False, False),
    "global": (True, False),
    "rebound": (True, False),
    "not_literal": (False, False),
    "syntax": (False, False),
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    producers.clear_shapes()
    yield
    producers.clear_shapes()


@pytest.mark.parametrize("label", sorted(_TEXTS))
def test_the_memoized_shape_equals_the_direct_one(label: str) -> None:
    text = _TEXTS[label]
    direct = producers._literal_shape(text, "TABLE")
    assert direct == _EXPECTED[label]
    assert producers.literal_shape(text, "TABLE") == direct  # miss
    assert producers.literal_shape(text, "TABLE") == direct  # hit


def test_an_edit_changes_the_key_and_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    direct = producers._literal_shape

    def counted(text: str, name: str) -> tuple[bool, bool]:
        calls.append(text)
        return direct(text, name)

    monkeypatch.setattr(producers, "_literal_shape", counted)
    assert producers.literal_shape(_TEXTS["literal"], "TABLE") == (True, True)
    assert producers.literal_shape(_TEXTS["literal"], "TABLE") == (True, True)
    assert producers.literal_shape(_TEXTS["mutated"], "TABLE") == (True, False)
    assert producers.literal_shape(_TEXTS["literal"], "OTHER") == (False, False)
    assert calls == [_TEXTS["literal"], _TEXTS["mutated"], _TEXTS["literal"]]


def test_off_and_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(loader.ENV_VAR, "off")
    producers.literal_shape(_TEXTS["literal"], "TABLE")
    assert len(producers._SHAPES) == 0
    monkeypatch.delenv(loader.ENV_VAR)
    monkeypatch.setattr(producers, "_SHAPES_MAX", 3)
    for index in range(6):
        producers.literal_shape(f"T{index} = [1]\n", f"T{index}")
    assert list(producers._SHAPES)[-1][1] == "T5"
    assert len(producers._SHAPES) == 3
