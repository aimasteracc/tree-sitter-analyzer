"""Regression suite for the single-source ext→language map.

Pins the contract introduced in commit 50e99a8f after the 2026-05-24
Alamofire benchmark surfaced that two diverged ext-to-language maps
were silently dropping Swift / Kotlin / Ruby / PHP / C# files at the
indexer boundary.

Three invariants enforced here:

1. Every language plugin under ``tree_sitter_analyzer/languages/`` that
   advertises a ``self.language`` token MUST have at least one
   extension entry in ``EXT_TO_LANG`` — otherwise the plugin can never
   be reached via the indexer.
2. The legacy ``project_graph._language_from_ext`` and
   ``ast_cache._EXT_TO_LANG`` aliases MUST resolve to the same source
   of truth (otherwise we re-introduce the historical divergence).
3. The five "long-broken" extensions stay wired: ``.swift``, ``.kt``,
   ``.rb``, ``.php``, ``.cs`` — these are the ones the benchmark
   caught.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# -- helpers ------------------------------------------------------------

PLUGIN_DIR = Path("tree_sitter_analyzer/languages")

# Plugins that intentionally have no extension wiring (yet). Listed
# explicitly so adding a new scaffold plugin doesn't silently slip the
# coverage test — every entry below is a known TODO and the gap-audit
# doc tracks the work.
SCAFFOLDS_WITHOUT_EXT: set[str] = {
    # Code-targeted plugins waiting for ext wiring (tree-sitter parsers
    # available on PyPI; plugin scaffolds in place; needs validation pass).
    # NOTE: "bash" graduated 2026-06-10 — tree-sitter-bash dep added,
    # .sh/.bash/.zsh wired in language_detector + _lang_extension_map +
    # file_handler.
    "scala",
    "json",
    # Data / markup plugins. Reachable via the CLI single-file path
    # (file_handler.py uses its own ext map), but NOT yet wired into
    # the ast_cache indexer because their plugin chain returns errors
    # rather than empty-symbols cleanly. See the markup-wiring task in
    # the gap-audit doc — short follow-up; not urgent.
    "css",
    "html",
    "markdown",
    "sql",
    "yaml",
}


# -- invariant 1: every plugin reachable via extension ------------------


def _discover_plugin_languages() -> set[str]:
    """Return the language tokens of every plugin under languages/.

    Plugins identify themselves two ways depending on how they were
    written. We look for both:

    1. ``self.language = "<lang>"`` (most plugins)
    2. ``def get_language_name(self) -> str: return "<lang>"`` (PHP,
       Ruby — single-method form)

    This stays a source-level grep — no imports — so it doesn't trip
    side-effect hooks on plugin load.
    """
    pat_self = re.compile(r'^\s*self\.language\s*=\s*["\']([a-z_]+)["\']', re.MULTILINE)
    pat_method = re.compile(
        r"def\s+get_language_name\s*\([^)]*\)[^:]*:\s*\n\s+(?:\"\"\"[^\"]*\"\"\"\s*\n\s+)?"
        r'return\s+["\']([a-z_]+)["\']',
        re.MULTILINE,
    )
    langs: set[str] = set()
    for entry in PLUGIN_DIR.iterdir():
        if entry.name.startswith("_") or entry.name.startswith("__"):
            continue
        # both ``swift_plugin.py`` (single-file) and ``python_plugin/`` (pkg)
        if entry.is_file() and entry.name.endswith("_plugin.py"):
            text = entry.read_text(encoding="utf-8")
        elif entry.is_dir() and entry.name.endswith("_plugin"):
            text = ""
            for sib in list(entry.glob("__init__.py")) + list(entry.glob("plugin.py")):
                if sib.is_file():
                    text += sib.read_text(encoding="utf-8") + "\n"
        else:
            continue
        for m in pat_self.finditer(text):
            langs.add(m.group(1))
        for m in pat_method.finditer(text):
            langs.add(m.group(1))
    return langs


def test_every_plugin_has_extension_wiring() -> None:
    """Every plugin must be reachable via at least one file extension."""
    from tree_sitter_analyzer._lang_extension_map import supported_languages

    plugin_langs = _discover_plugin_languages()
    mapped_langs = supported_languages()
    missing = sorted(plugin_langs - mapped_langs - SCAFFOLDS_WITHOUT_EXT)
    assert missing == [], (
        f"These language plugins exist but have NO extension entry in "
        f"tree_sitter_analyzer/_lang_extension_map.py::EXT_TO_LANG: "
        f"{missing}. Either wire them (preferred) or add to "
        f"SCAFFOLDS_WITHOUT_EXT with a tracking note. This is the "
        f"same class of bug as the 2026-05-24 Swift/Kotlin/Ruby/PHP/"
        f"C# silent-drop incident."
    )


# -- invariant 2: both legacy aliases point at the same map -------------


def test_ast_cache_alias_matches_canonical() -> None:
    from tree_sitter_analyzer._lang_extension_map import EXT_TO_LANG
    from tree_sitter_analyzer.ast_cache import _EXT_TO_LANG

    assert _EXT_TO_LANG is EXT_TO_LANG, (
        "ast_cache._EXT_TO_LANG must be the SAME object as "
        "_lang_extension_map.EXT_TO_LANG (not just structurally equal). "
        "Otherwise drift is back."
    )


def test_project_graph_alias_resolves_via_canonical() -> None:
    from tree_sitter_analyzer._lang_extension_map import language_from_ext
    from tree_sitter_analyzer.project_graph import _language_from_ext

    for sample in (
        "foo.py",
        "Foo.java",
        "Foo.swift",
        "Foo.kt",
        "foo.rb",
        "foo.php",
        "Foo.cs",
        "foo.unknown",
    ):
        assert _language_from_ext(sample) == language_from_ext(sample), sample


# -- invariant 3: the five long-broken extensions stay wired ------------


@pytest.mark.parametrize(
    "ext, expected",
    [
        (".swift", "swift"),
        (".swiftinterface", "swift"),  # issue #131
        (".kt", "kotlin"),
        (".rb", "ruby"),
        (".php", "php"),
        (".cs", "csharp"),
    ],
)
def test_long_broken_extensions_stay_wired(ext: str, expected: str) -> None:
    from tree_sitter_analyzer._lang_extension_map import language_from_ext

    assert language_from_ext(f"foo{ext}") == expected, (
        f"{ext} → {expected} regression. This wiring was missing for "
        f"months until the 2026-05-24 benchmark surfaced it (Alamofire "
        f"indexed 10/98 files, all of them JS noise from docs/)."
    )


def test_swiftinterface_resolves_in_all_known_ext_maps() -> None:
    """``.swiftinterface`` must map to swift across every ext-resolver.

    Issue #131 added module-interface support. ``_lang_extension_map``
    is the SSoT for indexer wiring, but a handful of bespoke maps in
    ``file_handler`` / ``language_detector`` / detector helpers /
    health_scorer / mcp tools have their own copies (intentional —
    they cover different code paths). All of them must agree, or a
    file resolves as swift in one path and ``unknown`` in another.
    """
    from tree_sitter_analyzer._lang_extension_map import language_from_ext
    from tree_sitter_analyzer.file_handler import detect_language_from_extension
    from tree_sitter_analyzer.language_detector import LanguageDetector

    sample = "Foundation.swiftinterface"

    # 1. Indexer SSoT
    assert language_from_ext(sample) == "swift"

    # 2. CLI single-file path (file_handler)
    assert detect_language_from_extension(sample) == "swift"

    # 3. Generic language detector (used by some MCP tools)
    detector = LanguageDetector()
    assert detector.detect_from_extension(sample) == "swift"


# -- meta: the helper itself works --------------------------------------


def test_discover_plugin_languages_finds_known_set() -> None:
    """Sanity-check: discovery returns the expected languages."""
    langs = _discover_plugin_languages()
    expected_subset = {
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "csharp",
        "swift",
        "kotlin",
        "ruby",
        "php",
    }
    assert expected_subset <= langs, (
        f"plugin-language discovery seems broken: expected at least "
        f"{expected_subset}, found {langs}"
    )
