"""Contracts for the NO1-010B ``python -m`` entry point."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.__main__ import main

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"
CORPUS = CORPUS_ROOT / "corpus.jsonl"


@pytest.fixture(scope="session")
def written_report(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("no1_010b") / "report.json"


@pytest.fixture(scope="session")
def run(written_report: Path) -> tuple[int, dict]:
    """One real entry-point run over the committed corpus, shared per module.

    Preflight executes ten oracles as subprocesses; doing it in module setup
    keeps that real cost out of the unit-suite per-test call budget while still
    exercising the real ``--report`` write path.
    """
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = main(["--corpus", str(CORPUS), "--report", str(written_report)])
    return code, json.loads(stream.getvalue())


def test_entry_point_exits_nonzero_when_preflight_rejects_the_run(
    run: tuple[int, dict],
) -> None:
    assert run[0] == 1


def test_entry_point_emits_the_report_on_stdout(run: tuple[int, dict]) -> None:
    assert run[1]["schema"] == "no1-010b/report/2"


def test_entry_point_records_zero_model_calls(run: tuple[int, dict]) -> None:
    assert run[1]["provenance"]["model_calls"] == 0


def test_provenance_reports_the_working_tree_state(run: tuple[int, dict]) -> None:
    """A digest attested against a dirty tree is not provenance unless it says so."""
    assert run[1]["provenance"]["analyzer"]["tree_state"] in {"clean", "dirty"}


def test_provenance_states_whether_the_corpus_exists_at_the_named_commit(
    run: tuple[int, dict],
) -> None:
    """The first draft named a develop commit where the corpus did not exist."""
    assert run[1]["provenance"]["analyzer"]["corpus_present_at_commit"] is True


def test_provenance_declares_the_digest_normalization(
    run: tuple[int, dict],
) -> None:
    assert (
        run[1]["provenance"]["digest_normalization"]
        == "CRLF collapsed to LF before hashing"
    )


def test_reported_corpus_digest_matches_the_committed_manifest(
    run: tuple[int, dict],
) -> None:
    """The report's digest must be obtainable on this checkout, LF or CRLF."""
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert run[1]["provenance"]["corpus_sha256"] == manifest["corpus_sha256"]


def test_entry_point_writes_the_report_to_the_requested_path(
    run: tuple[int, dict], written_report: Path
) -> None:
    assert json.loads(written_report.read_text(encoding="utf-8"))["phase"] == "B2"


def test_written_report_is_identical_to_the_stdout_report(
    run: tuple[int, dict], written_report: Path
) -> None:
    assert json.loads(written_report.read_text(encoding="utf-8")) == run[1]


def test_update_manifest_rewrites_the_digests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy = tmp_path / "no1_010b"
    shutil.copytree(CORPUS_ROOT, copy)
    fixture = copy / "fixtures" / "dispatch_app" / "src" / "dispatch.py"
    fixture.write_text(
        fixture.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8"
    )
    before = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    assert main(["--corpus", str(copy / "corpus.jsonl"), "--update-manifest"]) == 0
    capsys.readouterr()
    after = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    assert after["fixture_tree_sha256"] != before["fixture_tree_sha256"]


def test_entry_point_reports_a_corpus_error_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"id": "x"}\n', encoding="utf-8")
    assert main(["--corpus", str(broken)]) == 2
    assert "corpus preflight failed" in capsys.readouterr().err
