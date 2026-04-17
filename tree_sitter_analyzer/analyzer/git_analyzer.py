"""Git analyzer for churn and ownership analysis.

This module provides functionality to analyze git repositories for:
- File churn (commit frequency)
- Code ownership (top contributor per file)
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__all__ = ["GitAnalyzer", "FileChurn", "FileOwnership"]


@dataclass(frozen=True)
class FileChurn:
    """Churn metrics for a single file."""

    path: str
    commit_count: int
    first_commit_date: str | None
    last_commit_date: str | None
    authors: list[tuple[str, int]]  # (email, commit_count) sorted by count


@dataclass(frozen=True)
class FileOwnership:
    """Ownership metrics for a single file."""

    path: str
    top_contributor: str  # email
    top_contributor_count: int
    total_commits: int
    ownership_percentage: float


class GitAnalyzer:
    """Analyze git repositories for churn and ownership metrics."""

    def __init__(self, repo_path: str | Path) -> None:
        """Initialize the analyzer with a repository path.

        Args:
            repo_path: Path to the git repository.

        Raises:
            ValueError: If repo_path is not a valid git repository.
        """
        self.repo_path = Path(repo_path).resolve()
        if not self._is_git_repo():
            msg = f"Not a git repository: {self.repo_path}"
            raise ValueError(msg)
        self._git_exe = "git.exe" if sys.platform == "win32" else "git"

    def _is_git_repo(self) -> bool:
        """Check if the path is a valid git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def _run_git(
        self, args: list[str], cwd: Path | None = None, check: bool = True
    ) -> str:
        """Run a git command and return stdout.

        Args:
            args: Git command arguments (without 'git' prefix).
            cwd: Working directory (defaults to repo_path).
            check: Whether to raise an error if command fails.

        Returns:
            Command output as string.

        Raises:
            subprocess.CalledProcessError: If command fails and check=True.
        """
        work_dir = cwd or self.repo_path
        cmd = [self._git_exe, *args]
        env = os.environ.copy()
        # Disable pager for all git commands
        env["GIT_PAGER"] = ""
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=check,
            env=env,
        )
        return result.stdout

    def get_file_churn(
        self, since: str | None = None, extension: str | None = None
    ) -> dict[str, FileChurn]:
        """Get commit count per file.

        Args:
            since: Time spec for git log (e.g., "6 months ago", "2024-01-01").
                   If None, analyzes entire history.
            extension: Filter by file extension (e.g., ".py"). If None, includes all.

        Returns:
            Dictionary mapping file paths to FileChurn objects.
        """
        args = ["log", "--name-only", "--format=format:%H|%ae|%ad", "--date=iso"]
        if since:
            args.extend(["--since", since])
        if extension:
            args.append(f"*{extension}")

        try:
            output = self._run_git(args)
        except subprocess.CalledProcessError:
            # Repository might have no commits
            return {}

        churn: dict[str, list[tuple[str, str]]] = {}  # path -> [(hash, email)]
        dates: dict[str, list[str]] = {}  # path -> [dates]

        for line in output.splitlines():
            if not line:
                continue
            if "|" in line:
                # Commit line: hash|email|date
                commit_hash, email, date = line.split("|", 2)
                current_commit = (commit_hash, email)
                current_date = date
            else:
                # File path line
                path = line.strip()
                if path:
                    churn.setdefault(path, []).append(current_commit)
                    dates.setdefault(path, []).append(current_date)

        result: dict[str, FileChurn] = {}
        for path, commits in churn.items():
            path_dates = dates.get(path, [])
            # Count commits per author
            author_counts: Counter[str] = Counter()
            for _commit_hash, email in commits:
                author_counts[email] += 1

            authors = sorted(author_counts.items(), key=lambda x: (-x[1], x[0]))
            first_date = min(path_dates) if path_dates else None
            last_date = max(path_dates) if path_dates else None

            result[path] = FileChurn(
                path=path,
                commit_count=len(commits),
                first_commit_date=first_date,
                last_commit_date=last_date,
                authors=authors,
            )

        return result

    def get_file_ownership(
        self, since: str | None = None
    ) -> dict[str, FileOwnership]:
        """Get top contributor per file via git blame.

        Args:
            since: Time spec for git log (e.g., "6 months ago", "2024-01-01").
                   If None, analyzes entire history.

        Returns:
            Dictionary mapping file paths to FileOwnership objects.
        """
        # First get all tracked files
        try:
            files_output = self._run_git(["ls-files"])
        except subprocess.CalledProcessError:
            return {}

        files = [f.strip() for f in files_output.splitlines() if f.strip()]

        result: dict[str, FileOwnership] = {}

        for file_path in files:
            full_path = self.repo_path / file_path
            if not full_path.is_file():
                continue

            # Use git log to count commits per author for this file
            args = ["log", "--format=format:%ae", file_path]
            if since:
                args.extend(["--since", since])

            try:
                output = self._run_git(args)
            except subprocess.CalledProcessError:
                continue

            if not output.strip():
                continue

            authors: Counter[str] = Counter(output.splitlines())
            if not authors:
                continue

            top_author, top_count = authors.most_common(1)[0]
            total = sum(authors.values())
            ownership_pct = (top_count / total * 100) if total > 0 else 0.0

            result[file_path] = FileOwnership(
                path=file_path,
                top_contributor=top_author,
                top_contributor_count=top_count,
                total_commits=total,
                ownership_percentage=ownership_pct,
            )

        return result

    def get_repo_age_days(self) -> int:
        """Get the age of the repository in days.

        Returns:
            Number of days since first commit, or 0 if no commits.
        """
        try:
            output = self._run_git(["log", "--reverse", "--format=%ad", "--date=iso"])
            lines = output.strip().splitlines()
            if not lines:
                return 0
            first_commit_date = lines[0]
            try:
                first_date = datetime.fromisoformat(first_commit_date)
            except ValueError:
                # Try parsing without timezone
                first_date = datetime.fromisoformat(first_commit_date.split("+")[0])

            # Get current time as offset-aware if first_date is offset-aware
            now = datetime.now()
            if first_commit_date and "+" in first_commit_date:
                # first_date is timezone-aware, make now aware too
                from datetime import timezone

                now = datetime.now(timezone.utc)

            return (now - first_date).days
        except (subprocess.CalledProcessError, ValueError):
            return 0
