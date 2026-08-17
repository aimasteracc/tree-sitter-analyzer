"""Trusted tool-artifact exclusion for path enforcement (RFC-0026 C25).

When the declared verification command or oracle runs, normal tooling
creates untracked files (``.pytest_cache/``, ``__pycache__/``, ...). The
allowlist recheck (C18) must not treat those as path violations.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Pinned set of tool-created directory basenames excluded from path
# enforcement (RFC-0026 C25). Everything else that appears post-command is a
# violation candidate.
TRUSTED_TOOL_ARTIFACT_DIRS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        ".coverage_cache",
    }
)

# Trusted artifact files at the repository root (coverage databases etc.).
TRUSTED_TOOL_ARTIFACT_FILES = frozenset({".coverage", ".pytest_cache"})


def is_trusted_tool_artifact(rel_path: str) -> bool:
    """Return whether one repository-relative path is a trusted artifact.

    Any path segment equal to a trusted directory basename marks the whole
    subtree as trusted (e.g. ``tests/__pycache__/x.cpython-311.pyc``).
    """
    parts = PurePosixPath(rel_path.replace("\\", "/")).parts
    if any(part in TRUSTED_TOOL_ARTIFACT_DIRS for part in parts):
        return True
    if len(parts) == 1 and parts[0] in TRUSTED_TOOL_ARTIFACT_FILES:
        return True
    return False
