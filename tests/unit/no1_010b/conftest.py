"""Shared, session-scoped NO1-010B corpus fixtures.

RFC-0026 §3's oracle red-baseline check executes all ten oracles as real
subprocesses. Doing that once per test *module* meant ~30 process spawns per
xdist worker, which is enough CPU contention on a slow CI runner to push
unrelated unit tests past their per-test wall-clock budget. Computing it once
per session keeps the real check while cutting the footprint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.preflight import PreflightResult, run_preflight
from tree_sitter_analyzer.no1_010b.record import BenchmarkRecord
from tree_sitter_analyzer.no1_010b.record_loader import load_corpus_records

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"
CORPUS_PATH = CORPUS_ROOT / "corpus.jsonl"


@pytest.fixture(scope="session")
def committed_records() -> list[BenchmarkRecord]:
    return load_corpus_records(str(CORPUS_PATH))


@pytest.fixture(scope="session")
def committed_preflight(
    committed_records: list[BenchmarkRecord],
) -> PreflightResult:
    """One real preflight over the committed corpus, shared by every module."""
    return run_preflight(committed_records, CORPUS_ROOT, corpus_path=CORPUS_PATH)


@pytest.fixture(scope="session")
def committed_checks(committed_preflight: PreflightResult) -> dict[str, str]:
    return {check.check: check.status for check in committed_preflight.checks}
