"""Shared Git repository fixture helpers for frozen snapshot tests."""

import os
import subprocess
from pathlib import Path

import pytest

POSIX_SNAPSHOT_TEST = pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: RFC-0022 P0.2 workspace snapshots require POSIX openat/O_NOFOLLOW",
)


def make_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "old.py").write_text("value = 1\n")
    (tmp_path / "gone.py").write_text("gone = True\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path
