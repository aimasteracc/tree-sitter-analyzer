"""Git helpers: content-addressed trees for refs and (possibly dirty) worktrees."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

PACKAGE = "tree_sitter_analyzer"


class GitError(RuntimeError):
    pass


def git_bytes(cwd: Path | str, *args: str, env: dict[str, str] | None = None) -> bytes:
    full_env = None if env is None else {**os.environ, **env}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        env=full_env,
        check=False,
    )
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed in {cwd}: {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def git(cwd: Path | str, *args: str, env: dict[str, str] | None = None) -> str:
    return git_bytes(cwd, *args, env=env).decode("utf-8", "replace")


def ref_tree(repo: Path, ref: str, path: str = PACKAGE) -> str:
    """Tree hash of ``path`` at ``ref``."""
    return git(repo, "rev-parse", f"{ref}^{{commit}}:{path}").strip()


def commit_of(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", f"{ref}^{{commit}}").strip()


def ignored_package_files(worktree: Path) -> list[str]:
    """Ignored files under the package other than bytecode caches.

    Python would import them but the tree hash would not cover them, so the
    gate refuses to run on such a worktree instead of caching under a hash that
    does not describe the code.
    """
    out = git(
        worktree,
        "status",
        "--porcelain",
        "--ignored",
        "--untracked-files=all",
        "--",
        PACKAGE,
    )
    bad = []
    for line in out.splitlines():
        if not line.startswith("!! "):
            continue
        path = line[3:].strip().strip('"')
        if "__pycache__/" in path or path.endswith((".pyc", ".pyo")):
            continue
        bad.append(path)
    return bad


def worktree_tree(worktree: Path, path: str = PACKAGE) -> str:
    """Tree hash of ``path`` as it is on disk (tracked edits and untracked files included).

    Uses a throwaway index file, so the worktree's own index is not touched.
    """
    fd, tmp_index = tempfile.mkstemp(prefix="callers-gate-index-")
    os.close(fd)
    os.unlink(tmp_index)
    env = {"GIT_INDEX_FILE": tmp_index}
    try:
        git(worktree, "read-tree", "HEAD", env=env)
        git(worktree, "add", "-A", "--", path, env=env)
        return git(worktree, "write-tree", f"--prefix={path}/", env=env).strip()
    finally:
        try:
            os.unlink(tmp_index)
        except OSError:
            pass


def tree_blobs(repo: Path, tree: str) -> dict[str, str]:
    """``relative path -> blob sha`` for every file under ``tree`` (recursive)."""
    out = git(repo, "ls-tree", "-r", "-z", "--full-tree", tree)
    blobs: dict[str, str] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, rel = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            blobs[rel] = parts[2]
    return blobs


def blob_of(repo: Path, ref: str, path: str) -> str | None:
    try:
        return git(repo, "rev-parse", f"{ref}:{path}").strip()
    except GitError:
        return None


def worktree_blob(worktree: Path, path: str) -> str | None:
    target = worktree / path
    if not target.is_file():
        return None
    return git(worktree, "hash-object", "--", path).strip()


#: Snapshot mtimes are ``EPOCH_NS`` + an offset derived from the tree hash.
EPOCH_NS = 1_000_000_000 * 10**9
#: Offsets stay below ~31.7 years, at NTFS's 100 ns resolution.
_SPAN_100NS = 10**16


def tree_stamp_ns(tree: str) -> int:
    """A file mtime (ns) that is a pure function of ``tree``.

    ``git archive`` of a tree object stamps every file with the current second,
    and TSA's ``source_fingerprint`` hashes path + size + mtime only, so two
    different trees with equal file sizes extracted in one second would share a
    fingerprint (and every cache keyed by it). Stamping each snapshot from its
    own tree hash makes equal fingerprints imply equal trees (up to a 2^53-ish
    collision of the stamp), and the same tree always gets the same stamps.
    """
    return EPOCH_NS + (int(tree[:16], 16) % _SPAN_100NS) * 100


def extract_tree(repo: Path, tree: str, dest: Path, prefix: str = PACKAGE) -> None:
    """Write ``tree`` to ``dest/<prefix>/`` atomically (``git archive`` of a tree object)."""
    if (dest / prefix).is_dir() and (dest / ".complete").is_file():
        return
    staging = dest.with_name(dest.name + f".tmp{os.getpid()}")
    shutil.rmtree(staging, ignore_errors=True)
    (staging / prefix).mkdir(parents=True)
    data = git_bytes(repo, "archive", "--format=tar", tree)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if member.name.startswith(("/", "..")) or ".." in Path(member.name).parts:
                raise GitError(f"unsafe archive member {member.name!r}")
        if hasattr(tarfile, "data_filter"):  # 3.10.12+ / 3.11.4+
            tar.extractall(staging / prefix, filter="data")
        else:  # pragma: no cover - older interpreters
            tar.extractall(staging / prefix)  # noqa: S202 - members validated above
    stamp = tree_stamp_ns(tree)
    for path in (staging / prefix).rglob("*"):
        if path.is_file():
            os.utime(path, ns=(stamp, stamp))
    (staging / ".complete").write_text(tree, encoding="utf-8")
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, dest)
