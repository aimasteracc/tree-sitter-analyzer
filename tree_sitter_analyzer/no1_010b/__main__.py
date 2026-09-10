"""NO1-010B benchmark entry point (internal experiment only).

Not registered as an MCP facade, CLI command, or codemap surface — a benchmark
harness is measurement infrastructure, not a product surface, so RFC-0022's
public-surface menu gate and the codemap-sync gate both keep it out. The shape
mirrors ``tree_sitter_analyzer/task_harness.py``: a ``python -m`` module entry
with no packaging console script.

Usage::

    uv run python -m tree_sitter_analyzer.no1_010b \\
        --corpus benchmarks/no1_010b/corpus.jsonl \\
        --report benchmarks/no1_010b/report.json

    # after a deliberate corpus/fixture/oracle change:
    uv run python -m tree_sitter_analyzer.no1_010b \\
        --corpus benchmarks/no1_010b/corpus.jsonl --update-manifest

The entry point runs RFC-0026 §4 corpus preflight — including §3's oracle
red-baseline execution on the unmodified fixtures — and emits the B2 report
shape. It never calls a model and never applies a patch: patch application and
the sandboxed verification/stale-row checks are RFC-0026 B1 scope and do not
exist yet, so preflight rejects the run with zero attempts consumed.

Provenance records the analyzer commit **and its working-tree state**. A digest
attested against a commit that does not contain the corpus, or against a dirty
tree, is not provenance; ``tree_state`` makes that visible instead of implied.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess  # nosec B404 - list-form git queries for report provenance
import sys
from pathlib import Path
from typing import Any

from .. import __version__
from .digest import corpus_digests, file_sha256
from .preflight import MANIFEST_NAME, run_preflight
from .record import BenchmarkRecordError
from .record_loader import load_corpus_records
from .report import build_report

_GIT_TIMEOUT_S = 30


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(  # nosec B603 B607
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _analyzer_identity(repo_root: Path, corpus_path: Path) -> dict[str, Any]:
    """Return the analyzer commit plus the facts that make it verifiable."""
    head = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain")
    try:
        relative = corpus_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = corpus_path.as_posix()
    commit = head.strip() if head else "unavailable"
    contains = (
        _git(repo_root, "cat-file", "-e", f"{commit}:{relative}") is not None
        if head
        else False
    )
    return {
        "commit": commit,
        "version": __version__,
        "tree_state": "unknown"
        if status is None
        else ("clean" if not status.strip() else "dirty"),
        "corpus_present_at_commit": contains,
        "reproducible_at_commit": bool(head)
        and contains
        and status is not None
        and not status.strip(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tree_sitter_analyzer.no1_010b",
        description=(
            "NO1-010B change-outcome benchmark runner (internal; RFC-0026). "
            "Runs corpus preflight and emits the B2 report shape."
        ),
    )
    parser.add_argument(
        "--corpus",
        required=True,
        help="Path to the pre-registered corpus JSONL ('-' reads stdin).",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional path to write the report JSON to (stdout always carries it).",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help=(
            "Rewrite the corpus manifest digests after a deliberate corpus "
            "change, then exit. The manifest is an in-repository drift "
            "detector, NOT the C14/C27 external registration anchor."
        ),
    )
    return parser


def _write_manifest(corpus_root: Path, corpus_path: Path) -> Path:
    manifest_path = corpus_root / MANIFEST_NAME
    payload = {
        "schema": "no1-010b/manifest/1",
        "note": (
            "In-repository drift detector for the NO1-010B corpus: preflight "
            "recomputes these digests and fails on mismatch. It is NOT the "
            "C14/C27 external registration anchor - a git-committed file cannot "
            "establish pre-execution ordering. Digests normalise CRLF to LF so "
            "they never depend on checkout configuration."
        ),
        **corpus_digests(corpus_root, corpus_path),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        records = load_corpus_records(args.corpus)
    except (BenchmarkRecordError, OSError) as exc:
        print(f"corpus preflight failed: {exc}", file=sys.stderr)
        return 2

    corpus_path = Path(args.corpus)
    corpus_root = corpus_path.parent if args.corpus != "-" else Path()
    repo_root = Path(__file__).resolve().parents[2]

    if args.update_manifest:
        if args.corpus == "-":
            print(
                "--update-manifest requires a corpus file, not stdin", file=sys.stderr
            )
            return 2
        written = _write_manifest(corpus_root, corpus_path)
        print(f"wrote {written.as_posix()}", file=sys.stderr)
        return 0

    provenance = {
        "analyzer": _analyzer_identity(repo_root, corpus_path),
        "corpus_path": corpus_path.as_posix(),
        "corpus_sha256": file_sha256(corpus_path) if args.corpus != "-" else "stdin",
        "fixture_tree_sha256": corpus_digests(corpus_root, corpus_path)[
            "fixture_tree_sha256"
        ],
        "oracle_digests": corpus_digests(corpus_root, corpus_path)["oracles"],
        "digest_normalization": "CRLF collapsed to LF before hashing",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "model_calls": 0,
        "model_spend": "none - model-free run, no LLM was invoked",
        "registration_registry": None,
    }

    report = build_report(
        records=records,
        preflight=run_preflight(
            records,
            corpus_root,
            corpus_path=corpus_path if args.corpus != "-" else None,
        ),
        provenance=provenance,
    )
    rendered = json.dumps(report, indent=2, sort_keys=False) + "\n"
    if args.report:
        Path(args.report).write_text(rendered, encoding="utf-8", newline="\n")
    sys.stdout.write(rendered)
    return 0 if report["run_status"] == "COMPLETED" else 1


if __name__ == "__main__":  # pragma: no cover - module entry
    raise SystemExit(main())
