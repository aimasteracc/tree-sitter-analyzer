"""Corpus preflight for the NO1-010B benchmark (RFC-0026 §3/§4/§5).

RFC-0026 §4 requires preflight to run **before any attempt is recorded**: a
preflight failure rejects the corpus run with zero attempts consumed.

The load-bearing check is the **oracle red baseline** (§3): *"Preflight executes
the oracle on the unmodified fixture and requires declared FAIL plus the exact
token."* Without it the corpus's only valuable property — that each oracle can
tell a correct patch from an empty one — lives as prose, and an innocent fixture
edit silently and permanently invalidates a task while every other check still
passes. Executing a **committed fixture** needs no sandbox: ``oracle.py``'s
sandbox requirement is about *candidate* code (arbitrary, untrusted, able to
forge completion), and §3 places this check before any candidate tree exists. A
committed fixture is exactly as trusted as ``tests/``.

The remaining gates are computed from the run's actual inputs, never asserted as
literals, and each carries a category so the record cannot blur *code-blocked*
work (model-free engineering, no budget) with *budget-blocked* work (needs
authorized model spend).
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - list-form oracle launch, never a shell
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .digest import corpus_digests
from .oracle import (
    ORACLE_TIMEOUT_S,
    OracleStatus,
)
from .oracle import (
    # Same-package sibling: reusing the one declared-result parser is correct,
    # and keeps ``oracle.py`` untouched so its pre-existing POSIX-only
    # ``signal.SIGKILL`` mypy baseline entry is not dragged into this change.
    _parse_result_line as parse_declared_result,
)
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

MANIFEST_NAME = "manifest.json"
_PLACEHOLDER_COMMIT = "0" * 40

#: Gate categories. The distinction is load-bearing: B1 is entirely model-free,
#: so folding it in with the arm gates teaches the next reader that nothing can
#: progress without a budget decision, which is false.
CODE_BLOCKED = "code_blocked"
BUDGET_BLOCKED = "budget_blocked"
EXTERNAL_PARTY_BLOCKED = "external_party_blocked"

CATEGORY_MEANING = {
    CODE_BLOCKED: (
        "model-free engineering work; needs no model spend and no external party"
    ),
    BUDGET_BLOCKED: "needs pre-authorized model spend (human decision)",
    EXTERNAL_PARTY_BLOCKED: (
        "needs an independent human or an out-of-evaluator-control store; "
        "no model spend"
    ),
}


@dataclass(frozen=True)
class Check:
    """One decidable preflight check and its outcome."""

    check: str
    status: str  # PASS | FAIL
    detail: str


@dataclass(frozen=True)
class Gate:
    """One RFC-0026 gate this run does not satisfy, with its blocking category."""

    gate: str
    constraint: str
    category: str
    status: str  # NOT_SATISFIED
    detail: str


@dataclass(frozen=True)
class OracleSignature:
    """An independent reviewer's approval of one registered oracle (C59)."""

    task_id: str
    signer: str
    key_fingerprint: str
    signature: str


@dataclass(frozen=True)
class PreflightResult:
    """Aggregate preflight outcome; ``ACCEPTED`` only when nothing blocks."""

    status: str  # ACCEPTED | REJECTED
    checks: tuple[Check, ...]
    gates: tuple[Gate, ...]

    @property
    def baseline_verified(self) -> bool:
        return all(
            check.status == "PASS"
            for check in self.checks
            if check.check == "oracle_red_baseline"
        ) and any(check.check == "oracle_red_baseline" for check in self.checks)


def _fixture_suite(repo_dir: Path) -> set[str]:
    """Return the fixture's complete pytest suite as canonical relative paths."""
    return {
        path.relative_to(repo_dir).as_posix()
        for path in repo_dir.glob("tests/**/test_*.py")
    }


def _terminal_counts(records: Sequence[BenchmarkRecord]) -> tuple[int, int]:
    passes = sum(1 for item in records if item.expected_terminal.verdict == "PASS")
    fails = sum(1 for item in records if item.expected_terminal.verdict == "FAIL")
    return passes, fails


