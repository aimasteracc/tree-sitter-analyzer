"""NO1-010B benchmark entry point (internal experiment only).

Not registered as an MCP facade, CLI command, or codemap surface — a benchmark
harness is measurement infrastructure, not a product surface, so RFC-0022's
public-surface menu gate and the codemap-sync gate both keep it out. The shape
mirrors ``tree_sitter_analyzer/task_harness.py``: a ``python -m`` module entry
with no packaging console script.

Usage::

    python -m tree_sitter_analyzer.no1_010b \\
        --corpus benchmarks/no1_010b/corpus.jsonl \\
        --report benchmarks/no1_010b/report.json

The entry point runs RFC-0026 §4 corpus preflight and emits the B2 report
shape. It never calls a model, never applies a patch, and never executes
candidate code: patch application and the sandboxed oracle/verification/
stale-row checks are RFC-0026 B1 scope and do not exist yet, so preflight
rejects the run with zero attempts consumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess  # nosec B404 - list-form `git rev-parse` for report provenance
import sys
from pathlib import Path

from .. import __version__
from .preflight import run_preflight
from .record import BenchmarkRecordError
from .record_loader import load_corpus_records
from .report import build_report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analyzer_commit(repo_root: Path) -> str:
    try:
        completed = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


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
    return parser


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

    # Digest keys are shaped ``"commit"`` / ``*_sha256`` so they match the
    # repository's existing detect-secrets line exemptions instead of forcing
    # the secret filter to be widened for a report file.
    provenance = {
        "analyzer": {
            "commit": _analyzer_commit(repo_root),
            "version": __version__,
        },
        "corpus_path": corpus_path.as_posix(),
        "corpus_sha256": _sha256(corpus_path) if args.corpus != "-" else "stdin",
        "oracle_digests": [
            {
                "oracle": item.oracle,
                "oracle_sha256": _sha256(corpus_root / item.oracle),
            }
            for item in records
            if (corpus_root / item.oracle).is_file()
        ],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "model_calls": 0,
        "model_spend": "none - model-free run, no LLM was invoked",
        "registration_registry": None,
    }

    report = build_report(
        records=records,
        preflight=run_preflight(records, corpus_root),
        provenance=provenance,
    )
    rendered = json.dumps(report, indent=2, sort_keys=False) + "\n"
    if args.report:
        Path(args.report).write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["run_status"] == "COMPLETED" else 1


if __name__ == "__main__":  # pragma: no cover - module entry
    raise SystemExit(main())
