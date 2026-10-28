"""The Tier-2 fixture scan resolves basenames with one source walk (#1779)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.security import fixture_detector


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "project"
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_full_scan_walks_the_source_tree_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Resolving every ``*.py`` literal with its own ``rglob`` made the cold
    # real-repo scan overrun the 30 s pytest-timeout on a macOS release runner.
    root = _make_project(
        tmp_path,
        {
            "tests/test_a.py": (
                "SAMPLE_FOO = 'tree_sitter_analyzer/foo.py'\n"
                "x = 'tree_sitter_analyzer/bar.py'\n"
                "PLUGINS = ['go_plugin.py', 'java_plugin.py', 'rust_plugin.py']\n"
            ),
            "tests/test_b.py": "y = 'tree_sitter_analyzer/foo.py'\n",
            "tree_sitter_analyzer/foo.py": "",
            "tree_sitter_analyzer/sub/bar.py": "",
            "tree_sitter_analyzer/languages/java_plugin.py": "",
        },
    )
    src_dir = root / "tree_sitter_analyzer"
    real_walk = os.walk
    walked: list[str] = []

    def counting_walk(top, *args, **kwargs):
        if Path(top) == src_dir:
            walked.append(str(top))
        return real_walk(top, *args, **kwargs)

    def no_rglob(self, pattern, *args, **kwargs):
        raise AssertionError(f"unexpected rglob({pattern!r})")

    monkeypatch.setattr(fixture_detector.os, "walk", counting_walk)
    monkeypatch.setattr(Path, "rglob", no_rglob)
    index = fixture_detector._scan_tests(root / "tests", root)
    assert len(walked) == 1
    assert index["tree_sitter_analyzer/foo.py"].confidence == 0.85
    # A plugin manifest suppresses its basenames.
    assert "tree_sitter_analyzer/languages/java_plugin.py" not in index


def test_source_index_memoises_and_keeps_ambiguity_and_inventory(
    tmp_path: Path,
) -> None:
    root = _make_project(
        tmp_path,
        {
            "tree_sitter_analyzer/foo.py": "",
            "tree_sitter_analyzer/vendor/foo.py": "",
            "tree_sitter_analyzer/one.py": "",
        },
    )
    index = fixture_detector._SourceIndex(root)
    assert index.resolve("one.py") == "tree_sitter_analyzer/one.py"
    assert index.resolve("foo.py") is None  # two matches: ambiguous
    assert index.resolve("missing.py") is None
    assert index.resolve("a/b.py") == "a/b.py"  # already relative
    certified = fixture_detector._SourceIndex(
        root, inventory=frozenset({"tree_sitter_analyzer/foo.py"})
    )
    assert certified.resolve("foo.py") == "tree_sitter_analyzer/foo.py"
    assert fixture_detector._SourceIndex(tmp_path / "nowhere").resolve("x.py") is None