def run_oracle_baseline(
    record: BenchmarkRecord,
    corpus_root: Path,
    *,
    python_executable: str | None = None,
) -> tuple[bool, str]:
    """Execute one oracle on its unmodified fixture; require declared FAIL.

    Returns ``(red, detail)``. ``red`` is true only when the oracle exits 0 and
    declares ``FAIL`` with the exact registered ``oracle_baseline_reason``
    token. A declared ``PASS`` means the fixture no longer exhibits the defect,
    so the task can never distinguish a real patch from an empty one.
    """
    # Absolute: the child runs with cwd set to the fixture root, so a corpus-root
    # relative oracle path would no longer resolve there.
    oracle_path = (corpus_root / record.oracle).resolve()
    fixture_root = (corpus_root / record.repo).resolve()
    if not oracle_path.is_file():
        return False, f"{record.id}: oracle file missing"
    if not fixture_root.is_dir():
        return False, f"{record.id}: fixture repo missing"
    try:
        completed = subprocess.run(  # nosec B603
            [python_executable or sys.executable, "-u", str(oracle_path)],
            cwd=str(fixture_root),
            capture_output=True,
            text=True,
            timeout=ORACLE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"{record.id}: oracle timed out on the unmodified fixture"
    except OSError as exc:
        return False, f"{record.id}: oracle could not execute ({exc})"
    if completed.returncode != 0:
        return False, (
            f"{record.id}: oracle exited {completed.returncode} on the "
            "unmodified fixture (load or execution error, not a verdict)"
        )
    status = parse_declared_result(
        completed.stdout + completed.stderr, record.oracle_baseline_reason
    )
    if status is OracleStatus.FAIL:
        return True, f"{record.id}: red with token {record.oracle_baseline_reason!r}"
    if status is OracleStatus.PASS:
        return False, (
            f"{record.id}: oracle declares PASS on the UNMODIFIED fixture - the "
            "registered defect is gone, so this task can no longer detect a "
            "wrong patch"
        )
    return False, (
        f"{record.id}: declared-result protocol violated (missing, duplicated, "
        f"non-final marker, or reason token != "
        f"{record.oracle_baseline_reason!r})"
    )


def _oracle_baseline_check(
    records: Sequence[BenchmarkRecord],
    corpus_root: Path,
    python_executable: str | None,
) -> Check:
    failures = []
    for record in records:
        red, detail = run_oracle_baseline(
            record, corpus_root, python_executable=python_executable
        )
        if not red:
            failures.append(detail)
    if failures:
        return Check("oracle_red_baseline", "FAIL", "; ".join(failures))
    return Check(
        "oracle_red_baseline",
        "PASS",
        f"all {len(records)} oracles declare FAIL on their unmodified fixture "
        "with the exact registered token",
    )


def _manifest_check(corpus_root: Path, corpus_path: Path) -> Check:
    manifest_path = corpus_root / MANIFEST_NAME
    if not manifest_path.is_file():
        return Check(
            "manifest_digests_match",
            "FAIL",
            f"{MANIFEST_NAME} is missing; the corpus is unpinned",
        )
    try:
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Check("manifest_digests_match", "FAIL", f"unreadable manifest: {exc}")
    measured = corpus_digests(corpus_root, corpus_path)
    drifted = [
        key
        for key in ("corpus_sha256", "fixture_tree_sha256", "oracles")
        if recorded.get(key) != measured[key]
    ]
    if drifted:
        return Check(
            "manifest_digests_match",
            "FAIL",
            f"digest drift in {drifted}; regenerate with --update-manifest after "
            "a deliberate corpus change",
        )
    return Check(
        "manifest_digests_match",
        "PASS",
        "corpus, fixture-tree and oracle digests match the recorded manifest",
    )


def static_checks(
    records: Sequence[BenchmarkRecord],
    corpus_root: Path,
    *,
    corpus_path: Path | None = None,
    python_executable: str | None = None,
) -> list[Check]:
    """Run every preflight check, including the §3 oracle red-baseline check."""
    checks: list[Check] = []

    count = len(records)
    checks.append(
        Check(
            "task_count_exact",
            "PASS" if count == EXPECTED_TASK_COUNT else "FAIL",
            f"{count} tasks (registered {EXPECTED_TASK_COUNT})",
        )
    )

    counts = per_class_counts(list(records))
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

    escaping = sorted(
        {
            item.repo
            for item in records
            if not (corpus_root / item.repo)
            .resolve()
            .is_relative_to(corpus_root.resolve())
        }
    )
    missing_repos = sorted(
        {item.repo for item in records if not (corpus_root / item.repo).is_dir()}
    )
    checks.append(
        Check(
            "fixture_repos_present",
            "PASS" if not missing_repos and not escaping else "FAIL",
            "all pinned fixture repos exist beneath the corpus root"
            if not missing_repos and not escaping
            else f"missing: {missing_repos}; outside corpus root: {escaping}",
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

    if corpus_path is not None:
        checks.append(_manifest_check(corpus_root, corpus_path))

    checks.append(_oracle_baseline_check(records, corpus_root, python_executable))
    return checks


def unsatisfied_gates(
    records: Sequence[BenchmarkRecord],
    *,
    arm_ids: Sequence[str] = (),
    paired_cell_count: int = 0,
    verifier_available: bool = False,
    registration_anchor: str | None = None,
    oracle_signatures: Sequence[OracleSignature] = (),
) -> list[Gate]:
    """Derive the unsatisfied gates from the run's actual inputs.

    Every branch is computed, so a future run that genuinely supplies arms, a
    verifier, an external anchor or signatures sees the corresponding gate
    disappear instead of being told it is permanently blocked.
    """
    gates: list[Gate] = []

    if not verifier_available:
        gates.append(
            Gate(
                "patch_verifier_runner",
                "RFC-0026 B1",
                CODE_BLOCKED,
                "NOT_SATISFIED",
                "no patch application, isolated worktree, read-only candidate "
                "mount, write journal, stale-row projection comparison, or "
                "unsupported-relationship evidence check exists. B1 is entirely "
                "model-free: its exit artifact is 10/10 pre-registered terminal "
                "pairs plus the mutation suite, with no arms and no spend",
            )
        )

    placeholder = sorted(
        {item.repo for item in records if item.repo_commit == _PLACEHOLDER_COMMIT}
    )
    if placeholder:
        gates.append(
            Gate(
                "fixture_commit_pinning",
                "RFC-0026 §1",
                CODE_BLOCKED,
                "NOT_SATISFIED",
                f"{placeholder} carry the all-zero placeholder repo_commit, so "
                "the runner cannot check out a pinned commit and fail closed on "
                "drift; the committed manifest digests are a drift detector, not "
                "a commit pin",
            )
        )

    if registration_anchor is None:
        gates.append(
            Gate(
                "external_registration_anchor",
                "C14/C27",
                EXTERNAL_PARTY_BLOCKED,
                "NOT_SATISFIED",
                "pre-registration must be anchored in an append-only store "
                "outside evaluator control; a git-committed file (including this "
                "corpus manifest) cannot establish pre-execution ordering",
            )
        )

    signed = {signature.task_id for signature in oracle_signatures}
    unsigned = sorted({item.id for item in records} - signed)
    if unsigned:
        gates.append(
            Gate(
                "independent_oracle_signature",
                "C59",
                EXTERNAL_PARTY_BLOCKED,
                "NOT_SATISFIED",
                f"{len(unsigned)} of {len(records)} oracles carry no signature "
                "over (task_id, repo_commit, oracle_hash, expected_terminal) by "
                "a reviewer who authored neither the corpus nor the "
                "implementation under test",
            )
        )

    distinct_arms = sorted(set(arm_ids))
    if len(distinct_arms) < 3:
        gates.append(
            Gate(
                "three_non_pooled_agent_arms",
                "C31 / RFC-0026 §2",
                BUDGET_BLOCKED,
                "NOT_SATISFIED",
                f"{len(distinct_arms)} distinct arms registered; at least three "
                "non-pooled client/model arms are a mandatory B2 completion "
                "gate, and a baseline produced only from supplied reference "
                "patches does not satisfy NO1-010B",
            )
        )

    if paired_cell_count == 0:
        gates.append(
            Gate(
                "paired_control_arms",
                "C28/C37/C56",
                BUDGET_BLOCKED,
                "NOT_SATISFIED",
                "no paired cells registered; each evidence-enabled arm needs a "
                "pre-registered evidence-disabled control and a complete "
                "pair_id x task_id x repeat_index matrix",
            )
        )

    return gates


def run_preflight(
    records: Sequence[BenchmarkRecord],
    corpus_root: Path,
    *,
    corpus_path: Path | None = None,
    python_executable: str | None = None,
    arm_ids: Sequence[str] = (),
    paired_cell_count: int = 0,
    verifier_available: bool = False,
    registration_anchor: str | None = None,
    oracle_signatures: Sequence[OracleSignature] = (),
) -> PreflightResult:
    """Return the preflight verdict for the committed corpus."""
    checks = static_checks(
        records,
        corpus_root,
        corpus_path=corpus_path,
        python_executable=python_executable,
    )
    gates = unsatisfied_gates(
        records,
        arm_ids=arm_ids,
        paired_cell_count=paired_cell_count,
        verifier_available=verifier_available,
        registration_anchor=registration_anchor,
        oracle_signatures=oracle_signatures,
    )
    blocked = any(check.status != "PASS" for check in checks) or bool(gates)
    return PreflightResult(
        status="REJECTED" if blocked else "ACCEPTED",
        checks=tuple(checks),
        gates=tuple(gates),
    )
