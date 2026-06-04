"""Cross-language compatibility families for callee-resolution gates."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer._language_family import (
    language_from_path,
    languages_compatible,
)


@pytest.mark.parametrize(
    "a,b",
    [
        ("python", "python"),  # identical
        ("javascript", "typescript"),  # JS/TS family
        ("typescript", "jsx"),
        ("tsx", "javascript"),
        ("c", "cpp"),  # C/C++ family (Codex P2: .cpp caller -> .h `c` def)
        ("cpp", "c"),
        ("objc", "cpp"),
        ("python", ""),  # unknown -> never block
        ("", "swift"),
    ],
)
def test_compatible_pairs(a: str, b: str) -> None:
    assert languages_compatible(a, b) is True


@pytest.mark.parametrize(
    "a,b",
    [
        ("python", "javascript"),
        ("python", "swift"),
        ("c", "python"),
        ("cpp", "javascript"),
        ("java", "kotlin"),  # interop in practice, but kept distinct for binding
    ],
)
def test_incompatible_pairs(a: str, b: str) -> None:
    assert languages_compatible(a, b) is False


def test_language_from_path_covers_c_cpp_headers() -> None:
    assert language_from_path("src/util.cpp") == "cpp"
    # A C++ project's headers index as `c`; the family makes the cross-edge valid.
    assert language_from_path("src/util.h") == "c"
    assert language_from_path("a/b/lib.ts") == "typescript"
    assert language_from_path("x.py") == "python"
    assert language_from_path("noext") == ""
