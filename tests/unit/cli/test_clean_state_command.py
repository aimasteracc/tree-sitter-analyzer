"""Tests for ``--clean-state`` / ``--clean-state-dry-run`` dispatcher."""

from __future__ import annotations

import argparse
from pathlib import Path

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
    """A present file should be unlinked and reported as ``removed``."""
    target = tmp_path / "ruvector.db"
    target.write_text("placeholder")

    errors = _capture_errors()
    exit_code = run_clean_state(_args(tmp_path), errors.append)

    assert exit_code == 0
    assert errors == []
    out = capsys.readouterr().out
    assert "removed: ruvector.db" in out
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
