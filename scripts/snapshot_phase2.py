#!/usr/bin/env python3
"""Phase 2 golden master snapshot tool.

Usage:
  python scripts/snapshot_phase2.py                    # generate snapshots for all languages
  python scripts/snapshot_phase2.py --compare          # compare current output vs snapshots
  python scripts/snapshot_phase2.py --lang go,python   # filter by language
  python scripts/snapshot_phase2.py --compare --lang go

Exit codes:
  0 - success (generate: all snapshots written; compare: zero diff)
  1 - comparison found differences
  2 - unexpected error
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve project root so the script works regardless of cwd
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_GOLDEN_DIR = _PROJECT_ROOT / "tests" / "golden"
_SNAPSHOTS_DIR = _GOLDEN_DIR / "snapshots"

# Map language name -> (corpus filename, tree-sitter module name, language key)
# tree-sitter module name is used to load the parser
_LANG_CONFIG: dict[str, tuple[str, str, str]] = {
    "bash": ("corpus_bash.sh", "tree_sitter_bash", "bash"),
    "c": ("corpus_c.c", "tree_sitter_c", "c"),
    "cpp": ("corpus_cpp.cpp", "tree_sitter_cpp", "cpp"),
    "css": ("corpus_css.css", "tree_sitter_css", "css"),
    "go": ("corpus_go.go", "tree_sitter_go", "go"),
    "html": ("corpus_html.html", "tree_sitter_html", "html"),
    "java": ("corpus_java.java", "tree_sitter_java", "java"),
    "javascript": ("corpus_javascript.js", "tree_sitter_javascript", "javascript"),
    "json": ("corpus_json.json", "tree_sitter_json", "json"),
    "kotlin": ("corpus_kotlin.kt", "tree_sitter_kotlin", "kotlin"),
    "markdown": ("corpus_markdown.md", "tree_sitter_markdown", "markdown"),
    "php": ("corpus_php.php", "tree_sitter_php", "php"),
    "python": ("corpus_python.py", "tree_sitter_python", "python"),
    "ruby": ("corpus_ruby.rb", "tree_sitter_ruby", "ruby"),
    "rust": ("corpus_rust.rs", "tree_sitter_rust", "rust"),
    "scala": ("corpus_scala.scala", "tree_sitter_scala", "scala"),
    "sql": ("corpus_sql.sql", "tree_sitter_languages", "sql"),
    "swift": ("corpus_swift.swift", "tree_sitter_swift", "swift"),
    "typescript": ("corpus_typescript.ts", "tree_sitter_typescript", "typescript"),
    "yaml": ("corpus_yaml.yaml", "tree_sitter_yaml", "yaml"),
}


def _get_ts_language(ts_module: str, lang_key: str) -> Any:
    """Load a tree-sitter Language object from a module."""
    import tree_sitter

    try:
        mod = __import__(ts_module)
        # Most tree-sitter-* packages expose a .language() function
        if hasattr(mod, "language"):
            return tree_sitter.Language(mod.language())
        # tree_sitter_typescript has .language_typescript / .language_tsx
        if lang_key == "typescript" and hasattr(mod, "language_typescript"):
            return tree_sitter.Language(mod.language_typescript())
        if lang_key == "php":
            # tree_sitter_php has language_php / language_php_only
            if hasattr(mod, "language_php"):
                return tree_sitter.Language(mod.language_php())
        if lang_key == "markdown" and hasattr(mod, "language_markdown"):
            return tree_sitter.Language(mod.language_markdown())
        # Fallback: try get_language
        if hasattr(mod, "get_language"):
            return mod.get_language(lang_key)
    except Exception as exc:
        raise RuntimeError(
            f"Cannot load tree-sitter language for {lang_key}: {exc}"
        ) from exc
    raise RuntimeError(
        f"Cannot load tree-sitter language for {lang_key}: no language() found in {ts_module}"
    )


def _analyze_with_plugin(corpus_file: Path, lang_key: str) -> dict[str, Any]:
    """Use PluginManager + direct tree-sitter parse to extract symbols."""
    import tree_sitter

    from tree_sitter_analyzer.plugins.manager import PluginManager

    pm = PluginManager()
    pm.load_plugins()
    plugin = pm.get_plugin(lang_key)

    corpus_fname, ts_module, _ = _LANG_CONFIG[lang_key]

    with open(corpus_file, encoding="utf-8", errors="replace") as f:
        source = f.read()

    symbols: list[dict[str, Any]] = []

    if plugin is not None:
        try:
            ts_lang = _get_ts_language(ts_module, lang_key)
            parser = tree_sitter.Parser()
            parser.language = ts_lang
            tree = parser.parse(bytes(source, "utf-8"))
            extractor = plugin.create_extractor()
            extractor.current_file = str(corpus_file)

            all_elems: list[Any] = []
            try:
                all_elems.extend(extractor.extract_functions(tree, source))
            except Exception:
                pass
            try:
                all_elems.extend(extractor.extract_classes(tree, source))
            except Exception:
                pass
            try:
                all_elems.extend(extractor.extract_variables(tree, source))
            except Exception:
                pass
            try:
                all_elems.extend(extractor.extract_imports(tree, source))
            except Exception:
                pass

            for elem in all_elems:
                symbols.append(
                    {
                        "name": getattr(elem, "name", ""),
                        "kind": type(elem).__name__.lower(),
                        "start_line": getattr(elem, "start_line", 0),
                    }
                )
        except Exception as exc:
            # Gracefully store 0 symbols with error note
            symbols = [{"name": f"__error__: {exc}", "kind": "error", "start_line": 0}]

    # Sort for stable comparison
    symbols.sort(key=lambda s: (s.get("start_line", 0), s.get("name", "")))

    return {
        "language": lang_key,
        "corpus_file": str(corpus_file.relative_to(_PROJECT_ROOT)),
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "edges": [],
    }


def _snapshot_path(language: str) -> Path:
    return _SNAPSHOTS_DIR / f"phase2_before_{language}.json"


def cmd_generate(languages: list[str]) -> int:
    """Generate snapshots; return exit code."""
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0
    for lang in languages:
        corpus_fname, ts_module, lang_key = _LANG_CONFIG[lang]
        corpus_file = _GOLDEN_DIR / corpus_fname
        if not corpus_file.exists():
            print(f"[WARN] corpus file not found: {corpus_file}", file=sys.stderr)
            continue
        try:
            data = _analyze_with_plugin(corpus_file, lang_key)
            out = _snapshot_path(lang)
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(
                f"[OK]   {lang}: {data['symbol_count']} symbols -> {out.relative_to(_PROJECT_ROOT)}"
            )
            ok += 1
        except Exception as exc:
            print(f"[FAIL] {lang}: {exc}", file=sys.stderr)
            fail += 1

    print(f"\nGenerated: {ok}, Failed: {fail}")
    return 0 if fail == 0 else 2


def cmd_compare(languages: list[str]) -> int:
    """Compare current output vs snapshots; return 0 if no diff, 1 if diff."""
    diffs: list[str] = []

    for lang in languages:
        snap_path = _snapshot_path(lang)
        if not snap_path.exists():
            print(f"[WARN] no snapshot for {lang}: {snap_path}", file=sys.stderr)
            continue

        corpus_fname, ts_module, lang_key = _LANG_CONFIG[lang]
        corpus_file = _GOLDEN_DIR / corpus_fname
        if not corpus_file.exists():
            print(f"[WARN] corpus file not found: {corpus_file}", file=sys.stderr)
            continue

        try:
            baseline = json.loads(snap_path.read_text())
            current = _analyze_with_plugin(corpus_file, lang_key)
        except Exception as exc:
            print(f"[FAIL] {lang}: {exc}", file=sys.stderr)
            diffs.append(f"{lang}: exception during comparison: {exc}")
            continue

        # Compare symbol lists (name+kind+start_line triples, sorted)
        base_syms = sorted(
            baseline.get("symbols", []),
            key=lambda s: (s.get("start_line", 0), s.get("name", "")),
        )
        cur_syms = sorted(
            current.get("symbols", []),
            key=lambda s: (s.get("start_line", 0), s.get("name", "")),
        )

        if base_syms == cur_syms:
            print(f"[OK]   {lang}: {len(cur_syms)} symbols, zero diff")
        else:
            base_set = {json.dumps(s, sort_keys=True) for s in base_syms}
            cur_set = {json.dumps(s, sort_keys=True) for s in cur_syms}
            added = cur_set - base_set
            removed = base_set - cur_set
            msg = (
                f"{lang}: diff! "
                f"+{len(added)} symbols, -{len(removed)} symbols "
                f"(baseline={len(base_syms)}, current={len(cur_syms)})"
            )
            print(f"[DIFF] {msg}")
            if added:
                for s in sorted(added)[:5]:
                    print(f"       + {s}")
            if removed:
                for s in sorted(removed)[:5]:
                    print(f"       - {s}")
            diffs.append(msg)

    if diffs:
        print(f"\n{len(diffs)} language(s) with differences:")
        for d in diffs:
            print(f"  {d}")
        return 1
    print("\nAll compared languages: zero diff.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare current output vs saved snapshots instead of generating",
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="Comma-separated language names to process (default: all)",
    )
    args = parser.parse_args()

    if args.lang:
        languages = [lang.strip() for lang in args.lang.split(",") if lang.strip()]
        unknown = [lang for lang in languages if lang not in _LANG_CONFIG]
        if unknown:
            print(f"Unknown language(s): {unknown}", file=sys.stderr)
            print(f"Known: {sorted(_LANG_CONFIG)}", file=sys.stderr)
            return 2
    else:
        languages = sorted(_LANG_CONFIG.keys())

    if args.compare:
        return cmd_compare(languages)
    else:
        return cmd_generate(languages)


if __name__ == "__main__":
    sys.exit(main())
