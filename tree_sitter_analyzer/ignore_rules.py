"""Ignore-rule matching shared by the filesystem discovery paths.

Discovery that honors ``.gitignore`` must draw the rules from one place: the
index paths and ``source_lines`` previously disagreed about which directories
are part of a project. A rule file applies to the directory that declares it
and to every directory below, and a later rule with an opinion overrides an
earlier one, which is what makes ``!`` negation work.
"""

from __future__ import annotations

import os

import pathspec

# Rule files honored per directory, in increasing precedence.
IGNORE_RULE_FILES = (".gitignore", ".ignore", ".rgignore")

# Collected rules: each entry pairs the directory that declared a rule file
# (relative to the walk root, "" for the root) with its compiled spec.
IgnoreRules = list[tuple[str, pathspec.GitIgnoreSpec]]


def load_ignore_rules(
    project_root: str,
    rel_dir: str,
    inherited: IgnoreRules,
) -> IgnoreRules:
    """Return ``inherited`` plus the ignore specs declared in ``rel_dir``.

    ``rel_dir`` is relative to ``project_root``; the empty string is the root.
    A symlinked or unreadable rule file is skipped rather than fatal, so
    discovery never fails because of an ignore file.
    """
    rules = list(inherited)
    base = os.path.join(project_root, rel_dir) if rel_dir else project_root
    for name in IGNORE_RULE_FILES:
        path = os.path.join(base, name)
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        rules.append((rel_dir, pathspec.GitIgnoreSpec.from_lines(lines)))
    return rules


def is_gitignored(
    rel_path: str,
    rules: IgnoreRules,
    *,
    directory: bool,
) -> bool:
    """Whether ``rules`` exclude ``rel_path``; later specs override earlier ones.

    ``rel_path`` is relative to the same root the rules were collected from.
    ``directory`` appends the trailing slash gitignore patterns use to anchor a
    rule to directories.
    """
    ignored = False
    posix = rel_path.replace(os.sep, "/")
    for base, spec in rules:
        if base:
            prefix = base + "/"
            if not posix.startswith(prefix):
                continue
            target = posix[len(prefix) :]
        else:
            target = posix
        if not target:
            continue
        result = spec.check_file(target + ("/" if directory else ""))
        if result.include is not None:
            ignored = bool(result.include)
    return ignored
