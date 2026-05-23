"""Disposable git-repository builder for Feature 2 (Temporal Activation) tests.

Why this helper exists
----------------------
The temporal-activation module walks ``git log --follow -p -U0`` and attributes
each commit's hunks back to per-symbol line ranges. To exercise that code we
need deterministic, isolated repositories — no leakage from the developer's
real history, no dependence on ``$HOME/.gitconfig``, no flakiness from random
timestamps.

``make_repo(tmp_path, commits)`` builds such a repo from a pure data
description. Every test gets a fresh ``tmp_path``, so we never share state
between tests, and pytest cleans the directory up automatically.

Usage
-----
    from tests.fixtures.git_temporal import make_repo

    repo = make_repo(tmp_path, [
        {
            "message": "initial",
            "files": {"src/foo.py": "def foo():\\n    return 1\\n"},
        },
        {
            "message": "tweak",
            "files": {"src/foo.py": "def foo():\\n    return 2\\n"},
            "date": "5 days ago",   # parsed by git via --date
        },
    ])
    # repo is the absolute Path to the working tree.

Commit dict schema
------------------
    message: str                  required — commit message
    files:   dict[str, str]       required — relative path -> file contents
                                  (use ``None`` to delete an existing file)
    date:    str | None           optional — passed to ``--date=`` (e.g.
                                  "100 days ago", "2024-01-15T12:00:00")
    rename:  tuple[str, str] |    optional — (old_rel, new_rel) — perform a
             None                 ``git mv`` BEFORE writing this commit's
                                  files. Use to exercise ``--follow``.

Determinism
-----------
We force ``user.email`` and ``user.name`` inside each repo so CI environments
without a global git identity still work. We do NOT touch the user's global
config (project rule: never modify global git config).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, TypedDict


class Commit(TypedDict, total=False):
    """Type hint for a commit description. ``files`` and ``message`` required."""

    message: str
    files: dict[str, str | None]
    date: str | None
    rename: tuple[str, str] | None


def _resolve_date(date_spec: str) -> str:
    """Convert a relative date like '100 days ago' to an absolute ISO timestamp.

    ``GIT_AUTHOR_DATE`` / ``GIT_COMMITTER_DATE`` env vars require an absolute
    format. The ``--date`` flag to ``git commit`` can parse relative specs but
    only sets the author date. This helper resolves once so both env vars match.
    """
    import re

    m = re.match(r"(\d+)\s+days?\s+ago", date_spec, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        import datetime

        ts = datetime.datetime.now() - datetime.timedelta(days=days)
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    return date_spec


def _run(repo: Path, args: list[str], env: dict[str, str] | None = None) -> str:
    """Run a git command inside ``repo`` and return stdout.

    Raises CalledProcessError on non-zero exit so test failures surface clearly.
    """
    base_env = os.environ.copy()
    # Disable any global hooks / templates that could interfere on the user's
    # machine.
    base_env["GIT_TEMPLATE_DIR"] = ""
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"
    if env:
        base_env.update(env)
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=base_env,
    )
    return completed.stdout


def _ensure_git_available() -> None:
    """Skip test if git is missing (e.g. minimal CI images)."""
    if shutil.which("git") is None:
        import pytest

        pytest.skip("git executable not on PATH")


def make_repo(tmp_path: Path, commits: list[dict[str, Any]]) -> Path:
    """Initialize a fresh git repo in ``tmp_path/repo`` and seed commits.

    Args:
        tmp_path: pytest tmp_path fixture (or any writable directory).
        commits: ordered list of commit descriptions; see module docstring
            for schema.

    Returns:
        Absolute Path to the new repository's working tree.
    """
    _ensure_git_available()

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Initial branch name is hard-coded to ``main`` so tests don't depend on
    # the host's ``init.defaultBranch`` setting.
    _run(repo, ["init", "--initial-branch=main"])
    _run(repo, ["config", "user.email", "test@example.com"])
    _run(repo, ["config", "user.name", "Test"])
    # Make commit hashes deterministic-ish (no GPG signing prompts).
    _run(repo, ["config", "commit.gpgsign", "false"])

    for spec in commits:
        rename = spec.get("rename")
        if rename is not None:
            old_rel, new_rel = rename
            new_abs = repo / new_rel
            new_abs.parent.mkdir(parents=True, exist_ok=True)
            # Use git mv so the rename is tracked (required for --follow).
            _run(repo, ["mv", old_rel, new_rel])
            # ``git mv`` already stages the rename.

        files = spec.get("files") or {}
        for rel, content in files.items():
            target = repo / rel
            if content is None:
                # Deletion case.
                if target.exists():
                    _run(repo, ["rm", "-f", rel])
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            _run(repo, ["add", "--", rel])

        message = spec["message"]
        env_overrides: dict[str, str] | None = None
        date = spec.get("date")
        commit_args = ["commit", "-m", message, "--allow-empty"]
        if date:
            abs_date = _resolve_date(date)
            env_overrides = {
                "GIT_AUTHOR_DATE": abs_date,
                "GIT_COMMITTER_DATE": abs_date,
            }

        _run(repo, commit_args, env=env_overrides)

    return repo


def make_shallow_marker(repo: Path) -> None:
    """Mark ``repo`` as a shallow clone by creating ``.git/shallow``.

    The contents are a dummy commit-ish line — production code only checks
    for the file's existence, not its contents, per SPEC.
    """
    shallow = repo / ".git" / "shallow"
    shallow.parent.mkdir(parents=True, exist_ok=True)
    shallow.write_text("0000000000000000000000000000000000000000\n", encoding="utf-8")
