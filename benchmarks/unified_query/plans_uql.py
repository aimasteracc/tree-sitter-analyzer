"""One ``search action=uql`` call per question (the "after" arm, RFC-0041).

Each plan sends one query and reads the answer sets and claims straight from
the compact payload: ``results[group]`` rows are ``"file:line name"`` (or
``"file:line Class.name"``), and each group's claim is its stage's effective
completeness.
"""

from __future__ import annotations

from typing import Any

from harness import TsaClient

Answer = tuple[dict[str, set[str]], dict[str, str | None]]


def _key(label: str) -> str:
    where, _, name = label.rstrip(" ?").partition(" ")
    file = where.rsplit(":", 1)[0] if ":" in where else where
    return f"{file}::{name.rpartition('.')[2]}"


def _class_key(label: str) -> str:
    where, _, name = label.partition(" ")
    file = where.rsplit(":", 1)[0]
    return f"{file}::{name.rpartition('.')[0]}"


def _uql(c: TsaClient, query: str) -> dict[str, Any]:
    return c.call("search", {"action": "uql", "query": query, "limit": 500})


def _group(r: dict[str, Any], name: str) -> set[str]:
    return {_key(x) for x in (r.get("results") or {}).get(name) or []}


def _claim(r: dict[str, Any], op: str, nth: int = 0) -> str | None:
    stages = [s for s in r.get("stages") or [] if s.get("op") == op]
    return stages[nth]["c"] if len(stages) > nth else None


def _last_claim(r: dict[str, Any]) -> str | None:
    stages = r.get("stages") or []
    return stages[-1]["c"] if stages else None


def callers_tests(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['x']}').callers().tests()")
    return (
        {"callers": _group(r, "callers"), "tests": _group(r, "tests")},
        {"callers": _claim(r, "callers"), "tests": _claim(r, "tests")},
    )


def module_untested(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(
        c,
        f"symbol('{p['y']}').callers().filter(file='{p['module']}')"
        ".exclude(name='<module>').untested()",
    )
    return {"functions": _group(r, "callers")}, {"functions": _last_claim(r)}


def callers_depth(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(
        c,
        f"symbol('{p['x']}').callers(depth={p['depth']})"
        f".filter(path='{p['prefix']}').exclude(name='<module>')",
    )
    return {"callers": _group(r, "callers")}, {"callers": _last_claim(r)}


def implementers(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['m']}').callers()")
    classes = {
        _class_key(x)
        for x in (r.get("results") or {}).get("symbol") or []
        if "." in x.partition(" ")[2]
    }
    return (
        {"classes": classes, "callers": _group(r, "callers")},
        {"classes": _claim(r, "symbol"), "callers": _claim(r, "callers")},
    )


def impact(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['x']}').impact()")
    tests = _group(r, "impact.tests")
    callers = _group(r, "impact") | tests
    files = set(r.get("files") or [])
    files -= {k.split("::")[0] for k in _group(r, "symbol")} - {
        k.split("::")[0] for k in callers
    }
    claim = _claim(r, "impact")
    return (
        {"callers": callers, "tests": tests, "files": files},
        {"callers": claim, "tests": claim, "files": claim},
    )


def callers(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['x']}').callers()")
    return {"callers": _group(r, "callers")}, {"callers": _claim(r, "callers")}


def tests(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['x']}').tests()")
    return {"tests": _group(r, "tests")}, {"tests": _claim(r, "tests")}


def callees(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _uql(c, f"symbol('{p['x']}', file='{p['file']}').callees()")
    names = {k.split("::", 1)[1] for k in _group(r, "callees")}
    return {"callees": names}, {"callees": _claim(r, "callees")}


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

#: The one grammar-discovery call (``help target_action=uql``), paid once.
DISCOVERY = {
    kind: ("search", {"action": "help", "target_action": "uql"}) for kind in PLANS
}
