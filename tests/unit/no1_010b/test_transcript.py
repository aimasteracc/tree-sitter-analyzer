"""NO1-010B E0 参考 transcript 的纵向行为测试。"""

from __future__ import annotations

import json
from pathlib import Path

from tree_sitter_analyzer.no1_010b.__main__ import main
from tree_sitter_analyzer.no1_010b.transcript import _touched_paths, _tree_digest

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
