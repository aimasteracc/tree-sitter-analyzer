"""Contract tests for the NO1-010B strict benchmark-record model (RFC-0026 §1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.record import (
    BenchmarkRecordError,
    load_corpus_records,
    path_allowed,
    per_class_counts,
    record_from_dict,
)

CORPUS = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b" / "corpus"


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
        "oracle_baseline_reason": "returns None, no 404 branch",
        "verification_command": "uv run pytest tests/ -q",
        "expected_outcome": "PASS",
        "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"},
    }


def test_record_from_dict_accepts_valid_payload() -> None:
    record = record_from_dict(_valid_payload())
    assert record.id == "no1-010b/0001-bugfix-dispatch-null"
    assert record.task_class == "bugfix"
    assert record.repo_commit == "0" * 40
    assert record.allowed_paths == ("src/dispatch.py", "tests/")


def test_record_from_dict_rejects_unknown_fields() -> None:
    payload = _valid_payload()
    payload["sneaky"] = True
    with pytest.raises(BenchmarkRecordError, match="unknown record fields"):
        record_from_dict(payload)


def test_record_from_dict_rejects_invalid_enums() -> None:
    for field, bad in (
        ("task_class", "bugfiix"),
        ("operation", "understnd"),
        ("expected_outcome", "MAYBE"),
    ):
        payload = _valid_payload()
        payload[field] = bad
        with pytest.raises(BenchmarkRecordError, match="invalid"):
            record_from_dict(payload)


def test_record_from_dict_rejects_empty_task_and_short_commit() -> None:
    payload = _valid_payload()
    payload["task"] = "  "
    with pytest.raises(BenchmarkRecordError, match="task must not be empty"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["repo_commit"] = "abc"
    with pytest.raises(BenchmarkRecordError, match="40-char git sha"):
        record_from_dict(payload)


def test_record_from_dict_rejects_non_canonical_paths() -> None:
    for bad in ("/abs/path.py", "./rel.py", "a/../b.py", "dir//x.py"):
        payload = _valid_payload()
        payload["allowed_paths"] = [bad]
        with pytest.raises(BenchmarkRecordError, match="path"):
            record_from_dict(payload)


def test_path_allowed_is_segment_aware() -> None:
    allowed = ("src/dispatch.py", "tests/")
    assert path_allowed("src/dispatch.py", allowed) is True
    assert path_allowed("tests/test_dispatch.py", allowed) is True
    assert path_allowed("tests-escape/file.py", allowed) is False
    assert path_allowed("src/routes.py", allowed) is False
    assert path_allowed("tests", allowed) is False  # the dir itself is not a descendant


def test_record_rejects_malformed_payloads() -> None:
    with pytest.raises(BenchmarkRecordError, match="JSON object"):
        record_from_dict([])  # type: ignore[arg-type]
    payload = _valid_payload()
    del payload["operation"]
    with pytest.raises(BenchmarkRecordError, match="missing record fields"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["id"] = "  "
    with pytest.raises(BenchmarkRecordError, match="id must be a non-empty"):
        record_from_dict(payload)
    for field in ("repo", "oracle", "oracle_baseline_reason", "verification_command"):
        payload = _valid_payload()
        payload[field] = "  "
        with pytest.raises(BenchmarkRecordError, match=f"{field} must be a non-empty"):
            record_from_dict(payload)
    payload = _valid_payload()
    payload["defect"] = "not-an-object"
    with pytest.raises(BenchmarkRecordError, match="defect must be an object"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["patch"] = 42
    with pytest.raises(BenchmarkRecordError, match="patch must be a string"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["selected_tests"] = "tests/x.py"
    with pytest.raises(BenchmarkRecordError, match="list of strings"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["selected_tests"] = ["tests/x.py", 42]
    with pytest.raises(BenchmarkRecordError, match="list of strings"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["allowed_paths"] = ["tests/", "tests/"]
    with pytest.raises(BenchmarkRecordError, match="duplicates"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["allowed_paths"] = []
    with pytest.raises(BenchmarkRecordError, match="non-empty list"):
        record_from_dict(payload)


def test_path_canonicalization_rejects_all_bad_forms() -> None:
    for bad in (
        None,
        "",
        "..",
        "../x.py",
        "a/../b.py",
        "a//b.py",
    ):
        payload = _valid_payload()
        payload["allowed_paths"] = [bad]
        with pytest.raises(BenchmarkRecordError, match="path"):
            record_from_dict(payload)


def test_to_task_request_covers_all_operations() -> None:
    understand = record_from_dict({**_valid_payload(), "operation": "understand"})
    op, req = understand.to_task_request()
    assert op == "understand" and req == {"task": understand.task}
    plan = record_from_dict(_valid_payload())
    op, req = plan.to_task_request()
    assert op == "plan_change" and req == {"task": plan.task}
    assess = record_from_dict({**_valid_payload(), "operation": "assess_change"})
    op, req = assess.to_task_request()
    assert op == "assess_change" and req == {"diff": {"source": "workspace"}}


def test_to_task_request_projection() -> None:
    record = record_from_dict(_valid_payload())
    operation, request = record.to_task_request()
    assert operation == "plan_change"
    assert request == {"task": "dispatch returns None for an unknown route"}
    # The projection never leaks benchmark-only fields into the task request.
    assert "allowed_paths" not in request


def test_seed_corpus_loads_with_exact_class_counts() -> None:
    records = load_corpus_records(str(CORPUS / "no1_010b_v1.jsonl"))
    assert len(records) == 10
    assert per_class_counts(records) == {
        "bugfix": 4,
        "refactor": 2,
        "migration": 2,
        "test_selection": 2,
    }
    assert sum(1 for r in records if r.expected_outcome == "PASS") == 9
    assert sum(1 for r in records if r.expected_outcome == "FAIL") == 1
    ids = [record.id for record in records]
    assert len(set(ids)) == 10  # no duplicates


def test_loader_rejects_invalid_json_line(tmp_path: Path) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="invalid JSON"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records("-")


def test_loader_rejects_empty_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("\n\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="corpus is empty"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_file(tmp_path: Path) -> None:
    corpus = tmp_path / "big.jsonl"
    corpus.write_text("x" * (8 * 1024 * 1024 + 1), encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records(str(corpus))


def test_per_class_counts_is_exact_for_all_classes() -> None:
    records = load_corpus_records(str(CORPUS / "no1_010b_v1.jsonl"))
    counts = per_class_counts(records)
    assert counts == {
        "bugfix": 4,
        "refactor": 2,
        "migration": 2,
        "test_selection": 2,
    }
    # An empty corpus yields zeroed counts, not KeyErrors.
    assert per_class_counts([]) == {
        "bugfix": 0,
        "refactor": 0,
        "migration": 0,
        "test_selection": 0,
    }


def test_seed_corpus_duplicate_id_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    line = json.dumps(_valid_payload())
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n" + line + "\n"))
    with pytest.raises(BenchmarkRecordError, match="duplicate id"):
        load_corpus_records("-")
