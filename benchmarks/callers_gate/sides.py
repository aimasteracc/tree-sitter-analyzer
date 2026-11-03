"""Resolve the base and head code: tree hash, package location, blobs, environment."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import gitutil
from .keys import env_fingerprint
from .layout import Layout
from .mcp_client import SERVER_ENV_TEMPLATE


class SideError(RuntimeError):
    pass


@dataclass(frozen=True)
class Side:
    label: str  # "base" | "head"
    ref: str  # what the user passed
    tree: str  # tree hash of tree_sitter_analyzer/
    pkg_parent: (
        Path | None
    )  # directory holding tree_sitter_analyzer/ (None until materialized)
    blobs: dict[str, str]  # package-relative path -> blob sha
    pyproject_blob: str | None
    commit: str | None


def resolve_ref(layout: Layout, git_dir: Path, ref: str, label: str) -> Side:
    """A committed ref (snapshot is extracted lazily, only when a server needs it)."""
    try:
        commit = gitutil.commit_of(git_dir, ref)
        tree = gitutil.ref_tree(git_dir, commit)
    except gitutil.GitError as exc:
        raise SideError(f"{label}: cannot resolve {ref!r}: {exc}") from exc
    snapshot = layout.src(tree)
    return Side(
        label,
        ref,
        tree,
        snapshot,
        gitutil.tree_blobs(git_dir, tree),
        gitutil.blob_of(git_dir, commit, "pyproject.toml"),
        commit,
    )


def resolve_worktree(path: Path, label: str) -> Side:
    """A worktree as it is on disk (uncommitted edits included in the tree hash)."""
    if not (path / gitutil.PACKAGE / "__init__.py").is_file():
        raise SideError(f"{label}: {path} has no {gitutil.PACKAGE}/ package")
    ignored = gitutil.ignored_package_files(path)
    if ignored:
        raise SideError(
            f"{label}: ignored files under the package would run but not be hashed: {ignored[:5]}"
        )
    tree = gitutil.worktree_tree(path)
    return Side(
        label,
        str(path),
        tree,
        path,
        gitutil.tree_blobs(path, tree),
        gitutil.worktree_blob(path, "pyproject.toml"),
        gitutil.commit_of(path, "HEAD"),
    )


def materialize(layout: Layout, git_dir: Path, side: Side) -> Path:
    """Directory that holds ``tree_sitter_analyzer/`` for ``side`` (extracting a snapshot if needed)."""
    assert side.pkg_parent is not None
    if side.pkg_parent == layout.src(side.tree):
        gitutil.extract_tree(git_dir, side.tree, side.pkg_parent)
    return side.pkg_parent


def environment(python: Path) -> tuple[str, str, list[str]]:
    """(fingerprint, python version, distributions) of the gate interpreter."""
    probe = (
        "import json,sys,importlib.metadata as m;"
        "print(json.dumps({'v':sys.version,'d':sorted(f\"{d.metadata['Name']}=={d.version}\" for d in m.distributions())}))"
    )
    proc = subprocess.run(
        [str(python), "-s", "-P", "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SideError(f"gate interpreter {python} failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    return (
        env_fingerprint(data["v"], data["d"], SERVER_ENV_TEMPLATE),
        data["v"],
        data["d"],
    )
