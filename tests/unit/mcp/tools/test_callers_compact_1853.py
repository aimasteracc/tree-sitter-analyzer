"""#1853: ``nav action=callers format=compact`` — one line per caller + a verdict.

The compact answer is a projection of the full answer: the caller set and the
RFC-0040 completeness verdict are read from it, never recomputed, so the
compact verdict can never be more optimistic than the full one.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.wrong_complete.tsa_driver import index_project, write_project
from tests.known_answer._compact import (
    assert_equivalent,
    expected_shape,
    parse_compact,
)
from tree_sitter_analyzer.mcp.tools.callers_compact import (
    CALLERS_FORMATS,
    compact_callers,
    compact_verdict,
)
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade


def _full(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "success": True,
        "verdict": "INFO",
        "function": "load",
        "caller_count": 0,
        "callers": [],
        "completeness": "complete",
        "completeness_reason": None,
        "completeness_reasons": [],
    }
    return {**base, **fields}


def _caller(name: str, file: str, line: int, **extra: Any) -> dict[str, Any]:
    return {"name": name, "file": file, "line": line, **extra}


# -- pure projection --------------------------------------------------------


def test_complete_answer_is_one_line_per_caller_plus_verdict() -> None:
    full = _full(
        caller_count=2,
        callers=[
            _caller("main", "app/cli.py", 10, callee_resolution="project"),
            _caller("run", "app/x.py", 3, callee_resolution="local"),
        ],
    )
    out = compact_callers(full)
    assert out["answer"] == (
        "callers of load: 2\n"
        "main  app/cli.py:10  project\n"
        "run  app/x.py:3  local\n"
        "verdict: complete"
    )
    assert out["completeness"] == "complete"
    assert_equivalent(full, out)


def test_incomplete_answer_names_the_top_three_reasons_and_counts_the_rest() -> None:
    reasons = ["UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND", "A", "B", "C"]
    full = _full(
        caller_count=1,
        callers=[_caller("main", "m.py", 1, callee_resolution="project")],
        completeness="incomplete",
        completeness_reason=reasons[0],
        completeness_reasons=reasons,
    )
    out = compact_callers(full)
    assert out["answer"].splitlines()[-1] == (
        "verdict: incomplete (UNRESOLVED_INBOUND, NAME_ONLY_INBOUND, A, +2); "
        "details: format=verbose"
    )
    assert_equivalent(full, out)


def test_unknown_answer_keeps_its_reason() -> None:
    full = _full(completeness="unknown", completeness_reasons=["SOURCE_MISSING"])
    out = compact_callers(full)
    assert out["answer"] == (
        "callers of load: 0\nverdict: unknown (SOURCE_MISSING); details: format=verbose"
    )
    assert_equivalent(full, out)


def test_reason_falls_back_to_the_single_reason_field() -> None:
    full = _full(
        completeness="unknown",
        completeness_reasons=None,
        completeness_reason="INDEX_MISSING",
    )
    assert compact_verdict(full) == "unknown (INDEX_MISSING)"


@pytest.mark.parametrize("value", [None, "", "partial", "COMPLETE", 1, True])
def test_any_unrecognised_completeness_is_unknown_never_complete(value: Any) -> None:
    full = _full(completeness=value)
    if value is None:
        full.pop("completeness")
    out = compact_callers(full)
    assert out["completeness"] == "unknown"
    assert out["answer"].splitlines()[-1].startswith("verdict: unknown")


def test_annotated_resolution_kind_wins_over_callee_resolution() -> None:
    full = _full(
        caller_count=1,
        callers=[
            _caller(
                "use",
                "u.py",
                4,
                callee_resolution="project",
                resolution_kind="annotated_receiver",
            )
        ],
    )
    assert "use  u.py:4  annotated_receiver" in compact_callers(full)["answer"]


def test_missing_caller_fields_render_placeholders() -> None:
    full = _full(caller_count=1, callers=[{}])
    listed = compact_callers(full, include_unconfirmed=True)["answer"]
    assert "?  ?:0  unknown" in listed


def test_truncated_answer_says_how_many_are_hidden() -> None:
    full = _full(
        caller_count=5,
        callers=[_caller("a", "a.py", 1, callee_resolution="project")],
        truncated=True,
    )
    out = compact_callers(full)
    assert "+4 more (raise limit)" in out["answer"].splitlines()
    assert_equivalent(full, out)


def test_error_answers_pass_through_unchanged() -> None:
    failure = {"success": False, "error": "boom"}
    assert compact_callers(failure) is failure
    assert compact_callers("not a dict") == "not a dict"  # type: ignore[arg-type]


def test_the_compact_answer_is_much_smaller_than_the_full_answer() -> None:
    callers = [
        _caller(
            f"f{i}",
            f"pkg/m{i}.py",
            i,
            callee_resolution="project",
            language="python",
            callee_resolved_file="pkg/t.py",
            body="def f():\n    return load()\n",
        )
        for i in range(10)
    ]
    full = _full(
        caller_count=10,
        callers=callers,
        completeness_checks={"required": 12, "checked": 12},
    )
    compact = compact_callers(full)
    assert len(json.dumps(compact)) * 3 < len(json.dumps(full))


# -- property: projection over arbitrary full answers -----------------------

_REASONS = st.sampled_from(
    [
        "UNRESOLVED_INBOUND",
        "NAME_ONLY_INBOUND",
        "UNRESOLVED_IN_DECLARING_FILE",
        "SOURCE_STALE",
        "EXCLUDED_FILE",
        "NON_CALL_REFERENCE",
    ]
)
_NAME = st.sampled_from(
    ["main", "<module>", "Text.join", "_run", "handler", "load", "a.b.c", "?"]
)
_FILE = st.builds(
    lambda d, f, ext: f"{d}{f}.{ext}",
    st.sampled_from(["", "pkg/", "src/app/", "tests/"]),
    st.sampled_from(["core", "app", "m_1", "index"]),
    st.sampled_from(["py", "ts", "java"]),
)
_CALLER = st.builds(
    lambda name, file, line, kind, annotated: {
        "name": name,
        "file": file,
        "line": line,
        "callee_resolution": kind,
        **({"resolution_kind": annotated} if annotated else {}),
    },
    _NAME,
    _FILE,
    st.integers(min_value=0, max_value=99999),
    st.sampled_from(["project", "same_file", "unknown", "import"]),
    st.sampled_from([None, "annotated_receiver", "import_alias"]),
)


@st.composite
def _full_answers(draw: st.DrawFn) -> dict[str, Any]:
    callers = draw(st.lists(_CALLER, max_size=12))
    hidden = draw(st.integers(min_value=0, max_value=5))
    completeness = draw(st.sampled_from(["complete", "incomplete", "unknown", None]))
    reasons = (
        []
        if completeness == "complete"
        else draw(st.lists(_REASONS, max_size=6, unique=True))
    )
    return _full(
        caller_count=len(callers) + hidden,
        callers=callers,
        truncated=bool(hidden),
        completeness=completeness,
        completeness_reason=reasons[0] if reasons else None,
        completeness_reasons=reasons,
    )


# slow_ok: pure projection, ~0.2 s standalone, but Hypothesis data generation
# under the coverage tracer took 14.7 s on the CI coverage axis. The live-index
# counterpart is invariant f in tests/property/test_callers_oracle_properties.py.
@pytest.mark.slow_ok
@settings(max_examples=60, deadline=None, database=None)
@given(full=_full_answers())
def test_property_compact_is_an_exact_projection_of_the_full_answer(
    full: dict[str, Any],
) -> None:
    out = compact_callers(full)
    assert_equivalent(full, out)
    shape = parse_compact(out)
    # Never more optimistic: `complete` iff the full answer says `complete`.
    assert (shape.completeness == "complete") == (full["completeness"] == "complete")
    assert set(shape.callers) == set(expected_shape(full).callers)


# -- facade wiring ------------------------------------------------------------

_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def load():\n    return 1\n",
    "pkg/app.py": (
        "from pkg.core import load\n\n\n"
        "def main():\n    return load()\n\n\n"
        "def again():\n    return load() + 1\n"
    ),
}


@pytest.fixture(scope="module")
def indexed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(tmp_path_factory.mktemp("compact1853"))
    write_project(root, _PROJECT)
    asyncio.run(index_project(root))
    return root


def _nav(root: Path, **args: Any) -> dict[str, Any]:
    return asyncio.run(
        build_nav_facade(str(root)).execute({"action": "callers", **args})
    )


def test_facade_compact_matches_the_full_answer(indexed: Path) -> None:
    full = _nav(indexed, function_name="load", limit=5000, include_bodies=False)
    compact = _nav(indexed, function_name="load", limit=5000, format="compact")
    assert {c["name"] for c in full["callers"]} == {"main", "again"}
    assert_equivalent(full, compact)


def test_facade_compact_with_bodies_requested_is_still_the_same_set(
    indexed: Path,
) -> None:
    full = _nav(indexed, function_name="load")
    compact = _nav(indexed, function_name="load", format="compact", include_bodies=True)
    assert_equivalent(full, compact)


def test_facade_default_and_verbose_are_the_full_answer(indexed: Path) -> None:
    default = _nav(indexed, function_name="load", include_bodies=False)
    verbose = _nav(
        indexed, function_name="load", include_bodies=False, format="verbose"
    )
    assert "format" not in default
    assert "callers" in default and "completeness_checks" in default
    assert set(verbose) == set(default)
    assert verbose["callers"] == default["callers"]
    assert verbose["completeness"] == default["completeness"]


def test_facade_rejects_an_unknown_format(indexed: Path) -> None:
    out = _nav(indexed, function_name="load", format="skeletal")
    assert out["success"] is False
    assert out["error_code"] == "INVALID_ARGUMENT"
    for allowed in CALLERS_FORMATS:
        assert allowed in out["error"]


def test_facade_rejects_compact_for_graph_scope(indexed: Path) -> None:
    out = _nav(indexed, function_name="load", format="compact", scope="graph")
    assert out["success"] is False
    assert out["error_code"] == "INVALID_ARGUMENT"
    assert "scope=point" in out["error"]


def test_facade_compact_carries_the_follow_up_hint(indexed: Path) -> None:
    facade = build_nav_facade(str(indexed))

    async def run() -> dict[str, Any]:
        await facade.execute({"action": "callers", "function_name": "load"})
        # Asking for a caller of the previous answer triggers the RFC-0041 hint.
        return await facade.execute(
            {"action": "callers", "function_name": "main", "format": "compact"}
        )

    out = asyncio.run(run())
    assert out["format"] == "compact"
    assert "uql" in out.get("next_step", "")


def test_help_schema_declares_format_for_callers_only() -> None:
    facade = build_nav_facade(project_root=None)

    async def run(action: str) -> dict[str, Any]:
        return await facade.execute({"action": "help", "target_action": action})

    callers_help = json.dumps(asyncio.run(run("callers")))
    assert "compact" in callers_help
    assert "format=compact" in facade.full_description()
