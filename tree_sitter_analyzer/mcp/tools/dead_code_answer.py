"""Evidence-carrying answers for the dead-code surfaces (#1958).

"No dead code" is only an answer when functions were analyzed and the callers
evidence could certify candidates. With 0 functions in scope (wrong root, a
``path`` that matches nothing, only test files) or with evidence that cannot
certify anything (no index, certification budget spent before any candidate
was certified) the answer is ``unknown`` (``success: false``,
``error_code: INSUFFICIENT_EVIDENCE``) and names the exact command, for the
CLI and for MCP, that would produce evidence. A known answer names how many
functions and files it covers. Same contract as ``--unreachable-code`` (#1955).

This module only reads counts; which candidates are dead is still decided by
the #1941 certification (:mod:`.dead_code_certify`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...dead_code_entries import _is_test_file
from .dead_code_certify import CERTIFY_BUDGET_SECONDS

STATUS_FOUND = "dead_code_found"
STATUS_NONE_FOUND = "none_found"
STATUS_UNKNOWN = "unknown"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

#: Machine-readable causes of an ``unknown`` answer.
NO_FUNCTIONS = "NO_FUNCTIONS"
EMPTY_SCOPE = "EMPTY_SCOPE"
TESTS_ONLY = "TESTS_ONLY"
NO_INDEX = "NO_INDEX"
CERTIFICATION_BUDGET = "CERTIFICATION_BUDGET"

_DEAD_CLI = "tree-sitter-analyzer --dead-code"
_OVERVIEW_CLI = "tree-sitter-analyzer --codegraph-overview"
_PREFIXES_NAMED = 5


@dataclass(frozen=True)
class ScopeEvidence:
    """How many functions the answer can speak about."""

    project_functions: int
    functions_in_scope: int
    files_in_scope: int
    test_functions_in_scope: int
    indexed: bool
    path: str | None = None
    include_tests: bool = False
    #: ``(prefix, functions)`` holding analyzable functions, largest first:
    #: one level below ``path`` when that scope has functions, else project top.
    prefixes: tuple[tuple[str, int], ...] = ()

    def to_stats(self) -> dict[str, Any]:
        return {
            "functions_in_scope": self.functions_in_scope,
            "files_in_scope": self.files_in_scope,
            "test_functions_in_scope": self.test_functions_in_scope,
            "index_used": self.indexed,
        }


@dataclass(frozen=True)
class CertCounts:
    """What the callers certification did with the in-scope candidates."""

    candidates: int
    certified: int
    unchecked: int


def under_path(file_path: str, path: str) -> bool:
    """True if ``file_path`` is ``path`` or lives under it, on whole segments.

    Both sides use forward slashes; a trailing slash is ignored, a leading
    ``./`` is stripped and ``.`` (or empty) means the whole project, so
    'a/m' does NOT match 'a/mcp/x.py' while ``./pkg`` matches ``pkg/x.py``.
    """
    f = file_path.replace("\\", "/")
    p = _norm(path)
    if p == "":
        return True
    return f == p or f.startswith(p + "/")


def _norm(path: str) -> str:
    p = path.replace("\\", "/").strip()
    if p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    return "" if p == "." else p


def scope_evidence(
    function_files: Mapping[str, int],
    *,
    path: str | None,
    include_tests: bool,
    indexed: bool,
) -> ScopeEvidence:
    """Count the functions in scope from ``{file: function count}``."""
    in_scope = {
        f: n for f, n in function_files.items() if path is None or under_path(f, path)
    }
    tests = {f for f in in_scope if not include_tests and _is_test_file(f)}
    analyzed = {f: n for f, n in in_scope.items() if f not in tests and n}
    if analyzed:
        prefixes = _prefixes(analyzed, _norm(path or ""))
    else:
        project = {
            f: n
            for f, n in function_files.items()
            if n and (include_tests or not _is_test_file(f))
        }
        prefixes = _prefixes(project, "")
    return ScopeEvidence(
        project_functions=sum(function_files.values()),
        functions_in_scope=sum(analyzed.values()),
        files_in_scope=len(analyzed),
        test_functions_in_scope=sum(in_scope[f] for f in tests),
        indexed=indexed,
        path=path,
        include_tests=include_tests,
        prefixes=prefixes,
    )


def _prefixes(files: Mapping[str, int], base: str) -> tuple[tuple[str, int], ...]:
    depth = len(base.split("/")) if base else 0
    counts: Counter[str] = Counter()
    for file_path, n in files.items():
        parts = file_path.replace("\\", "/").split("/")
        # A file directly in ``base`` keeps its own path as the prefix.
        counts["/".join(parts[: depth + 1])] += n
    return tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def evidence_sentence(ev: ScopeEvidence) -> str:
    return f"{ev.functions_in_scope} function(s) in {ev.files_in_scope} file(s)"


def insufficient_evidence(
    ev: ScopeEvidence, counts: CertCounts, root: str, *, surface: str = "dead"
) -> tuple[str, str] | None:
    """``(cause, next_step)`` when the answer has no evidence, else ``None``."""
    if ev.project_functions == 0:
        return NO_FUNCTIONS, _no_functions(root, surface)
    if ev.functions_in_scope == 0:
        if ev.test_functions_in_scope:
            return TESTS_ONLY, _tests_only(ev, root)
        return EMPTY_SCOPE, _empty_scope(ev, root)
    if counts.candidates and not counts.certified:
        if not ev.indexed:
            return NO_INDEX, _no_index(counts, root, surface)
        if counts.unchecked:
            return CERTIFICATION_BUDGET, _budget(ev, counts, root)
    return None


def overview_dead_answer(
    ev: ScopeEvidence, counts: CertCounts, root: str, certified_status: str
) -> tuple[str, str, str | None]:
    """``(dead_code_status, dead_code_next_step, cause)`` for codegraph_overview."""
    found = insufficient_evidence(ev, counts, root, surface="overview")
    if found is not None:
        cause, step = found
        return STATUS_UNKNOWN, step, cause
    if counts.certified:
        step = f"{counts.certified} certified dead of {evidence_sentence(ev)} analyzed."
    else:
        step = f"No certified dead code among {evidence_sentence(ev)} analyzed."
    return certified_status, step, None


def mark_unknown(response: dict[str, Any], cause: str, next_step: str) -> None:
    """Turn ``response`` into an ``INSUFFICIENT_EVIDENCE`` answer, in place."""
    response.update(
        {
            "success": False,
            "status": STATUS_UNKNOWN,
            # A failure may only carry ERROR / NOT_FOUND, and NOT_FOUND reads
            # as "no dead code" -- the exact misreading to avoid.
            "verdict": "ERROR",
            "error_code": INSUFFICIENT_EVIDENCE,
            "insufficient_evidence_reason": cause,
            "error": (
                f"{INSUFFICIENT_EVIDENCE} ({cause}): the dead-code evidence is "
                "insufficient, so this is not a 'no dead code' answer."
            ),
            "next_step": next_step,
        }
    )


def _rerun(surface: str, root: str) -> str:
    if surface == "overview":
        return (
            f'`{_OVERVIEW_CLI} --project-root "{root}"` (MCP: `health action=overview`)'
        )
    return f'`{_DEAD_CLI} --project-root "{root}"` (MCP: `health action=dead`)'


def _no_functions(root: str, surface: str) -> str:
    cli = _OVERVIEW_CLI if surface == "overview" else _DEAD_CLI
    action = "overview" if surface == "overview" else "dead"
    return (
        f"0 functions found under {root}: no supported source file defines a "
        "function there (wrong root, or an unsupported language). Point the "
        f'analysis at the source tree: `{cli} --project-root "<source dir>"` '
        f"(MCP: `set_project_path` to the source dir, then `health action={action}`)."
    )


def _path_flags(ev: ScopeEvidence) -> tuple[str, str]:
    if ev.path is None:
        return "", ""
    return f' --dead-code-path "{ev.path}"', f' path="{ev.path}"'


def _tests_only(ev: ScopeEvidence, root: str) -> str:
    where = f"under path {ev.path!r}" if ev.path is not None else f"under {root}"
    cli_path, mcp_path = _path_flags(ev)
    return (
        f"All {ev.test_functions_in_scope} function(s) {where} are in test files, "
        "which count as entry points (never dead) unless analyzed as code. "
        f"Include them: `{_DEAD_CLI} --dead-code-include-tests{cli_path} "
        f'--project-root "{root}"` (MCP: `health action=dead '
        f"include_test_files=true{mcp_path}`)."
    )


def _empty_scope(ev: ScopeEvidence, root: str) -> str:
    head = (
        f"No function is defined under path {ev.path!r} "
        f"({ev.project_functions} function(s) in the project; path is "
        "project-relative and matched on whole segments)."
    )
    if not ev.prefixes:
        return (
            f"{head} The project's functions are all in test files: "
            f'`{_DEAD_CLI} --dead-code-include-tests --project-root "{root}"` '
            "(MCP: `health action=dead include_test_files=true`)."
        )
    named = ", ".join(f"{p} ({n})" for p, n in ev.prefixes[:_PREFIXES_NAMED])
    best = ev.prefixes[0][0]
    return (
        f"{head} Prefixes that hold functions: {named}. Re-run on one: "
        f'`{_DEAD_CLI} --dead-code-path "{best}" --project-root "{root}"` '
        f'(MCP: `health action=dead path="{best}"`).'
    )


def _no_index(counts: CertCounts, root: str, surface: str) -> str:
    return (
        f"The project has no index, so the callers evidence could not certify "
        f"any of the {counts.candidates} candidate(s) (possibly_dead names the "
        "open evidence for each). Build the index: "
        f'`tree-sitter-analyzer --full-index --project-root "{root}"` '
        f"(MCP: `index action=full`), then re-run {_rerun(surface, root)}."
    )


def _budget(ev: ScopeEvidence, counts: CertCounts, root: str) -> str:
    best = ev.prefixes[0][0] if ev.prefixes else (ev.path or ".")
    return (
        f"The {CERTIFY_BUDGET_SECONDS:g}s certification budget ran out: "
        f"{counts.unchecked} of {counts.candidates} candidate(s) were not checked "
        "and none was certified. Narrow the scope: "
        f'`{_DEAD_CLI} --dead-code-path "{best}" --project-root "{root}"` '
        f'(MCP: `health action=dead path="{best}"`).'
    )
