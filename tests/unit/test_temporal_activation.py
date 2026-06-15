"""RED tests for Feature 2 — per-symbol temporal activation.

Describes the behaviour of the not-yet-implemented module
``tree_sitter_analyzer.git_activation``. Every test in this file MUST fail
today (ImportError, missing table, missing attr) — they only pass once the
implementation lands. See Feature 2 brief for the SPEC.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from unittest import mock

import pytest

from tests.fixtures.git_temporal import make_repo
from tests.fixtures.git_temporal.make_repo import make_shallow_marker

_GIT_TIMEOUT_SECONDS = 15


def _import_git_activation():
    """Deferred import so collection works before the module exists."""
    return importlib.import_module("tree_sitter_analyzer.git_activation")


def _sym(name: str, line: int, end_line: int, sid: int) -> dict:
    """Minimal ast_symbol_rows-shaped dict used as compute_symbol_activation input."""
    return {
        "id": sid,
        "name": name,
        "kind": "function",
        "line": line,
        "end_line": end_line,
    }


def _seven_line_function(label: str) -> str:
    """7-line python function body for fixture files."""
    return (
        f"def {label}(x):\n"
        f"    a = x + 1\n"
        f"    b = a * 2\n"
        f"    c = b - 3\n"
        f"    d = c / 4\n"
        f"    e = d + 5\n"
        f"    return e\n"
    )


def _read_activation_rows(db_path: str) -> list[dict]:
    """Read all ast_symbol_activation rows; [] if the table is missing."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM ast_symbol_activation")
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _git_env() -> dict[str, str]:
    """Return the same isolated git environment used by the fixture builder."""
    env = os.environ.copy()
    env["GIT_TEMPLATE_DIR"] = ""
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _run_git(repo: Path, args: list[str]) -> None:
    """Run a bounded git command in a test repo."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
        timeout=_GIT_TIMEOUT_SECONDS,
    )


def _init_git_repo(repo: Path) -> None:
    """Initialize and configure a bounded disposable git repository."""
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    _run_git(repo, ["config", "user.email", "test@example.com"])
    _run_git(repo, ["config", "user.name", "Test"])
    _run_git(repo, ["config", "commit.gpgsign", "false"])


def _index_with_activation(repo: Path, files: list[str]) -> str:
    """Run ASTCache.index_file on each rel-path and return the db_path.

    Activation columns are populated as a side-effect of indexing when the
    feature is wired in. Until then this is RED because the table is missing.
    """
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(repo))
    try:
        for rel in files:
            cache.index_file(str(repo / rel))
        return cache.db_path
    finally:
        cache.close()


# --- detect_git_state -------------------------------------------------------


class TestDetectGitState:
    def test_tracked_file_returns_tracked(self, tmp_path):
        repo = make_repo(
            tmp_path, [{"message": "init", "files": {"a.py": "def a(): pass\n"}}]
        )
        ga = _import_git_activation()
        assert ga.detect_git_state(str(repo / "a.py")) == "tracked"

    def test_untracked_file_returns_untracked(self, tmp_path):
        repo = make_repo(
            tmp_path, [{"message": "init", "files": {"keep.py": "x = 1\n"}}]
        )
        new_file = repo / "new.py"
        new_file.write_text("def y(): pass\n", encoding="utf-8")
        ga = _import_git_activation()
        assert ga.detect_git_state(str(new_file)) == "untracked"

    def test_no_repo_returns_no_repo(self, tmp_path):
        loose = tmp_path / "loose.py"
        loose.write_text("x = 1\n", encoding="utf-8")
        ga = _import_git_activation()
        assert ga.detect_git_state(str(loose)) == "no_repo"

    def test_shallow_clone_returns_shallow(self, tmp_path):
        repo = make_repo(tmp_path, [{"message": "init", "files": {"a.py": "x = 1\n"}}])
        make_shallow_marker(repo)
        ga = _import_git_activation()
        assert ga.detect_git_state(str(repo / "a.py")) == "shallow"


# --- parse_log_hunks --------------------------------------------------------


class TestParseLogHunks:
    def test_parses_single_commit_single_hunk(self):
        ga = _import_git_activation()
        sample = (
            "__C__ abc123 1700000000\n"
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -10,0 +11,3 @@\n"
            "+def foo():\n+    return 1\n+\n"
        )
        commits = ga.parse_log_hunks(sample)
        assert len(commits) == 1
        assert commits[0].sha == "abc123"
        assert commits[0].ts == 1700000000
        # hunks describe the NEW file's [start, end] inclusive line range.
        assert len(commits[0].hunks) == 1
        start, end = commits[0].hunks[0]
        assert start == 11
        assert end == 13  # 11 + 3 - 1

    def test_parses_multiple_commits(self):
        ga = _import_git_activation()
        sample = (
            "__C__ aaa111 1700000000\n@@ -1,0 +1,2 @@\n+a\n+b\n"
            "__C__ bbb222 1700100000\n@@ -5,0 +5,1 @@\n+c\n"
        )
        commits = ga.parse_log_hunks(sample)
        assert [c.sha for c in commits] == ["aaa111", "bbb222"]
        assert commits[0].ts == 1700000000
        assert commits[1].ts == 1700100000

    def test_zero_length_hunk_is_ignored(self):
        """``@@ -1,1 +1,0 @@`` (pure deletion) yields no addition hunks."""
        ga = _import_git_activation()
        sample = "__C__ zzz999 1700000000\n@@ -1,1 +1,0 @@\n-removed\n"
        commits = ga.parse_log_hunks(sample)
        assert len(commits) == 1
        assert commits[0].hunks == []

    def test_empty_input_returns_empty(self):
        ga = _import_git_activation()
        assert ga.parse_log_hunks("") == []


# --- attribution semantics --------------------------------------------------


class TestSymbolAttribution:
    def test_symbol_attribution_overlaps_hunk_line_range(self, tmp_path, monkeypatch):
        """Commit modifying lines ~10-15 hits the symbol at 5-25, not 30-40."""
        v0 = (
            "# header\n"
            + "\n" * 3
            + _seven_line_function("first")  # lines 5..11
            + "\n" * 14  # padding lines 12..25
            + _seven_line_function("second")  # lines 26..32
            + "\n" * 8
        )
        repo = make_repo(tmp_path, [{"message": "init", "files": {"mod.py": v0}}])

        lines = v0.split("\n")
        for i in range(9, 15):  # 1-based lines 10..15 — inside "first"
            if i < len(lines):
                lines[i] = lines[i] + "  # tweaked"
        v1 = "\n".join(lines)
        (repo / "mod.py").write_text(v1, encoding="utf-8")
        _run_git(repo, ["add", "mod.py"])
        _run_git(repo, ["commit", "-m", "tweak first"])

        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        symbols = [_sym("first", 5, 25, 1), _sym("second", 30, 40, 2)]
        rows = ga.compute_symbol_activation("mod.py", symbols)
        by_id = {r.symbol_id: r for r in rows}
        assert by_id[1].mod_count_all == 1  # "first" was touched
        assert by_id[2].mod_count_all == 0  # "second" untouched

    def test_follow_tracks_renamed_file(self, tmp_path, monkeypatch):
        """``--follow`` semantics: renamed file's history carries forward."""
        body = _seven_line_function("foo")
        repo = make_repo(
            tmp_path,
            [
                {"message": "init", "files": {"src/old.py": body}},
                {
                    "message": "rename and tweak",
                    "rename": ("src/old.py", "src/new.py"),
                    "files": {"src/new.py": body.replace("a = x + 1", "a = x + 100")},
                },
            ],
        )
        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("src/new.py", [_sym("foo", 1, 7, 10)])
        assert len(rows) == 1
        # Original commit (under old.py) + rename-tweak commit (under new.py)
        assert rows[0].mod_count_all == 2


