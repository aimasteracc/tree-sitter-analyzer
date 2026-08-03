"""Produce exact, model-free Gin index evidence for NO1-001B."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.adapters.codegraph import CodeGraphAdapter
from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import TSAAdapter
from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.schemas import IndexStatsV1

READINESS_ORACLE = "gin.Engine.ServeHTTP@gin.go"
INDEX_LAYOUT = {
    "tsa-warm": (".ast-cache", "index.db"),
    "codegraph-warm": (".codegraph", "codegraph.db"),
}


def canonical_semantic_digest(database: Path) -> str:
    """Hash every user table's schema and rows without creating sidecars."""

    payload = []
    uri = f"file:{database}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for table, sql in tables:
            columns = tuple(
                row[1]
                for row in connection.execute(
                    f'PRAGMA table_info("{str(table).replace(chr(34), chr(34) * 2)}")'
                ).fetchall()
            )
            quoted = str(table).replace('"', '""')
            rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()
            canonical_rows = sorted(
                json.dumps(
                    [_semantic_value(value) for value in row],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                for row in rows
            )
            payload.append((table, sql, columns, canonical_rows))
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _semantic_value(value: Any) -> tuple[str, Any]:
    if value is None:
        return ("null", None)
    if isinstance(value, bytes):
        return ("blob", value.hex())
    return (type(value).__name__, value)


_GENERATED_MARKER = "Code generated"
_GENERATED_SUFFIX = "DO NOT EDIT."


def index_content_hash(index_dir: Path) -> str:
    """Hash every relative path and byte in a closed, regular-file index tree."""

    digest = hashlib.sha256()
    files = sorted(path for path in index_dir.rglob("*") if path.is_file())
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Index content cannot contain symlinks: {path}")
        relative = path.relative_to(index_dir).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def tracked_paths(repo_path: Path) -> tuple[str, ...]:
    """Return the exact sorted inventory of every tracked repository path."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    return tuple(
        sorted(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)
    )


def tracked_go_paths(repo_path: Path) -> tuple[str, ...]:
    """Return the exact sorted tracked Go path inventory."""

    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.go"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    return tuple(
        sorted(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)
    )


def classify_go_paths(
    repo_path: Path, paths: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split tracked Go files into eligible and generated exclusions."""

    eligible: list[str] = []
    generated: list[str] = []
    for relative in paths:
        path = repo_path / relative
        prefix = path.read_text(encoding="utf-8", errors="replace")[:2048]
        target = (
            generated
            if _GENERATED_MARKER in prefix and _GENERATED_SUFFIX in prefix
            else eligible
        )
        target.append(relative)
    return tuple(eligible), tuple(generated)


def repository_fingerprint(repo_path: Path, tracked_paths: tuple[str, ...]) -> str:
    """Hash the pinned commit and every tracked file byte-for-byte."""

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if dirty:
        raise ValueError(f"Tracked benchmark checkout is dirty: {dirty.splitlines()}")
    files = [
        {"path": relative, "sha256": _sha256((repo_path / relative).read_bytes().hex())}
        for relative in tracked_paths
    ]
    return _sha256({"commit": commit, "files": files})


@contextmanager
def masked_paths(repo_path: Path, paths: tuple[str, ...]) -> Iterator[None]:
    """Temporarily remove pre-registered exclusions and always restore them."""

    with tempfile.TemporaryDirectory(
        prefix="no1-001b-excluded-", dir=repo_path.parent
    ) as directory:
        staging = Path(directory)
        moved: list[tuple[Path, Path]] = []
        try:
            for relative in paths:
                source = repo_path / relative
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
                moved.append((source, destination))
            yield
        finally:
            for source, destination in reversed(moved):
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(source)


def _tsa_indexed_paths(repo_path: Path) -> tuple[str, ...]:
    database = repo_path / ".ast-cache" / "index.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT file_path FROM ast_index ORDER BY file_path"
        ).fetchall()
    return tuple(str(row[0]).replace("\\", "/") for row in rows)


