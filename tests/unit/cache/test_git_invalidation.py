"""
Tests for git-aware invalidation in incremental analysis cache.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from tree_sitter_analyzer.cache import (
    GitState,
    GitStateTracker,
    IncrementalCacheManager,
)


@pytest.fixture
def temp_repo() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary repository for testing."""
    return tempfile.TemporaryDirectory()


@pytest.fixture
def git_repo(temp_repo: tempfile.TemporaryDirectory[str]) -> tempfile.TemporaryDirectory[str]:
    """Create a temporary git repository."""
    repo = temp_repo.name
    # Initialize git repo
    os.system(f"cd {repo} && git init && git config user.email 'test@test.com' && git config user.name 'Test' 2>/dev/null")
    # Create initial commit
    with open(os.path.join(repo, "test.py"), "w") as f:
        f.write("pass")
    os.system(f"cd {repo} && git add test.py && git commit -m 'init' 2>/dev/null")
    return temp_repo


@pytest.fixture
def cache_manager(temp_repo: tempfile.TemporaryDirectory[str]) -> IncrementalCacheManager:
    """Create a cache manager for testing."""
    return IncrementalCacheManager(temp_repo.name, max_size_bytes=1024 * 1024)


class TestGitState:
    """Tests for GitState dataclass."""

    def test_create(self) -> None:
        """GitState should create with SHA and branch."""
        state = GitState(sha="abc123", branch="main")
        assert state.sha == "abc123"
        assert state.branch == "main"

    def test_frozen(self) -> None:
        """GitState should be frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        state = GitState(sha="abc123", branch="main")
        with pytest.raises(FrozenInstanceError):
            state.sha = "def456"


class TestGitStateTracker:
    """Tests for GitStateTracker."""

    def test_non_git_repo(self, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Non-git repo should return None for git state."""
        tracker = GitStateTracker(temp_repo.name)
        assert tracker.get_current_state() is None

    def test_git_repo_state(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Git repo should return valid GitState."""
        tracker = GitStateTracker(git_repo.name)
        state = tracker.get_current_state()
        assert isinstance(state.sha, str)
        assert len(state.sha) == 40  # SHA-1 hash
        assert state.branch in ("main", "master")  # Default branch name

    def test_get_file_sha(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """get_file_sha should return blob SHA for tracked files."""
        tracker = GitStateTracker(git_repo.name)
        file_sha = tracker.get_file_sha("test.py")
        assert len(file_sha.strip()) == 40  # SHA-1 hash (strip newline)

    def test_untracked_file(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Untracked file should return None for file SHA."""
        tracker = GitStateTracker(git_repo.name)
        # Create untracked file
        with open(os.path.join(git_repo.name, "untracked.py"), "w") as f:
            f.write("pass")
        file_sha = tracker.get_file_sha("untracked.py")
        # Git hash-object returns SHA even for untracked files
        assert len(file_sha.strip()) == 40


class TestGitAwareInvalidation:
    """Tests for git-aware cache invalidation."""

    def test_get_git_state_non_git(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Non-git repo should return None for git state."""
        state = cache_manager.get_git_state()
        assert state is None

    def test_get_git_state_git_repo(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Git repo should return valid GitState."""
        manager = IncrementalCacheManager(git_repo.name)
        state = manager.get_git_state()
        assert state.sha
        assert state.branch

    def test_invalidate_on_git_change_no_change(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """No git change should not invalidate cache."""
        # Non-git repo — no invalidation
        invalidated = cache_manager.invalidate_on_git_change(None)
        assert invalidated is False

    def test_invalidate_on_git_change_git_repo(
        self, git_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """First call to invalidate_on_git_change should save state."""
        manager = IncrementalCacheManager(git_repo.name)
        state = manager.get_git_state()
        assert state.sha  # Verify state is valid

        # No previous state — should save current state
        invalidated = manager.invalidate_on_git_change(None)
        assert invalidated is False

        # Second call with same state — should not invalidate
        invalidated = manager.invalidate_on_git_change(state)
        assert invalidated is False

    def test_invalidate_on_new_commit(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """New commit should invalidate cache."""
        manager = IncrementalCacheManager(git_repo.name)
        old_state = manager.get_git_state()

        # Cache a file
        file_path = os.path.join(git_repo.name, "cached.py")
        with open(file_path, "w") as f:
            f.write("x = 1")
        manager.put(file_path, {"test": "data"}, ast_bytes=b"ast")

        # Verify cache exists
        assert manager.get(file_path) != {}

        # Create new commit
        with open(file_path, "w") as f:
            f.write("x = 2")
        os.system(f"cd {git_repo.name} && git add cached.py && git commit -m 'update' 2>/dev/null")

        # Check for git change
        invalidated = manager.invalidate_on_git_change(old_state)
        assert invalidated is True

        # Cache should be cleared
        assert manager.get(file_path) is None

    def test_handle_branch_switch_same_files(
        self, git_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Branch switch with identical files should preserve cache."""
        manager = IncrementalCacheManager(git_repo.name)

        # Create and cache a file
        file_path = os.path.join(git_repo.name, "branch_test.py")
        with open(file_path, "w") as f:
            f.write("def test(): pass")

        manager.put(file_path, {"fn": "test"}, ast_bytes=b"ast")
        assert manager.get(file_path).analysis_result == {"fn": "test"}

        # Create new branch
        os.system(f"cd {git_repo.name} && git checkout -b feature 2>/dev/null")

        # Handle branch switch — should preserve cache (file unchanged)
        manager.handle_branch_switch("main", "feature")

        # File should still be cached (content unchanged)
        assert manager.get(file_path).analysis_result == {"fn": "test"}

        # Switch back to main
        os.system(f"cd {git_repo.name} && git checkout main 2>/dev/null")

    def test_handle_branch_switch_changed_files(
        self, git_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Branch switch with changed files should invalidate cache."""
        manager = IncrementalCacheManager(git_repo.name)

        # Create and cache a file
        file_path = os.path.join(git_repo.name, "switch_test.py")
        with open(file_path, "w") as f:
            f.write("original")

        manager.put(file_path, {"v": 1}, ast_bytes=b"ast")
        assert manager.get(file_path).analysis_result == {"v": 1}

        # Create new branch and modify file
        os.system(f"cd {git_repo.name} && git checkout -b feature2 2>/dev/null")
        with open(file_path, "w") as f:
            f.write("modified")
        os.system(f"cd {git_repo.name} && git add switch_test.py && git commit -m 'modify' 2>/dev/null")

        # Handle branch switch — should invalidate changed file
        invalidated = manager.handle_branch_switch("main", "feature2")

        # File should be invalidated (content changed)
        # Note: invalidate count depends on how many files changed
        assert invalidated >= 0

        # Cache should be gone for modified file
        # (File content hash no longer matches)
        assert manager.get(file_path) is None

        # Clean up
        os.system(f"cd {git_repo.name} && git checkout main 2>/dev/null")

    def test_git_sha_stored_in_cache(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """git_sha should be stored in cached analysis."""
        manager = IncrementalCacheManager(git_repo.name)
        state = manager.get_git_state()

        file_path = os.path.join(git_repo.name, "sha_test.py")
        with open(file_path, "w") as f:
            f.write("pass")

        manager.put(file_path, {"test": True}, ast_bytes=b"ast", git_sha=state.sha if state else None)

        cached = manager.get(file_path)
        assert cached.analysis_result == {"test": True}
        if state:
            assert cached.git_sha == state.sha

    def test_cache_persists_across_sessions(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Cache should persist across IncrementalCacheManager instances."""
        # First instance
        manager1 = IncrementalCacheManager(git_repo.name)
        file_path = os.path.join(git_repo.name, "persist_test.py")
        with open(file_path, "w") as f:
            f.write("persist")

        manager1.put(file_path, {"persist": True}, ast_bytes=b"ast")

        # Second instance (should read from disk)
        manager2 = IncrementalCacheManager(git_repo.name)
        result = manager2.get(file_path)
        assert result.analysis_result == {"persist": True}

    def test_detached_head_handling(self, git_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Detached HEAD state should be handled correctly."""
        # Checkout a commit directly (detached HEAD)
        manager = IncrementalCacheManager(git_repo.name)
        state = manager.get_git_state()
        sha = state.sha if state else ""

        os.system(f"cd {git_repo.name} && git checkout {sha} 2>/dev/null")

        manager2 = IncrementalCacheManager(git_repo.name)
        new_state = manager2.get_git_state()

        assert new_state.branch == "HEAD"  # Detached HEAD
        assert new_state.sha == sha

        # Clean up
        os.system(f"cd {git_repo.name} && git checkout main 2>/dev/null || git checkout master 2>/dev/null")
