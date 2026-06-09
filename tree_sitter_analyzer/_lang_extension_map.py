"""Single source of truth for file-extension → language mapping.

History
-------
Before 2026-05-24 this lived in TWO places:

* ``tree_sitter_analyzer/ast_cache.py::_EXT_TO_LANG``
* ``tree_sitter_analyzer/project_graph.py::_language_from_ext``

Those two maps drifted. ``project_graph`` omitted Swift / Kotlin / Ruby /
PHP / C# while ``ast_cache`` had them. Since ``ast_cache.index_file``
calls ``project_graph._language_from_ext``, the smaller map won and
five fully-wired language plugins silently rejected every file with
``status: skipped, reason: unsupported language``. The Alamofire
benchmark surfaced it: TSA indexed 10 / 98 files (and the 10 were JS
files from the docs/ folder). See commit 50e99a8f.

This module is now the ONLY place where the mapping lives. Both
``ast_cache`` and ``project_graph`` import from here.

Adding a new language
---------------------
1. Make sure ``tree_sitter_analyzer/languages/<lang>_plugin.py`` (or
   the ``<lang>_plugin/`` package) exists AND its constructor sets
   ``self.language = "<lang>"`` to a key the plugin registry recognises.
2. (Optional) Add ``tree_sitter_analyzer/queries/<lang>.py`` if symbol
   extraction needs custom queries beyond what the extractor handles.
3. Add the extension(s) here.
4. ``tests/unit/test_lang_extension_map.py`` enforces that every plugin
   listed in ``tree_sitter_analyzer/languages/`` has at least one entry
   here. Add the test fixture entry if necessary.
"""

from __future__ import annotations

from pathlib import Path

# ext (lowercase, including the leading dot) → language token used as the
# key into the plugin registry. Keep this list alphabetised by extension
# so diffs are obvious in code review.
EXT_TO_LANG: dict[str, str] = {
    # Code languages — symbol-bearing, used by call graph + impact tools.
    ".bash": "bash",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".cxx": "cpp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".swift": "swift",
    # .swiftinterface — module-interface files emitted by
    # `swiftc -emit-module-interface`. Syntactically a subset of Swift,
    # parsed by tree-sitter-swift without modification. Useful for SDK
    # analysis (Apple ships SwiftUI / Foundation / etc. as .swiftinterface
    # in the toolchain). Issue #131.
    ".swiftinterface": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".zsh": "bash",
    # NOTE: ``.css / .html / .md / .sql / .yaml / .yml`` have plugins
    # but are intentionally NOT wired here — their indexing path through
    # the ast_cache is not fully exercised yet (see
    # SCAFFOLDS_WITHOUT_EXT in tests/unit/test_lang_extension_map.py).
    # They remain reachable via the CLI single-file analysis path
    # (e.g. ``tree-sitter-analyzer foo.md --structure``), which uses a
    # different file-extension map in file_handler.py.
}


def language_from_ext(file_path: str | Path) -> str | None:
    """Return the language token for ``file_path``'s extension, or None."""
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LANG.get(ext)


def supported_extensions() -> frozenset[str]:
    """Set of extensions (with leading dot) the indexer accepts."""
    return frozenset(EXT_TO_LANG)


def supported_languages() -> frozenset[str]:
    """Set of language tokens emitted by :func:`language_from_ext`."""
    return frozenset(EXT_TO_LANG.values())
