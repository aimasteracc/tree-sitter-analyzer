"""Discovery honors the ignore files that define a project's first-party sources.

GH-1449: discovery pruned only ``EXCLUDE_DIRS`` plus hidden names, so a
gitignored build directory such as tsc's ``lib/`` was indexed as source. The
indexer and the candidate walker now consult one rule matcher, so this file
pins the matcher's own contract and then proves both discovery paths obey it.
"""

from __future__ import annotations

import builtins
import errno
import os

import pytest

from tests.unit._ast_cache_helpers import _OsProxy
from tree_sitter_analyzer.cache.indexer import _walk_source_files
from tree_sitter_analyzer.ignore_rules import is_gitignored, load_ignore_rules
from tree_sitter_analyzer.index_candidate_walker import walk_candidate_entries

_DEFAULTS = {
    "excluded_dir_names": frozenset(),
    "entry_budget": 100,
    "path_byte_budget": 10_000,
    "discovery_seconds": 5.0,
    "budget_error": "DISCOVERY_LIMIT",
}

_posix_only = pytest.mark.skipif(
    os.name != "posix", reason="symlinks with permissions are POSIX-only"
)


def _write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _indexed(root):
    return sorted(
        os.path.relpath(value, str(root)) for value in _walk_source_files(str(root))
    )


def _walked(root):
    return sorted(
        os.path.relpath(value, str(root))
        for value in walk_candidate_entries(str(root), **_DEFAULTS)
    )


def _select_path_fallback(walker, monkeypatch):
    # Patch the walker's own view of ``os``: patching the process-global
    # ``os.name`` makes pathlib build a WindowsPath while pytest reports.
    monkeypatch.setattr(walker, "os", _OsProxy(name="nt"))


# --- Rule matcher contract -------------------------------------------------


def test_later_rule_file_overrides_an_earlier_one(tmp_path):
    # Precedence is per rule file, not per pattern: a negation in .ignore
    # re-includes a path that .gitignore dropped.
    _write(tmp_path, ".gitignore", "*.log\n")
    _write(tmp_path, ".ignore", "!keep.log\n")

    rules = load_ignore_rules(str(tmp_path), "", [])

    assert is_gitignored("drop.log", rules, directory=False) is True
    assert is_gitignored("keep.log", rules, directory=False) is False


def test_rules_do_not_reach_outside_the_directory_that_declared_them(tmp_path):
    # A rule file governs its own directory and everything below it. A path that
    # never passes through that directory must not be matched by its patterns.
    _write(tmp_path, "pkg/.gitignore", "out/\n")

    rules = load_ignore_rules(str(tmp_path), "pkg", [])

    assert is_gitignored("pkg/out", rules, directory=True) is True
    assert is_gitignored("src/main.py", rules, directory=False) is False


def test_the_empty_relative_path_is_the_walk_root(tmp_path):
    # The walk root is never a discovery candidate, even under a catch-all rule.
    _write(tmp_path, ".gitignore", "*\n")

    rules = load_ignore_rules(str(tmp_path), "", [])

    assert is_gitignored("", rules, directory=False) is False
    assert is_gitignored("anything.py", rules, directory=False) is True


@_posix_only
def test_unreadable_rule_file_is_skipped_rather_than_fatal(tmp_path):
    # An ignore file that cannot be read must degrade to "no rules here"; a
    # discovery pass is not allowed to fail because of one unreadable file.
    _write(tmp_path, ".gitignore", "*.log\n")
    (tmp_path / "drop.log").write_text("x\n", encoding="utf-8")
    ignore_file = tmp_path / ".gitignore"
    ignore_file.chmod(0o000)
    try:
        try:
            ignore_file.read_text(encoding="utf-8")
        except OSError:
            pass
        else:
            pytest.skip("the test user can read a 0o000 file")

        rules = load_ignore_rules(str(tmp_path), "", [])
    finally:
        ignore_file.chmod(0o600)

    assert rules == []
    assert is_gitignored("drop.log", rules, directory=False) is False


def test_rule_file_read_failure_skips_only_that_file(tmp_path, monkeypatch):
    # Exhausted descriptors and I/O errors reach the same handler as EACCES.
    _write(tmp_path, ".gitignore", "*.log\n")
    _write(tmp_path, ".ignore", "*.tmp\n")
    real_open = builtins.open

    def flaky_open(file, *args, **kwargs):
        if os.path.basename(os.fspath(file)) == ".gitignore":
            raise OSError(errno.EMFILE, "Too many open files")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    rules = load_ignore_rules(str(tmp_path), "", [])

    assert is_gitignored("drop.log", rules, directory=False) is False
    assert is_gitignored("scratch.tmp", rules, directory=False) is True


