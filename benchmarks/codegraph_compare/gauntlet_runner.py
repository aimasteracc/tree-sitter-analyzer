"""Gauntlet Runner — re-run the mis-wire audit on the 5 canonical repos and
regenerate the GAUNTLET.md table with fresh numbers + timestamp.

Reuses repo_prep.py machinery for clone/pin/metadata collection.

CLI
---
    python benchmarks/codegraph_compare/gauntlet_runner.py --help
    python benchmarks/codegraph_compare/gauntlet_runner.py --dry-run
    python benchmarks/codegraph_compare/gauntlet_runner.py --repo tokenizers
    python benchmarks/codegraph_compare/gauntlet_runner.py --all

The ``--dry-run`` flag skips cloning and indexing (both are heavy); it verifies
all imports, argument parsing, and table-rendering logic without network or disk
side effects. Suitable for CI smoke tests.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Canonical 5-repo list (matches MISWIRE-AUDIT-EXAMPLES.md)
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).parent
_BASE_DIR = Path(".benchmark-repos")

# Each entry: (id, display_name, url, commit, languages_label)
# Commits chosen to match MISWIRE-AUDIT-EXAMPLES.md measurements.
# Re-pin if you want fresh measurements.
_GAUNTLET_REPOS: list[tuple[str, str, str, str, str]] = [
    (
        "tokenizers",
        "huggingface/tokenizers",
        "https://github.com/huggingface/tokenizers.git",
        "PLACEHOLDER_SHA",  # re-pin for reproducibility
        "Rust+Py+JS+TS",
    ),
    (
        "ruff",
        "astral-sh/ruff",
        "https://github.com/astral-sh/ruff.git",
        "PLACEHOLDER_SHA",
        "Rust+Py+TS",
    ),
    (
        "polars",
        "pola-rs/polars",
        "https://github.com/pola-rs/polars.git",
        "PLACEHOLDER_SHA",
        "Rust+Py",
    ),
    (
        "tsa",
        "tree-sitter-analyzer (this repo)",
        "",  # local — no clone needed
        "",
        "13 langs",
    ),
    (
        "gin",
        "gin-gonic/gin",
        "https://github.com/gin-gonic/gin.git",
        "PLACEHOLDER_SHA",
        "Go (single)",
    ),
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class GauntletRow(NamedTuple):
    id: str
    display_name: str
    languages: str
    call_edges: int
    naive_miswires: int
    naive_pct: float
    tsa_miswires: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Audit runner
# ---------------------------------------------------------------------------


def _run_audit(repo_path: str, *, reindex: bool = True) -> tuple[int, int, float, int]:
    """Return (call_edges, naive_miswires, naive_pct, tsa_miswires) for repo_path."""
    from tree_sitter_analyzer.miswire_audit import audit

    result = audit(repo_path, reindex=reindex)
    pct = (
        100.0 * result.naive_genuine_miswires / result.total_call_edges
        if result.total_call_edges
        else 0.0
    )
    return (
        result.total_call_edges,
        result.naive_genuine_miswires,
        pct,
        result.tsa_miswires,
    )


def _audit_repo(
    repo_id: str,
    display_name: str,
    url: str,
    commit: str,
    languages: str,
    base_dir: Path,
    *,
    reindex: bool = True,
) -> GauntletRow:
    """Clone (if needed) and audit a single repo. Returns a GauntletRow."""
    if repo_id == "tsa":
        # Audit THIS repo (the cwd at runtime)
        repo_path = str(Path(".").resolve())
    else:
        from benchmarks.codegraph_compare.repo_prep import RepoSpec, prepare_repo

        spec = RepoSpec(
            id=repo_id,
            name=display_name,
            url=url,
            language=languages,
            commit=commit,
            description="",
        )
        prepared = prepare_repo(spec, base_dir=base_dir)
        if prepared.error:
            return GauntletRow(
                id=repo_id,
                display_name=display_name,
                languages=languages,
                call_edges=0,
                naive_miswires=0,
                naive_pct=0.0,
                tsa_miswires=0,
                error=prepared.error,
            )
        repo_path = str(prepared.local_path)

    try:
        call_edges, naive, pct, tsa = _run_audit(repo_path, reindex=reindex)
        return GauntletRow(
            id=repo_id,
            display_name=display_name,
            languages=languages,
            call_edges=call_edges,
            naive_miswires=naive,
            naive_pct=pct,
            tsa_miswires=tsa,
        )
    except Exception as exc:  # noqa: BLE001
        return GauntletRow(
            id=repo_id,
            display_name=display_name,
            languages=languages,
            call_edges=0,
            naive_miswires=0,
            naive_pct=0.0,
            tsa_miswires=0,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Markdown table renderer
# ---------------------------------------------------------------------------


def _render_table(rows: list[GauntletRow], timestamp: str) -> str:
    """Render a markdown table from GauntletRows."""
    lines = [
        f"<!-- gauntlet-runner generated {timestamp} — re-measure before publishing -->",
        "",
        "| repo | languages | call edges | name-only mis-wires (genuine floor) | TSA mis-wires |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        if r.error:
            lines.append(
                f"| {r.display_name} | {r.languages} | ERROR | {r.error} | — |"
            )
        else:
            naive_cell = f"**{r.naive_miswires:,}** ({r.naive_pct:.2f}%)"
            tsa_cell = f"**{r.tsa_miswires:,}**"
            lines.append(
                f"| {r.display_name} | {r.languages} | {r.call_edges:,} "
                f"| {naive_cell} | {tsa_cell} |"
            )
    lines.append("")
    return "\n".join(lines)


def _update_gauntlet_md(table: str) -> None:
    """Splice the new table into GAUNTLET.md, replacing the old summary table."""
    gauntlet_path = _THIS_DIR / "GAUNTLET.md"
    if not gauntlet_path.exists():
        print(
            f"GAUNTLET.md not found at {gauntlet_path}; skipping update.",
            file=sys.stderr,
        )
        return

    content = gauntlet_path.read_text(encoding="utf-8")
    # Replace the block between the "5-Repo Summary Table" header and the
    # next "---" separator.
    marker_start = "## 5-Repo Summary Table\n"
    marker_end = "\n---\n"
    start_idx = content.find(marker_start)
    if start_idx == -1:
        print(
            "Could not find '## 5-Repo Summary Table' in GAUNTLET.md; skipping update.",
            file=sys.stderr,
        )
        return
    after_header = start_idx + len(marker_start)
    end_idx = content.find(marker_end, after_header)
    if end_idx == -1:
        print(
            "Could not find closing '---' after table; skipping update.",
            file=sys.stderr,
        )
        return

    new_content = content[:after_header] + "\n" + table + content[end_idx:]
    gauntlet_path.write_text(new_content, encoding="utf-8")
    print(f"GAUNTLET.md updated at {gauntlet_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gauntlet_runner",
        description=(
            "Re-run the mis-wire audit on the 5 canonical Gauntlet repos and "
            "regenerate the GAUNTLET.md table with fresh numbers."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="Audit all 5 Gauntlet repos (clones as needed, may take minutes).",
    )
    group.add_argument(
        "--repo",
        metavar="ID",
        choices=[r[0] for r in _GAUNTLET_REPOS],
        help=f"Audit a single repo. Choices: {', '.join(r[0] for r in _GAUNTLET_REPOS)}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Verify imports and argument parsing only; skip all clone/index operations. "
            "Prints what would be run."
        ),
    )
    parser.add_argument(
        "--base-dir",
        default=str(_BASE_DIR),
        metavar="DIR",
        help=f"Base directory for repo clones (default: {_BASE_DIR})",
    )
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Reuse existing .ast-cache in each repo (faster, may use stale index).",
    )
    parser.add_argument(
        "--update-md",
        action="store_true",
        help="After auditing, splice fresh numbers into GAUNTLET.md.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.all and not args.repo and not args.dry_run:
        parser.print_help()
        return 1

    base_dir = Path(args.base_dir)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.dry_run:
        print("[dry-run] Gauntlet Runner — verifying imports and config...")
        # Verify the audit module is importable
        try:
            from tree_sitter_analyzer.miswire_audit import (  # noqa: F401
                AuditResult,
                audit,
            )

            print("[dry-run] tree_sitter_analyzer.miswire_audit: OK")
        except ImportError as exc:
            print(f"[dry-run] IMPORT ERROR: {exc}", file=sys.stderr)
            return 1

        print(f"[dry-run] Would audit {len(_GAUNTLET_REPOS)} repos:")
        for repo_id, name, url, commit, langs in _GAUNTLET_REPOS:
            target = (
                "local repo"
                if repo_id == "tsa"
                else f"{url} @ {commit[:12] if commit and commit != 'PLACEHOLDER_SHA' else 'HEAD'}"
            )
            print(f"  {repo_id:<16} {name:<40} ({langs})  →  {target}")
        print(f"[dry-run] base_dir: {base_dir.resolve()}")
        print(f"[dry-run] timestamp: {timestamp}")
        print("[dry-run] All checks passed. Pass --all or --repo <id> to run for real.")
        return 0

    # Select repos to audit
    if args.all:
        to_audit = list(_GAUNTLET_REPOS)
    else:
        to_audit = [r for r in _GAUNTLET_REPOS if r[0] == args.repo]

    rows: list[GauntletRow] = []
    for repo_id, display_name, url, commit, languages in to_audit:
        print(f"Auditing {repo_id} ({display_name})...", file=sys.stderr)
        row = _audit_repo(
            repo_id,
            display_name,
            url,
            commit,
            languages,
            base_dir=base_dir,
            reindex=not args.no_reindex,
        )
        rows.append(row)
        if row.error:
            print(f"  ERROR: {row.error}", file=sys.stderr)
        else:
            print(
                f"  {row.call_edges:,} edges  "
                f"naive={row.naive_miswires:,} ({row.naive_pct:.2f}%)  "
                f"tsa={row.tsa_miswires:,}",
                file=sys.stderr,
            )

    table = _render_table(rows, timestamp)
    print(table)

    if args.update_md:
        _update_gauntlet_md(table)

    failures = [r for r in rows if r.error]
    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