# --- windowing --------------------------------------------------------------


class TestWindowing:
    def test_30d_window_excludes_old_commits(self, tmp_path, monkeypatch):
        body = _seven_line_function("foo")
        repo = make_repo(
            tmp_path,
            [
                {
                    "message": "ancient",
                    "files": {"a.py": body},
                    "date": "100 days ago",
                }
            ],
        )
        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("a.py", [_sym("foo", 1, 7, 21)])
        assert len(rows) == 1
        row = rows[0]
        # 100d ago is outside both 30d and 90d windows.
        assert row.mod_count_30d == 0
        assert row.mod_count_90d == 0
        # SPEC: "For older commits, count all without hunk attribution."
        assert row.mod_count_all == 1


# --- cold start / failure modes --------------------------------------------


class TestColdStart:
    def test_cold_start_no_git_history(self, tmp_path, monkeypatch):
        """Fresh ``git init`` with no commits: counts all zero, no exception."""
        repo = tmp_path / "fresh"
        repo.mkdir()
        _init_git_repo(repo)
        (repo / "a.py").write_text(_seven_line_function("foo"), encoding="utf-8")

        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("a.py", [_sym("foo", 1, 7, 31)])
        assert len(rows) == 1
        row = rows[0]
        assert row.mod_count_30d == 0
        assert row.mod_count_90d == 0
        assert row.mod_count_all == 0
        # Newly-init'd repo without commits is still "tracked-but-cold".
        assert row.git_state in ("tracked", "untracked")

    def test_file_not_in_repo(self, tmp_path, monkeypatch):
        """Outside any git dir: git_state='no_repo', zero counts, row exists."""
        loose_dir = tmp_path / "loose"
        loose_dir.mkdir()
        (loose_dir / "a.py").write_text(_seven_line_function("foo"), encoding="utf-8")
        monkeypatch.chdir(loose_dir)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("a.py", [_sym("foo", 1, 7, 41)])
        assert len(rows) == 1
        row = rows[0]
        assert row.git_state == "no_repo"
        assert row.mod_count_30d == 0
        assert row.mod_count_90d == 0
        assert row.mod_count_all == 0
        assert row.last_modified_commit in (None, "")

    def test_shallow_clone_marker(self, tmp_path, monkeypatch):
        """``.git/shallow`` marker → git_state='shallow'."""
        repo = make_repo(
            tmp_path,
            [{"message": "init", "files": {"a.py": _seven_line_function("foo")}}],
        )
        make_shallow_marker(repo)
        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("a.py", [_sym("foo", 1, 7, 51)])
        assert len(rows) == 1
        assert rows[0].git_state == "shallow"