def _codegraph_indexed_paths(repo_path: Path) -> tuple[str, ...]:
    database = repo_path / ".codegraph" / "codegraph.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT DISTINCT file_path FROM nodes "
            "WHERE file_path IS NOT NULL AND file_path <> '' ORDER BY file_path"
        ).fetchall()
    return tuple(str(row[0]).replace("\\", "/") for row in rows)


def _tsa_readiness(repo_path: Path) -> bool:
    database = repo_path / ".ast-cache" / "index.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = 'gin.go'"
        ).fetchone()
    return bool(row and "ServeHTTP" in str(row[0]))


def _codegraph_readiness(repo_path: Path) -> bool:
    database = repo_path / ".codegraph" / "codegraph.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(nodes)").fetchall()
        }
        if not {"name", "file_path"} <= columns:
            raise ValueError("CodeGraph nodes schema lacks readiness columns")
        row = connection.execute(
            "SELECT 1 FROM nodes WHERE file_path = ? AND name LIKE ? LIMIT 1",
            ("gin.go", "%ServeHTTP%"),
        ).fetchone()
    return row is not None


def inspect_frozen_index(arm: str, index_root: Path) -> tuple[str, ...]:
    """Validate one fixed arm snapshot without creating SQLite sidecars."""

    if arm not in INDEX_LAYOUT:
        raise ValueError(f"Unsupported indexed Smoke arm: {arm}")
    _, database_name = INDEX_LAYOUT[arm]
    database = index_root / database_name
    regular_files = tuple(
        sorted(
            path.relative_to(index_root)
            for path in index_root.rglob("*")
            if path.is_file()
        )
    )
    candidates = tuple(
        path.as_posix()
        for path in regular_files
        if path.suffix in {".db", ".sqlite", ".sqlite3"}
    )
    if candidates != (database_name,):
        raise ValueError(f"{arm} must contain exactly one primary database")
    sidecars = tuple(
        path.as_posix()
        for path in regular_files
        if path.name.endswith(("-wal", "-shm", "-journal"))
    )
    if sidecars:
        raise ValueError(f"Frozen index contains SQLite sidecars: {sidecars}")
    uri = f"file:{database}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError(f"{arm} frozen database failed integrity_check")
        if arm == "tsa-warm":
            rows = connection.execute(
                "SELECT file_path FROM ast_index ORDER BY file_path"
            ).fetchall()
            ready = connection.execute(
                "SELECT symbols_json FROM ast_index WHERE file_path = 'gin.go'"
            ).fetchone()
            if not ready or "ServeHTTP" not in str(ready[0]):
                raise ValueError(f"{arm} failed readiness oracle {READINESS_ORACLE}")
        else:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(nodes)").fetchall()
            }
            if not {"name", "file_path"} <= columns:
                raise ValueError("CodeGraph nodes schema lacks readiness columns")
            rows = connection.execute(
                "SELECT DISTINCT file_path FROM nodes "
                "WHERE file_path IS NOT NULL AND file_path <> '' ORDER BY file_path"
            ).fetchall()
            ready = connection.execute(
                "SELECT 1 FROM nodes WHERE file_path = ? AND name LIKE ? LIMIT 1",
                ("gin.go", "%ServeHTTP%"),
            ).fetchone()
            if ready is None:
                raise ValueError(f"{arm} failed readiness oracle {READINESS_ORACLE}")
    return tuple(str(row[0]).replace("\\", "/") for row in rows)


