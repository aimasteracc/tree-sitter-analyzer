"""Repo preparation module for the CodeGraph comparison benchmark harness.

Clones repos to ``.benchmark-repos/<repo-id>/``, pins to a specific commit,
and collects metadata (file counts, sizes).

Public API
----------
    prepare_repo(repo, base_dir) -> PreparedRepo
    prepare_all(repos, base_dir) -> list[PreparedRepo]
    load_prepared_manifest(path) -> list[PreparedRepo]
    save_prepared_manifest(repos, path) -> None

CLI
---
    python benchmarks/codegraph_compare/repo_prep.py prepare --repo gin
    python benchmarks/codegraph_compare/repo_prep.py prepare --all
    python benchmarks/codegraph_compare/repo_prep.py status

Created: 2026-05-26
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_DIR = Path(".benchmark-repos")

REPOS_CONFIG = Path(__file__).parent / "repos.yaml"

# Directories excluded from file counts
_EXCLUDED_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".benchmark-repos"}

# Source file extensions that count toward source_file_count
_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".swift",
    ".kt",
    ".cpp",
    ".c",
    ".h",
    ".cs",
}

# Sentinel commit value meaning "use HEAD on default branch"
_PLACEHOLDER_SHA = "PLACEHOLDER_SHA"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RepoSpec:
    """Specification for a repository to benchmark."""

    id: str
    name: str
    url: str
    language: str
    commit: str
    description: str = ""


@dataclass
class PreparedRepo:
    """Result of successfully (or unsuccessfully) preparing a repository."""

    id: str
    name: str
    language: str
    local_path: Path
    actual_commit: str
    file_count: int
    source_file_count: int
    size_bytes: int
    prepared_at: str  # ISO 8601 timestamp
    error: str | None = None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_repos_config(path: Path = REPOS_CONFIG) -> list[RepoSpec]:
    """Load repo specs from a YAML config file.

    Expected YAML structure::

        repos:
          - id: gin
            name: gin-gonic/gin
            url: https://github.com/gin-gonic/gin.git
            language: Go
            commit: abc123def456...
            description: "Fast HTTP web framework for Go"
    """
    if not path.exists():
        raise FileNotFoundError(f"Repos config not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or "repos" not in raw:
        raise ValueError(f"repos.yaml must have a top-level 'repos' list: {path}")

    specs = []
    for entry in raw["repos"]:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Each entry in repos.yaml must be a mapping, got: {entry!r}"
            )
        specs.append(
            RepoSpec(
                id=str(entry["id"]),
                name=str(entry["name"]),
                url=str(entry["url"]),
                language=str(entry["language"]),
                commit=str(entry["commit"]),
                description=str(entry.get("description", "")),
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stderr(*args: Any, **kwargs: Any) -> None:
    """Print progress messages to stderr so stdout stays machine-readable."""
    print(*args, **kwargs, file=sys.stderr)


def _run_git(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    """Run a git command and return stdout as a stripped string."""
    cmd = ["git"] + args
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )
    return result.stdout.strip()


def _get_current_commit(repo_dir: Path) -> str:
    """Return the current HEAD commit SHA in the given repo dir."""
    return _run_git(["rev-parse", "HEAD"], cwd=repo_dir)


def _is_excluded(path: Path, base: Path) -> bool:
    """Return True if the path is inside an excluded directory."""
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    # Check every part of the relative path against excluded dir names
    return any(part in _EXCLUDED_DIRS for part in relative.parts)


def _collect_stats(repo_dir: Path) -> tuple[int, int, int]:
    """Walk repo_dir and return (file_count, source_file_count, size_bytes).

    Excludes .git/, node_modules/, vendor/, __pycache__/, .benchmark-repos/
    from all counts.
    """
    file_count = 0
    source_file_count = 0
    size_bytes = 0

    for entry in repo_dir.rglob("*"):
        if not entry.is_file():
            continue
        if _is_excluded(entry, repo_dir):
            continue

        file_count += 1
        if entry.suffix.lower() in _SOURCE_EXTENSIONS:
            source_file_count += 1
        try:
            size_bytes += entry.stat().st_size
        except OSError:
            pass  # race condition or unreadable file — skip silently

    return file_count, source_file_count, size_bytes


def _clone_repo(url: str, dest: Path) -> None:
    """Clone a repo from url into dest (must not exist yet)."""
    _stderr(f"  Cloning {url} → {dest}")
    subprocess.run(
        ["git", "clone", "--quiet", url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _checkout_commit(repo_dir: Path, commit: str) -> None:
    """Hard-checkout a specific commit (detached HEAD)."""
    _stderr(f"  Checking out {commit[:12]}…")
    _run_git(["checkout", "--quiet", commit], cwd=repo_dir)


def _get_default_branch_head(repo_dir: Path) -> str:
    """Return the current HEAD SHA without checking out anything extra.

    After a plain ``git clone``, HEAD is already at the default branch tip,
    so we just resolve it.
    """
    return _run_git(["rev-parse", "HEAD"], cwd=repo_dir)


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def prepare_repo(
    repo: RepoSpec,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> PreparedRepo:
    """Clone repo to ``base_dir/<repo.id>/``, pin to commit, collect metadata.

    Idempotent: if the directory already exists and HEAD matches
    ``repo.commit``, the clone step is skipped.

    If ``repo.commit == "PLACEHOLDER_SHA"``, the latest commit on the cloned
    default branch is used and recorded as ``actual_commit``.

    Any exception during preparation is caught; the returned ``PreparedRepo``
    will have ``error`` set instead of raising.
    """
    base_dir = base_dir.resolve()
    repo_dir = base_dir / repo.id
    prepared_at = datetime.now(tz=timezone.utc).isoformat()

    try:
        base_dir.mkdir(parents=True, exist_ok=True)

        use_placeholder = repo.commit == _PLACEHOLDER_SHA

        # --- Determine whether we can skip the clone ---
        already_exists = repo_dir.exists()
        skip_clone = False

        if already_exists and not use_placeholder:
            try:
                current_sha = _get_current_commit(repo_dir)
                if current_sha == repo.commit:
                    _stderr(
                        f"[{repo.id}] Already at {repo.commit[:12]}, skipping clone."
                    )
                    skip_clone = True
                else:
                    _stderr(
                        f"[{repo.id}] Exists but at {current_sha[:12]} "
                        f"(want {repo.commit[:12]}); re-cloning."
                    )
            except subprocess.CalledProcessError:
                _stderr(f"[{repo.id}] Exists but git check failed; re-cloning.")

        if not skip_clone:
            # Remove stale directory if present
            if already_exists:
                import shutil as _shutil

                _stderr(f"[{repo.id}] Removing stale directory {repo_dir}")
                _shutil.rmtree(repo_dir)

            _stderr(f"[{repo.id}] Cloning …")
            _clone_repo(repo.url, repo_dir)

        # --- Resolve actual commit ---
        if use_placeholder:
            actual_commit = _get_default_branch_head(repo_dir)
            _stderr(f"[{repo.id}] PLACEHOLDER_SHA resolved to {actual_commit[:12]}")
        else:
            if not skip_clone:
                _checkout_commit(repo_dir, repo.commit)
            actual_commit = _get_current_commit(repo_dir)

        # --- Collect metadata ---
        _stderr(f"[{repo.id}] Counting files …")
        file_count, source_file_count, size_bytes = _collect_stats(repo_dir)
        _stderr(
            f"[{repo.id}] Done — {file_count} files, "
            f"{source_file_count} source files, "
            f"{size_bytes:,} bytes"
        )

        return PreparedRepo(
            id=repo.id,
            name=repo.name,
            language=repo.language,
            local_path=repo_dir,
            actual_commit=actual_commit,
            file_count=file_count,
            source_file_count=source_file_count,
            size_bytes=size_bytes,
            prepared_at=prepared_at,
            error=None,
        )

    except Exception as exc:  # noqa: BLE001
        _stderr(f"[{repo.id}] ERROR: {exc}")
        return PreparedRepo(
            id=repo.id,
            name=repo.name,
            language=repo.language,
            local_path=repo_dir,
            actual_commit="",
            file_count=0,
            source_file_count=0,
            size_bytes=0,
            prepared_at=prepared_at,
            error=str(exc),
        )


def prepare_all(
    repos: list[RepoSpec],
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[PreparedRepo]:
    """Prepare every repo in ``repos`` sequentially, collecting all results.

    Failed repos have ``error`` set; preparation continues for the rest.
    """
    results: list[PreparedRepo] = []
    total = len(repos)
    for idx, repo in enumerate(repos, start=1):
        _stderr(f"\n[{idx}/{total}] Preparing repo: {repo.id} ({repo.language})")
        prepared = prepare_repo(repo, base_dir=base_dir)
        results.append(prepared)
    return results


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------


def _prepared_repo_to_dict(pr: PreparedRepo) -> dict[str, Any]:
    """Convert a PreparedRepo to a JSON-serializable dict."""
    d = dataclasses.asdict(pr)
    d["local_path"] = str(pr.local_path)
    return d


def _prepared_repo_from_dict(d: dict[str, Any]) -> PreparedRepo:
    """Reconstruct a PreparedRepo from a plain dict (e.g. loaded from JSON)."""
    return PreparedRepo(
        id=d["id"],
        name=d["name"],
        language=d["language"],
        local_path=Path(d["local_path"]),
        actual_commit=d["actual_commit"],
        file_count=int(d["file_count"]),
        source_file_count=int(d["source_file_count"]),
        size_bytes=int(d["size_bytes"]),
        prepared_at=d["prepared_at"],
        error=d.get("error"),
    )


def save_prepared_manifest(repos: list[PreparedRepo], path: Path) -> None:
    """Serialize ``repos`` to a JSON file at ``path``.

    Parent directories are created as needed.  The file is written atomically
    via a temporary sibling so a partial write never corrupts a previous run.
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = [_prepared_repo_to_dict(r) for r in repos]
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    _stderr(f"Manifest saved → {path}")


