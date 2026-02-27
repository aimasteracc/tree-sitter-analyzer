"""Shared fixtures for security tests."""

import os

import pytest


@pytest.fixture
def secure_temp_dir(tmp_path):
    """Create a temporary directory structure for boundary testing."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    restricted_dir = tmp_path / "restricted"
    restricted_dir.mkdir()

    (allowed_dir / "safe_file.py").write_text(
        "# safe content\n", encoding="utf-8"
    )
    (restricted_dir / "secret.py").write_text(
        "SECRET_KEY = 'hidden'\n", encoding="utf-8"
    )

    return {
        "root": tmp_path,
        "allowed": allowed_dir,
        "restricted": restricted_dir,
    }


@pytest.fixture
def symlink_dir(tmp_path):
    """Create a directory with symlinks for boundary escape testing."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    target_dir = tmp_path / "outside"
    target_dir.mkdir()

    (target_dir / "external.py").write_text(
        "# external content\n", encoding="utf-8"
    )

    symlink_path = base_dir / "link_to_outside"
    try:
        os.symlink(target_dir, symlink_path)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    return {
        "base": base_dir,
        "target": target_dir,
        "symlink": symlink_path,
    }
