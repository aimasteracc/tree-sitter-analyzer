"""Today's best TSA call sequences per question (the "before" arm, RFC-0041).

Each plan is what a TSA-fluent agent does with the existing surface: the
cheapest combination of ``nav`` / ``search`` actions that answers the question,
with token-saving options an expert would know (``include_bodies=false``).
Plans return ``(answer_sets, claims)`` where ``claims`` maps an answer set to
the completeness the tools asserted for it (``None`` when the tools made no
claim at all).
"""

from __future__ import annotations

from typing import Any

from harness import TsaClient
from oracle import is_test_entry, is_test_file

Answer = tuple[dict[str, set[str]], dict[str, str | None]]


def _key(entry: dict[str, Any]) -> str:
    return f"{entry.get('file')}::{entry.get('name')}"


def _callers(c: TsaClient, name: str, file: str | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {
        "action": "callers",
        "function_name": name,
        "include_bodies": False,
        "limit": 500,
    }
    if file:
        args["file_path"] = file
    return c.call("nav", args)


def _test_map(c: TsaClient, name: str, file: str | None = None) -> set[str]:
    args: dict[str, Any] = {"action": "test_map", "symbol": name}
    if file:
        args["file_path"] = file
    r = c.call("nav", args)
    return set(r.get("test_functions") or [])


def _tree_nodes(node: dict[str, Any], out: list[dict[str, Any]]) -> None:
    for child in node.get("children") or []:
        out.append(child)
        _tree_nodes(child, out)


def _caller_tree(
    c: TsaClient, name: str, depth: int
) -> tuple[list[dict[str, Any]], bool]:
    r = c.call("nav", {"action": "caller_tree", "symbol": name, "max_depth": depth})
    nodes: list[dict[str, Any]] = []
    _tree_nodes((r.get("tree") or {}).get("root") or {}, nodes)
    return nodes, bool(r.get("truncated"))


def _claim(r: dict[str, Any]) -> str | None:
    value = r.get("completeness")
    return value if isinstance(value, str) else None


def callers_tests(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _callers(c, p["x"])
    callers = {_key(e) for e in r.get("callers") or []}
    tests: set[str] = set()
    for e in r.get("callers") or []:
        if not is_test_file(str(e.get("file"))):
            tests |= _test_map(c, str(e["name"]), str(e["file"]))
    return {"callers": callers, "tests": tests}, {"callers": _claim(r), "tests": None}


def module_untested(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _callers(c, p["y"])
    out: set[str] = set()
    for e in r.get("callers") or []:
        if e.get("file") != p["module"] or e.get("name") == "<module>":
            continue
        if not _test_map(c, str(e["name"]), str(e["file"])):
            out.add(_key(e))
    return {"functions": out}, {"functions": None}


def callers_depth(c: TsaClient, p: dict[str, Any]) -> Answer:
    selector = f"*:calls(#{p['x']}){{1,{p['depth']}}}:in({p['prefix']})"
    r = c.call("search", {"action": "tql_execute", "selector": selector})
    return {"callers": {_key(s) for s in r.get("symbols") or []}}, {"callers": None}


def implementers(c: TsaClient, p: dict[str, Any]) -> Answer:
    # ``#m`` rows carry no class; ``:has(#m)`` returns the containing classes.
    r = c.call(
        "search",
        {
            "action": "tql_execute",
            "selector": f".class:has(#{p['m']})",
            "max_results": 1000,
        },
    )
    classes = {f"{s.get('file')}::{s.get('name')}" for s in r.get("symbols") or []}
    rc = _callers(c, p["m"])
    return (
        {"classes": classes, "callers": {_key(e) for e in rc.get("callers") or []}},
        {"classes": None, "callers": _claim(rc)},
    )


def impact(c: TsaClient, p: dict[str, Any]) -> Answer:
    nodes, _truncated = _caller_tree(c, p["x"], 10)
    callers = {_key(n) for n in nodes}
    tests = {k for k in callers if is_test_entry(k.split("::")[0], k.split("::")[1])}
    tests |= _test_map(c, p["x"])
    files = {k.split("::")[0] for k in callers | tests}
    return (
        {"callers": callers, "tests": tests, "files": files},
        {"callers": None, "tests": None, "files": None},
    )


def callers(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = _callers(c, p["x"])
    return {"callers": {_key(e) for e in r.get("callers") or []}}, {
        "callers": _claim(r)
    }


def tests(c: TsaClient, p: dict[str, Any]) -> Answer:
    return {"tests": _test_map(c, p["x"])}, {"tests": None}


def callees(c: TsaClient, p: dict[str, Any]) -> Answer:
    r = c.call(
        "nav",
        {
            "action": "callees",
            "function_name": p["x"],
            "file_path": p["file"],
            "include_bodies": False,
        },
    )
    # Builtins come back with the caller's file; keep project-resolved callees.
    names = {
        str(e.get("name"))
        for e in r.get("callees") or []
        if e.get("callee_resolution") == "project"
    }
    return {"callees": names}, {"callees": _claim(r)}


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

#: Discovery an agent must pay once before a plan's DSL is usable.
DISCOVERY = {
    "callers_depth": ("search", {"action": "tql_schema"}),
    "implementers": ("search", {"action": "tql_schema"}),
}
