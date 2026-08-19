"""Contracts for the NO1-010B ``python -m`` entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.__main__ import main

CORPUS = (
    Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b" / "corpus.jsonl"
)


def test_entry_point_exits_nonzero_when_preflight_rejects_the_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--corpus", str(CORPUS)]) == 1
    capsys.readouterr()


def test_entry_point_writes_the_report_to_the_requested_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "report.json"
    main(["--corpus", str(CORPUS), "--report", str(target)])
    capsys.readouterr()
    assert json.loads(target.read_text(encoding="utf-8"))["phase"] == "B2"


def test_entry_point_emits_the_report_on_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--corpus", str(CORPUS)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "no1-010b/report/1"


def test_entry_point_records_zero_model_calls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--corpus", str(CORPUS)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["provenance"]["model_calls"] == 0


def test_entry_point_reports_a_corpus_error_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"id": "x"}\n', encoding="utf-8")
    assert main(["--corpus", str(broken)]) == 2
    assert "corpus preflight failed" in capsys.readouterr().err
