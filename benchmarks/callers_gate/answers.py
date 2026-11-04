"""Answer sets on disk: ``baseline/`` (base side) and ``results/`` (head side).

One file per ``(tree, index key, repo)``. A file is used only when every field
that identifies it matches the request and its rows hash to the recorded
digest. Anything else -- unreadable JSON, a wrong tree, key, repo, query key or
row digest -- is *corrupt*: it is moved aside to ``*.corrupt`` and treated as a
miss, so the side is recomputed. A corrupt file can never supply answers.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layout import GATE_FORMAT, Layout

KIND = "callers-gate-answers"
#: Row fields that are measurements, not answers (excluded from the digest and the diff).
VOLATILE = ("seconds", "bytes", "compact_bytes")


@dataclass(frozen=True)
class AnswerKey:
    tree: str
    index_key: str
    repo: str
    repo_sha: str
    query_key: str


def rows_digest(rows: list[dict[str, Any]]) -> str:
    stable = [{k: v for k, v in row.items() if k not in VOLATILE} for row in rows]
    data = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def write_answers(
    path: Path, key: AnswerKey, rows: list[dict[str, Any]], source: str
) -> None:
    payload = {
        "format": GATE_FORMAT,
        "kind": KIND,
        "tree": key.tree,
        "index_key": key.index_key,
        "repo": key.repo,
        "repo_sha": key.repo_sha,
        "query_key": key.query_key,
        "source": source,
        "created": time.time(),
        "n": len(rows),
        "rows_sha256": rows_digest(rows),
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class CorruptAnswers(ValueError):
    pass


def validate(payload: Any, key: AnswerKey) -> list[dict[str, Any]]:
    """Rows of ``payload`` if it is exactly the answer set ``key`` names; raises otherwise."""
    if not isinstance(payload, dict):
        raise CorruptAnswers("not an object")
    expected = {
        "format": GATE_FORMAT,
        "kind": KIND,
        "tree": key.tree,
        "index_key": key.index_key,
        "repo": key.repo,
        "repo_sha": key.repo_sha,
        "query_key": key.query_key,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise CorruptAnswers(f"{field}={payload.get(field)!r}, expected {value!r}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or payload.get("n") != len(rows):
        raise CorruptAnswers("row list missing or count mismatch")
    if rows_digest(rows) != payload.get("rows_sha256"):
        raise CorruptAnswers("row digest mismatch")
    return rows


def read_answers(
    path: Path, key: AnswerKey, log: Any = print
) -> list[dict[str, Any]] | None:
    """Validated rows, or None on a miss. A corrupt file is quarantined, never used."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate(payload, key)
    except (OSError, ValueError) as exc:
        quarantine = path.with_name(path.name + f".{int(time.time())}.corrupt")
        with contextlib.suppress(OSError):
            os.replace(path, quarantine)
        log(
            f"[{key.repo}] answer cache {path} is corrupt ({exc}); moved to {quarantine.name}, recomputing"
        )
        return None


def pick_run(
    paths: list[Path], key: AnswerKey, run_id: str | None, log: Any = print
) -> list[dict[str, Any]] | None:
    """The validated rows of one run's head answers, chosen explicitly.

    With ``run_id`` only that run counts. Without it, the candidates must all
    validate and hold identical rows (then which run does not matter);
    otherwise nothing is picked and the caller recomputes. Candidates are read
    without quarantine: a run's results are its record, never moved.
    """
    chosen = [p for p in paths if run_id is None or p.parent.name == run_id]
    rows_seen: list[list[dict[str, Any]]] = []
    for path in chosen:
        try:
            rows_seen.append(
                validate(json.loads(path.read_text(encoding="utf-8")), key)
            )
        except (OSError, ValueError) as exc:
            log(f"[{key.repo}] results {path} unusable ({exc})")
            return None
    if not rows_seen:
        return None
    digests = {rows_digest(rows) for rows in rows_seen}
    if len(digests) != 1:
        log(
            f"[{key.repo}] {len(chosen)} runs of tree {key.tree[:12]} disagree; "
            "pass --run to promote one explicitly"
        )
        return None
    return rows_seen[-1]


def promote(
    layout: Layout, tree: str, log: Any = print, run_id: str | None = None
) -> list[Path]:
    """Copy validated ``results/<tree>/<key>/<run>/<repo>.json`` into ``baseline/<tree>/<key>/``.

    One run is picked per (index key, repo) by :func:`pick_run`: ``run_id``
    when given, else only when every run of that tree agrees.
    """
    source = layout.results_dir(tree)
    copied: list[Path] = []
    if not source.is_dir():
        return copied
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in sorted(source.glob("*/*/*.json")):
        groups.setdefault((path.parent.parent.name, path.stem), []).append(path)
    for (index_key, repo), paths in sorted(groups.items()):
        try:
            payload = json.loads(paths[-1].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log(f"[promote] skip {paths[-1]}: {exc}")
            continue
        key = AnswerKey(
            tree,
            index_key,
            repo,
            payload.get("repo_sha", ""),
            payload.get("query_key", ""),
        )
        rows = pick_run(paths, key, run_id, log)
        if rows is None:
            log(f"[promote] skip {repo} {index_key}: no single validated run")
            continue
        dest = layout.baseline(tree, index_key, repo)
        write_answers(dest, key, rows, f"promoted:{run_id or 'agreeing runs'}")
        copied.append(dest)
    return copied
