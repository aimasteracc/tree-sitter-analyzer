#!/usr/bin/env python3
"""CLI dispatcher for ``--clean-state`` / ``--clean-state-dry-run``.

Removes ephemeral workspace state that accumulates from running the CLI
(AST cache, tree-sitter cache, the literal ``:memory:`` directory some
legacy code creates, and the large test fixture directory).

Scope (#988): clean-state removes ONLY tree-sitter-analyzer's own
artifacts. It must never touch sibling tools' databases that happen to
live in the same directory — e.g. Ruflo's ``ruvector.db`` and
``agentdb.rvf*`` files. Those are owned by another tool and may hold
irreplaceable state; a user consenting to reset TSA's cache did not
consent to wiping Ruflo's memory.

Each path is handled independently so a missing one doesn't stop the
sweep. Output is one line per path: ``removed: <path>``, ``skipped (not
present): <path>``, or ``failed: <path>: <error>`` — easy to grep and
easy for tests to assert on. With ``--format json`` the sweep emits a
structured envelope instead (``success`` / ``dry_run`` / ``removed`` /
``skipped`` / ``failed``).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ..output_format import wants_json_output

# Exact list of ephemeral paths owned by tree-sitter-analyzer. Relative
# to the current project root (or CWD if --project-root is unset). Keep
# this tuple frozen so callers and tests can introspect what the sweep
# considers "ephemeral state".
#
# IMPORTANT (#988): this list MUST contain only TSA-owned artifacts.
# Sibling-tool databases (Ruflo's ``ruvector.db`` / ``agentdb.rvf*``)
# were historically bundled here from a co-located install and were
# silently deleted on clean-state — a cross-tool data-loss bug. They
# are deliberately NOT listed here.
EPHEMERAL_STATE_PATHS: tuple[str, ...] = (
    ".ast-cache",
    ".tree-sitter-cache",
    # ``:memory:`` is created as a literal directory by some legacy code
    # paths that mis-pass the SQLite in-memory sentinel as a filesystem
    # path. Removing it as part of clean-state keeps re-runs clean.
    ":memory:",
    "tests/temp_cli_test_large",
)

OutputErrorFn = Callable[[str], None]


def run_clean_state(args: Any, output_error: OutputErrorFn) -> int:
    """Remove ephemeral state files. Returns exit code 0 on success.

    Args:
        args: argparse namespace with ``clean_state`` / ``clean_state_dry_run``
            / ``project_root`` attributes.
        output_error: callback for any unrecoverable errors. Per-path
            failures are printed inline (one line per path) and don't bump
            the exit code; the function only returns non-zero if the
            project root itself can't be resolved.

    Returns:
        0 if the sweep completed (even with per-path skips/failures),
        1 if the project root is unusable.
    """
    project_root = getattr(args, "project_root", None) or os.getcwd()
    dry_run = bool(getattr(args, "clean_state_dry_run", False))

    try:
        root_path = Path(project_root).resolve()
    except OSError as exc:
        output_error(f"--clean-state cannot resolve project_root: {exc}")
        return 1

    summary = _sweep(root_path, EPHEMERAL_STATE_PATHS, dry_run=dry_run)

    if wants_json_output(args):
        print(json.dumps(_build_json_payload(summary, dry_run=dry_run), indent=2))
    else:
        for line in summary:
            print(line)
    return 0


def _build_json_payload(summary: list[str], *, dry_run: bool) -> dict[str, Any]:
    """Bucket the per-path status lines into a structured JSON envelope.

    Each line is ``"<status>: <rel>"`` (failures are ``"failed: <rel>: <err>"``).
    We split on the first ``": "`` to recover the relative path so the
    envelope mirrors exactly what the text output reported. ``success`` is
    ``True`` when no path failed.
    """
    removed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for line in summary:
        status, _, rest = line.partition(": ")
        if status in ("removed", "would_remove"):
            removed.append(rest)
        elif status == "failed":
            # rest is "<rel>: <error>"; keep the whole detail.
            failed.append(rest)
        else:  # "skipped (not present)" / "would_skip (not present)"
            skipped.append(rest)
    return {
        "success": not failed,
        "dry_run": dry_run,
        "removed": removed,
        "skipped": skipped,
        "failed": failed,
    }


def _sweep(
    root: Path,
    relative_paths: Iterable[str],
    *,
    dry_run: bool,
) -> list[str]:
    """Remove each path under ``root``. Returns one status line per path."""
    lines: list[str] = []
    prefix_remove = "would_remove" if dry_run else "removed"
    prefix_skip = "would_skip (not present)" if dry_run else "skipped (not present)"
    for rel in relative_paths:
        target = root / rel
        if not target.exists():
            lines.append(f"{prefix_skip}: {rel}")
            continue
        if dry_run:
            lines.append(f"{prefix_remove}: {rel}")
            continue
        lines.append(_remove_single(target, rel, prefix_remove))
    return lines


def _remove_single(target: Path, rel: str, prefix_remove: str) -> str:
    """Best-effort removal of a single path. Returns the status line."""
    try:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    except FileNotFoundError:
        # Raced against another cleaner — treat as skipped.
        return f"skipped (not present): {rel}"
    except OSError as exc:
        return f"failed: {rel}: {exc}"
    return f"{prefix_remove}: {rel}"
