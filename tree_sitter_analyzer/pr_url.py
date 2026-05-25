"""GitHub PR URL parser and diff fetcher for change-impact analysis."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPRUrl:
    """Components extracted from a GitHub PR URL."""

    owner: str
    repo: str
    pr_number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.slug}/pull/{self.pr_number}"


_GITHUB_PR_PATTERN = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)

_GITHUB_PR_API_PATTERN = re.compile(
    r"https?://api\.github\.com/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<number>\d+)"
)


def parse_pr_url(url: str) -> ParsedPRUrl | None:
    """Parse a GitHub PR URL into owner, repo, and PR number.

    Supports:
      - https://github.com/owner/repo/pull/123
      - https://github.com/owner/repo/pull/123/files
      - http:// (non-SSL)
      - API URLs: https://api.github.com/repos/owner/repo/pulls/123
    """
    url = url.strip()
    m = _GITHUB_PR_PATTERN.match(url)
    if m:
        return ParsedPRUrl(
            owner=m.group("owner"),
            repo=m.group("repo"),
            pr_number=int(m.group("number")),
        )
    m = _GITHUB_PR_PATTERN.search(url)
    if m:
        return ParsedPRUrl(
            owner=m.group("owner"),
            repo=m.group("repo"),
            pr_number=int(m.group("number")),
        )
    m = _GITHUB_PR_API_PATTERN.match(url)
    if m:
        return ParsedPRUrl(
            owner=m.group("owner"),
            repo=m.group("repo"),
            pr_number=int(m.group("number")),
        )
    return None


def _run_gh(args: list[str], timeout: int = 30) -> tuple[int, str]:
    """Run a gh CLI subprocess and return (returncode, stdout)."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""


def fetch_pr_changed_files(pr: ParsedPRUrl) -> list[str]:
    """Fetch the list of changed files in a PR via gh CLI.

    Returns a list of file paths relative to the repo root.
    """
    rc, out = _run_gh(
        [
            "pr",
            "diff",
            str(pr.pr_number),
            "--repo",
            pr.slug,
            "--name-only",
        ]
    )
    if rc != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def fetch_pr_diff_stat(pr: ParsedPRUrl) -> str:
    """Fetch the diff stat summary for a PR via gh CLI."""
    rc, out = _run_gh(
        [
            "pr",
            "diff",
            str(pr.pr_number),
            "--repo",
            pr.slug,
            "--stat",
        ]
    )
    return out if rc == 0 else ""


def fetch_pr_diff(pr: ParsedPRUrl) -> str:
    """Fetch the full diff for a PR via gh CLI."""
    rc, out = _run_gh(
        [
            "pr",
            "diff",
            str(pr.pr_number),
            "--repo",
            pr.slug,
        ],
        timeout=60,
    )
    return out if rc == 0 else ""


def check_gh_available() -> bool:
    """Check if the gh CLI is installed and authenticated."""
    rc, _ = _run_gh(["auth", "status"])
    return rc == 0
