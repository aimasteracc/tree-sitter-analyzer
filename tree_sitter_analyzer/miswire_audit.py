#!/usr/bin/env python3
"""Mis-Wire Audit — run TSA's cross-language correctness check on ANY repo.

The point: a name-only code-intelligence index (the common design — CodeGraph
included) binds a call to *any* definition that shares the callee's name, even
when that definition is in a different language. So a Python ``sorted()`` call
gets wired to a Swift ``func sorted`` if Swift is the only ``sorted`` definition
in the tree. TSA gates every binding by language family, so it does not.

This audit makes that difference legible on YOUR OWN code, in one command, with
**no CodeGraph install required**: it models what a name-only resolver *would*
do from TSA's own index (the same-name heuristic, validated in
``benchmarks/codegraph_compare/REPORT-v1.21.0.md``), and contrasts it with what
TSA actually resolves.

    uv run python -m scripts.miswire_audit .            # audit the current repo
    uv run python -m scripts.miswire_audit /path/to/repo --card

Output: total call edges, how many a name-only resolver WOULD mis-wire across a
language boundary, how many TSA mis-wires, the multiplier, and the top offending
edges (file:line, caller-lang → callee-lang).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer._language_family import languages_compatible
from tree_sitter_analyzer.ast_cache import ASTCache

_DEF_KINDS = ("function", "method", "class")


@dataclass
class Offender:
    callee_name: str
    caller_file: str
    caller_lang: str
    callee_file: str
    callee_lang: str
    line: int


@dataclass
class AuditResult:
    project_root: str
    total_call_edges: int = 0
    resolvable_edges: int = 0
    naive_miswires: int = 0
    tsa_miswires: int = 0
    naive_offenders: list[Offender] = field(default_factory=list)
    tsa_offenders: list[Offender] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)

    @property
    def multiplier(self) -> float:
        """How many times cleaner TSA is (naive / TSA), guarded for 0."""
        if self.tsa_miswires == 0:
            return float(self.naive_miswires) if self.naive_miswires else 1.0
        return self.naive_miswires / self.tsa_miswires


def _name_to_langs(conn: Any) -> dict[str, set[str]]:
    """Map each defined symbol name -> the set of languages that define it."""
    out: dict[str, set[str]] = defaultdict(set)
    placeholders = ",".join("?" for _ in _DEF_KINDS)
    rows = conn.execute(
        f"SELECT name, language FROM ast_symbol_rows WHERE kind IN ({placeholders})",
        _DEF_KINDS,
    ).fetchall()
    for r in rows:
        out[r["name"]].add(r["language"])
    return out


def _name_to_file_lang(conn: Any) -> dict[str, list[tuple[str, str]]]:
    """Map each defined name -> [(file, language), ...] for offender examples."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    placeholders = ",".join("?" for _ in _DEF_KINDS)
    rows = conn.execute(
        f"SELECT name, file_path, language FROM ast_symbol_rows "
        f"WHERE kind IN ({placeholders})",
        _DEF_KINDS,
    ).fetchall()
    for r in rows:
        out[r["name"]].append((r["file_path"], r["language"]))
    return out


def audit(project_root: str, *, reindex: bool = True, top: int = 5) -> AuditResult:
    """Run the mis-wire audit against ``project_root`` using TSA's index."""
    cache = ASTCache(project_root)
    if reindex:
        cache.index_project()
    conn = cache.get_conn()
    try:
        result = AuditResult(project_root=project_root)
        result.languages = {
            r["language"]: r["n"]
            for r in conn.execute(
                "SELECT language, COUNT(*) n FROM ast_index GROUP BY language"
            ).fetchall()
        }
        file_lang = {
            r["file_path"]: r["language"]
            for r in conn.execute(
                "SELECT file_path, language FROM ast_index"
            ).fetchall()
        }
        name_langs = _name_to_langs(conn)
        name_files = _name_to_file_lang(conn)

        edges = conn.execute(
            "SELECT callee_name, language AS caller_lang, callee_resolved_file, "
            "file_path AS caller_file, callee_line "
            "FROM edges WHERE kind='calls' AND callee_name != ''"
        ).fetchall()

        for e in edges:
            result.total_call_edges += 1
            caller_lang = e["caller_lang"]
            name = e["callee_name"]

            # --- TSA's actual resolution: cross-language only if it bound a file
            #     in an incompatible language (the real, measured mis-wire). ---
            resolved = e["callee_resolved_file"]
            if resolved:
                result.resolvable_edges += 1
                rlang = file_lang.get(resolved)
                if rlang and not languages_compatible(caller_lang, rlang):
                    result.tsa_miswires += 1
                    if len(result.tsa_offenders) < top:
                        result.tsa_offenders.append(
                            Offender(name, e["caller_file"], caller_lang,
                                     resolved, rlang, e["callee_line"] or 0)
                        )

            # --- Naive name-only model (what CodeGraph-style indexes do): a call
            #     binds to a same-name definition regardless of language. It
            #     mis-wires when a same-name def exists but NONE is in a
            #     compatible language — so the only binding choice crosses the
            #     boundary (exactly the live-measured Python sorted()->Swift case).
            defs = name_langs.get(name)
            if defs:
                has_compatible = any(
                    languages_compatible(caller_lang, dl) for dl in defs
                )
                if not has_compatible:
                    result.naive_miswires += 1
                    # show DISTINCT callee names (not 5× the same one) so the
                    # breadth of collisions is visible.
                    seen_names = {o.callee_name for o in result.naive_offenders}
                    if len(result.naive_offenders) < top and name not in seen_names:
                        for df, dl in name_files.get(name, []):
                            if not languages_compatible(caller_lang, dl):
                                result.naive_offenders.append(
                                    Offender(name, e["caller_file"], caller_lang,
                                             df, dl, e["callee_line"] or 0)
                                )
                                break
        return result
    finally:
        cache.close()