# --- persistence: ast_symbol_activation table ------------------------------


class TestReindexIdempotence:
    def test_reindex_replaces_activation(self, tmp_path, monkeypatch):
        """Re-indexing leaves a single row per symbol with refreshed counts."""
        body = _seven_line_function("foo")
        repo = make_repo(tmp_path, [{"message": "init", "files": {"a.py": body}}])
        monkeypatch.chdir(repo)

        db_path = _index_with_activation(repo, ["a.py"])
        rows_first = [
            r for r in _read_activation_rows(db_path) if r["file_path"] == "a.py"
        ]
        assert len(rows_first) == 1
        first_count_all = rows_first[0]["mod_count_all"]

        # Add another commit touching the same body.
        new_body = body.replace("a = x + 1", "a = x + 999")
        (repo / "a.py").write_text(new_body, encoding="utf-8")
        _run_git(repo, ["add", "a.py"])
        _run_git(repo, ["commit", "-m", "bump"])

        db_path_2 = _index_with_activation(repo, ["a.py"])
        assert db_path_2 == db_path  # same db
        rows_second = [
            r for r in _read_activation_rows(db_path) if r["file_path"] == "a.py"
        ]
        assert len(rows_second) == len(rows_first)
        assert rows_second[0]["mod_count_all"] == first_count_all + 1


# --- env knob ---------------------------------------------------------------


