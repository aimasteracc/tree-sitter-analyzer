"""Copy one callers-gate index to a scratch root and rebind the copy (RFC-0043 measurements).

Usage::

    python benchmarks/resident/copy_gate_index.py --src <gate>/v2/index/<repo>/<key>/tree --dst PATH

The gate's index caches (``docs/dev/callers-gate.md``) are shared with running
gates and must stay read-only. A published index names its project root in two
places: the generation selector (``index-generations/active.json``) and the
snapshot manifest row, whose index fingerprint covers the root. A copy under
another path is therefore refused by certification (``NO_EXACT_FULL_INDEX_MANIFEST``)
and every query would recapture. This script copies the tree (file times kept,
the worktree's ``.git`` link left out so no git command can reach the gate's
repository), then rewrites the selector and the manifest row **of the copy**
with the same functions certification uses. The copy answers exactly like the
original: ``corpus_replay.py`` found 0 differing rows over all 2,457 stored
answers of the 7 gate repos.

It refuses a destination inside the source and never opens the source for
writing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def copy_tree(src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst`` with file times; skip the worktree's ``.git`` link file."""

    def ignore(directory: str, names: list[str]) -> list[str]:
        return [".git"] if Path(directory) == src and ".git" in names else []

    shutil.copytree(src, dst, ignore=ignore, copy_function=shutil.copy2)


def rebind(root: Path) -> str:
    """Point the copy's selector and manifest at ``root``; returns the new fingerprint."""
    from tree_sitter_analyzer import index_snapshot

    canonical = os.path.realpath(str(root))
    selector_path = root / ".ast-cache" / "index-generations" / "active.json"
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    selector["canonical_root"] = canonical
    selector["logical_path"] = str(Path(canonical) / ".ast-cache" / "index.db")
    os.chmod(selector_path, stat.S_IWRITE | stat.S_IREAD)
    selector_path.write_bytes(
        json.dumps(selector, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    database = (
        root
        / ".ast-cache"
        / "index-generations"
        / "generations"
        / selector["generation_id"]
        / "index.db"
    )
    mode = os.stat(database).st_mode
    os.chmod(database, stat.S_IWRITE | stat.S_IREAD)
    try:
        conn = sqlite3.connect(str(database))
        try:
            (version,) = conn.execute(
                "SELECT manifest_version FROM ast_index_snapshot_manifest"
            ).fetchone()
            fingerprint = index_snapshot._index_fingerprint_with_deadline(
                conn, canonical, index_snapshot._clock() + 600, None, version
            )
            conn.execute(
                "UPDATE ast_index_snapshot_manifest "
                "SET canonical_root = ?, index_fingerprint = ?",
                (canonical, fingerprint),
            )
            conn.commit()
        finally:
            conn.close()
    finally:
        os.chmod(database, mode)
    return str(fingerprint)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--src", required=True, help="the gate index's tree/ directory")
    parser.add_argument("--dst", required=True, help="new, non-existent scratch root")
    args = parser.parse_args()
    src = Path(args.src).resolve()
    dst = Path(args.dst).resolve()
    if dst == src or src in dst.parents:
        parser.error("--dst must be outside --src")
    if dst.exists():
        parser.error("--dst must not exist")
    if not (src / ".ast-cache" / "index-generations" / "active.json").is_file():
        parser.error("--src has no published index")
    copy_tree(src, dst)
    print(json.dumps({"root": str(dst), "index_fingerprint": rebind(dst)}))


if __name__ == "__main__":
    main()
