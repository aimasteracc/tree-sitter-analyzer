"""Plain ``git grep`` + def-outline plans (the no-TSA arm, RFC-0041).

The agent greps ``\\bname\\s*\\(`` for call sites, then greps each hit file's
``def`` lines to map a hit to its enclosing function. Grep makes no
completeness claim, so every claim is ``None``.
"""

from __future__ import annotations

from typing import Any

from harness import GrepClient, enclosing
from oracle import is_test_entry, is_test_file

Answer = tuple[dict[str, set[str]], dict[str, str | None]]

_GREP_CALL_BUDGET = 60


def _callers(g: GrepClient, name: str, cache: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for file, line, text in g.grep(rf"\b{name}\s*\("):
        stripped = text.strip()
        if stripped.startswith(("def ", "async def ", "class ")):
            continue
        if file not in cache:
            cache[file] = g.outline(file)
        out.add(f"{file}::{enclosing(cache[file], line, text)}")
    return out


def _tests_of(g: GrepClient, name: str, cache: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in _callers(g, name, cache):
        file, func = key.split("::", 1)
        if not is_test_file(file):
            continue
        if is_test_entry(file, func):
            out.add(key)
            continue
        out |= {k for k in _callers(g, func, cache) if is_test_entry(*k.split("::", 1))}
    return out


def _prod(keys: set[str]) -> set[str]:
    return {k for k in keys if not is_test_file(k.split("::")[0])}


def callers_tests(g: GrepClient, p: dict[str, Any]) -> Answer:
    cache: dict[str, Any] = {}
    callers = _callers(g, p["x"], cache)
    tests: set[str] = set()
    for key in _prod(callers):
        tests |= _tests_of(g, key.split("::", 1)[1], cache)
    return {"callers": callers, "tests": tests}, {"callers": None, "tests": None}


def module_untested(g: GrepClient, p: dict[str, Any]) -> Answer:
    cache: dict[str, Any] = {}
    out = {
        key
        for key in _callers(g, p["y"], cache)
        if key.split("::")[0] == p["module"]
        and not key.endswith("::<module>")
        and not _tests_of(g, key.split("::", 1)[1], cache)
    }
    return {"functions": out}, {"functions": None}


def callers_depth(g: GrepClient, p: dict[str, Any]) -> Answer:
    cache: dict[str, Any] = {}
    frontier, seen, out = {p["x"]}, set(), set()
    for _ in range(p["depth"]):
        nxt: set[str] = set()
        for name in frontier:
            for key in _callers(g, name, cache):
                file, func = key.split("::", 1)
                if func == "<module>":
                    continue
                if file.startswith(p["prefix"]):
                    out.add(key)
                if func not in seen:
                    seen.add(func)
                    nxt.add(func)
        frontier = nxt
    return {"callers": out}, {"callers": None}


def implementers(g: GrepClient, p: dict[str, Any]) -> Answer:
    classes: set[str] = set()
    for file, line, _text in g.grep(rf"def {p['m']}\s*\("):
        last = "?"
        for _cfile, cline, ctext in g.grep(r"^class \w+", file):
            if cline < line:
                last = ctext.split("class ", 1)[1].split("(")[0].split(":")[0].strip()
        classes.add(f"{file}::{last}")
    return (
        {"classes": classes, "callers": _callers(g, p["m"], {})},
        {"classes": None, "callers": None},
    )


def impact(g: GrepClient, p: dict[str, Any]) -> Answer:
    # A name-based closure explodes through common names (``__init__``, ...):
    # uncapped, it took 1,020 greps / 373 s on rich. An agent stops; we stop
    # at the same call budget an agent plausibly spends (60 calls).
    cache: dict[str, Any] = {}
    frontier, seen, callers = {p["x"]}, {p["x"]}, set()
    for _ in range(50):
        nxt: set[str] = set()
        for name in sorted(frontier):
            if len(g.trace.calls) >= _GREP_CALL_BUDGET:
                break
            for key in _callers(g, name, cache):
                callers.add(key)
                func = key.split("::", 1)[1]
                if func not in seen and func != "<module>":
                    seen.add(func)
                    nxt.add(func)
        if not nxt:
            break
        frontier = nxt
    tests = {k for k in callers if is_test_entry(*k.split("::", 1))}
    files = {k.split("::")[0] for k in callers | tests}
    return (
        {"callers": callers, "tests": tests, "files": files},
        {"callers": None, "tests": None, "files": None},
    )


def callers(g: GrepClient, p: dict[str, Any]) -> Answer:
    return {"callers": _callers(g, p["x"], {})}, {"callers": None}


def tests(g: GrepClient, p: dict[str, Any]) -> Answer:
    return {"tests": _tests_of(g, p["x"], {})}, {"tests": None}


def callees(g: GrepClient, p: dict[str, Any]) -> Answer:
    rows = g.outline(p["file"])
    start, indent = next((line, i) for line, i, name in rows if name == p["x"])
    end = next((line for line, i, _ in rows if line > start and i <= indent), 10**9)
    body = g.read(p["file"], start, end - 1)
    names: set[str] = set()
    for text in body:
        names |= _call_names(text)
    names.discard(p["x"])
    if not names:
        return {"callees": set()}, {"callees": None}
    pattern = r"^\s*(async\s+)?def (" + "|".join(sorted(names)) + r")\s*\("
    defined = {
        text.strip().split("def ", 1)[1].split("(")[0] for _, _, text in g.grep(pattern)
    }
    return {"callees": names & defined}, {"callees": None}


def _call_names(text: str) -> set[str]:
    import re

    return set(re.findall(r"(\w+)\s*\(", text))


PLANS = {
    "callers_tests": callers_tests,
    "module_untested": module_untested,
    "callers_depth": callers_depth,
    "implementers": implementers,
    "impact": impact,
    "callers": callers,
    "tests": tests,
    "callees": callees,
}