def _fmt_pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.2f}%" if total else "0.00%"


def render_terminal(r: AuditResult) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("  ── TSA Mis-Wire Audit " + "─" * 38)
    langs = ", ".join(f"{k}:{v}" for k, v in sorted(r.languages.items()))
    lines.append(f"  repo: {r.project_root}")
    lines.append(f"  languages indexed: {langs}")
    lines.append(f"  call edges analysed: {r.total_call_edges:,}")
    lines.append("")
    lines.append(
        f"  ❌ a NAME-ONLY resolver would mis-wire up to "
        f"{r.naive_miswires:,} call edges across a language boundary "
        f"({_fmt_pct(r.naive_miswires, r.total_call_edges)}) — binding a call to a "
        f"same-named definition in another language"
    )
    lines.append(
        f"  ✅ Tree-sitter Analyzer mis-wires {r.tsa_miswires:,} "
        f"({_fmt_pct(r.tsa_miswires, r.total_call_edges)})"
    )
    if r.naive_miswires and r.tsa_miswires < r.naive_miswires:
        lines.append("")
        lines.append(f"     → TSA is {r.multiplier:.0f}× cleaner on YOUR code.")
    lines.append("")
    lines.append(
        "  (the name-only figure is the worst case for a name-only index — the "
        "design CodeGraph and most indexes use. A live head-to-head vs CodeGraph "
        "specifically — 745 vs 6 on TSA's repo — is in"
    )
    lines.append("   benchmarks/codegraph_compare/REPORT-v1.21.0.md.)")
    lines.append("")
    if r.naive_offenders:
        lines.append("  cross-language mis-wires a name-only index would make here:")
        for o in r.naive_offenders:
            lines.append(
                f"    • {o.caller_lang} caller `{o.callee_name}()` "
                f"→ {o.callee_lang} def in {o.callee_file} "
                f"(at {o.caller_file}:{o.line})"
            )
    else:
        lines.append("  (no cross-language same-name collisions in this repo)")
    lines.append("  " + "─" * 60)
    lines.append("")
    return "\n".join(lines)


def render_card(r: AuditResult) -> str:
    """A copy-paste markdown social card."""
    mult = f"{r.multiplier:.0f}×" if r.naive_miswires else "—"
    out = [
        "### 🧬 TSA Mis-Wire Audit",
        "",
        f"Repo: `{r.project_root.split('/')[-1] or r.project_root}` · "
        f"{r.total_call_edges:,} call edges · {len(r.languages)} languages",
        "",
        "| resolver | cross-language mis-wires | rate |",
        "|---|---|---|",
        f"| a name-only resolver (worst case) | **{r.naive_miswires:,}** | "
        f"{_fmt_pct(r.naive_miswires, r.total_call_edges)} |",
        f"| **Tree-sitter Analyzer** | **{r.tsa_miswires:,}** | "
        f"{_fmt_pct(r.tsa_miswires, r.total_call_edges)} |",
        "",
        f"**{mult} cleaner** — run it on your repo: "
        "`uvx --from tree-sitter-analyzer miswire-audit .`",
        "",
        "_Name-only is the design most code indexes (incl. CodeGraph) use. Live "
        "head-to-head vs CodeGraph: 745 vs 6 — see REPORT-v1.21.0.md._",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="miswire-audit",
        description="Audit cross-language call-graph mis-wires in any repo "
        "(no CodeGraph install needed).",
    )
    parser.add_argument("path", nargs="?", default=".", help="repo path (default: .)")
    parser.add_argument("--card", action="store_true", help="emit a markdown card")
    parser.add_argument("--top", type=int, default=5, help="offenders to show")
    parser.add_argument(
        "--no-reindex", action="store_true", help="reuse the existing .ast-cache"
    )
    args = parser.parse_args(argv)

    result = audit(args.path, reindex=not args.no_reindex, top=args.top)
    # Human-readable goes to stdout (this IS the machine output of the tool).
    print(render_terminal(result))
    if args.card:
        print(render_card(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