class TestEnvDisable:
    def test_index_disabled_via_env(self, tmp_path, monkeypatch):
        """``TSA_INDEX_ACTIVATION=0`` skips writes AND skips git subprocess."""
        repo = make_repo(
            tmp_path,
            [{"message": "init", "files": {"a.py": _seven_line_function("foo")}}],
        )
        monkeypatch.chdir(repo)
        monkeypatch.setenv("TSA_INDEX_ACTIVATION", "0")

        ga = _import_git_activation()
        with mock.patch.object(ga, "subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = AssertionError(
                "subprocess.run must NOT be called when TSA_INDEX_ACTIVATION=0"
            )
            db_path = _index_with_activation(repo, ["a.py"])

            conn = sqlite3.connect(db_path)
            try:
                try:
                    cur = conn.execute("SELECT COUNT(*) FROM ast_symbol_activation")
                    count = cur.fetchone()[0]
                except sqlite3.OperationalError:
                    # Table may not exist when feature is disabled —
                    # equally acceptable: nothing was written.
                    count = 0
            finally:
                conn.close()
            assert count == 0
            assert mock_subprocess.run.call_count == 0


# --- perf smoke -------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.slow_ok  # legitimately exceeds the 5s unit budget
def test_perf_indexing_budget_smoke(tmp_path, monkeypatch):
    """50-file index with activation must stay within 40% of the baseline."""
    files = {f"src/m{i}.py": _seven_line_function(f"fn_{i}") for i in range(50)}
    repo = make_repo(tmp_path, [{"message": "seed", "files": files}])
    monkeypatch.chdir(repo)

    rel_paths = list(files.keys())

    monkeypatch.setenv("TSA_INDEX_ACTIVATION", "0")
    t0 = time.monotonic()
    _index_with_activation(repo, rel_paths)
    baseline = time.monotonic() - t0

    monkeypatch.setenv("TSA_INDEX_ACTIVATION", "1")
    t0 = time.monotonic()
    _index_with_activation(repo, rel_paths)
    with_activation = time.monotonic() - t0

    # Use a 50ms floor so sub-second baselines don't blow up the ratio.
    budget = max(baseline * 1.4, baseline + 0.05)
    assert with_activation <= budget, (
        f"activation indexing overhead too high: "
        f"baseline={baseline:.3f}s, with_activation={with_activation:.3f}s, "
        f"budget={budget:.3f}s"
    )


# --- module surface ---------------------------------------------------------


class TestModuleSurface:
    def test_exports_compute_symbol_activation(self):
        ga = _import_git_activation()
        assert callable(ga.compute_symbol_activation)

    def test_exports_detect_git_state(self):
        ga = _import_git_activation()
        assert callable(ga.detect_git_state)

    def test_exports_parse_log_hunks(self):
        ga = _import_git_activation()
        assert callable(ga.parse_log_hunks)

    def test_activation_row_has_required_fields(self, tmp_path, monkeypatch):
        """ActivationRow exposes every column the SQLite table needs."""
        repo = make_repo(
            tmp_path,
            [{"message": "init", "files": {"a.py": _seven_line_function("foo")}}],
        )
        monkeypatch.chdir(repo)
        ga = _import_git_activation()
        rows = ga.compute_symbol_activation("a.py", [_sym("foo", 1, 7, 99)])
        assert len(rows) == 1
        row = rows[0]
        for field in (
            "symbol_id",
            "file_path",
            "last_modified_commit",
            "last_modified_at",
            "mod_count_30d",
            "mod_count_90d",
            "mod_count_all",
            "computed_at",
            "git_state",
        ):
            assert hasattr(row, field), f"ActivationRow missing field: {field}"


# --- sanity: global git config not polluted --------------------------------


def test_fixture_does_not_pollute_global_git_config(tmp_path):
    """make_repo must leave ``$GIT_CONFIG_GLOBAL`` untouched (project rule)."""
    before = os.environ.get("GIT_CONFIG_GLOBAL", "")
    make_repo(tmp_path, [{"message": "x", "files": {"a.py": "x = 1\n"}}])
    after = os.environ.get("GIT_CONFIG_GLOBAL", "")
    assert before == after


# Silence unused-import warnings — Path used implicitly by type annotations.
_ = Path
