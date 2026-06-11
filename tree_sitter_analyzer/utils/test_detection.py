"""Canonical, cross-language test-file detection and test-intent parsing.

Before this module the codebase carried ~5 independent ``_is_test_file`` /
``is_test_or_fixture_path`` / ``_is_test_path`` variants, each covering a
different subset of conventions (one matched only ``/tests/``; another missed
Go ``*_test.go``; another missed ``.spec.tsx``). The divergence meant a
concept query like ``render`` surfaced ``TestRenderJSON`` above the real
``Render`` in some tools but not others.

This module is the single source of truth, used by every symbol-ranking and
filtering path so behavior is consistent. Detection is **path-based only** —
never by symbol name — so a production class literally named ``TestRunner`` is
never misclassified as a test.
"""

from __future__ import annotations

import re

# Directory segments that mark a test/fixture tree (any depth).
_TEST_DIR_SEGMENTS: tuple[str, ...] = (
    "/test/",
    "/tests/",
    "/__tests__/",
    "/spec/",
    "/specs/",
    "/fixtures/",
    "/testdata/",
)

# Path prefixes (repo-root-relative) that mark a test tree. Must mirror the
# ``/segment/`` entries above so a repo-root ``fixtures/data.go`` is detected
# the same as a nested ``pkg/fixtures/data.go`` (Codex P2 on #294).
_TEST_DIR_PREFIXES: tuple[str, ...] = (
    "test/",
    "tests/",
    "__tests__/",
    "spec/",
    "specs/",
    "fixtures/",
    "testdata/",
)

# Basename suffixes that mark a test file, across languages.
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.go",  # Go
    "_test.py",  # Python (pytest/unittest, *_test.py)
    "_test.rs",  # Rust
    "_test.cc",
    "_test.cpp",
    "_test.cxx",  # C++
    "_spec.rb",  # Ruby
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",  # JS/TS
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
)


def is_test_file(path: str | None) -> bool:
    """Return True when *path* points at a test/spec/fixture file.

    Path-based only (see module docstring). Covers Go ``*_test.go``, Python
    ``test_*.py`` / ``*_test.py``, JS/TS ``*.test.*`` / ``*.spec.*``, Maven
    ``src/test/`` layouts, ``__tests__/``, ``testdata/``, ``fixtures/``, etc.
    """
    if not path:
        return False
    p = path.replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]
    if p.startswith(_TEST_DIR_PREFIXES):
        return True
    if any(seg in p for seg in _TEST_DIR_SEGMENTS):
        return True
    if base.endswith(_TEST_FILE_SUFFIXES):
        return True
    # Require the full path to start with ``test_`` (repo-root convention) so a
    # production file like ``tree_sitter_analyzer/mcp/tools/test_gap_tool.py``
    # is NOT mis-detected: the basename starts with ``test_`` but the file sits
    # inside a production package, not a test tree.  Files at the repo root
    # (``test_thing.py``, ``test_gap_analyzer.py``) are still detected correctly.
    if p.startswith("test_") and base.endswith(
        ".py"
    ):  # pytest test_*.py, repo-root only
        return True
    return False


def rank_tier(path: str | None, *, wants_tests: bool = False) -> int:
    """Ranking tier: 0 (non-test, ranks first) or 1 (test, demoted).

    When *wants_tests* is set — the caller's query explicitly asks about tests —
    the tier is forced to 0 so relevant test symbols are not demoted past a
    result limit.
    """
    if wants_tests:
        return 0
    return 1 if is_test_file(path) else 0


# Whole-word signals in a query/task that mean the user actually WANTS test code.
_TEST_INTENT_RE = re.compile(
    r"\b(tests?|testing|tested|test[_-]?cases?|spec|specs|unit[_-]?tests?|"
    r"benchmarks?|fixtures?)\b",
    re.IGNORECASE,
)


def query_wants_tests(query: str | None) -> bool:
    """True when the query/task explicitly asks about test/spec/benchmark code."""
    return bool(_TEST_INTENT_RE.search(query or ""))


__all__ = ["is_test_file", "query_wants_tests", "rank_tier"]
