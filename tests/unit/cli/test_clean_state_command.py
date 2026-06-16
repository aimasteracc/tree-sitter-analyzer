"""Tests for ``--clean-state`` / ``--clean-state-dry-run`` dispatcher."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.commands.clean_state_command import (
    EPHEMERAL_STATE_PATHS,
    run_clean_state,
)


def _args(project_root: Path, **overrides: object) -> argparse.Namespace:
    defaults = {
        "project_root": str(project_root),
        "clean_state": True,
        "clean_state_dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _capture_errors() -> list[str]:
    return []


def test_removes_present_file(tmp_path: Path, capsys) -> None:
    """A present TSA-owned file should be unlinked and reported as ``removed``."""
    target = tmp_path / ".tree-sitter-cache"
    target.write_text("placeholder")

    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    assert errors == []
    out = capsys.readouterr().out
    assert "removed: .tree-sitter-cache" in out
    assert not target.exists()


def test_removes_present_directory(tmp_path: Path, capsys) -> None:
    """A present directory should be removed recursively."""
    target = tmp_path / ".ast-cache"
    (target / "nested").mkdir(parents=True)
    (target / "nested" / "data.bin").write_text("x")

    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    assert errors == []
    out = capsys.readouterr().out
    assert "removed: .ast-cache" in out
    assert not target.exists()


def test_absent_paths_are_reported_skipped(tmp_path: Path, capsys) -> None:
    """When nothing exists each path should yield a ``skipped`` line."""
    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    out = capsys.readouterr().out
    for rel in EPHEMERAL_STATE_PATHS:
        assert f"skipped (not present): {rel}" in out


def test_dry_run_does_not_touch_filesystem(tmp_path: Path, capsys) -> None:
    """``--clean-state-dry-run`` reports actions but doesn't delete anything."""
    target = tmp_path / ".ast-cache"
    target.mkdir()
    sentinel = target / "marker.txt"
    sentinel.write_text("keep me")

    errors = _capture_errors()
    exit_code = run_clean_state(
        _args(tmp_path, clean_state=False, clean_state_dry_run=True),
        errors.append,
    )

    assert exit_code == 0
    assert errors == []
    out = capsys.readouterr().out
    assert "would_remove: .ast-cache" in out
    # Sentinel file must still be present.
    assert sentinel.exists()
    assert sentinel.read_text() == "keep me"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows-specific incompatibility — tracked separately",
)
def test_handles_literal_colon_memory_directory(tmp_path: Path, capsys) -> None:
    """The literal ``:memory:`` directory created by legacy code is swept."""
    target = tmp_path / ":memory:"
    target.mkdir()
    (target / "spurious.db").write_text("oops")

    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "removed: :memory:" in out
    assert not target.exists()


def test_returns_failure_when_project_root_invalid(monkeypatch) -> None:
    """A resolution error on the project root surfaces as exit 1."""
    errors: list[str] = []

    def boom(_self: object) -> Path:
        raise OSError("synthetic")

    monkeypatch.setattr(Path, "resolve", boom)
    exit_code = run_clean_state(
        argparse.Namespace(
            project_root="/nonexistent",
            clean_state=True,
            clean_state_dry_run=False,
        ),
        errors.append,
    )

    assert exit_code == 1
    assert errors == ["--clean-state cannot resolve project_root: synthetic"]


# --- #988: scope to TSA-owned artifacts only -------------------------------


def test_allowlist_excludes_foreign_ruflo_artifacts() -> None:
    """The ephemeral allowlist must never contain Ruflo-owned databases (#988)."""
    forbidden = {"ruvector.db", "agentdb.rvf", "agentdb.rvf.lock"}
    assert set(EPHEMERAL_STATE_PATHS) & forbidden == set()


def test_clean_state_preserves_foreign_dbs_deletes_tsa_artifact(
    tmp_path: Path,
) -> None:
    """Critical regression guard (#988).

    With BOTH a TSA artifact and Ruflo's foreign DBs co-located, clean-state
    must delete the TSA artifact and leave every foreign file untouched.
    """
    tsa_artifact = tmp_path / ".ast-cache"
    tsa_artifact.mkdir()
    (tsa_artifact / "index.db").write_text("tsa state")

    foreign = [
        tmp_path / "ruvector.db",
        tmp_path / "agentdb.rvf",
        tmp_path / "agentdb.rvf.wal",
        tmp_path / "agentdb.rvf.lock",
    ]
    for path in foreign:
        path.write_text("ruflo state")

    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    assert errors == []
    # TSA artifact gone.
    assert tsa_artifact.exists() is False
    # Every foreign file STILL present.
    for path in foreign:
        assert path.exists() is True


def test_format_json_emits_structured_envelope(tmp_path: Path, capsys) -> None:
    """``--format json`` must emit a parseable JSON envelope (#988)."""
    target = tmp_path / ".ast-cache"
    target.mkdir()
    (target / "data.bin").write_text("x")

    errors = _capture_errors()
    exit_code = run_clean_state(
        _args(tmp_path, format="json"),
        errors.append,
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["dry_run"] is False
    assert payload["removed"] == [".ast-cache"]
    assert payload["failed"] == []
