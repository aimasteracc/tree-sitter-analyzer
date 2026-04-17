"""
Incremental analysis cache implementation.

Caches analysis results by file content hash, with git-aware invalidation
and concurrent access support.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import pickle
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pickle protocol compatible with Python 3.8+
PICKLE_PROTOCOL = 4


@dataclass(frozen=True)
class CacheKey:
    """Cache key that uniquely identifies a file's analysis result."""

    file_path: str
    content_hash: str  # SHA256 of file content
    tree_sitter_version: str  # Grammar version (for future use)
    language: str  # python, javascript, etc.

    def __hash__(self) -> int:
        return hash((self.file_path, self.content_hash, self.language))


@dataclass
class CachedAnalysis:
    """Analysis result stored in cache."""

    key: CacheKey
    ast_bytes: bytes  # Serialized tree-sitter Tree
    analysis_result: dict[str, Any]  # Tool-specific analysis
    timestamp: float
    git_sha: str | None  # None for non-git repos


@dataclass
class CacheEntry:
    """Single cache entry with metadata for eviction."""

    key: CacheKey
    value: CachedAnalysis
    last_access: float  # For LRU tracking
    size_bytes: int  # For size-based eviction


@dataclass(frozen=True)
class GitState:
    """Git repository state for cache invalidation."""

    sha: str  # Current commit SHA
    branch: str  # Current branch name


