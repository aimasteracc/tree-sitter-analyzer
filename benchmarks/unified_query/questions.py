"""Benchmark questions and their oracle answers (RFC-0041).

Each question names the analyst's question, the concrete targets for one
repository, and how the independent oracle answers it. Targets were chosen so
every name on the relevant relation path has exactly one definition in the
repository (see ``oracle.unique_definition``); a name-based oracle is exact
under that constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from oracle import Oracle, is_test_file


@dataclass(frozen=True)
class Question:
    qid: str
    kind: str
    text: str
    params: dict[str, Any] = field(default_factory=dict)


QUESTIONS: dict[str, list[Question]] = {
    "rich": [
        Question(
            "Q1",
            "callers_tests",
            "Who calls get_truecolor, and which tests cover those callers?",
            {"x": "get_truecolor"},
        ),
        Question(
            "Q2",
            "module_untested",
            "Functions in rich/_win32_console.py that call "
            "SetConsoleCursorPosition but have no tests.",
            {"module": "rich/_win32_console.py", "y": "SetConsoleCursorPosition"},
        ),
        Question(
            "Q3",
            "callers_depth",
            "Callers of blend_rgb up to two levels, restricted to rich/.",
            {"x": "blend_rgb", "depth": 2, "prefix": "rich/"},
        ),
        Question(
            "Q4",
            "implementers",
            "Classes implementing __rich_measure__, with the functions that call it.",
            {"m": "__rich_measure__"},
        ),
        Question(
            "Q5",
            "impact",
            "Impact of changing export_html: transitive callers, tests and files.",
            {"x": "export_html"},
        ),
        Question("Q6", "callers", "Who calls pad_right?", {"x": "pad_right"}),
        Question(
            "Q7",
            "tests",
            "Which tests exercise adjust_line_length?",
            {"x": "adjust_line_length"},
        ),
        Question(
            "Q8",
            "callees",
            "Which project functions does export_html call?",
            {"x": "export_html", "file": "rich/console.py"},
        ),
    ],
    "tsa": [
        Question(
            "Q1",
            "callers_tests",
            "Who calls raw_to_path, and which tests cover those callers?",
            {"x": "raw_to_path"},
        ),
        Question(
            "Q2",
            "module_untested",
            "Functions in synapse_resolver/__init__.py that call resolve_items "
            "but have no tests.",
            {
                "module": "tree_sitter_analyzer/synapse_resolver/__init__.py",
                "y": "resolve_items",
            },
        ),
        Question(
            "Q3",
            "callers_depth",
            "Callers of file_content_hash up to two levels, restricted to "
            "tree_sitter_analyzer/.",
            {"x": "file_content_hash", "depth": 2, "prefix": "tree_sitter_analyzer/"},
        ),
        Question(
            "Q4",
            "implementers",
            "Classes implementing _on_project_root_changed, with the functions "
            "that call it.",
            {"m": "_on_project_root_changed"},
        ),
        Question(
            "Q5",
            "impact",
            "Impact of changing _ensure_column: transitive callers, tests and files.",
            {"x": "_ensure_column"},
        ),
        Question(
            "Q6",
            "callers",
            "Who calls build_test_command?",
            {"x": "build_test_command"},
        ),
        Question(
            "Q7",
            "tests",
            "Which tests exercise callee_refs_of?",
            {"x": "callee_refs_of"},
        ),
        Question(
            "Q8",
            "callees",
            "Which project functions does capture_current_source_snapshot call?",
            {
                "x": "capture_current_source_snapshot",
                "file": "tree_sitter_analyzer/index_source_snapshot.py",
            },
        ),
    ],
}


def _prod(keys: set[str]) -> set[str]:
    return {k for k in keys if not is_test_file(k.split("::")[0])}


def _name(key: str) -> str:
    return key.split("::", 1)[1]


def oracle_answer(oracle: Oracle, q: Question) -> dict[str, set[str]]:
    """The ground-truth sets for one question."""
    p = q.params
    if q.kind == "callers_tests":
        callers = oracle.callers(p["x"])
        tests: set[str] = set()
        for key in _prod(callers):
            tests |= oracle.tests_of(_name(key))
        return {"callers": callers, "tests": tests}
    if q.kind == "module_untested":
        return {
            "functions": oracle.module_funcs_calling_without_tests(p["module"], p["y"])
        }
    if q.kind == "callers_depth":
        return {"callers": oracle.callers_within(p["x"], p["depth"], p["prefix"])}
    if q.kind == "implementers":
        return {
            "classes": oracle.implementers(p["m"]),
            "callers": oracle.callers(p["m"]),
        }
    if q.kind == "impact":
        callers = oracle.transitive_callers(p["x"])
        tests = oracle.tests_of(p["x"])
        for key in callers:
            tests |= oracle.tests_of(_name(key))
        files = {k.split("::")[0] for k in callers | tests}
        return {"callers": callers, "tests": tests, "files": files}
    if q.kind == "callers":
        return {"callers": oracle.callers(p["x"])}
    if q.kind == "tests":
        return {"tests": oracle.tests_of(p["x"])}
    if q.kind == "callees":
        return {"callees": oracle.callees(p["file"], p["x"])}
    raise ValueError(f"unknown question kind {q.kind}")
