"""Tests for ``tree_sitter_analyzer.symbol_extractors`` (PR-0.2).

Covers the Python top-level def/class extractor that feeds
``DependencyGraph._symbol_def_files`` and indirectly
``DependencyGraph.symbol_in_degree``.

The extractor's contract (also documented in the module docstring):

1. **Top-level only.** Functions / classes nested inside other defs, ``if
   __name__ == "__main__"`` blocks, or methods inside classes are NOT
   counted — only the names a sibling module could ``from X import``.
2. **Decorated definitions are unwrapped one level.** ``@decorator`` is
   transparent for our purposes; the wrapped name is the symbol.
3. **Failure modes are silent.** Unparseable file, missing language
   support, OS-level read errors all return an empty set rather than
   raising. Same contract as ``import_extractors.extract_imports_from_file``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.symbol_extractors import (
    extract_top_level_defs_from_file,
)


def _write(tmp_path: Path, body: str, name: str = "sample.py") -> str:
    """Write ``body`` to ``<tmp_path>/<name>`` and return the absolute path."""

    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


class TestPythonTopLevel:
    def test_simple_def_and_class(self, tmp_path: Path) -> None:
        src = (
            "def hello() -> str:\n"
            "    return 'hi'\n"
            "\n"
            "class Greeter:\n"
            "    def greet(self) -> None:\n"
            "        pass\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"hello", "Greeter"}

    def test_nested_def_is_excluded(self, tmp_path: Path) -> None:
        # ``inner`` is defined inside ``outer`` — only ``outer`` is
        # importable from elsewhere, so only ``outer`` should appear.
        src = "def outer():\n    def inner():\n        return 1\n    return inner\n"
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"outer"}

    def test_class_methods_are_excluded(self, tmp_path: Path) -> None:
        src = (
            "class Service:\n"
            "    def public_method(self):\n"
            "        return 1\n"
            "\n"
            "    def _private(self):\n"
            "        return 2\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        # The class is exported; its methods are not module-level symbols.
        assert names == {"Service"}

    def test_decorated_def_unwrapped(self, tmp_path: Path) -> None:
        src = (
            "from functools import lru_cache\n"
            "\n"
            "@lru_cache(maxsize=8)\n"
            "def cached(x: int) -> int:\n"
            "    return x * x\n"
            "\n"
            "@staticmethod\n"
            "def static_helper():\n"  # invalid at module level but valid syntactically
            "    pass\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"cached", "static_helper"}

    def test_decorated_class_unwrapped(self, tmp_path: Path) -> None:
        src = (
            "from dataclasses import dataclass\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Point:\n"
            "    x: int\n"
            "    y: int\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"Point"}

    def test_def_inside_if_main_is_excluded(self, tmp_path: Path) -> None:
        # ``main`` lives inside ``if __name__ == "__main__":`` — it is
        # NOT a top-level module symbol (it cannot be imported).
        src = (
            "def public_api():\n"
            "    return 42\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    def main():\n"
            "        public_api()\n"
            "    main()\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"public_api"}

    def test_empty_file_returns_empty_set(self, tmp_path: Path) -> None:
        names = extract_top_level_defs_from_file(_write(tmp_path, ""), "python")
        assert names == set()

    def test_file_with_only_imports(self, tmp_path: Path) -> None:
        src = "import os\nfrom pathlib import Path\n"
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == set()

    def test_unicode_identifiers(self, tmp_path: Path) -> None:
        # Python 3 allows unicode identifiers; the byte-offset slicing
        # in ``_node_text`` must handle this correctly.
        src = "def 你好() -> str:\n    return 'hi'\n"
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        assert names == {"你好"}

    def test_multiple_decorators_still_unwrap_once(self, tmp_path: Path) -> None:
        src = (
            "import functools\n"
            "\n"
            "@functools.wraps(print)\n"
            "@staticmethod\n"
            "def deeply_decorated():\n"
            "    pass\n"
        )
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        # Multiple stacked decorators still wrap a single function_definition
        # at the innermost layer — extractor finds it.
        assert names == {"deeply_decorated"}


class TestNonPythonLanguages:
    @pytest.mark.parametrize(
        "language",
        [
            "javascript",
            "typescript",
            "go",
            "rust",
            "java",
            "kotlin",
            "swift",
            "ruby",
            "php",
            "c",
            "cpp",
        ],
    )
    def test_non_python_returns_empty_set(self, tmp_path: Path, language: str) -> None:
        # PR-0.2 ships Python-only; other languages are documented
        # limitations — extractor returns empty set, not error.
        names = extract_top_level_defs_from_file(
            _write(tmp_path, "function foo() {}\n", name="sample.js"),
            language,
        )
        assert names == set()

    def test_unknown_language_returns_empty_set(self, tmp_path: Path) -> None:
        names = extract_top_level_defs_from_file(
            _write(tmp_path, "foo bar\n"), "klingon"
        )
        assert names == set()


class TestFailureModes:
    def test_missing_file_returns_empty_set(self) -> None:
        names = extract_top_level_defs_from_file(
            "/nonexistent/path/that/does/not/exist.py", "python"
        )
        assert names == set()

    def test_syntactically_broken_python_returns_empty_set(
        self, tmp_path: Path
    ) -> None:
        # Tree-sitter is error-tolerant — it parses broken Python into a
        # tree containing ``ERROR`` nodes but still has a top-level
        # structure. The extractor should harvest whatever defs it can
        # find. Worst case: no defs found, empty set returned.
        src = "def good():\n    pass\n\ndef bad(\n"  # unclosed paren
        names = extract_top_level_defs_from_file(_write(tmp_path, src), "python")
        # ``good`` should still be recoverable; ``bad`` might or might not
        # be (parser-dependent). At minimum, no exception.
        assert "good" in names or names == set()
