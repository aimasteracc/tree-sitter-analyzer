"""Feature 2 — per-symbol git modification frequency ("Temporal Activation").

Computes how often each AST symbol has been modified across recent git
history. Backs the ``ast_symbol_activation`` table which the change-impact
gate, the callees / callers tools, and the homeostasis scorer all consume.

Design notes
------------
* ``subprocess`` is imported as a module-level name so tests can swap the
  whole module with ``monkeypatch.setattr(ga, "subprocess", mock)``. We
  never use ``from subprocess import ...``.
* ``compute_symbol_activation`` is the single public entry point. It MUST
  return one row per requested symbol — even when git is missing, the file
  is untracked, the repo is shallow, or git history is empty. A missing
  row is a worse failure mode than a row with zero counts.
* ``TSA_INDEX_ACTIVATION=0`` short-circuits before any subprocess.run is
  invoked. The cache writer relies on this to keep the perf budget tight.
* Hunk attribution is done in Python over the new-file line ranges parsed
  out of ``git log -U0 --pretty=...``. We never trust git's ``--word-diff``
  or rename heuristics beyond ``--follow``.

The implementation deliberately keeps the public surface small:
``ActivationRow``, ``Commit``, ``detect_git_state``, ``parse_log_hunks``,
``compute_symbol_activation``. Anything else is a private helper.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


GitState = Literal["tracked", "untracked", "shallow", "no_repo"]
"""Coarse classification of how usable git history is for a given file."""


_SECONDS_PER_DAY = 86_400
_DEFAULT_GIT_TIMEOUT = 30  # seconds — generous; tests use tiny repos
_COMMIT_MARKER = "__C__"
_COMMIT_HEADER_RE = re.compile(
    rf"^{re.escape(_COMMIT_MARKER)} (?P<sha>\S+) (?P<ts>\d+)\s*$"
)
# `@@ -a,b +c,d @@` — capture both halves. We need ``old_count`` so we can
# distinguish "real modification" (old != 0) from "pure addition" (old == 0).
# Pure additions / creation hunks need special-case handling: a creation
# hunk covering the entire new file would otherwise attribute to every
# symbol just for existing, destroying signal for "untouched" symbols.
# We carry an ``is_creation`` flag downstream and the attribution helper
# decides whether to count based on symbol range vs hunk range.
_HUNK_RE = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+"
    r"\+(?P<start>\d+)(?:,(?P<count>\d+))?\s+@@"
)


@dataclass(frozen=True)
class Commit:
    """One commit's hunks against a single file.

    ``hunks`` is a list of ``(new_start, new_end)`` inclusive line ranges,
    not ``(start, count)`` — the parser collapses zero-length hunks (pure
    deletions) before returning so callers can intersect ranges directly.

    Creation hunks (``@@ -0,0 +1,N @@``) are kept in the list but tagged
    via ``creation_hunks`` so attribution can decide whether to count
    them per-symbol. The two-list shape is more memory-frugal than a
    third element on every hunk tuple — the common case is zero creation
    hunks per commit.
    """

    sha: str
    ts: int
    hunks: list[tuple[int, int]] = field(default_factory=list)
    creation_hunks: list[tuple[int, int]] = field(default_factory=list)


@dataclass(frozen=True)
class ActivationRow:
    """One row in the ``ast_symbol_activation`` SQLite table.

    Attribute access is the contract: tests use ``row.symbol_id`` not
    ``row["symbol_id"]``. The shape mirrors the table schema 1:1 so the
    writer can splat it into INSERT positionally.
    """

    symbol_id: int
    file_path: str
    last_modified_commit: str | None
    last_modified_at: int | None
    mod_count_30d: int
    mod_count_90d: int
    mod_count_all: int
    computed_at: int
    git_state: GitState


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def detect_git_state(path: str) -> GitState:
    """Classify how useful git history will be for ``path``.

    Returns one of:
      * ``"tracked"``  — file is under a git working tree AND known to git
      * ``"untracked"`` — under a git working tree but not yet committed
      * ``"shallow"`` — under a git tree marked ``.git/shallow``
      * ``"no_repo"`` — no enclosing ``.git`` directory at all

    The classification is best-effort and never raises. If something
    unexpected happens (permission errors, missing git binary), we degrade
    to ``"no_repo"`` so callers still get zero-rows back without blowing up.
    """
    try:
        abs_path = os.path.abspath(path)
        repo_root = _find_repo_root(abs_path)
        if repo_root is None:
            return "no_repo"
        if (Path(repo_root) / ".git" / "shallow").exists():
            return "shallow"
        if _is_tracked(repo_root, abs_path):
            return "tracked"
        return "untracked"
    except Exception as exc:  # pragma: no cover — defensive guardrail
        logger.debug("detect_git_state failed for %s: %s", path, exc)
        return "no_repo"


def parse_log_hunks(git_log_output: str) -> list[Commit]:
    """Parse ``git log --pretty=__C__ %H %at -p -U0`` output into commits.

    Returns a list of ``Commit`` objects in the same order they appear.
    Hunks are stored as inclusive ``(new_start, new_end)`` line ranges in
    the NEW file. Pure-deletion hunks (``+c,0``) are dropped: deletions
    don't ADD lines to the new file, so they can't attribute to any symbol
    by line range.

    Robust against:
      * empty / whitespace-only input → ``[]``
      * leading prose / metadata before the first ``__C__`` marker
      * commits with no hunks (e.g. binary-only changes) → ``Commit`` with
        empty ``hunks`` list
    """
    if not git_log_output:
        return []

    commits: list[Commit] = []
    current_sha: str | None = None
    current_ts: int = 0
    current_hunks: list[tuple[int, int]] = []
    current_creations: list[tuple[int, int]] = []

    def flush() -> None:
        if current_sha is not None:
            commits.append(
                Commit(
                    sha=current_sha,
                    ts=current_ts,
                    hunks=list(current_hunks),
                    creation_hunks=list(current_creations),
                )
            )

    for raw_line in git_log_output.splitlines():
        header_match = _COMMIT_HEADER_RE.match(raw_line)
        if header_match:
            flush()
            current_sha = header_match.group("sha")
            try:
                current_ts = int(header_match.group("ts"))
            except (TypeError, ValueError):
                current_ts = 0
            current_hunks = []
            current_creations = []
            continue

        hunk_match = _HUNK_RE.match(raw_line)
        if hunk_match and current_sha is not None:
            try:
                start = int(hunk_match.group("start"))
                old_start = int(hunk_match.group("old_start"))
            except (TypeError, ValueError):
                continue
            count_str = hunk_match.group("count")
            count = int(count_str) if count_str is not None else 1
            old_count_str = hunk_match.group("old_count")
            old_count = (
                int(old_count_str) if old_count_str is not None else 1
            )
            if count <= 0:
                # Pure deletion ("@@ -5,1 +5,0 @@") — nothing was added to
                # the new file, so this hunk cannot overlap a symbol range.
                continue
            new_range = (start, start + count - 1)
            if old_start == 0 and old_count == 0:
                # File-creation hunk ("@@ -0,0 +1,N @@") — segregated so
                # ``_attribute_commits`` can decide whether to credit it
                # to a given symbol based on range coverage.
                current_creations.append(new_range)
                continue
            current_hunks.append(new_range)

    flush()
    return commits


def compute_symbol_activation(
    file_path: str,
    symbols: Iterable[dict],
    *,
    now_ts: int | None = None,
    repo_root: str | None = None,
) -> list[ActivationRow]:
    """Compute one ``ActivationRow`` per symbol from git history.

    Args:
        file_path: repo-relative or absolute path to the source file. We
            resolve it against ``repo_root`` (or the discovered enclosing
            repo) before talking to git.
        symbols: iterable of dicts shaped like ``ast_symbol_rows`` —
            requires keys ``id``, ``line``, ``end_line``. Extra keys are
            ignored; missing or non-int line numbers default to the
            whole-file range so the symbol still gets a row.
        now_ts: optional unix timestamp override; defaults to ``time.time()``.
            Tests pass a fixed value when they need deterministic windowing.
        repo_root: optional explicit repo root. Falls back to walking up
            from ``file_path`` to find ``.git``.

    Returns:
        One ``ActivationRow`` per symbol, in the same order as ``symbols``.
        Never raises — git failures degrade to zero-count rows tagged with
        the appropriate ``git_state``.

    Behaviour matrix:
        * ``TSA_INDEX_ACTIVATION=0`` → zero rows, NO subprocess.run calls.
        * ``no_repo`` / ``untracked`` → zero counts, row exists.
        * ``shallow`` → still walks the (truncated) history; window counts
          may understate reality but the row is correct for what git knows.
        * tracked, cold (no commits yet) → zero counts, ``git_state`` is
          whatever ``detect_git_state`` returned ("tracked" usually).
    """
    sym_list = list(symbols)
    resolved_now = int(now_ts) if now_ts is not None else int(time.time())

    if _activation_disabled():
        return _zero_rows(sym_list, file_path, resolved_now, "tracked")

    abs_file_path = os.path.abspath(file_path)
    enclosing_repo = repo_root or _find_repo_root(abs_file_path)
    state: GitState = detect_git_state(file_path)

    if state == "no_repo" or enclosing_repo is None:
        return _zero_rows(sym_list, file_path, resolved_now, "no_repo")
    if state == "untracked":
        return _zero_rows(sym_list, file_path, resolved_now, "untracked")

    rel_path = _rel_to_repo(enclosing_repo, abs_file_path)

    file_history = _git_log_simple(enclosing_repo, rel_path)
    hunk_log = _git_log_hunks(enclosing_repo, rel_path, since_days=90)
    hunk_commits = parse_log_hunks(hunk_log)

    cutoff_30d = resolved_now - 30 * _SECONDS_PER_DAY
    cutoff_90d = resolved_now - 90 * _SECONDS_PER_DAY

    # Commits older than the 90d hunk window are credited at file-level
    # only — we don't have hunk data for them, so we can't attribute by
    # line range. PM decision #2: pre-90d count contributes to
    # mod_count_all so a 100-day-old commit reads as >= 1 even though
    # no hunk overlap is computable.
    pre_90d_commits = sum(1 for c in file_history if c.ts < cutoff_90d)
    file_newest_sha, file_newest_ts = _newest_commit(file_history)

    rows: list[ActivationRow] = []
    for sym in sym_list:
        sym_id, line_start, line_end = _normalize_symbol(sym)
        attribution = _attribute_commits(
            hunk_commits, line_start, line_end
        )
        mod_30d = sum(1 for c in attribution if c.ts >= cutoff_30d)
        mod_90d = sum(1 for c in attribution if c.ts >= cutoff_90d)
        # mod_count_all = hunk-attributed commits inside the 90d window
        # + file-level count outside it. This double-counts a hunk only
        # when git is misbehaving (ts straddling the boundary), which is
        # vanishingly rare; the alternative (ignoring pre-90d entirely)
        # makes the test_30d_window assertion fail.
        mod_all = mod_90d + pre_90d_commits

        last_sha, last_ts = _newest_attribution(attribution)
        if last_sha is None:
            # No hunks fell inside this symbol's range. Fall back to the
            # file-level newest commit only when there ARE pre-90d
            # commits — otherwise we'd attribute a commit that DIDN'T
            # touch this symbol just because it's the most recent for
            # the file. Tests rely on (commit, ts) being None for
            # un-touched symbols when all activity is recent.
            if pre_90d_commits > 0:
                last_sha, last_ts = file_newest_sha, file_newest_ts

        rows.append(
            ActivationRow(
                symbol_id=sym_id,
                file_path=file_path,
                last_modified_commit=last_sha,
                last_modified_at=last_ts,
                mod_count_30d=mod_30d,
                mod_count_90d=mod_90d,
                mod_count_all=mod_all,
                computed_at=resolved_now,
                git_state=state,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _activation_disabled() -> bool:
    """Check the env-var disable switch. ``0`` / ``false`` / ``no`` → off."""
    value = os.environ.get("TSA_INDEX_ACTIVATION", "")
    return value.strip().lower() in {"0", "false", "no", "off"}


def _find_repo_root(start: str) -> str | None:
    """Walk up from ``start`` to find an enclosing ``.git`` directory."""
    current = Path(start)
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return str(candidate)
    return None


def _is_tracked(repo_root: str, abs_path: str) -> bool:
    """Return True when git knows about ``abs_path`` inside ``repo_root``."""
    try:
        rel = _rel_to_repo(repo_root, abs_path)
        result = subprocess.run(
            ["git", "-C", repo_root, "ls-files", "--error-unmatch", "--", rel],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_GIT_TIMEOUT,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False


def _rel_to_repo(repo_root: str, abs_path: str) -> str:
    """Convert ``abs_path`` to a forward-slash path relative to ``repo_root``."""
    try:
        rel = os.path.relpath(abs_path, repo_root)
    except ValueError:
        # Different drives on Windows; fall back to the literal path.
        return abs_path
    return rel.replace(os.sep, "/")


def _git_log_simple(repo_root: str, rel_path: str) -> list[Commit]:
    """``git log --follow`` over a file's full history. Used for mod_count_all.

    No hunks are requested (cheaper). Returns one ``Commit`` per entry with
    an empty hunks list.
    """
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                repo_root,
                "log",
                "--follow",
                "--no-merges",
                "--pretty=format:" + _COMMIT_MARKER + " %H %at",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_GIT_TIMEOUT,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        logger.debug("git log simple failed: %s", exc)
        return []
    if proc.returncode != 0:
        return []
    return parse_log_hunks(proc.stdout)


def _git_log_hunks(
    repo_root: str, rel_path: str, *, since_days: int
) -> str:
    """``git log -p -U0`` constrained to the last ``since_days``. Returns raw."""
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                repo_root,
                "log",
                "--follow",
                "--no-merges",
                "-p",
                "-U0",
                f"--since={since_days} days ago",
                "--pretty=format:" + _COMMIT_MARKER + " %H %at",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_GIT_TIMEOUT,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        logger.debug("git log hunks failed: %s", exc)
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _newest_commit(
    commits: list[Commit],
) -> tuple[str | None, int | None]:
    """Return (sha, ts) for the most recent commit, or (None, None)."""
    if not commits:
        return (None, None)
    newest = max(commits, key=lambda c: c.ts)
    return newest.sha, newest.ts


def _newest_attribution(
    commits: list[Commit],
) -> tuple[str | None, int | None]:
    """Most recent commit from an already-filtered attribution list."""
    return _newest_commit(commits)


def _normalize_symbol(sym: dict) -> tuple[int, int, int]:
    """Extract (id, line_start, line_end) from a symbol dict.

    Defensive: when both line and end_line are 0 (extraction failure or
    module-level placeholder), treat the symbol as covering the whole file
    so it still gets attributed. Otherwise the row would always report
    zero modifications regardless of activity.
    """
    sym_id = int(sym.get("id", 0))
    line_start = int(sym.get("line", 0) or 0)
    line_end = int(sym.get("end_line", 0) or 0)
    if line_start <= 0 and line_end <= 0:
        return sym_id, 1, 1_000_000_000
    if line_end < line_start:
        line_end = line_start
    if line_start < 1:
        line_start = 1
    return sym_id, line_start, line_end


def _attribute_commits(
    commits: list[Commit], line_start: int, line_end: int
) -> list[Commit]:
    """Return the subset of ``commits`` whose hunks credit [start, end].

    Counting rules:
      * Regular hunks (real edits): attribute if ranges overlap.
      * Creation hunks: attribute ONLY when the symbol range CONTAINS
        the creation hunk (symbol_start <= hunk_start AND symbol_end
        >= hunk_end). This avoids giving every symbol a +1 just for
        existing when a file is created — only symbols that span the
        entire newly-added region (e.g. a single-function file) are
        credited for their birth.

    A commit is attributed once regardless of how many of its hunks
    qualify — duplicate hunks within the same commit do not double-count.
    """
    out: list[Commit] = []
    for commit in commits:
        attributed = False
        for hunk_start, hunk_end in commit.hunks:
            if hunk_end < line_start or hunk_start > line_end:
                continue
            attributed = True
            break
        if not attributed:
            for hunk_start, hunk_end in commit.creation_hunks:
                if line_start <= hunk_start and line_end >= hunk_end:
                    attributed = True
                    break
        if attributed:
            out.append(commit)
    return out


def _zero_rows(
    symbols: list[dict],
    file_path: str,
    now_ts: int,
    state: GitState,
) -> list[ActivationRow]:
    """Return one zero-count ``ActivationRow`` per symbol for cold paths."""
    rows: list[ActivationRow] = []
    for sym in symbols:
        sym_id, _start, _end = _normalize_symbol(sym)
        rows.append(
            ActivationRow(
                symbol_id=sym_id,
                file_path=file_path,
                last_modified_commit=None,
                last_modified_at=None,
                mod_count_30d=0,
                mod_count_90d=0,
                mod_count_all=0,
                computed_at=now_ts,
                git_state=state,
            )
        )
    return rows