@_posix_only
def test_symlinked_rule_file_is_skipped(tmp_path):
    # A symlinked rule file can point outside the project, so it is not followed.
    real = tmp_path / "shared-ignore"
    real.write_text("*.log\n", encoding="utf-8")
    (tmp_path / ".gitignore").symlink_to(real)

    rules = load_ignore_rules(str(tmp_path), "", [])

    assert rules == []


# --- Indexer discovery -----------------------------------------------------


def test_indexer_prunes_a_gitignored_build_directory(tmp_path):
    # The GH-1449 regression: tsc emits lib/, .gitignore names it, and the
    # build output must not be indexed as first-party source.
    _write(tmp_path, ".gitignore", "lib/\ndist/\n")
    _write(tmp_path, "src/index.ts", "export const a = 1\n")
    _write(tmp_path, "lib/index.js", "var a = 1\n")
    _write(tmp_path, "dist/index.js", "var a = 1\n")

    assert _indexed(tmp_path) == [os.path.join("src", "index.ts")]


def test_indexer_keeps_lib_when_the_project_does_not_ignore_it(tmp_path):
    # Ruby and Python keep first-party sources under lib/, so the walk follows
    # the project's rules instead of hardcoding an ecosystem directory name.
    _write(tmp_path, ".gitignore", "build/\n")
    _write(tmp_path, "lib/thing.rb", "def thing; end\n")

    assert os.path.join("lib", "thing.rb") in _indexed(tmp_path)


def test_indexer_skips_a_gitignored_file(tmp_path):
    _write(tmp_path, ".gitignore", "generated.py\n")
    _write(tmp_path, "generated.py", "value = 1\n")
    _write(tmp_path, "handwritten.py", "value = 2\n")

    assert _indexed(tmp_path) == ["handwritten.py"]


def test_indexer_applies_a_nested_gitignore_below_its_directory(tmp_path):
    _write(tmp_path, "pkg/.gitignore", "out/\n")
    _write(tmp_path, "pkg/src.js", "var s = 1\n")
    _write(tmp_path, "pkg/out/generated.js", "var g = 1\n")

    indexed = _indexed(tmp_path)

    assert os.path.join("pkg", "src.js") in indexed
    assert os.path.join("pkg", "out", "generated.js") not in indexed


@_posix_only
def test_indexer_yields_a_source_named_directory_symlink(tmp_path):
    # A directory symlink whose name carries a source extension is a candidate;
    # os.walk does not descend it, so the link itself stands in for the tree.
    target = tmp_path / "source_dir"
    _write(target, "hidden.py", "value = 1\n")
    (tmp_path / "alias.py").symlink_to(target, target_is_directory=True)

    assert _indexed(tmp_path) == [
        "alias.py",
        os.path.join("source_dir", "hidden.py"),
    ]


@_posix_only
def test_indexer_skips_a_gitignored_directory_symlink(tmp_path):
    target = tmp_path / "source_dir"
    _write(target, "hidden.py", "value = 1\n")
    (tmp_path / "alias.py").symlink_to(target, target_is_directory=True)
    _write(tmp_path, ".gitignore", "alias.py\n")

    assert _indexed(tmp_path) == [os.path.join("source_dir", "hidden.py")]


# --- Candidate walker fallback path ----------------------------------------


def test_path_fallback_skips_a_gitignored_file(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    _write(tmp_path, ".gitignore", "generated.py\n")
    _write(tmp_path, "generated.py", "value = 1\n")
    _write(tmp_path, "handwritten.py", "value = 2\n")

    _select_path_fallback(walker, monkeypatch)
    walked = _walked(tmp_path)

    assert "handwritten.py" in walked
    assert "generated.py" not in walked


def test_path_fallback_descends_into_a_kept_directory(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    _write(tmp_path, ".gitignore", "lib/\n")
    _write(tmp_path, "pkg/inner.js", "var i = 1\n")
    _write(tmp_path, "lib/index.js", "var a = 1\n")

    _select_path_fallback(walker, monkeypatch)
    walked = _walked(tmp_path)

    assert os.path.join("pkg", "inner.js") in walked
    assert os.path.join("lib", "index.js") not in walked