def load_prepared_manifest(path: Path) -> list[PreparedRepo]:
    """Load a list of PreparedRepo objects from a JSON manifest file."""
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in manifest, got: {type(raw)}")

    return [_prepared_repo_from_dict(entry) for entry in raw]


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

_DEFAULT_MANIFEST = Path("prepared_repos.json")


def _fmt_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def _cmd_prepare(args: argparse.Namespace) -> int:
    """Handle ``prepare`` subcommand."""
    specs = load_repos_config()

    if args.all:
        to_prepare = specs
    elif args.repo:
        by_id = {s.id: s for s in specs}
        if args.repo not in by_id:
            _stderr(
                f"Unknown repo id '{args.repo}'. Available: {', '.join(sorted(by_id))}"
            )
            return 1
        to_prepare = [by_id[args.repo]]
    else:
        _stderr("Error: specify --repo <id> or --all")
        return 1

    base_dir = Path(args.base_dir) if args.base_dir else DEFAULT_BASE_DIR
    results = prepare_all(to_prepare, base_dir=base_dir)

    manifest_path = Path(args.manifest) if args.manifest else _DEFAULT_MANIFEST

    # Merge with any existing manifest entries for repos we didn't touch
    existing: dict[str, PreparedRepo] = {}
    if manifest_path.exists():
        try:
            for pr in load_prepared_manifest(manifest_path):
                existing[pr.id] = pr
        except Exception as exc:
            _stderr(f"Warning: could not load existing manifest: {exc}")

    for pr in results:
        existing[pr.id] = pr

    save_prepared_manifest(list(existing.values()), manifest_path)

    failures = [r for r in results if r.error]
    if failures:
        _stderr(f"\n{len(failures)} repo(s) failed:")
        for r in failures:
            _stderr(f"  {r.id}: {r.error}")
        return 2

    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Handle ``status`` subcommand — print a table from the manifest."""
    manifest_path = Path(args.manifest) if args.manifest else _DEFAULT_MANIFEST
    try:
        repos = load_prepared_manifest(manifest_path)
    except FileNotFoundError:
        _stderr(f"Manifest not found: {manifest_path}. Run 'prepare --all' first.")
        return 1

    # Column widths
    col_id = max(len("ID"), max(len(r.id) for r in repos)) + 2
    col_lang = max(len("Language"), max(len(r.language) for r in repos)) + 2
    col_files = 8
    col_src = 10
    col_size = 10
    col_commit = 14
    col_status = 10

    header = (
        f"{'ID':<{col_id}}"
        f"{'Language':<{col_lang}}"
        f"{'Files':>{col_files}}"
        f"{'SrcFiles':>{col_src}}"
        f"{'Size':>{col_size}}"
        f"  {'Commit':<{col_commit}}"
        f"  {'Status':<{col_status}}"
    )
    separator = "-" * len(header)

    print(header)
    print(separator)

    for r in sorted(repos, key=lambda x: x.id):
        status = "ERROR" if r.error else "OK"
        commit_short = r.actual_commit[:12] if r.actual_commit else "—"
        size_human = _fmt_size(r.size_bytes)
        row = (
            f"{r.id:<{col_id}}"
            f"{r.language:<{col_lang}}"
            f"{r.file_count:>{col_files}}"
            f"{r.source_file_count:>{col_src}}"
            f"{size_human:>{col_size}}"
            f"  {commit_short:<{col_commit}}"
            f"  {status:<{col_status}}"
        )
        print(row)
        if r.error:
            print(f"  {'':>{col_id}}error: {r.error}")

    print(separator)
    print(f"Total: {len(repos)} repo(s)")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo_prep",
        description="Prepare benchmark repositories for the CodeGraph comparison harness.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=f"Path to the JSON manifest file (default: {_DEFAULT_MANIFEST})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ---- prepare ----
    prep = sub.add_parser("prepare", help="Clone and pin one or all repos.")
    prep_group = prep.add_mutually_exclusive_group(required=True)
    prep_group.add_argument("--repo", metavar="ID", help="Prepare a single repo by id.")
    prep_group.add_argument(
        "--all", action="store_true", help="Prepare all repos in repos.yaml."
    )
    prep.add_argument(
        "--base-dir",
        default=None,
        metavar="DIR",
        help=f"Base directory for clones (default: {DEFAULT_BASE_DIR})",
    )

    # ---- status ----
    sub.add_parser("status", help="Print status table from the prepared manifest.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "prepare":
        return _cmd_prepare(args)
    if args.command == "status":
        return _cmd_status(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
