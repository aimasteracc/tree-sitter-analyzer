"""RFC-0043: the process-wide memo of facts derived from one source text."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tree_sitter_analyzer.resident import parse_facts


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(parse_facts.ENV_VAR, raising=False)
    monkeypatch.delenv("TSA_RESIDENT", raising=False)
    parse_facts.clear()
    yield
    parse_facts.clear()


def _counting():
    calls: list[str] = []

    def make(value):
        def compute():
            calls.append(value)
            return (value,)

        return compute

    return calls, make


def test_on_by_default_and_reuses_byte_identical_content() -> None:
    calls, make = _counting()

    first = parse_facts.facts("k", "python", "x = 1\n", make("a"))
    again = parse_facts.facts("k", "python", "x = 1\n", make("b"))

    assert first == again == ("a",)
    assert calls == ["a"]
    assert parse_facts.stats()["hits"] == 1
    assert parse_facts.stats()["misses"] == 1


def test_changed_content_is_computed_again() -> None:
    calls, make = _counting()
    parse_facts.facts("k", "python", "x = 1\n", make("a"))

    assert parse_facts.facts("k", "python", "x = 2\n", make("b")) == ("b",)
    assert calls == ["a", "b"]


@pytest.mark.parametrize(
    ("kind", "language", "extra"),
    [("other", "python", ()), ("k", "java", ()), ("k", "python", ("a.py",))],
)
def test_kind_language_and_extra_separate_entries(
    kind: str, language: str, extra: tuple
) -> None:
    calls, make = _counting()
    parse_facts.facts("k", "python", "same", make("a"))
    parse_facts.facts(kind, language, "same", make("b"), extra=extra)

    assert calls == ["a", "b"]


def test_text_and_bytes_of_the_same_content_are_separate() -> None:
    calls, make = _counting()
    parse_facts.facts("k", "python", "same", make("a"))
    parse_facts.facts("k", "python", b"same", make("b"))

    assert calls == ["a", "b"]


@pytest.mark.parametrize("value", ["0", "off", "False", " no "])
def test_off_switch_computes_every_time(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(parse_facts.ENV_VAR, value)
    calls, make = _counting()
    parse_facts.facts("k", "python", "x", make("a"))
    parse_facts.facts("k", "python", "x", make("b"))

    assert calls == ["a", "b"]
    assert parse_facts.stats()["entries"] == 0
    assert parse_facts.enabled() is False


def test_resident_kill_switch_turns_it_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSA_RESIDENT", "off")

    assert parse_facts.enabled() is False


def test_failure_is_not_stored() -> None:
    def broken():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        parse_facts.facts("k", "python", "x", broken)
    calls, make = _counting()

    assert parse_facts.facts("k", "python", "x", make("a")) == ("a",)
    assert calls == ["a"]


def test_entry_bound_evicts_least_recently_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parse_facts, "MAX_ENTRIES", 2)
    calls, make = _counting()
    parse_facts.facts("k", "python", "a", make("a"))
    parse_facts.facts("k", "python", "b", make("b"))
    parse_facts.facts("k", "python", "a", make("a2"))  # hit: "a" is now newest
    parse_facts.facts("k", "python", "c", make("c"))  # evicts "b"
    parse_facts.facts("k", "python", "a", make("a3"))
    parse_facts.facts("k", "python", "b", make("b2"))

    assert calls == ["a", "b", "c", "b2"]
    assert parse_facts.stats()["entries"] == 2


def test_byte_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    one = parse_facts.estimate_bytes(("x" * 100,)) + 400
    monkeypatch.setattr(parse_facts, "MAX_BYTES", one * 2)
    for index in range(5):
        parse_facts.facts("k", "python", str(index), lambda: ("x" * 100,))

    stats = parse_facts.stats()
    assert stats["bytes"] <= one * 2
    assert 1 <= stats["entries"] < 5


def test_value_larger_than_the_budget_is_not_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parse_facts, "MAX_BYTES", 64)
    value = parse_facts.facts("k", "python", "x", lambda: ("y" * 1000,))

    assert value == ("y" * 1000,)
    assert parse_facts.stats()["entries"] == 0


def test_replacing_an_entry_keeps_the_byte_count_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = ("k", "python", (), "str", parse_facts.digest("x"))
    parse_facts._store(key, ("a",))
    parse_facts._store(key, ("a",))

    stats = parse_facts.stats()
    assert stats["entries"] == 1
    assert stats["bytes"] == parse_facts.estimate_bytes(("a",)) + (
        parse_facts.estimate_bytes(key)
    )


@dataclass(frozen=True)
class _Fact:
    name: str
    lines: tuple[int, ...]


def test_estimate_counts_nested_values() -> None:
    flat = parse_facts.estimate_bytes(_Fact("n", ()))
    nested = parse_facts.estimate_bytes(_Fact("n" * 500, (1, 2, 3)))
    mapping = parse_facts.estimate_bytes({"a": frozenset({"b", "c"})})

    assert nested > flat
    assert mapping > parse_facts.estimate_bytes({})


def test_estimate_stops_at_depth() -> None:
    value: tuple = ()
    for _ in range(20):
        value = (value,)

    assert parse_facts.estimate_bytes(value) > 0
