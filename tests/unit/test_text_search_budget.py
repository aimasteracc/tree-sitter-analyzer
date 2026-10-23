"""#1783: live text search budgets, concurrency and actionable failure payloads."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer import text_search
from tree_sitter_analyzer.text_search import (
    DEFAULT_TEXT_SEARCH_TIMEOUT_SECONDS,
    TextSearchError,
    TextSearchRequest,
    search_text,
    search_text_bounded,
)


def _request(project: Path, **overrides) -> TextSearchRequest:
    values = {
        "project_root": str(project),
        "root": ".",
        "query": "needle",
        "case_mode": "smart",
        "word_match": False,
        "include_globs": (),
        "exclude_globs": (),
        "timeout": 5.0,
    }
    values.update(overrides)
    return TextSearchRequest(**values)


def _write_files(project: Path, count: int, body: str = "needle\n") -> None:
    for number in range(count):
        (project / f"f{number:02d}.py").write_bytes(body.encode("utf-8"))


class _GatedReader:
    """Every read blocks until ``parties`` reads are in flight at once."""

    def __init__(self, parties: int):
        self.barrier = threading.Barrier(parties, timeout=5)

    def __call__(self, root: str, *, deadline: float) -> _GatedReader:
        self.root = root
        return self

    def read(self, relative: str, *, limit: int):
        self.barrier.wait()
        return SimpleNamespace(
            kind="file", data=(Path(self.root) / relative).read_bytes()
        )

    def verify(self) -> None:
        return None

    def __enter__(self) -> _GatedReader:
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_default_scan_budget_covers_cold_windows_scans() -> None:
    # #1783: the old 5 s default could not cover ~550 first-time file opens on
    # Windows with on-access scanning (~25-65 ms each).
    assert DEFAULT_TEXT_SEARCH_TIMEOUT_SECONDS >= 30.0
    request = TextSearchRequest(
        project_root=".",
        root=".",
        query="x",
        case_mode="smart",
        word_match=False,
        include_globs=(),
        exclude_globs=(),
    )
    assert request.timeout == DEFAULT_TEXT_SEARCH_TIMEOUT_SECONDS


def test_file_reads_overlap_instead_of_running_serially(tmp_path, monkeypatch):
    # #1783 regression: per-file open latency must overlap.  A serial reader
    # never gets 4 reads in flight, so the barrier would break and fail closed.
    _write_files(tmp_path, 8)
    monkeypatch.setattr(text_search, "SourceBatchReader", _GatedReader(parties=4))

    report = search_text(_request(tmp_path))

    assert report.total_count == 8
    assert report.files_scanned == 8


def test_time_budget_failure_names_budget_limit_and_progress(tmp_path, monkeypatch):
    _write_files(tmp_path, 3)
    clock = iter([0.0, 0.0] + [100.0] * 1000)
    monkeypatch.setattr(
        text_search, "time", SimpleNamespace(monotonic=lambda: next(clock))
    )

    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path, timeout=2.5))

    assert caught.value.code == "SOURCE_SCAN_BUDGET_EXCEEDED"
    details = caught.value.details
    assert details["budget"] == {"name": "time", "limit": 2.5, "unit": "seconds"}
    assert details["progress"]["files_scanned"] == 0
    assert set(details["progress"]) == {
        "phase",
        "candidates_discovered",
        "files_scanned",
        "bytes_scanned",
        "elapsed_seconds",
    }


def test_read_timeout_reports_time_budget_and_file(tmp_path, monkeypatch):
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    _write_files(tmp_path, 1)

    class _SlowReader(_GatedReader):
        def read(self, relative: str, *, limit: int):
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")

    monkeypatch.setattr(text_search, "SourceBatchReader", _SlowReader(parties=1))
    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path, timeout=1.0))

    assert caught.value.code == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert caught.value.details["budget"]["name"] == "time"
    assert caught.value.details["budget"]["file"] == "f00.py"


def test_total_bytes_budget_failure_reports_bytes(tmp_path, monkeypatch):
    _write_files(tmp_path, 2)
    monkeypatch.setattr(text_search, "_MAX_TOTAL_BYTES", 10)

    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path))

    assert caught.value.code == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert caught.value.details["budget"] == {
        "name": "total_bytes",
        "limit": 10,
        "unit": "bytes",
    }
    # Two 7-byte files: the second one crosses the 10-byte ceiling.
    assert caught.value.details["progress"]["bytes_scanned"] == 14
    assert caught.value.details["progress"]["files_scanned"] == 2


def test_single_file_budget_failure_names_the_file(tmp_path, monkeypatch):
    (tmp_path / "big.py").write_text("needle " * 10, encoding="utf-8")
    monkeypatch.setattr(text_search, "_MAX_FILE_BYTES", 8)

    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path))

    assert caught.value.code == "SOURCE_FILE_BUDGET_EXCEEDED"
    assert caught.value.details["budget"]["name"] == "file_bytes"
    assert caught.value.details["budget"]["file"] == "big.py"


def test_match_budget_failure_reports_matches(tmp_path, monkeypatch):
    _write_files(tmp_path, 1, body="needle\n" * 5)
    monkeypatch.setattr(text_search, "_MAX_MATCHES", 2)

    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path))

    assert caught.value.code == "SOURCE_MATCH_BUDGET_EXCEEDED"
    assert caught.value.details["budget"]["name"] == "matches"
    assert caught.value.details["budget"]["limit"] == 2


def test_discovery_budget_failure_names_the_entry_budget(tmp_path, monkeypatch):
    _write_files(tmp_path, 4)
    monkeypatch.setattr(text_search, "_MAX_ENTRIES", 2)

    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path))

    assert caught.value.code == "SOURCE_DISCOVERY_BUDGET_EXCEEDED"
    budget = caught.value.details["budget"]
    assert (budget["name"], budget["limit"], budget["unit"]) == (
        "entries",
        2,
        "entries",
    )
    assert budget["entries_seen"] == 3


class _FakeProcess:
    def __init__(self, *, stdout: str = "", stderr: str = "", hang: bool = False):
        self.stdout, self.stderr, self.hang = stdout, stderr, hang
        self.returncode = 0
        self.killed = False
        self.calls = 0

    def communicate(self, _input=None, timeout=None):
        self.calls += 1
        if self.hang and self.calls == 1:
            raise subprocess.TimeoutExpired("worker", timeout)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True


def test_killed_worker_reports_last_progress(tmp_path, monkeypatch):
    progress = {"phase": "scan", "files_scanned": 7, "bytes_scanned": 70}
    process = _FakeProcess(
        hang=True,
        stderr="warning: noise\n"
        + json.dumps({"progress": {"files_scanned": 1}})
        + "\n"
        + json.dumps({"progress": progress})
        + "\n",
    )
    monkeypatch.setattr(text_search.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(TextSearchError) as caught:
        search_text_bounded(_request(tmp_path, timeout=3.0))

    assert process.killed
    assert caught.value.code == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert caught.value.details["budget"]["name"] == "time"
    assert caught.value.details["budget"]["limit"] == 3.0
    assert caught.value.details["budget"]["enforced_by"] == "worker_kill"
    assert caught.value.details["progress"] == progress


def test_killed_worker_without_progress_reports_startup(tmp_path, monkeypatch):
    process = _FakeProcess(hang=True)
    monkeypatch.setattr(text_search.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(TextSearchError) as caught:
        search_text_bounded(_request(tmp_path))

    assert caught.value.details["progress"] == {"phase": "worker_startup"}


def test_worker_error_details_survive_the_process_boundary(tmp_path, monkeypatch):
    details = {"budget": {"name": "total_bytes", "limit": 1, "unit": "bytes"}}
    process = _FakeProcess(
        stdout=json.dumps({"error": "SOURCE_SCAN_BUDGET_EXCEEDED", "details": details})
    )
    monkeypatch.setattr(text_search.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(TextSearchError) as caught:
        search_text_bounded(_request(tmp_path))

    assert caught.value.code == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert caught.value.details == details


def test_worker_scan_budget_excludes_interpreter_startup(tmp_path, monkeypatch):
    seen: dict[str, float] = {}
    process = _FakeProcess(stdout=json.dumps({"error": "SOURCE_FILE_CHANGED"}))

    def communicate(_input=None, timeout=None):
        seen["timeout"] = timeout
        return process.stdout, ""

    process.communicate = communicate  # type: ignore[method-assign]
    monkeypatch.setattr(text_search.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(TextSearchError):
        search_text_bounded(_request(tmp_path, timeout=4.0))

    assert seen["timeout"] == 4.0 + text_search._WORKER_STARTUP_SECONDS


def test_real_worker_returns_complete_result(tmp_path) -> None:
    _write_files(tmp_path, 3)

    report = search_text_bounded(_request(tmp_path, timeout=30.0))

    assert report.total_count == 3
    assert report.scan_complete is True


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_matches_equal_git_grep_on_admitted_tracked_files(tmp_path) -> None:
    # #1783 acceptance: same rows as `git grep -n -F` over tracked files, minus
    # the documented admission exclusions (hidden paths, dependency/build dirs).
    project = tmp_path / "repo"
    (project / "src" / "deep").mkdir(parents=True)
    (project / "build").mkdir()
    (project / ".github").mkdir()
    (project / "src" / "a.py").write_text("needle = 1\nother\n", encoding="utf-8")
    (project / "src" / "deep" / "b.md").write_text(
        "x needle y needle\nneedle\n", encoding="utf-8"
    )
    (project / "build" / "gen.py").write_text("needle\n", encoding="utf-8")
    (project / ".github" / "ci.yml").write_text("needle\n", encoding="utf-8")
    (project / "blob.bin").write_bytes(b"needle\x00")
    git = ["git", "-c", "safe.directory=*", "-C", str(project)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)

    report = search_text(_request(project, query="needle", case_mode="sensitive"))
    grep = subprocess.run(
        [*git, "grep", "-n", "-I", "-F", "-e", "needle"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    expected = set()
    for line in grep.splitlines():
        file, number, _text = line.split(":", 2)
        parts = PurePosixPath(file).parts
        if any(part.startswith(".") for part in parts) or "build" in parts[:-1]:
            continue
        expected.add((file, int(number)))

    assert {(hit.file, hit.line) for hit in report.hits} == expected
    assert expected == {("src/a.py", 1), ("src/deep/b.md", 1), ("src/deep/b.md", 2)}


def test_progress_writer_throttles_stderr(monkeypatch, capsys) -> None:
    ticks = iter([1.0, 1.1, 1.5])
    monkeypatch.setattr(
        text_search, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )
    write = text_search._progress_writer()

    write({"files_scanned": 1})
    write({"files_scanned": 2})
    write({"files_scanned": 3})

    lines = capsys.readouterr().err.splitlines()
    assert [json.loads(line)["progress"]["files_scanned"] for line in lines] == [1, 3]


def test_partial_scan_never_completes_after_time_check(tmp_path, monkeypatch):
    # Honesty: a budget failure mid-scan raises; it never returns a report.
    _write_files(tmp_path, 20)
    start = time.monotonic()
    calls = {"n": 0}

    def monotonic() -> float:
        calls["n"] += 1
        return start if calls["n"] < 10 else start + 1000

    monkeypatch.setattr(text_search, "time", SimpleNamespace(monotonic=monotonic))
    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path))
    assert caught.value.code in {
        "SOURCE_SCAN_BUDGET_EXCEEDED",
        "SOURCE_DISCOVERY_BUDGET_EXCEEDED",
    }
    assert caught.value.details["budget"]["name"] == "time"


def test_tool_error_payload_is_actionable_and_never_partial(tmp_path, monkeypatch):
    import asyncio

    from tree_sitter_analyzer.mcp.tools import text_search_tool
    from tree_sitter_analyzer.mcp.tools.text_search_tool import TextSearchTool

    details = {
        "budget": {"name": "time", "limit": 30.0, "unit": "seconds"},
        "progress": {
            "phase": "scan",
            "candidates_discovered": 553,
            "files_scanned": 120,
            "bytes_scanned": 4096,
            "elapsed_seconds": 30.0,
        },
    }

    def fail(_request):
        raise TextSearchError("SOURCE_SCAN_BUDGET_EXCEEDED", details)

    monkeypatch.setattr(text_search_tool, "search_text_bounded", fail)
    result = asyncio.run(
        TextSearchTool(str(tmp_path)).execute({"query": "render_lines"})
    )

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["results"] == []
    assert result["source_evidence"]["scan_complete"] is False
    assert result["error_code"] == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert result["budget"] == details["budget"]
    assert result["scan_progress"] == details["progress"]
    summary = result["agent_summary"]["summary_line"]
    assert "time budget 30.0 seconds exceeded" in summary
    assert "120 of 553" in summary
    assert "no partial results" in summary
    assert "total_count" not in result


def test_tool_error_without_details_keeps_legacy_envelope(tmp_path, monkeypatch):
    import asyncio

    from tree_sitter_analyzer.mcp.tools import text_search_tool
    from tree_sitter_analyzer.mcp.tools.text_search_tool import TextSearchTool

    def fail(_request):
        raise TextSearchError("SOURCE_FILE_CHANGED")

    monkeypatch.setattr(text_search_tool, "search_text_bounded", fail)
    result = asyncio.run(TextSearchTool(str(tmp_path)).execute({"query": "x"}))

    assert result["agent_summary"]["summary_line"] == (
        "text search failed: SOURCE_FILE_CHANGED"
    )
    assert "budget" not in result
    assert "scan_progress" not in result


def _run_main(monkeypatch, capsys, payload) -> dict:
    import io

    monkeypatch.setattr(
        text_search.sys,
        "stdin",
        io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)),
    )
    text_search._main()
    return json.loads(capsys.readouterr().out)


def _worker_payload(project: Path) -> dict:
    return {
        "project_root": str(project),
        "root": ".",
        "query": "needle",
        "case_mode": "smart",
        "word_match": False,
        "include_globs": [],
        "exclude_globs": [],
        "timeout": 5.0,
    }


def test_worker_main_reports_complete_result(tmp_path, monkeypatch, capsys):
    _write_files(tmp_path, 2)

    result = _run_main(monkeypatch, capsys, _worker_payload(tmp_path))

    assert [hit["file"] for hit in result["hits"]] == ["f00.py", "f01.py"]
    assert result["scan_complete"] is True


def test_worker_main_serialises_budget_details(tmp_path, monkeypatch, capsys):
    _write_files(tmp_path, 1, body="needle\n" * 3)
    monkeypatch.setattr(text_search, "_MAX_MATCHES", 1)

    result = _run_main(monkeypatch, capsys, _worker_payload(tmp_path))

    assert result["error"] == "SOURCE_MATCH_BUDGET_EXCEEDED"
    assert result["details"]["budget"]["name"] == "matches"


def test_worker_main_rejects_invalid_request(monkeypatch, capsys):
    assert _run_main(monkeypatch, capsys, {"query": "x"}) == {
        "error": "SOURCE_WORKER_INVALID_REQUEST"
    }


def test_worker_main_names_response_budget(tmp_path, monkeypatch, capsys):
    _write_files(tmp_path, 1)
    monkeypatch.setattr(text_search, "_MAX_RESPONSE_BYTES", 10)

    result = _run_main(monkeypatch, capsys, _worker_payload(tmp_path))

    assert result["error"] == "SOURCE_RESPONSE_BUDGET_EXCEEDED"
    assert result["details"]["budget"] == {
        "name": "response_bytes",
        "limit": 10,
        "unit": "bytes",
    }


def test_last_progress_ignores_noise() -> None:
    stderr = "\n".join(
        ["not json", json.dumps([1, 2]), json.dumps({"progress": "bad"})]
    )
    assert text_search._last_progress(stderr) is None
    assert text_search._last_progress(None) is None


def test_reader_construction_timeout_reports_time_budget(tmp_path, monkeypatch):
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    def refuse(_root, *, deadline):
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")

    monkeypatch.setattr(text_search, "SourceBatchReader", refuse)
    with pytest.raises(TextSearchError) as caught:
        search_text(_request(tmp_path, timeout=2.0))
    assert caught.value.details["budget"] == {
        "name": "time",
        "limit": 2.0,
        "unit": "seconds",
    }


def test_end_of_scan_verify_failure_fails_closed(tmp_path, monkeypatch):
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    _write_files(tmp_path, 2)

    class _DriftReader(_GatedReader):
        def verify(self) -> None:
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")

    monkeypatch.setattr(text_search, "SourceBatchReader", _DriftReader(parties=1))
    with pytest.raises(TextSearchError, match="^SOURCE_FILE_CHANGED$"):
        search_text(_request(tmp_path))


def test_symlink_and_special_entries_are_skipped_in_reader_threads(
    tmp_path, monkeypatch
):
    _write_files(tmp_path, 1)
    (tmp_path / "missing-now.py").write_text("needle\n", encoding="utf-8")
    real_lstat = Path.lstat

    def lstat(self):
        if self.name == "missing-now.py":
            raise FileNotFoundError(self)
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(TextSearchError, match="^SOURCE_FILE_UNAVAILABLE$"):
        search_text(_request(tmp_path))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("file_bytes", "Exclude the oversized file"),
        ("matches", "more specific query"),
        ("entries", "narrow"),
    ],
)
def test_tool_budget_explanation_names_the_next_action(name, expected) -> None:
    from tree_sitter_analyzer.mcp.tools.text_search_tool import _budget_explanation

    summary, next_step = _budget_explanation(
        "SOURCE_X", {"name": name, "limit": 1, "unit": "u", "file": "a.py"}, None
    )

    assert summary == (
        f"text search failed: SOURCE_X ({name} budget 1 u exceeded; at a.py); "
        "no partial results are returned"
    )
    assert expected in next_step
