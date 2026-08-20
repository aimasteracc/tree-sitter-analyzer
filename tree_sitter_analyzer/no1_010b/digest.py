"""Checkout-independent content digests for the NO1-010B corpus (RFC-0026 §4).

Two properties matter for a benchmark that claims its inputs are pinned.

**A digest must not depend on checkout configuration.** ``.gitattributes``
governs whether a text file lands in the working tree with LF or CRLF, so
hashing raw working-tree bytes yields a different digest per platform than the
committed blob. Every read here collapses CRLF to LF first, so the digest is a
property of the content, not of the clone.

**A digest must cover everything the benchmark depends on.** Hashing only
``corpus.jsonl`` leaves the fixture trees — where the oracles' red baseline
actually lives — completely unpinned. :func:`tree_sha256` therefore covers
every file under a root, keyed by relative path, so an edit, a rename, an
addition and a deletion all move the digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Never part of a digest: regenerated caches are not corpus content.
IGNORED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ast-cache"})
IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})


def normalized_bytes(path: Path) -> bytes:
    """Return the file's bytes with CRLF collapsed to LF."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def file_sha256(path: Path) -> str:
    """Return the checkout-independent SHA-256 of one file."""
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def _digest_members(root: Path) -> list[str]:
    members = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if IGNORED_DIR_NAMES.intersection(relative.parts):
            continue
        members.append(relative.as_posix())
    return sorted(members)


def tree_sha256(root: Path) -> str:
    """Return one digest over every content file beneath ``root``.

    Each member contributes its relative POSIX path and its content digest, so
    renames are detected as well as edits. Sorting makes the result independent
    of filesystem enumeration order.
    """
    accumulator = hashlib.sha256()
    for relative in _digest_members(root):
        accumulator.update(relative.encode("utf-8"))
        accumulator.update(b"\x00")
        accumulator.update(file_sha256(root / relative).encode("ascii"))
        accumulator.update(b"\x00")
    return accumulator.hexdigest()


def corpus_digests(corpus_root: Path, corpus_path: Path) -> dict[str, object]:
    """Return the full digest set the manifest pins and preflight compares."""
    return {
        "corpus_sha256": file_sha256(corpus_path),
        "fixture_tree_sha256": tree_sha256(corpus_root / "fixtures"),
        "oracles": [
            {"oracle": f"oracles/{path.name}", "oracle_sha256": file_sha256(path)}
            for path in sorted((corpus_root / "oracles").glob("*.py"))
        ],
    }
