"""Corpus preflight for the NO1-010B benchmark (RFC-0026 §4/§5).

RFC-0026 §4 requires preflight to run **before any attempt is recorded**: a
preflight failure rejects the corpus run with zero attempts consumed. This
module implements the checks that are decidable from the committed corpus
without executing candidate code, and it enumerates the gates that are
*not* satisfiable from inside the repository (they need the B1 sandboxed
patch verifier, a registration store outside evaluator control, an
independent human oracle signature, or authorized model spend).

Nothing here executes an oracle. RFC-0026 §3 and
``no1_010b/oracle.py`` are explicit that a parsed declared result may only
become a product verdict through B1's trusted wrapper behind a
kernel-enforced sandbox; this module therefore reports the oracle
red-baseline gate as unsatisfied rather than authorizing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .record import BenchmarkRecord
from .record_loader import per_class_counts

#: Pre-registered seed-corpus shape (RFC-0026 §5).
EXPECTED_TASK_COUNT = 10
EXPECTED_CLASS_COUNTS = {
    "bugfix": 4,
    "refactor": 2,
    "migration": 2,
    "test_selection": 2,
}
EXPECTED_PASS_COUNT = 9
EXPECTED_FAIL_COUNT = 1


@dataclass(frozen=True)
class Check:
    """One decidable preflight check and its outcome."""

    check: str
    status: str  # PASS | FAIL
    detail: str


@dataclass(frozen=True)
class Gate:
    """One RFC-0026 gate that cannot be satisfied from inside the repository."""

    gate: str
    constraint: str
    status: str  # NOT_SATISFIED
    detail: str


@dataclass(frozen=True)
class PreflightResult:
    """Aggregate preflight outcome; ``ACCEPTED`` only when nothing blocks."""

    status: str  # ACCEPTED | REJECTED
    checks: tuple[Check, ...]
    gates: tuple[Gate, ...]


def _fixture_suite(repo_dir: Path) -> set[str]:
    """Return the fixture's complete pytest suite as canonical relative paths."""
    return {
        path.relative_to(repo_dir).as_posix()
        for path in repo_dir.glob("tests/**/test_*.py")
    }


def _terminal_counts(records: list[BenchmarkRecord]) -> tuple[int, int]:
    passes = sum(1 for item in records if item.expected_terminal.verdict == "PASS")
    fails = sum(1 for item in records if item.expected_terminal.verdict == "FAIL")
    return passes, fails


def static_checks(records: list[BenchmarkRecord], corpus_root: Path) -> list[Check]:
    """Run every preflight check decidable without executing candidate code."""
    checks: list[Check] = []

    count = len(records)
    checks.append(
        Check(
            "task_count_exact",
            "PASS" if count == EXPECTED_TASK_COUNT else "FAIL",
            f"{count} tasks (registered {EXPECTED_TASK_COUNT})",
        )
    )

    counts = per_class_counts(records)
    checks.append(
        Check(
            "per_class_counts_exact",
            "PASS" if counts == EXPECTED_CLASS_COUNTS else "FAIL",
            f"{counts} (registered {EXPECTED_CLASS_COUNTS})",
        )
    )

    passes, fails = _terminal_counts(records)
    checks.append(
        Check(
            "expected_terminal_distribution_exact",
            "PASS"
            if (passes, fails) == (EXPECTED_PASS_COUNT, EXPECTED_FAIL_COUNT)
            else "FAIL",
            f"{passes} PASS / {fails} FAIL "
            f"(registered {EXPECTED_PASS_COUNT} PASS / {EXPECTED_FAIL_COUNT} FAIL)",
        )
    )

    missing_oracles = sorted(
        item.oracle for item in records if not (corpus_root / item.oracle).is_file()
    )
    checks.append(
        Check(
            "oracle_files_present",
            "PASS" if not missing_oracles else "FAIL",
            "all registered oracles exist"
            if not missing_oracles
            else f"missing: {missing_oracles}",
        )
    )

    missing_repos = sorted(
        {item.repo for item in records if not (corpus_root / item.repo).is_dir()}
    )
    checks.append(
        Check(
            "fixture_repos_present",
            "PASS" if not missing_repos else "FAIL",
            "all pinned fixture repos exist"
            if not missing_repos
            else f"missing: {missing_repos}",
        )
    )

    subset_failures: list[str] = []
    for item in records:
        if not item.selected_tests:
            continue
        suite = _fixture_suite(corpus_root / item.repo)
        selected = set(item.selected_tests)
        if not selected < suite:
            subset_failures.append(
                f"{item.id}: {sorted(selected)} vs suite {sorted(suite)}"
            )
    checks.append(
        Check(
            "affected_test_oracle_strict_subset",
            "PASS" if not subset_failures else "FAIL",
            "every test_selection oracle is a strict subset of its suite"
            if not subset_failures
            else f"violations: {subset_failures}",
        )
    )

    return checks


def unsatisfied_gates() -> list[Gate]:
    """Enumerate the RFC-0026 gates no in-repository run can satisfy."""
    return [
        Gate(
            "patch_verifier_runner",
            "RFC-0026 B1",
            "NOT_SATISFIED",
            "no patch application, isolated worktree, read-only candidate mount, "
            "write journal, stale-row projection comparison, or unsupported-"
            "relationship evidence check exists; only the pure record/patch/"
            "oracle-protocol pieces are implemented",
        ),
        Gate(
            "oracle_red_baseline",
            "C42/C43",
            "NOT_SATISFIED",
            "the declared-result protocol may only become a verdict through B1's "
            "trusted wrapper behind a kernel-enforced sandbox; oracle.py returns "
            "UNKNOWN/SANDBOX_FAILURE for every parsed declaration by design",
        ),
        Gate(
            "fixture_commit_pinning",
            "RFC-0026 §1",
            "NOT_SATISFIED",
            "the in-tree seed fixtures carry the RFC's all-zero placeholder "
            "repo_commit, so the runner cannot check out a pinned commit and fail "
            "closed on drift; a clean-tree fingerprint must replace it in B1",
        ),
        Gate(
            "external_registration_anchor",
            "C14/C27",
            "NOT_SATISFIED",
            "pre-registration must be anchored in an append-only store outside "
            "evaluator control; a git-committed file is explicitly insufficient",
        ),
        Gate(
            "independent_oracle_signature",
            "C59",
            "NOT_SATISFIED",
            "every oracle must be signed over (task_id, repo_commit, oracle_hash, "
            "expected_terminal) by a reviewer who authored neither the corpus nor "
            "the implementation under test; no signature exists",
        ),
        Gate(
            "three_non_pooled_agent_arms",
            "C31 / RFC-0026 §2",
            "NOT_SATISFIED",
            "at least three distinct, non-pooled client/model arms are a mandatory "
            "B2 completion gate; a baseline produced only from supplied reference "
            "patches does not satisfy NO1-010B",
        ),
        Gate(
            "paired_control_arms",
            "C28/C37/C56",
            "NOT_SATISFIED",
            "each evidence-enabled arm needs a pre-registered evidence-disabled "
            "control and a complete pair_id x task_id x repeat_index matrix",
        ),
    ]


def run_preflight(records: list[BenchmarkRecord], corpus_root: Path) -> PreflightResult:
    """Return the preflight verdict for the committed corpus."""
    checks = static_checks(records, corpus_root)
    gates = unsatisfied_gates()
    blocked = any(check.status != "PASS" for check in checks) or bool(gates)
    return PreflightResult(
        status="REJECTED" if blocked else "ACCEPTED",
        checks=tuple(checks),
        gates=tuple(gates),
    )
