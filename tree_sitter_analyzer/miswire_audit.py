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

    uvx --from tree-sitter-analyzer miswire-audit .       # audit the current repo
    uv run python -m tree_sitter_analyzer.miswire_audit /path --card

Output: total call edges, how many a name-only resolver WOULD mis-wire across a
language boundary, how many TSA mis-wires, the multiplier, and the top offending
edges (file:line, caller-lang → callee-lang).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer._language_family import languages_compatible
from tree_sitter_analyzer.ast_cache import ASTCache

_DEF_KINDS = ("function", "method", "class")


def _caller_builtins() -> dict[str, frozenset[str]]:
    """Per-caller-language bare builtin names a basic name-only index could
    special-case (so they are NOT genuine cross-language collisions).

    Reuses TSA's own resolver builtin sets where they exist; a small curated Rust
    prelude covers its most common bare calls. Languages without a set contribute
    no exclusions — keeping the 'genuine' count an honest LOWER bound.
    """
    out: dict[str, frozenset[str]] = {}
    try:
        from tree_sitter_analyzer.synapse_resolver._constants import BUILTINS_PY

        out["python"] = BUILTINS_PY
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        from tree_sitter_analyzer.synapse_resolver.languages._ruby_constants import (
            RUBY_BUILTIN_CALLS,
        )

        out["ruby"] = RUBY_BUILTIN_CALLS
    except Exception:  # pragma: no cover
        pass
    try:
        from tree_sitter_analyzer.synapse_resolver.languages._php_constants import (
            PHP_BUILTIN_FUNCTIONS,
        )

        out["php"] = PHP_BUILTIN_FUNCTIONS
    except Exception:  # pragma: no cover
        pass
    try:
        from tree_sitter_analyzer.synapse_resolver.languages._swift_constants import (
            SWIFT_STDLIB_FUNCTIONS,
        )

        out["swift"] = SWIFT_STDLIB_FUNCTIONS
    except Exception:  # pragma: no cover
        pass
    try:
        from tree_sitter_analyzer.synapse_resolver.languages._c_constants import (
            LIBC_FUNCTIONS_C,
        )

        out["c"] = LIBC_FUNCTIONS_C
        out["cpp"] = LIBC_FUNCTIONS_C
    except Exception:  # pragma: no cover
        pass
    # Curated bare-call builtins for the remaining languages (Codex #377 P2: a
    # language with no entry would count its OWN builtins -- JS Map()/Promise() --
    # as "genuine", reintroducing the skeptic-dismissable cases this floor excludes).
    # These err toward EXCLUDING common names, so genuine stays a conservative,
    # defensible lower bound.
    out["rust"] = frozenset(
        {
            "Ok",
            "Err",
            "Some",
            "None",
            "Vec",
            "Box",
            "String",
            "format",
            "println",
            "print",
            "eprintln",
            "eprint",
            "vec",
            "write",
            "writeln",
            "clone",
            "into",
            "from",
            "new",
            "default",
            "unwrap",
            "expect",
            "iter",
            "collect",
            "map",
            "filter",
            "to_string",
            "to_owned",
            "as_ref",
            "len",
            "push",
            "drop",
            "panic",
            "assert",
            "matches",
            "f",
        }
    )
    _js = frozenset(
        {
            "Map",
            "Set",
            "Promise",
            "Array",
            "Object",
            "JSON",
            "Math",
            "Symbol",
            "WeakMap",
            "WeakSet",
            "Proxy",
            "Reflect",
            "Date",
            "RegExp",
            "Error",
            "Number",
            "String",
            "Boolean",
            "BigInt",
            "Function",
            "parseInt",
            "parseFloat",
            "isNaN",
            "isFinite",
            "fetch",
            "require",
            "setTimeout",
            "setInterval",
            "clearTimeout",
            "console",
            "structuredClone",
            "keys",
            "values",
            "entries",
            "from",
            "of",
            "isArray",
            "assign",
            "push",
            "pop",
            "map",
            "filter",
            "forEach",
            "reduce",
            "then",
            "catch",
            "resolve",
        }
    )
    out["javascript"] = _js
    out["typescript"] = _js
    out["jsx"] = _js
    out["tsx"] = _js
    out["go"] = frozenset(
        {
            "len",
            "cap",
            "make",
            "append",
            "new",
            "copy",
            "delete",
            "panic",
            "recover",
            "print",
            "println",
            "close",
            "complex",
            "real",
            "imag",
            "min",
            "max",
            "clear",
            "Sprintf",
            "Printf",
            "Errorf",
            "Println",
        }
    )
    out["java"] = frozenset(
        {
            "toString",
            "equals",
            "hashCode",
            "valueOf",
            "getClass",
            "clone",
            "length",
            "size",
            "get",
            "put",
            "add",
            "remove",
            "contains",
            "isEmpty",
            "iterator",
            "next",
            "hasNext",
            "name",
            "ordinal",
            "compareTo",
            "of",
            "asList",
            "stream",
            "collect",
            "forEach",
        }
    )
    out["kotlin"] = frozenset(
        {
            "listOf",
            "mapOf",
            "setOf",
            "mutableListOf",
            "mutableMapOf",
            "println",
            "print",
            "require",
            "check",
            "error",
            "run",
            "let",
            "apply",
            "also",
            "with",
            "to",
            "arrayOf",
            "emptyList",
            "emptyMap",
            "lazy",
            "TODO",
        }
    )
    out["csharp"] = frozenset(
        {
            "ToString",
            "Equals",
            "GetHashCode",
            "GetType",
            "Contains",
            "Add",
            "Remove",
            "Count",
            "Where",
            "Select",
            "First",
            "Any",
            "All",
            "ToList",
            "ToArray",
            "WriteLine",
            "Write",
            "Format",
        }
    )
    return out


