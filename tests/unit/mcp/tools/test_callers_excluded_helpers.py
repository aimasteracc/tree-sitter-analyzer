"""#1635：``callers_excluded`` 的失败路径只会保留原答案，从不改写成别的原因。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from tree_sitter_analyzer.mcp.tools import callers_excluded, unindexed_sources
from tree_sitter_analyzer.mcp.tools.callers_excluded import (
    _definition_line,
    _definition_pattern,
    _excluded_sources,
    _relative,
    excluded_definition,
)

_PATTERNS = ["tests/golden/corpus_*"]


class _BrokenCache:
    def get_conn(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("database is locked")


class _Cache:
    def get_conn(self) -> object:
        return object()


def _corpus(root: Path, text: str = "def corpus_only():\n    return 1\n") -> str:
    (root / "tests" / "golden").mkdir(parents=True)
    (root / "tests" / "golden" / "corpus_python.py").write_text(text, encoding="utf-8")
    return "tests/golden/corpus_python.py"


def test_name_without_bare_part_is_not_checked(tmp_path) -> None:
    assert excluded_definition(_Cache(), str(tmp_path), "Owner.", None) is None


def test_unreadable_index_keeps_the_original_answer(tmp_path) -> None:
    assert excluded_definition(_BrokenCache(), str(tmp_path), "f", None) is None


def test_no_exclude_patterns_means_no_excluded_definition(
    tmp_path, monkeypatch
) -> None:
    _corpus(tmp_path)
    monkeypatch.setattr(unindexed_sources, "effective_excludes", lambda _c: frozenset())

    assert excluded_definition(_Cache(), str(tmp_path), "corpus_only", None) is None


def test_failed_walk_keeps_the_original_answer(tmp_path, monkeypatch) -> None:
    from tree_sitter_analyzer import index_candidate_walker

    def _fail(*_args, **_kwargs):
        raise OSError("walk failed")

    _corpus(tmp_path)
    monkeypatch.setattr(
        unindexed_sources, "effective_excludes", lambda _c: frozenset(_PATTERNS)
    )
    monkeypatch.setattr(index_candidate_walker, "walk_candidate_entries", _fail)

    assert excluded_definition(_Cache(), str(tmp_path), "corpus_only", None) is None


def test_too_many_excluded_files_gives_up(tmp_path, monkeypatch) -> None:
    _corpus(tmp_path)
    monkeypatch.setattr(callers_excluded, "_FILES_CAP", 0)

    assert _excluded_sources(str(tmp_path), _PATTERNS, None) is None


def test_named_file_is_the_only_file_checked(tmp_path) -> None:
    rel = _corpus(tmp_path)
    absolute = os.path.join(str(tmp_path), rel)

    assert _excluded_sources(str(tmp_path), _PATTERNS, absolute) == [
        (rel, "tests/golden/corpus_*")
    ]
    assert _excluded_sources(str(tmp_path), _PATTERNS, "main.py") == []
    assert _excluded_sources(str(tmp_path), _PATTERNS, "tests/golden/corpus.txt") == []


def test_relative_path_on_another_drive_is_kept(monkeypatch) -> None:
    def _other_drive(_path: str, _start: str) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    absolute = os.path.abspath(os.path.join(os.sep, "elsewhere", "x.py"))
    monkeypatch.setattr(os.path, "relpath", _other_drive)

    assert _relative("/root", absolute) == absolute.replace("\\", "/")


def test_missing_file_has_no_definition_line(tmp_path) -> None:
    assert (
        _definition_line(str(tmp_path), "gone.py", _definition_pattern("f"), None)
        is None
    )


def test_qualified_name_requires_the_owner_in_the_same_file(tmp_path) -> None:
    rel = _corpus(tmp_path, "class Other:\n    def spin(self):\n        return 1\n")

    assert (
        _definition_line(
            str(tmp_path),
            rel,
            _definition_pattern("spin"),
            _definition_pattern("CorpusThing"),
        )
        is None
    )
    assert (
        _definition_line(
            str(tmp_path),
            rel,
            _definition_pattern("spin"),
            _definition_pattern("Other"),
        )
        == 2
    )


def test_definition_keywords_across_languages() -> None:
    for line in (
        "export async function corpus_only() {}",
        "func (r *Repo) corpus_only() error {",
        "pub fn corpus_only() {}",
        "    def corpus_only(self):",
    ):
        assert _definition_pattern("corpus_only").search(line), line
    assert not _definition_pattern("corpus_only").search("return corpus_only()")
    assert not _definition_pattern("corpus").search("def corpus_only():")
