"""Tests for git_analyzer module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tree_sitter_analyzer.analyzer.git_analyzer import (
    FileChurn,
    FileOwnership,
    GitAnalyzer,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> GitAnalyzer:
    """Create a temporary git repository with some commits."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create some files and commits
    (repo_path / "file1.py").write_text("# First file\ndef foo():\n    pass\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    (repo_path / "file2.py").write_text("# Second file\ndef bar():\n    pass\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add file2"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Modify file1
    (repo_path / "file1.py").write_text(
        "# First file modified\ndef foo():\n    pass\ndef baz():\n    pass\n"
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Modify file1"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return GitAnalyzer(repo_path)


@pytest.fixture
def repo_path(temp_repo: GitAnalyzer) -> Path:
    """Get the repository path from temp_repo fixture."""
    return temp_repo.repo_path


def test_git_analyzer_init_valid_repo(temp_repo: GitAnalyzer) -> None:
    """Test GitAnalyzer initialization with valid repository."""
    assert temp_repo.repo_path.exists()
    assert (temp_repo.repo_path / ".git").exists()


def test_git_analyzer_init_invalid_repo(tmp_path: Path) -> None:
    """Test GitAnalyzer initialization with invalid repository."""
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()

    with pytest.raises(ValueError, match="Not a git repository"):
        GitAnalyzer(non_repo)


def test_get_file_churn_basic(temp_repo: GitAnalyzer) -> None:
    """Test basic file churn analysis."""
    churn = temp_repo.get_file_churn()

    assert len(churn) >= 2
    assert "file1.py" in churn
    assert "file2.py" in churn

    # file1.py was modified twice (initial + modify)
    file1_churn = churn["file1.py"]
    assert file1_churn.commit_count == 2
    assert file1_churn.path == "file1.py"
    assert file1_churn.first_commit_date is not None
    assert file1_churn.last_commit_date is not None

    # file2.py was added once
    file2_churn = churn["file2.py"]
    assert file2_churn.commit_count == 1


def test_get_file_churn_with_extension_filter(temp_repo: GitAnalyzer) -> None:
    """Test file churn with extension filter."""
    churn = temp_repo.get_file_churn(extension=".py")

    assert all(path.endswith(".py") for path in churn.keys())
    assert "file1.py" in churn


def test_get_file_churn_with_since_filter(temp_repo: GitAnalyzer) -> None:
    """Test file churn with time filter."""
    # Get all commits first
    all_churn = temp_repo.get_file_churn()
    assert len(all_churn) >= 2

    # Filter to recent commits only (should return fewer or no results)
    recent_churn = temp_repo.get_file_churn(since="1 minute ago")
    # Since we just created these commits, they should all be recent
    # But this test is timing-dependent, so we just verify it doesn't error
    assert isinstance(recent_churn, dict)


def test_get_file_churn_authors(temp_repo: GitAnalyzer) -> None:
    """Test that file churn includes author information."""
    churn = temp_repo.get_file_churn()

    file1_churn = churn["file1.py"]
    assert len(file1_churn.authors) > 0
    # All commits by same author
    assert file1_churn.authors[0][0] == "test@example.com"
    assert file1_churn.authors[0][1] == 2  # 2 commits


def test_get_file_ownership_basic(temp_repo: GitAnalyzer) -> None:
    """Test basic file ownership analysis."""
    ownership = temp_repo.get_file_ownership()

    assert len(ownership) >= 2
    assert "file1.py" in ownership
    assert "file2.py" in ownership

    file1_owner = ownership["file1.py"]
    assert file1_owner.top_contributor == "test@example.com"
    assert file1_owner.total_commits == 2
    assert file1_owner.ownership_percentage == 100.0

    file2_owner = ownership["file2.py"]
    assert file2_owner.top_contributor == "test@example.com"
    assert file2_owner.total_commits == 1


def test_get_file_ownership_with_since_filter(temp_repo: GitAnalyzer) -> None:
    """Test file ownership with time filter."""
    # All history
    all_ownership = temp_repo.get_file_ownership()
    assert len(all_ownership) >= 2

    # Recent only (timing-dependent, just verify no error)
    recent_ownership = temp_repo.get_file_ownership(since="1 minute ago")
    assert isinstance(recent_ownership, dict)


def test_get_file_ownership_dataclass(temp_repo: GitAnalyzer) -> None:
    """Test FileOwnership dataclass properties."""
    ownership = temp_repo.get_file_ownership()
    file1_owner = ownership["file1.py"]

    assert file1_owner.path == "file1.py"
    assert file1_owner.top_contributor_count == 2
    assert file1_owner.ownership_percentage == 100.0


def test_get_file_churn_dataclass(temp_repo: GitAnalyzer) -> None:
    """Test FileChurn dataclass properties."""
    churn = temp_repo.get_file_churn()
    file1_churn = churn["file1.py"]

    assert file1_churn.path == "file1.py"
    assert file1_churn.commit_count == 2
    assert isinstance(file1_churn.authors, list)
    assert len(file1_churn.authors) > 0


def test_get_repo_age_days(temp_repo: GitAnalyzer) -> None:
    """Test repository age calculation."""
    age = temp_repo.get_repo_age_days()
    # Repo was just created, so age should be small
    assert 0 <= age <= 1  # At most 1 day


def test_get_file_churn_empty_repo(tmp_path: Path) -> None:
    """Test file churn on repo with no commits."""
    repo_path = tmp_path / "empty_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)

    analyzer = GitAnalyzer(repo_path)
    churn = analyzer.get_file_churn()
    assert churn == {}


def test_run_git_command(temp_repo: GitAnalyzer) -> None:
    """Test _run_git method directly."""
    output = temp_repo._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    # Should be "master" or "main" depending on git version
    assert output.strip() in ("master", "main", "")


def test_file_churn_immutability(temp_repo: GitAnalyzer) -> None:
    """Test that FileChurn is frozen/immutable."""
    churn = temp_repo.get_file_churn()
    file1_churn = churn["file1.py"]

    with pytest.raises(Exception):  # FrozenInstanceError
        file1_churn.commit_count = 999


def test_file_ownership_immutability(temp_repo: GitAnalyzer) -> None:
    """Test that FileOwnership is frozen/immutable."""
    ownership = temp_repo.get_file_ownership()
    file1_owner = ownership["file1.py"]

    with pytest.raises(Exception):  # FrozenInstanceError
        file1_owner.top_contributor = "other@example.com"


def test_multiple_authors_per_file(tmp_path: Path) -> None:
    """Test file churn with multiple authors."""
    repo_path = tmp_path / "multi_author_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)

    # First author
    subprocess.run(
        ["git", "config", "user.email", "author1@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Author One"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    (repo_path / "shared.py").write_text("# Created by author1\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Author1 commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Second author
    subprocess.run(
        ["git", "config", "user.email", "author2@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Author Two"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    (repo_path / "shared.py").write_text("# Modified by author2\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Author2 commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    analyzer = GitAnalyzer(repo_path)
    churn = analyzer.get_file_churn()

    shared_churn = churn["shared.py"]
    assert len(shared_churn.authors) == 2
    assert shared_churn.commit_count == 2

    ownership = analyzer.get_file_ownership()
    shared_owner = ownership["shared.py"]
    # Both authors have 1 commit each, so ownership is 50%
    assert shared_owner.ownership_percentage == 50.0


def test_is_git_repo(temp_repo: GitAnalyzer, tmp_path: Path) -> None:
    """Test _is_git_repo method."""
    assert temp_repo._is_git_repo() is True

    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    temp_non_repo = GitAnalyzer.__new__(GitAnalyzer)
    temp_non_repo.repo_path = non_repo
    assert temp_non_repo._is_git_repo() is False