_CALLER_BUILTINS = _caller_builtins()


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
    # False on SQLite builds without FTS5, where index_project() does not write
    # call edges (Codex #369 L158) — the audit cannot measure mis-wires there.
    call_edges_available: bool = True
    # The skeptic-resistant floor: naive mis-wires EXCLUDING the caller language's
    # own builtins (print/range/Ok/…) — i.e. genuine cross-language collisions a
    # name-only index would still get wrong.
    naive_genuine_miswires: int = 0
    genuine_offenders: list[Offender] = field(default_factory=list)

    @property
    def multiplier(self) -> float:
        """How many times cleaner TSA is (naive / TSA), guarded for 0."""
        if self.tsa_miswires == 0:
            return float(self.naive_miswires) if self.naive_miswires else 1.0
        return self.naive_miswires / self.tsa_miswires


def _iter_symbol_defs(conn: Any) -> list[tuple[str, str, str]]:
    """Yield ``(name, file_path, language)`` for every function/method/class def.

    Prefers the ``ast_symbol_rows`` table. On SQLite builds WITHOUT FTS5,
    ``ASTCache`` does not create that table (Codex review #369), so we fall back
    to parsing ``ast_index.symbols_json`` — which always exists — keeping the
    audit functional in those supported environments.
    """
    import sqlite3

    try:
        # kinds are module constants, not user input — a literal IN clause keeps
        # bandit happy (no string-built SQL) and is exactly equivalent.
        rows = conn.execute(
            "SELECT name, file_path, language FROM ast_symbol_rows "
            "WHERE kind IN ('function', 'method', 'class')"
        ).fetchall()
        return [(r["name"], r["file_path"], r["language"]) for r in rows]
    except sqlite3.OperationalError:
        pass  # ast_symbol_rows absent (no-FTS5 build) — fall back below.

    import json

    defs: list[tuple[str, str, str]] = []
    for r in conn.execute(
        "SELECT file_path, language, symbols_json FROM ast_index"
    ).fetchall():
        raw = r["symbols_json"]
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for sym in payload.get("symbols", []):
            if sym.get("kind") in _DEF_KINDS and sym.get("name"):
                defs.append((sym["name"], r["file_path"], r["language"]))
    return defs


