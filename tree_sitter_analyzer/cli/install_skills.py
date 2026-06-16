"""install_skills — copy bundled tsa-* skills into a project's .claude/skills/.

Called by ``--install-skills`` / ``--install-skills-global`` CLI flags.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TypedDict


class InstallReport(TypedDict):
    installed_count: int
    skipped_count: int
    installed: list[str]
    skipped: list[str]
    destination: str


def _bundled_skills_dir() -> Path:
    """Return the absolute path to the bundled tsa-* skills directory."""
    from tree_sitter_analyzer import skills as _skills_pkg

    return Path(str(_skills_pkg.__file__)).parent


_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def _resolve_target(
    target_dir: Path | None,
    *,
    global_install: bool,
) -> Path:
    """Return the .claude/skills/ directory to install into."""
    if global_install:
        home = Path(os.environ.get("HOME") or str(Path.home()))
        return home / ".claude" / "skills"
    if target_dir is None:
        target_dir = Path.cwd()
    return Path(target_dir) / ".claude" / "skills"


def install_skills(
    target_dir: Path | None = None,
    *,
    global_install: bool = False,
) -> InstallReport:
    """Copy bundled tsa-* skills to *dest_skills_dir*.

    Parameters
    ----------
    target_dir:
        Project root to install into (``<target_dir>/.claude/skills/``).
        Defaults to CWD when *global_install* is ``False``.
    global_install:
        When ``True``, install to ``~/.claude/skills/`` instead.

    Returns
    -------
    InstallReport
        Counts of installed / skipped skill directories and their names.
    """
    src_root = _bundled_skills_dir()
    dest_root = _resolve_target(target_dir, global_install=global_install)

    # Guard: refuse to install if destination resolves into the bundled
    # skills directory itself (self-copy would corrupt the package).
    try:
        resolved_dest = dest_root.resolve()
        resolved_src = src_root.resolve()
    except Exception:
        resolved_dest = dest_root
        resolved_src = src_root
    if resolved_dest == resolved_src or resolved_src in resolved_dest.parents:
        raise ValueError(
            f"Destination {dest_root} resolves into the bundled skills "
            "directory — refusing to self-copy."
        )

    # #549: echo the resolved destination FIRST, so the user always knows
    # where skills are going before anything is installed or skipped.
    print(f"Installing skills into: {dest_root}", file=sys.stderr)

    try:
        dest_root.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot create skills directory {dest_root}: {exc}"
        ) from exc

    installed: list[str] = []
    skipped: list[str] = []

    for src_skill in sorted(src_root.iterdir()):
        if not src_skill.is_dir() or not src_skill.name.startswith("tsa-"):
            continue
        dest_skill = dest_root / src_skill.name
        if dest_skill.exists():
            skipped.append(src_skill.name)
            print(f"Skipped (already exists): {dest_skill}", file=sys.stderr)
        else:
            shutil.copytree(src_skill, dest_skill, ignore=_COPY_IGNORE)
            installed.append(src_skill.name)
            print(f"Installed: {dest_skill}", file=sys.stderr)

    return InstallReport(
        installed_count=len(installed),
        skipped_count=len(skipped),
        installed=installed,
        skipped=skipped,
        destination=str(dest_root),
    )
