"""Persistent indexes: ``index/<repo>/<key>/{tree/, manifest.json}``.

``tree/`` is a detached worktree of the bare clone at the pinned commit and is
the project root every server of that key uses, so its ``.ast-cache`` never
moves. A directory without a valid ``manifest.json`` is a partial build and is
rebuilt from scratch; nothing is ever repaired in place.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import gitutil
from ._boot import CHILD_PROCESS, EXCLUSION_VIOLATED, WRONG_PACKAGE
from .layout import GATE_FORMAT, Layout, RepoPin
from .mcp_client import BOOT, server_env

#: The checkout setting the r15 corpus clones used (part of the index key).
CHECKOUT_CONFIG = ("-c", "core.autocrlf=true")
MANIFEST = "manifest.json"
#: ``.ast-cache/graph-memo`` holds edge resolutions keyed by TSA's
#: ``source_fingerprint``; TSA only uses it when it is a real directory, so a
#: regular file in its place disables it for every server of the index.
GRAPH_MEMO = "graph-memo"
GRAPH_MEMO_BLOCKER = (
    "callers gate: query-time graph memo disabled (base and head share this index;\n"
    "TSA's source fingerprint is path + size + mtime and can collide across trees)\n"
)


def build_env(pythonpath: Path, private: Path) -> dict[str, str]:
    """Server environment plus ``TSA_INDEX_WORKERS=1``: the audited process does all the work."""
    return {**server_env(pythonpath, private), "TSA_INDEX_WORKERS": "1"}


def block_query_memos(tree: Path) -> None:
    """Replace ``.ast-cache/graph-memo`` by a regular file (idempotent)."""
    memo = tree / ".ast-cache" / GRAPH_MEMO
    if memo.is_file() and not memo.is_symlink():
        return
    if memo.is_symlink():
        memo.unlink()
    elif memo.is_dir():
        shutil.rmtree(memo)
    memo.write_text(GRAPH_MEMO_BLOCKER, encoding="utf-8")


def query_memos_blocked(tree: Path) -> bool:
    memo = tree / ".ast-cache" / GRAPH_MEMO
    return memo.is_file() and not memo.is_symlink()


class IndexError_(RuntimeError):  # noqa: N801 - avoid shadowing builtins.IndexError
    """The index could not be built or must not be used (fail closed)."""


@dataclass(frozen=True)
class IndexInfo:
    key: str
    root: Path  # project root (worktree) with .ast-cache inside
    built: bool
    seconds: float


@contextlib.contextmanager
def repo_lock(layout: Layout, repo: str, timeout: float = 3600) -> Iterator[None]:
    """One index writer per repo across concurrent gate runs (``O_EXCL`` lock file)."""
    path = layout.lock(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if _stale(path):
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            if time.monotonic() > deadline:
                raise IndexError_(f"index lock busy: {path}") from None
            time.sleep(2)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


def _stale(path: Path) -> bool:
    try:
        pid = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_manifest(directory: Path, key: str, pin: RepoPin) -> dict[str, Any] | None:
    """The manifest when it describes a finished build of exactly this key, else None."""
    try:
        data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = (
        isinstance(data, dict)
        and data.get("format") == GATE_FORMAT
        and data.get("key") == key
        and data.get("repo") == pin.name
        and data.get("repo_sha") == pin.sha
        and data.get("status") == "ready"
        and (directory / "tree" / ".ast-cache").is_dir()
    )
    return data if ok else None


def remove_index_dir(layout: Layout, pin: RepoPin, directory: Path) -> None:
    tree = directory / "tree"
    if tree.exists():
        with contextlib.suppress(gitutil.GitError):
            gitutil.git(
                layout.repo(pin.name), "worktree", "remove", "--force", str(tree)
            )
    if directory.exists():
        for path in directory.rglob("*"):
            with contextlib.suppress(OSError):
                os.chmod(path, 0o666)
        shutil.rmtree(directory, ignore_errors=True)
    with contextlib.suppress(gitutil.GitError):
        gitutil.git(layout.repo(pin.name), "worktree", "prune")
    if directory.exists():
        raise IndexError_(f"could not remove stale index dir {directory}")


def ensure_index(
    layout: Layout,
    pin: RepoPin,
    key: str,
    *,
    python: Path,
    head_pkg_parent: Path,
    excluded_modules: list[str],
    built_by: str,
    log: Callable[[str], None],
) -> IndexInfo:
    directory = layout.index_dir(pin.name, key)
    with repo_lock(layout, pin.name):
        manifest = read_manifest(directory, key, pin)
        if manifest is not None:
            block_query_memos(directory / "tree")
            touch = {**manifest, "last_used": time.time()}
            (directory / MANIFEST).write_text(
                json.dumps(touch, indent=1), encoding="utf-8"
            )
            return IndexInfo(key, directory / "tree", False, 0.0)
        if directory.exists():
            log(f"[{pin.name}] index {key}: partial or invalid, rebuilding")
            remove_index_dir(layout, pin, directory)
        directory.mkdir(parents=True)
        tree = directory / "tree"
        gitutil.git(
            layout.repo(pin.name),
            *CHECKOUT_CONFIG,
            "worktree",
            "add",
            "--detach",
            "--quiet",
            str(tree),
            pin.sha,
        )
        excluded_file = directory / "excluded-modules.json"
        excluded_file.write_text(json.dumps(excluded_modules), encoding="utf-8")
        out = directory / "build.json"
        started = time.perf_counter()
        with open(directory / "build.log", "ab") as build_log:
            proc = subprocess.run(
                [
                    str(python),
                    "-s",
                    str(BOOT),
                    "index",
                    str(head_pkg_parent / "tree_sitter_analyzer"),
                    str(tree),
                    str(out),
                    str(excluded_file),
                ],
                cwd=str(tree),
                env=build_env(head_pkg_parent, directory / "private"),
                stdout=build_log,
                stderr=build_log,
                check=False,
            )
        seconds = time.perf_counter() - started
        if proc.returncode == CHILD_PROCESS:
            detail = out.read_text(encoding="utf-8") if out.is_file() else ""
            raise IndexError_(
                f"[{pin.name}] the index build started a child interpreter, whose imports "
                f"the QUERY_ONLY audit cannot see. {detail}"
            )
        if proc.returncode == EXCLUSION_VIOLATED:
            detail = out.read_text(encoding="utf-8") if out.is_file() else ""
            raise IndexError_(
                f"[{pin.name}] the index build imported a QUERY_ONLY module; the index key would "
                f"ignore code that shapes the index. Fix keys.QUERY_ONLY. {detail}"
            )
        if proc.returncode == WRONG_PACKAGE:
            raise IndexError_(
                f"[{pin.name}] index worker imported the wrong analyzer package (see {directory / 'build.log'})"
            )
        if proc.returncode != 0:
            raise IndexError_(
                f"[{pin.name}] index build failed with {proc.returncode} (see {directory / 'build.log'})"
            )
        summary = json.loads(out.read_text(encoding="utf-8"))
        block_query_memos(tree)
        manifest = {
            "format": GATE_FORMAT,
            "key": key,
            "repo": pin.name,
            "repo_sha": pin.sha,
            "status": "ready",
            "built_by_tree": built_by,
            "seconds": round(seconds, 1),
            "summary": summary,
            "created": time.time(),
            "last_used": time.time(),
        }
        (directory / MANIFEST).write_text(
            json.dumps(manifest, indent=1), encoding="utf-8"
        )
        return IndexInfo(key, tree, True, seconds)


def prune_indexes(
    layout: Layout,
    pin: RepoPin,
    keep: int,
    protect: set[str],
    log: Callable[[str], None],
) -> None:
    """Delete all but the ``keep`` most recently used index keys of ``pin`` (never ``protect``)."""
    base = layout.index_root(pin.name)
    if not base.is_dir():
        return
    entries = []
    for directory in base.iterdir():
        if not directory.is_dir():
            continue
        try:
            used = float(
                json.loads((directory / MANIFEST).read_text(encoding="utf-8")).get(
                    "last_used", 0
                )
            )
        except (OSError, ValueError):
            used = 0.0
        entries.append((used, directory))
    entries.sort(reverse=True)
    kept = 0
    with repo_lock(layout, pin.name):
        for _used, directory in entries:
            if directory.name in protect:
                continue
            if kept < keep:
                kept += 1
                continue
            log(f"[{pin.name}] prune index {directory.name}")
            remove_index_dir(layout, pin, directory)
