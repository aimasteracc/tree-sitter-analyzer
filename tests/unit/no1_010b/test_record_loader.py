"""Contracts for the bounded NO1-010B JSONL record loader."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.no1_010b.record import BenchmarkRecordError, record_from_dict
from tree_sitter_analyzer.no1_010b.record_loader import (
    load_corpus_records,
    per_class_counts,
)


def _valid_payload() -> dict:
    return {
        "id": "no1-010b/0001-bugfix-dispatch-null",
        "task_class": "bugfix",
        "repo": "fixtures/dispatch_app",
        "repo_commit": "0" * 40,
        "operation": "plan_change",
        "task": "dispatch returns None for an unknown route",
        "allowed_paths": ["src/dispatch.py", "tests/"],
        "oracle": "oracles/0001.py",
        "oracle_baseline_reason": "dispatch-returns-none",
        "verification_argv": ["uv", "run", "pytest", "tests/", "-q"],
        "expected_terminal": {"verdict": "PASS", "reason_code": None},
        "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"},
    }


def test_loader_reads_binary_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = (json.dumps(_valid_payload()) + "\n").encode()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))

    assert load_corpus_records("-")[0].id == _valid_payload()["id"]


def test_loader_rejects_excessive_json_nesting(tmp_path: Path) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text("[" * 100_000 + "]" * 100_000 + "\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="invalid JSON"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records("-")


def test_loader_rejects_empty_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("\n\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="corpus is empty"):
        load_corpus_records(str(corpus))


def test_loader_enforces_file_limit_in_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "oversized.jsonl"
    corpus.write_bytes("界".encode() * ((8 * 1024 * 1024) // 3 + 1))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records(str(corpus))


def test_loader_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "binary.jsonl"
    corpus.write_bytes(b"\xff\n")
    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        load_corpus_records(str(corpus))


def test_loader_rejects_unencodable_text_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("\ud800"))
    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        load_corpus_records("-")


def test_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    corpus = tmp_path / "dup.jsonl"
    corpus.write_text('{"id": "a", "id": "b"}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="duplicate key"):
        load_corpus_records(str(corpus))


def test_loader_rejects_nan_constant(tmp_path: Path) -> None:
    corpus = tmp_path / "nan.jsonl"
    corpus.write_text('{"id": "a", "task": NaN}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="non-standard JSON constant"):
        load_corpus_records(str(corpus))


def test_loader_preserves_unicode_line_separator_inside_json(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["task"] = "first\u2028second"
    corpus = tmp_path / "unicode-separator.jsonl"
    corpus.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    assert load_corpus_records(str(corpus))[0].task == "first\u2028second"


def test_per_class_counts_is_exact_for_all_classes() -> None:
    records = [
        record_from_dict(
            {
                **_valid_payload(),
                "id": f"task-{index}",
                "task_class": task_class,
                "selected_tests": (
                    ["tests/test_app.py"] if task_class == "test_selection" else []
                ),
            }
        )
        for index, task_class in enumerate(
            ("bugfix", "refactor", "migration", "test_selection"), start=1
        )
    ]

    assert per_class_counts(records) == {
        "bugfix": 1,
        "refactor": 1,
        "migration": 1,
        "test_selection": 1,
    }


def test_per_class_counts_is_zero_for_empty_input() -> None:
    assert per_class_counts([]) == dict.fromkeys(
        ("bugfix", "refactor", "migration", "test_selection"), 0
    )


def test_loader_rejects_duplicate_record_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    line = json.dumps(_valid_payload())
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n" + line + "\n"))
    with pytest.raises(BenchmarkRecordError, match="duplicate id"):
        load_corpus_records("-")