class GitStateTracker:
    """
    Tracks git repository state for cache invalidation.

    Provides git SHA and branch information, with graceful fallback
    for non-git repos or when git is unavailable.
    """

    def __init__(self, repo_path: str | Path) -> None:
        """
        Initialize git state tracker.

        Args:
            repo_path: Path to the repository.
        """
        self.repo_path = Path(repo_path).resolve()
        self._git_exe = "git.exe" if sys.platform == "win32" else "git"
        self._is_git_repo = self._check_git_repo()

    def _check_git_repo(self) -> bool:
        """Check if the path is a valid git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def _run_git(self, args: list[str]) -> str | None:
        """
        Run a git command and return stdout.

        Returns:
            Command output as string, or None if git is unavailable.
        """
        if not self._is_git_repo:
            return None

        try:
            cmd = [self._git_exe, *args]
            env = os.environ.copy()
            env["GIT_PAGER"] = ""  # Disable pager
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, OSError):
            # Git not found
            pass
        return None

    def get_current_state(self) -> GitState | None:
        """
        Get current git repository state.

        Returns:
            GitState with SHA and branch, or None if not a git repo.
        """
        sha = self._run_git(["rev-parse", "HEAD"])
        if sha is None:
            return None

        sha = sha.strip()
        if not sha:
            return None

        # Get branch name (or "HEAD" if detached)
        branch_output = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = "HEAD" if branch_output is None else branch_output.strip() or "HEAD"

        return GitState(sha=sha, branch=branch)

    def get_file_sha(self, file_path: str) -> str | None:
        """
        Get git SHA for a specific file.

        Args:
            file_path: Path to the file (relative to repo root).

        Returns:
            Git blob SHA for the file, or None if not tracked.
        """
        return self._run_git(["hash-object", file_path])


class IncrementalCacheManager:
    """
    Manages incremental analysis cache with file-hash and git SHA invalidation.

    Features:
    - File-hash based caching (content-addressable)
    - Git SHA aware invalidation
    - Concurrent access via file locks
    - Size-based eviction with LRU
    - Fallback for non-git repos
    """

    def __init__(
        self,
        repo_path: str,
        cache_dir: str | None = None,
        max_size_bytes: int = 1024 * 1024 * 1024,  # 1GB default
    ) -> None:
        """
        Initialize cache manager.

        Args:
            repo_path: Path to the repository/codebase
            cache_dir: Cache directory (defaults to .tree-sitter-cache/)
            max_size_bytes: Maximum cache size in bytes
        """
        self.repo_path = Path(repo_path).resolve()
        self.max_size = max_size_bytes
        self._current_size = 0
        self._cache: dict[CacheKey, CacheEntry] = {}

        # Set up cache directory
        if cache_dir is None:
            cache_dir = str(self.repo_path / ".tree-sitter-cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # File lock for concurrent access
        self._lock_path = self.cache_dir / ".lock"
        self._lock_fd: int | None = None

        # Git state tracking
        self._git_tracker = GitStateTracker(self.repo_path)
        self._current_git_state: GitState | None = None

    def _acquire_lock(self, exclusive: bool = False) -> None:
        """Acquire file lock for concurrent access safety."""
        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        self._lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(self._lock_fd, lock_mode)

    def _release_lock(self) -> None:
        """Release file lock."""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def _get_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _make_cache_key(self, file_path: str, language: str) -> CacheKey:
        """Create cache key for a file."""
        content_hash = self._get_file_hash(file_path)
        # Resolve symlinks to handle macOS temp directories
        resolved_path = Path(os.path.realpath(file_path))
        try:
            relative_path = str(resolved_path.relative_to(self.repo_path))
        except ValueError:
            # File is outside repo_path, use absolute path
            relative_path = str(resolved_path)
        return CacheKey(
            file_path=relative_path,
            content_hash=content_hash,
            tree_sitter_version="1.0.0",  # TODO: Get from parser
            language=language,
        )

    def _get_cache_path(self, key: CacheKey) -> Path:
        """Get cache file path for a key."""
        # Use content_hash as filename for content-addressable storage
        # Include language in filename to distinguish different language analyses
        safe_path = key.file_path.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_path}.{key.language}.{key.content_hash[:16]}.cache"

    def _write_atomically(self, path: Path, data: bytes) -> None:
        """Write to temporary file, then rename for atomicity."""
        temp_path = path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "wb") as f:
            f.write(data)
        temp_path.rename(path)  # Atomic on POSIX

    def get(self, file_path: str, language: str = "python") -> CachedAnalysis | None:
        """
        Get cached analysis for a file.

        Args:
            file_path: Path to the file
            language: Programming language (for cache key)

        Returns:
            CachedAnalysis if found and valid, None otherwise
        """
        key = self._make_cache_key(file_path, language)
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        # Check if file content changed (hash mismatch)
        current_hash = self._get_file_hash(file_path)
        if key.content_hash != current_hash:
            return None

        try:
            self._acquire_lock(exclusive=False)
            with open(cache_path, "rb") as f:
                entry = pickle.load(f)

            # Update last access time for LRU
            if isinstance(entry, CacheEntry):
                entry.last_access = time.time()
            else:
                # Legacy format: wrap in CacheEntry
                entry = CacheEntry(
                    key=entry.key if hasattr(entry, "key") else key,
                    value=entry if isinstance(entry, CachedAnalysis) else entry,
                    last_access=time.time(),
                    size_bytes=cache_path.stat().st_size,
                )

            return entry.value if isinstance(entry, CacheEntry) else entry

        except (pickle.UnpicklingError, EOFError, OSError):
            # Corrupted cache — delete and return miss
            cache_path.unlink(missing_ok=True)
            return None
        finally:
            self._release_lock()

    def put(
        self,
        file_path: str,
        analysis_result: dict[str, Any],
        ast_bytes: bytes,
        language: str = "python",
        git_sha: str | None = None,
    ) -> None:
        """
        Store analysis result in cache.

        Args:
            file_path: Path to the file
            analysis_result: Analysis result to cache
            ast_bytes: Serialized AST (tree-sitter Tree)
            language: Programming language
            git_sha: Current git commit SHA (if available)
        """
        key = self._make_cache_key(file_path, language)
        cache_path = self._get_cache_path(key)

        cached = CachedAnalysis(
            key=key,
            ast_bytes=ast_bytes,
            analysis_result=analysis_result,
            timestamp=time.time(),
            git_sha=git_sha,
        )

        # Calculate entry size
        entry_size = sys.getsizeof(pickle.dumps(cached, protocol=PICKLE_PROTOCOL))

        self._acquire_lock(exclusive=True)
        try:
            # Evict if necessary
            if self._current_size + entry_size > self.max_size:
                self._evict_lru_until_fit(entry_size)

            # Write atomically
            entry = CacheEntry(
                key=key,
                value=cached,
                last_access=time.time(),
                size_bytes=entry_size,
            )
            data = pickle.dumps(entry, protocol=PICKLE_PROTOCOL)
            self._write_atomically(cache_path, data)

            self._cache[key] = entry
            self._current_size += entry_size

        finally:
            self._release_lock()

    def is_stale(self, cached: CachedAnalysis) -> bool:
        """
        Check if cached result is stale.

        Args:
            cached: Cached analysis result

        Returns:
            True if stale (file changed or git SHA changed)
        """
        # Check if file still exists and has same content
        file_path = self.repo_path / cached.key.file_path
        if not Path(file_path).exists():
            return True

        current_hash = self._get_file_hash(str(file_path))
        if cached.key.content_hash != current_hash:
            return True

        # Git SHA check is done at repo level (not here)
        # This method checks file-level staleness only
        return False

    def invalidate(self, file_path: str) -> None:
        """
        Invalidate cache entry for a file.

        Args:
            file_path: Path to the file
        """
        # Resolve symlinks to handle macOS temp directories
        resolved_path = Path(os.path.realpath(file_path))
        try:
            relative_path = str(resolved_path.relative_to(self.repo_path))
        except ValueError:
            relative_path = str(resolved_path)

        safe_path = relative_path.replace("/", "_").replace("\\", "_")

        # Remove all cache files matching this path (any language/hash)
        self._acquire_lock(exclusive=True)
        try:
            for cache_file in self.cache_dir.glob(f"{safe_path}.*.cache"):
                cache_file.unlink(missing_ok=True)
        finally:
            self._release_lock()

    def invalidate_all(self) -> None:
        """Invalidate all cache entries."""
        self._acquire_lock(exclusive=True)
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink(missing_ok=True)
            self._cache.clear()
            self._current_size = 0
        finally:
            self._release_lock()

    def _evict_lru_until_fit(self, required_bytes: int) -> None:
        """Evict least-recently-used entries until there's space."""
        while self._current_size + required_bytes > self.max_size and self._cache:
            # Find LRU entry
            lru_key = min(self._cache.items(), key=lambda x: x[1].last_access)[0]
            lru_entry = self._cache.pop(lru_key)

            # Delete cache file
            cache_path = self._get_cache_path(lru_entry.key)
            cache_path.unlink(missing_ok=True)

            self._current_size -= lru_entry.size_bytes

    def get_git_state(self) -> GitState | None:
        """
        Get current git repository state.

        Returns:
            GitState with SHA and branch, or None if not a git repo.
        """
        return self._git_tracker.get_current_state()

    def invalidate_on_git_change(self, old_state: GitState | None) -> bool:
        """
        Invalidate cache if git state changed (SHA or branch).

        Args:
            old_state: Previous git state to compare against.

        Returns:
            True if cache was invalidated (git changed), False otherwise.
        """
        new_state = self.get_git_state()

        # No git repo — nothing to invalidate
        if new_state is None:
            return False

        # No previous state — save current state
        if old_state is None:
            self._current_git_state = new_state
            return False

        # Check if SHA or branch changed
        if new_state.sha != old_state.sha or new_state.branch != old_state.branch:
            # Git state changed — invalidate all cache
            self.invalidate_all()
            self._current_git_state = new_state
            return True

        return False

    def handle_branch_switch(
        self, old_branch: str, new_branch: str
    ) -> int:
        """
        Handle branch switching by reusing unchanged files.

        When switching branches, files with identical content can reuse
        cached entries. Files that changed or don't exist are invalidated.

        Args:
            old_branch: Previous branch name.
            new_branch: New branch name.

        Returns:
            Number of cache entries invalidated.
        """
        invalidated = 0

        self._acquire_lock(exclusive=True)
        try:
            # Check all cached files
            for cache_file in self.cache_dir.glob("*.cache"):
                try:
                    with open(cache_file, "rb") as f:
                        entry = pickle.load(f)

                    if not isinstance(entry, CacheEntry):
                        continue

                    cached = entry.value
                    file_path = self.repo_path / cached.key.file_path

                    # Check if file exists on new branch
                    if not file_path.exists():
                        # File doesn't exist on new branch — invalidate
                        cache_file.unlink(missing_ok=True)
                        invalidated += 1
                        continue

                    # Check if file content changed
                    current_hash = self._get_file_hash(str(file_path))
                    if cached.key.content_hash != current_hash:
                        # File changed — invalidate
                        cache_file.unlink(missing_ok=True)
                        invalidated += 1

                except (pickle.UnpicklingError, EOFError, OSError):
                    # Corrupted cache — delete
                    cache_file.unlink(missing_ok=True)
                    invalidated += 1

        finally:
            self._release_lock()

        return invalidated

    def warm_cache(
        self,
        files: list[str] | None = None,
        top_n: int = 20,
        language: str = "python",
    ) -> int:
        """
        Warm cache by pre-caching complex files.

        Args:
            files: List of files to cache (if None, scans repo for all files)
            top_n: Number of most complex files to cache
            language: Default language for analysis

        Returns:
            Number of files successfully warmed.
        """
        # If no files provided, scan repo for source files
        if files is None:
            files = self._scan_repo_files(language)

        # Sort by complexity (file size as proxy)
        file_sizes: list[tuple[str, int]] = []
        # Use file size as complexity metric for MVP
        file_sizes = []
        for file_path in files:
            try:
                size = os.path.getsize(file_path)
                file_sizes.append((file_path, size))
            except OSError:
                continue

        # Sort by size descending (most complex first)
        file_sizes.sort(key=lambda x: x[1], reverse=True)

        # Warm top-N files
        warmed = 0
        for file_path, _size in file_sizes[:top_n]:
            try:
                # Create dummy analysis result for warming
                # In real usage, MCP tool would do actual analysis
                self.put(
                    file_path,
                    analysis_result={"warmed": True, "file": file_path},
                    ast_bytes=b"",  # Empty AST for warming
                    language=language,
                    git_sha=self._current_git_state.sha if self._current_git_state else None,
                )
                warmed += 1
            except OSError:
                # File might have been deleted
                continue

        return warmed

    def _scan_repo_files(self, language: str) -> list[str]:
        """
        Scan repository for source files of given language.

        Args:
            language: Programming language (python, javascript, etc.)

        Returns:
            List of file paths.
        """
        # Map language to file extensions
        extensions = {
            "python": [".py"],
            "javascript": [".js", ".jsx", ".mjs"],
            "typescript": [".ts", ".tsx"],
            "java": [".java"],
            "go": [".go"],
            "rust": [".rs"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".h"],
            "c_sharp": [".cs"],
        }

        exts = extensions.get(language, [f".{language}"])

        # Find matching files
        files: list[Path] = []
        for ext in exts:
            files.extend(self.repo_path.rglob(f"*{ext}"))

        return [str(f) for f in files if f.is_file()]

    def get_stats(self) -> dict[str, object]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics (entry count, total size, hit rate, etc.).
        """
        # Count cache files and total size
        cache_files = list(self.cache_dir.glob("*.cache"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "entry_count": len(cache_files),
            "total_size_bytes": total_size,
            "max_size_bytes": self.max_size,
            "usage_percent": (total_size / self.max_size * 100) if self.max_size > 0 else 0,
            "git_state": {
                "sha": self._current_git_state.sha if self._current_git_state else None,
                "branch": self._current_git_state.branch if self._current_git_state else None,
            } if self._current_git_state else None,
        }

    def __enter__(self) -> IncrementalCacheManager:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self._release_lock()