def _build_name_maps(
    conn: Any, present: set[str] | None
) -> tuple[dict[str, set[str]], dict[str, list[tuple[str, str]]]]:
    """Build name->languages and name->[(file,lang)] from current-repo defs."""
    name_langs: dict[str, set[str]] = defaultdict(set)
    name_files: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name, file_path, language in _iter_symbol_defs(conn):
        if present is not None and file_path not in present:
            continue  # skip stale rows for files no longer on disk (Codex #369)
        name_langs[name].add(language)
        name_files[name].append((file_path, language))
    return name_langs, name_files


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
        # Codex #369: an incremental reindex does NOT purge rows for files that
        # were deleted since a prior index, so the cache can carry stale
        # definitions/edges. Restrict the audit to files that still exist on
        # disk, so `miswire-audit .` reflects the CURRENT repo regardless of a
        # stale .ast-cache (the slow alternative — a full clean rebuild — would
        # punish every run).
        present = {
            f for f in file_lang if os.path.exists(os.path.join(project_root, f))
        }
        file_lang = {f: lang for f, lang in file_lang.items() if f in present}
        name_langs, name_files = _build_name_maps(conn, present)

        edges = conn.execute(
            "SELECT callee_name, language AS caller_lang, callee_resolved_file, "
            "file_path AS caller_file, callee_line "
            "FROM edges WHERE kind='calls' AND callee_name != ''"
        ).fetchall()

        # Codex #369 L158: on SQLite builds WITHOUT FTS5, index_project() does not
        # write call edges, so `edges` is empty and a "0 mis-wires" verdict would
        # be misleading. Flag it so the renderer can say so plainly instead.
        if not edges and not bool(getattr(cache, "fts5_available", True)):
            result.call_edges_available = False

        for e in edges:
            # skip edges whose caller file no longer exists (stale cache rows)
            if e["caller_file"] not in present:
                continue
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
                            Offender(
                                name,
                                e["caller_file"],
                                caller_lang,
                                resolved,
                                rlang,
                                e["callee_line"] or 0,
                            )
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
                    is_builtin = name in _CALLER_BUILTINS.get(caller_lang, frozenset())
                    if not is_builtin:
                        result.naive_genuine_miswires += 1
                    # pick one concrete cross-language def for the offender example
                    cross_def = next(
                        (
                            (df, dl)
                            for df, dl in name_files.get(name, [])
                            if not languages_compatible(caller_lang, dl)
                        ),
                        None,
                    )
                    if cross_def is None:
                        continue
                    off = Offender(
                        name,
                        e["caller_file"],
                        caller_lang,
                        cross_def[0],
                        cross_def[1],
                        e["callee_line"] or 0,
                    )
                    # DISTINCT names; lead the offender lists with GENUINE (non-
                    # builtin) collisions — the skeptic-resistant examples.
                    if (
                        not is_builtin
                        and name
                        not in {o.callee_name for o in result.genuine_offenders}
                        and len(result.genuine_offenders) < top
                    ):
                        result.genuine_offenders.append(off)
                    if (
                        name not in {o.callee_name for o in result.naive_offenders}
                        and len(result.naive_offenders) < top
                    ):
                        result.naive_offenders.append(off)
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
    if not r.call_edges_available:
        lines.append("")
        lines.append(
            "  ⚠ this Python's SQLite has no FTS5, so TSA did not produce call "
            "edges — the mis-wire audit needs them. Use a Python built with "
            "SQLite FTS5 (the default for python.org / most distros) and re-run."
        )
        lines.append("  " + "─" * 60)
        lines.append("")
        return "\n".join(lines)
    lines.append(f"  call edges analysed: {r.total_call_edges:,}")
    lines.append("")
    lines.append(
        f"  ❌ a NAME-ONLY resolver would mis-wire {r.naive_miswires:,} call edges "
        f"across a language boundary "
        f"({_fmt_pct(r.naive_miswires, r.total_call_edges)}); "
        f"{r.naive_genuine_miswires:,} are GENUINE collisions — same name in "
        f"another language, not a builtin a basic index could special-case"
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
        "  (worst case for a name-only index — the design most indexes use. The "
        "live head-to-head vs CodeGraph specifically — 745 vs 6 on TSA's repo — is"
    )
    lines.append("   in benchmarks/codegraph_compare/REPORT-v1.21.0.md.)")
    lines.append("")
    shown = r.genuine_offenders or r.naive_offenders
    if shown:
        label = (
            "genuine cross-language mis-wires a name-only index would make here:"
            if r.genuine_offenders
            else "cross-language mis-wires a name-only index would make here:"
        )
        lines.append("  " + label)
        for o in shown:
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