def _dir_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _build_stats(
    *,
    repo_path: Path,
    arm: str,
    eligible_paths: tuple[str, ...],
    generated_paths: tuple[str, ...],
    repo_fingerprint: str,
    tool_fingerprint: str,
) -> IndexStatsV1:
    adapter: Any
    index_dir: Path
    indexed_loader: Any
    readiness: Any
    if arm == "tsa-warm":
        adapter = TSAAdapter(arm)
        index_dir = repo_path / ".ast-cache"
        indexed_loader = _tsa_indexed_paths
        readiness = _tsa_readiness
    elif arm == "codegraph-warm":
        adapter = CodeGraphAdapter(arm)
        index_dir = repo_path / ".codegraph"
        indexed_loader = _codegraph_indexed_paths
        readiness = _codegraph_readiness
    else:
        raise ValueError(f"Unsupported indexed Smoke arm: {arm}")

    with masked_paths(repo_path, generated_paths):
        legacy = adapter.prepare_index(repo_path, cold=True)
    indexed_paths = indexed_loader(repo_path)
    if indexed_paths != eligible_paths:
        missing = tuple(sorted(set(eligible_paths) - set(indexed_paths)))
        unexpected = tuple(sorted(set(indexed_paths) - set(eligible_paths)))
        raise ValueError(
            f"{arm} index partition mismatch; missing={missing}, unexpected={unexpected}"
        )
    if not readiness(repo_path):
        raise ValueError(f"{arm} failed readiness oracle {READINESS_ORACLE}")
    empty: tuple[str, ...] = ()
    return IndexStatsV1(
        eligible_source_files=len(eligible_paths),
        indexed_source_files=len(indexed_paths),
        excluded_source_files=0,
        parse_error_files=0,
        eligible_paths_hash=_sha256(list(eligible_paths)),
        indexed_paths_hash=_sha256(list(indexed_paths)),
        excluded_paths_hash=_sha256(list(empty)),
        parse_error_paths_hash=_sha256(list(empty)),
        indexed_paths=indexed_paths,
        excluded_paths=empty,
        parse_error_paths=empty,
        build_seconds=legacy.build_seconds,
        index_size_bytes=_dir_size(index_dir),
        repo_fingerprint=repo_fingerprint,
        tool_fingerprint=tool_fingerprint,
        readiness_oracles=(READINESS_ORACLE,),
    )


def produce_gin_index_evidence(
    *,
    tsa_repo: Path,
    codegraph_repo: Path,
    output_path: Path,
    eligibility_path: Path,
    tool_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Build both indexes and exclusively persist strict V1 evidence."""

    inventories = {
        str(repo): tracked_go_paths(repo) for repo in (tsa_repo, codegraph_repo)
    }
    if len(set(inventories.values())) != 1:
        raise ValueError("Indexed-arm tracked path inventories differ")
    tracked = next(iter(inventories.values()))
    tsa_eligible, tsa_generated = classify_go_paths(tsa_repo, tracked)
    cg_eligible, cg_generated = classify_go_paths(codegraph_repo, tracked)
    if (tsa_eligible, tsa_generated) != (cg_eligible, cg_generated):
        raise ValueError("Indexed-arm eligibility classifications differ")
    full_inventories = {
        str(repo): tracked_paths(repo) for repo in (tsa_repo, codegraph_repo)
    }
    if len(set(full_inventories.values())) != 1:
        raise ValueError("Indexed-arm full tracked inventories differ")
    full_tracked = next(iter(full_inventories.values()))
    fingerprints = {
        str(repo): repository_fingerprint(repo, full_tracked)
        for repo in (tsa_repo, codegraph_repo)
    }
    if len(set(fingerprints.values())) != 1:
        raise ValueError("Indexed-arm repository fingerprints differ")
    repo_fingerprint = next(iter(fingerprints.values()))

    cells = []
    for arm, repo in (("tsa-warm", tsa_repo), ("codegraph-warm", codegraph_repo)):
        stats = _build_stats(
            repo_path=repo,
            arm=arm,
            eligible_paths=tsa_eligible,
            generated_paths=tsa_generated,
            repo_fingerprint=repo_fingerprint,
            tool_fingerprint=tool_fingerprints[arm],
        )
        cells.append({"repo_id": "gin", "arm_id": arm, "index_stats": asdict(stats)})
    evidence = {"schema_version": 1, "cells": cells}
    with output_path.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2, sort_keys=True)
        stream.write("\n")
    eligibility = {
        "schema_version": 1,
        "repo_id": "gin",
        "tracked_go_paths": list(tracked),
        "tracked_paths_hash": _sha256(list(full_tracked)),
        "eligible_paths": list(tsa_eligible),
        "generated_exclusions": list(tsa_generated),
        "eligible_paths_hash": _sha256(list(tsa_eligible)),
        "repo_fingerprint": repo_fingerprint,
    }
    with eligibility_path.open("x", encoding="utf-8") as stream:
        json.dump(eligibility, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return eligibility
