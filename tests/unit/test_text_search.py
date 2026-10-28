from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.text_search import (
    TextSearchError,
    TextSearchRequest,
    search_text,
    search_text_bounded,
)


def _request(project, **overrides):
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


def test_native_text_search_returns_deterministic_live_rows(tmp_path) -> None:
    (tmp_path / "z.txt").write_text("needle twice needle\n", encoding="utf-8")
    (tmp_path / "a.py").write_bytes(b"zero\rNeedle\rneedle\n")
    (tmp_path / ".secret.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"needle\n\x00tail")
    if os.name != "nt":
        os.symlink(tmp_path / "a.py", tmp_path / "linked.py")

    report = search_text(_request(tmp_path))

    assert [(hit.file, hit.line, hit.column, hit.text) for hit in report.hits] == [
        ("a.py", 2, 1, "Needle"),
        ("a.py", 3, 1, "needle"),
        ("z.txt", 1, 1, "needle twice needle"),
    ]
    assert report.total_count == 3
    assert report.file_count == 2
    assert report.scan_complete is True
    assert report.binary_files_skipped == 1


@pytest.mark.parametrize(
    ("case_mode", "query", "expected"),
    [
        ("smart", "needle", [1, 2]),
        ("smart", "Needle", [1]),
        ("sensitive", "needle", [2]),
        ("insensitive", "Needle", [1, 2]),
    ],
)
def test_text_search_case_modes_are_exact(
    tmp_path, case_mode: str, query: str, expected: list[int]
) -> None:
    (tmp_path / "case.py").write_text("Needle\nneedle\n", encoding="utf-8")

    report = search_text(_request(tmp_path, case_mode=case_mode, query=query))

    assert [hit.line for hit in report.hits] == expected


def test_text_search_word_and_glob_filters_are_exact(tmp_path) -> None:
    (tmp_path / "keep.py").write_text("needles\nneedle\n", encoding="utf-8")
    (tmp_path / "drop.txt").write_text("needle\n", encoding="utf-8")

    report = search_text(
        _request(
            tmp_path,
            word_match=True,
            include_globs=("*.py",),
            exclude_globs=("other.py",),
        )
    )

    assert [(hit.file, hit.line) for hit in report.hits] == [("keep.py", 2)]


def test_text_search_subroot_preserves_project_ignore_rules(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (tmp_path / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
    (source / "kept.py").write_text("needle\n", encoding="utf-8")
    (source / "ignored.py").write_text("needle\n", encoding="utf-8")

    report = search_text(_request(tmp_path, root="src"))

    assert [hit.file for hit in report.hits] == ["src/kept.py"]


def test_text_search_subroot_does_not_charge_entries_outside_scope(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import text_search

    source = tmp_path / "src"
    source.mkdir()
    (source / "kept.py").write_text("needle\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    for number in range(5):
        (outside / f"noise-{number}.txt").write_text("noise\n", encoding="utf-8")
    monkeypatch.setattr(text_search, "_MAX_ENTRIES", 1)

    report = search_text(_request(tmp_path, root="src"))

    assert [(hit.file, hit.line) for hit in report.hits] == [("src/kept.py", 1)]


def test_text_search_budget_failure_never_returns_partial_results(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import text_search

    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    monkeypatch.setattr(text_search, "_MAX_TOTAL_BYTES", 1)

    with pytest.raises(TextSearchError, match="SOURCE_SCAN_BUDGET_EXCEEDED"):
        search_text(_request(tmp_path))


class _RecordingReader:
    """Fake batch reader: records reads and the single end-of-scan verify."""

    instances: list[_RecordingReader] = []

    def __init__(self, root: str, *, deadline: float) -> None:
        self.root = root
        self.reads: list[str] = []
        self.verified = 0
        _RecordingReader.instances.append(self)

    def read(self, relative: str, *, limit: int):
        self.reads.append(relative)
        return SimpleNamespace(
            kind="file", data=(Path(self.root) / relative).read_bytes()
        )

    def verify(self) -> None:
        self.verified += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_shared_admission_streams_with_bounded_read_ahead(
    tmp_path, monkeypatch
) -> None:
    # #1783: reads run ahead of the consumer on a bounded pool, so memory stays
    # bounded by the read-ahead window and output keeps discovery order.
    from tree_sitter_analyzer import text_search

    files = [tmp_path / f"f{number:02d}.py" for number in range(40)]
    for path in files:
        path.write_bytes(path.name.encode())
    monkeypatch.setattr(
        text_search,
        "walk_candidate_entries",
        lambda *_args, **_kwargs: iter(str(path) for path in files),
    )
    _RecordingReader.instances.clear()
    monkeypatch.setattr(text_search, "SourceBatchReader", _RecordingReader)
    iterator = text_search._admitted_sources(
        _request(tmp_path), tmp_path, tmp_path, time.monotonic() + 5
    )

    assert _RecordingReader.instances == []
    first = next(iterator)
    (reader,) = _RecordingReader.instances
    assert first.file == "f00.py"
    assert first.data == b"f00.py"
    assert len(reader.reads) <= text_search._READ_AHEAD
    assert reader.verified == 0
    rest = [source.file for source in iterator]
    assert rest == [path.name for path in files[1:]]
    assert reader.verified == 1


def test_isolated_worker_preserves_unicode_and_complete_counts(tmp_path) -> None:
    (tmp_path / "日本語.py").write_text("针 needle\nneedle\n", encoding="utf-8")

    report = search_text_bounded(_request(tmp_path))

    assert report.total_count == 2
    assert [hit.file for hit in report.hits] == ["日本語.py", "日本語.py"]
