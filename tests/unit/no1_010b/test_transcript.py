"""NO1-010B E0 参考 transcript 的纵向行为测试。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.no1_010b.__main__ import main
from tree_sitter_analyzer.no1_010b.record import ExpectedTerminal
from tree_sitter_analyzer.no1_010b.transcript import (
    ReferenceTranscriptError,
    _apply_reference_edit,
    _reference_spec,
    _require_tool_success,
    _run_git,
    _touched_paths,
    _tree_digest,
    run_reference_transcript,
)

CORPUS = Path("benchmarks/no1_010b/corpus.jsonl")


def test_reference_transcript_reaches_registered_pass(capsys) -> None:
    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--reference-transcript-task",
            "no1-010b/0001-bugfix-dispatch-unknown-route",
        ]
    )
    captured = capsys.readouterr()
    transcript = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert transcript["schema"] == "no1-010b/transcript/1"
    assert transcript["evidence_level"] == "E0"
    assert transcript["qualification"] == "REFERENCE_ONLY"
    assert transcript["task_id"] == ("no1-010b/0001-bugfix-dispatch-unknown-route")
    assert transcript["model_executed"] is False
    assert transcript["public_claim"] is None
    assert [call["sequence"] for call in transcript["calls"]] == list(range(1, 10))
    assert [call["action"] for call in transcript["calls"]] == [
        "full",
        "symbol",
        "outline",
        "safe",
        "edit",
        "impact",
        "verify",
        "registered_verification",
        "oracle",
    ]
    assert transcript["calls"][1]["evidence"]["freshness"] == "fresh"
    assert transcript["calls"][1]["evidence"]["target"] == {
        "file": "src/dispatch.py",
        "name": "dispatch",
        "kind": "function",
        "line": 28,
    }
    assert transcript["calls"][6]["evidence"]["status"] == "passed"
    assert transcript["patch"]["changed_paths"] == ["src/dispatch.py"]
    assert transcript["patch"]["allowed_paths"] == ["src/dispatch.py", "tests/"]
    assert transcript["patch"]["allowlist_violations"] == []
    assert transcript["verification"]["argv"] == [
        "uv",
        "run",
        "pytest",
        "tests/",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    assert transcript["verification"]["passed"] is True
    assert transcript["oracle"]["status"] == "PASS"
    assert transcript["oracle"]["reason"] == "dispatch-returns-none"
    assert transcript["non_allowed_tree"]["unchanged"] is True
    assert (
        transcript["non_allowed_tree"]["before_sha256"]
        == transcript["non_allowed_tree"]["after_sha256"]
    )
    assert transcript["terminal"] == {"verdict": "PASS", "reason_code": None}
    assert transcript["limitations"] == [
        "repository-owned reference edit; no model was executed",
        "candidate execution is not protected by the RFC-0026 B1 sandbox",
        "result cannot support a public VCSR or default-tool claim",
    ]


@pytest.mark.parametrize(
    ("task_id", "task_class", "changed_paths", "target"),
    [
        (
            "no1-010b/0003-refactor-extract-route-registry",
            "refactor",
            ["src/dispatch.py", "src/registry.py"],
            ("dispatch", "src/dispatch.py"),
        ),
        (
            "no1-010b/0004-test-selection-dispatch-version",
            "test_selection",
            ["src/dispatch.py"],
            ("dispatch", "src/dispatch.py"),
        ),
        (
            "no1-010b/0007-migration-drop-legacy-total",
            "migration",
            ["src/orders.py"],
            ("place", "src/orders.py"),
        ),
    ],
)
def test_reference_transcript_covers_representative_success_scenarios(
    capsys, task_id, task_class, changed_paths, target
) -> None:
    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--reference-transcript-task",
            task_id,
        ]
    )
    captured = capsys.readouterr()
    transcript = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert transcript["task_id"] == task_id
    assert transcript["task_class"] == task_class
    assert transcript["patch"]["changed_paths"] == changed_paths
    assert transcript["calls"][1]["evidence"]["target"]["name"] == target[0]
    assert transcript["calls"][1]["evidence"]["target"]["file"] == target[1]
    assert transcript["verification"]["passed"] is True
    assert transcript["oracle"]["status"] == "PASS"
    assert transcript["terminal"] == {"verdict": "PASS", "reason_code": None}
    assert transcript["non_allowed_tree"]["unchanged"] is True

    if task_class == "test_selection":
        assert transcript["test_selection"] == {
            "expected": ["tests/test_dispatch.py"],
            "reported": ["tests/test_dispatch.py"],
            "matched": True,
        }
        impact = next(
            call for call in transcript["calls"] if call["action"] == "impact"
        )
        assert impact["evidence"]["verification_command"] == (
            "uv run pytest tests/test_dispatch.py -q"
        )
    else:
        assert transcript["test_selection"] is None


def test_reference_transcript_preserves_registered_verification_failure(capsys) -> None:
    task_id = "no1-010b/0006-bugfix-cancel-unknown-order"
    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--reference-transcript-task",
            task_id,
        ]
    )
    captured = capsys.readouterr()
    transcript = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert transcript["task_id"] == task_id
    assert transcript["task_class"] == "bugfix"
    assert transcript["patch"]["changed_paths"] == ["src/orders.py"]
    verify = next(call for call in transcript["calls"] if call["action"] == "verify")
    assert verify["success"] is False
    assert verify["evidence"]["status"] == "failed"
    assert transcript["verification"]["passed"] is False
    assert transcript["oracle"]["status"] == "PASS"
    assert transcript["terminal"] == {
        "verdict": "FAIL",
        "reason_code": "VERIFICATION_FAILED",
    }
    assert transcript["non_allowed_tree"]["unchanged"] is True


def test_non_allowed_digest_tracks_only_protected_files(tmp_path: Path) -> None:
    source = tmp_path / "src"
    tests = tmp_path / "tests"
    cache = tmp_path / ".ast-cache"
    source.mkdir()
    tests.mkdir()
    cache.mkdir()
    (source / "dispatch.py").write_text("before\n", encoding="utf-8")
    (source / "registry.py").write_text("stable\n", encoding="utf-8")
    (tests / "test_dispatch.py").write_text("before\n", encoding="utf-8")
    (cache / "index.db").write_bytes(b"before")
    initial = _tree_digest(tmp_path, ("src/dispatch.py", "tests/"))

    (source / "dispatch.py").write_text("after\n", encoding="utf-8")
    (tests / "test_dispatch.py").write_text("after\n", encoding="utf-8")
    (cache / "index.db").write_bytes(b"after")
    allowed_only = _tree_digest(tmp_path, ("src/dispatch.py", "tests/"))
    (source / "registry.py").write_text("changed\n", encoding="utf-8")
    protected_changed = _tree_digest(tmp_path, ("src/dispatch.py", "tests/"))

    assert allowed_only == initial
    assert protected_changed != initial


def test_touched_paths_includes_added_allowed_file() -> None:
    patch = (
        "diff --git a/src/dispatch.py b/src/dispatch.py\n"
        "--- a/src/dispatch.py\n"
        "+++ b/src/dispatch.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/tests/test_unknown.py b/tests/test_unknown.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/tests/test_unknown.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_unknown(): pass\n"
    )

    assert _touched_paths(patch) == ["src/dispatch.py", "tests/test_unknown.py"]


def test_reference_transcript_cli_rejects_unknown_task(capsys) -> None:
    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--reference-transcript-task",
            "no1-010b/not-registered",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "reference task not found: no1-010b/not-registered\n"


def test_reference_transcript_cli_reports_runtime_failure(monkeypatch, capsys) -> None:
    async def fail(*args, **kwargs):
        raise ReferenceTranscriptError("forced failure")

    monkeypatch.setattr(
        "tree_sitter_analyzer.no1_010b.__main__.run_reference_transcript", fail
    )

    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--reference-transcript-task",
            "no1-010b/0001-bugfix-dispatch-unknown-route",
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().err == "reference transcript failed: forced failure\n"


def test_reference_helpers_reject_failed_git_edit_and_tool_result(tmp_path) -> None:
    with pytest.raises(ReferenceTranscriptError, match="git rev-parse HEAD failed"):
        _run_git(tmp_path, "rev-parse", "HEAD")

    target = tmp_path / "src" / "dispatch.py"
    target.parent.mkdir()
    target.write_text("def dispatch():\n    pass\n", encoding="utf-8")
    with pytest.raises(ReferenceTranscriptError, match="anchor is not unique"):
        _apply_reference_edit(tmp_path)

    for result in (None, {}, {"success": False}):
        with pytest.raises(ReferenceTranscriptError, match="index.full failed"):
            _require_tool_success("index.full", result)


@pytest.mark.parametrize(
    ("record_change", "message"),
    [
        ({"id": "no1-010b/other"}, "unsupported reference task"),
        (
            {"expected_terminal": ExpectedTerminal("FAIL", "ORACLE_FAILED")},
            "must register terminal PASS",
        ),
        ({"repo": "fixtures/missing"}, "repo does not match its spec"),
    ],
)
def test_reference_transcript_rejects_unregistered_inputs(
    committed_records, record_change, message
) -> None:
    record = replace(committed_records[0], **record_change)

    with pytest.raises(ReferenceTranscriptError, match=message):
        asyncio.run(run_reference_transcript(record, CORPUS.parent))


def test_reference_transcript_rejects_missing_registered_fixture(
    committed_records, tmp_path
) -> None:
    with pytest.raises(
        ReferenceTranscriptError,
        match="fixture or oracle is missing",
    ):
        asyncio.run(run_reference_transcript(committed_records[0], tmp_path))


@pytest.mark.parametrize(
    ("task_id", "record_change", "field"),
    [
        (
            "no1-010b/0001-bugfix-dispatch-unknown-route",
            {"repo": "fixtures/orders_service"},
            "repo",
        ),
        (
            "no1-010b/0001-bugfix-dispatch-unknown-route",
            {"allowed_paths": ("src/",)},
            "allowed_paths",
        ),
        (
            "no1-010b/0001-bugfix-dispatch-unknown-route",
            {"oracle": "oracles/0002.py"},
            "oracle",
        ),
        (
            "no1-010b/0001-bugfix-dispatch-unknown-route",
            {"oracle_baseline_reason": "trailing-slash-not-normalized"},
            "oracle_baseline_reason",
        ),
        (
            "no1-010b/0001-bugfix-dispatch-unknown-route",
            {"verification_argv": ("python", "-c", "raise SystemExit(0)")},
            "verification_argv",
        ),
        (
            "no1-010b/0004-test-selection-dispatch-version",
            {"selected_tests": ("tests/test_registry.py",)},
            "selected_tests",
        ),
    ],
)
def test_reference_spec_rejects_registered_record_field_drift(
    committed_records, task_id, record_change, field
) -> None:
    record = next(item for item in committed_records if item.id == task_id)

    with pytest.raises(
        ReferenceTranscriptError,
        match=f"reference task {field} does not match its spec",
    ):
        _reference_spec(replace(record, **record_change))


class _TranscriptFacade:
    def __init__(self) -> None:
        self.responses = {
            "full": {"success": True},
            "symbol": {
                "success": True,
                "results": [
                    {
                        "name": "dispatch",
                        "file": "src/dispatch.py",
                        "kind": "function",
                        "line": 28,
                    }
                ],
                "source_evidence": {"freshness": "fresh"},
            },
            "outline": {"success": True},
            "safe": {"success": True},
            "impact": {
                "success": True,
                "verification_request": "bound-request",
            },
            "verify": {"success": True, "status": "passed"},
        }

    async def execute(self, arguments):
        return self.responses[arguments["action"]]


@pytest.fixture
def transcript_runtime(monkeypatch):
    """用真实 Git 补丁配合可控 facade，逐一验证失败关闭边界。"""
    from tree_sitter_analyzer.no1_010b import transcript

    facade = _TranscriptFacade()
    for name in (
        "build_index_facade",
        "build_search_facade",
        "build_structure_facade",
        "build_edit_facade",
    ):
        monkeypatch.setattr(transcript, name, lambda *args, _facade=facade: _facade)
    monkeypatch.setattr(
        transcript,
        "_run_registered_verification",
        lambda *args: {"passed": True, "argv": [], "exit_code": 0},
    )
    monkeypatch.setattr(
        transcript,
        "_run_reference_oracle",
        lambda *args: {"status": "PASS", "reason": "dispatch-returns-none"},
    )
    return transcript, facade


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("search", "one fresh target"),
        ("preflight", "reference patch rejected"),
        ("allowlist", "reference patch violations"),
        ("paths", "unexpected changed paths"),
        ("request", "did not issue a verification request"),
        ("verify", "edit.verify did not pass"),
        ("registered", "registered verification failed"),
        ("oracle", "reference oracle did not declare PASS"),
        ("digest", "non-allowed tree digest changed"),
    ],
)
def test_reference_transcript_fails_closed_at_each_boundary(
    committed_records, tmp_path, monkeypatch, transcript_runtime, failure, message
) -> None:
    transcript, facade = transcript_runtime
    if failure == "search":
        facade.responses["symbol"]["source_evidence"] = {"freshness": "stale"}
    elif failure == "preflight":
        monkeypatch.setattr(
            transcript,
            "preflight_agent_patch",
            lambda patch: SimpleNamespace(as_reason=lambda: "PATCH_REJECTED"),
        )
    elif failure == "allowlist":
        monkeypatch.setattr(
            transcript, "allowlist_violations", lambda *args: ["forbidden.py"]
        )
    elif failure == "paths":
        monkeypatch.setattr(transcript, "_touched_paths", lambda patch: ["tests/x.py"])
    elif failure == "request":
        facade.responses["impact"].pop("verification_request")
    elif failure == "verify":
        facade.responses["verify"]["status"] = "failed"
    elif failure == "registered":
        monkeypatch.setattr(
            transcript,
            "_run_registered_verification",
            lambda *args: {"passed": False},
        )
    elif failure == "oracle":
        monkeypatch.setattr(
            transcript,
            "_run_reference_oracle",
            lambda *args: {"status": "FAIL"},
        )
    else:
        digests = iter(["before", "after"])
        monkeypatch.setattr(transcript, "_tree_digest", lambda *args: next(digests))

    with pytest.raises(ReferenceTranscriptError, match=message):
        asyncio.run(
            run_reference_transcript(
                committed_records[0], CORPUS.parent, workspace_parent=tmp_path
            )
        )
