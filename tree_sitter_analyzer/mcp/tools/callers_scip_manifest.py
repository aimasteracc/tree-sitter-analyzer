"""The manifest that binds a SCIP index to one exact project state.

SCIP has no incremental update: an index describes the sources, the lockfile
and the installed dependencies at the moment it was built. TSA never runs the
indexer; whoever builds ``index.scip`` writes, right after the build, a
manifest beside it (``<index>.manifest.json``)::

    {"format": 1,
     "index_sha256": "<sha256 of the index file>",
     "git_tree": "<tree hash of HEAD>",
     "dirty": {"src/a.ts": "<sha256>", "src/gone.ts": "<deleted>"},
     "lockfiles": {"pnpm-lock.yaml": "<sha256>"},
     "indexer": {"name": "scip-typescript", "version": "0.6.1"}}

``dirty`` holds every path ``git status`` reports (modified, staged, deleted,
untracked; ignored files excluded), except ``.ast-cache/`` and the index and
manifest files themselves. At query time the same state is computed again;
any difference (another commit, an edited file, a new untracked file, a
changed lockfile, a rewritten index) means the index is ignored.

Write a manifest (the indexer has just written ``index.scip``)::

    python -m tree_sitter_analyzer.mcp.tools.callers_scip_manifest \\
        --project . --index .ast-cache/scip/index.scip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST_FORMAT = 1
MANIFEST_SUFFIX = ".manifest.json"
DELETED = "<deleted>"
#: Lockfiles whose content pins the dependency set the indexer resolved against.
LOCKFILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
)
#: Paths below these prefixes never count as dirty (TSA's own cache).
IGNORED_PREFIXES = (".ast-cache/",)
_GIT_TIMEOUT_S = 60


class ManifestError(ValueError):
    """The manifest is missing, unreadable or malformed."""


def manifest_path(index: Path) -> Path:
    return index.with_name(index.name + MANIFEST_SUFFIX)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> bytes | None:
    options = [a for a in args if a == "--no-optional-locks"]
    rest = [a for a in args if a != "--no-optional-locks"]
    try:
        proc = subprocess.run(
            ["git", *options, "-C", str(root), *rest],
            # An MCP server's stdin is the protocol pipe: git must never inherit
            # it (git for Windows was seen blocking on it indefinitely).
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _status_paths(raw: bytes) -> list[str]:
    """Paths of ``git status --porcelain=v1 -z`` (both sides of a rename)."""
    parts = raw.split(b"\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        paths.append(path.decode("utf-8", "surrogateescape"))
        if b"R" in code or b"C" in code:
            if i < len(parts) and parts[i]:
                paths.append(parts[i].decode("utf-8", "surrogateescape"))
            i += 1
    return paths


def _relative(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def project_state(
    root: Path, *, exclude: tuple[Path, ...] = ()
) -> dict[str, Any] | None:
    """``{git_tree, dirty, lockfiles}`` of ``root``; ``None`` when git cannot read it.

    ``dirty`` covers the whole repository (``root`` may be a sub-directory of a
    monorepo); its paths are relative to the repository top level, as git
    reports them. ``.ast-cache/`` is ignored below ``root``.
    """
    revs = _git(root, "rev-parse", "--show-toplevel", "HEAD^{tree}")
    status = _git(
        root,
        "--no-optional-locks",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    lines = (revs or b"").decode("utf-8", "surrogateescape").splitlines()
    if len(lines) != 2 or status is None:
        return None
    toplevel, tree = Path(lines[0].strip()), lines[1].strip().encode("ascii")
    prefix = _relative(toplevel, root)
    if prefix is None:
        return None
    base = "" if prefix in ("", ".") else prefix + "/"
    ignored = tuple(base + p for p in IGNORED_PREFIXES)
    skipped = {rel for rel in (_relative(toplevel, p) for p in exclude) if rel}
    dirty: dict[str, str] = {}
    for rel in sorted(set(_status_paths(status))):
        if rel in skipped or rel.startswith(ignored):
            continue
        path = toplevel / rel
        try:
            dirty[rel] = file_sha256(path) if path.is_file() else DELETED
        except OSError:
            return None
    locks: dict[str, str] = {}
    for name in LOCKFILES:
        path = root / name
        if path.is_file():
            try:
                locks[name] = file_sha256(path)
            except OSError:
                return None
    return {
        "git_tree": tree.decode("ascii", "replace").strip(),
        "dirty": dirty,
        "lockfiles": locks,
    }


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"no manifest at {path}") from exc
    except (OSError, ValueError) as exc:
        raise ManifestError(f"unreadable manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != MANIFEST_FORMAT:
        raise ManifestError(f"manifest {path} is not format {MANIFEST_FORMAT}")
    for key, kind in (
        ("index_sha256", str),
        ("git_tree", str),
        ("dirty", dict),
        ("lockfiles", dict),
    ):
        if not isinstance(data.get(key), kind):
            raise ManifestError(f"manifest {path}: field {key!r} missing or malformed")
    return data


def stale_reason(
    manifest: dict[str, Any], index_sha256: str, state: dict[str, Any] | None
) -> str | None:
    """Why the index does not describe the current project (``None``: it does)."""
    if manifest["index_sha256"] != index_sha256:
        return "index file differs from the one the manifest describes"
    if state is None:
        return "project state unreadable (git)"
    if manifest["git_tree"] != state["git_tree"]:
        return "git tree differs"
    if manifest["dirty"] != state["dirty"]:
        return "uncommitted files differ"
    if manifest["lockfiles"] != state["lockfiles"]:
        return "lockfiles differ"
    return None


def write_manifest(
    root: Path, index: Path, indexer: dict[str, str] | None = None
) -> dict[str, Any]:
    """Describe the current project state for ``index``; written beside it."""
    target = manifest_path(index)
    state = project_state(root, exclude=(index, target))
    if state is None:
        raise ManifestError(f"cannot read the git state of {root}")
    manifest: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "index_sha256": file_sha256(index),
        **state,
    }
    if indexer:
        manifest["indexer"] = dict(indexer)
    target.write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", required=True, help="project root (git worktree)")
    parser.add_argument("--index", required=True, help="the index.scip just written")
    parser.add_argument(
        "--check", action="store_true", help="only report whether the manifest holds"
    )
    args = parser.parse_args(argv)
    root, index = Path(args.project), Path(args.index)
    if not index.is_absolute():
        index = root / index
    try:
        if args.check:
            manifest = read_manifest(manifest_path(index))
            state = project_state(root, exclude=(index, manifest_path(index)))
            reason = stale_reason(manifest, file_sha256(index), state)
            print("fresh" if reason is None else f"stale: {reason}")
            return 0 if reason is None else 1
        from .callers_scip_index import parse_index

        parsed = parse_index(index.read_bytes())
        written = write_manifest(
            root, index, {"name": parsed.tool_name, "version": parsed.tool_version}
        )
    except (ManifestError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: written[k] for k in ("git_tree", "lockfiles")}))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
