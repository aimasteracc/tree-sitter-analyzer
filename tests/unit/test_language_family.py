"""Cross-language compatibility families for callee-resolution gates."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer._language_family import (
    language_from_path,
    languages_compatible,
)


@pytest.mark.parametrize(
    "caller,callee",
    [
        ("python", "python"),  # identical
        ("javascript", "typescript"),  # JS/TS family (symmetric)
        ("typescript", "jsx"),
        ("tsx", "javascript"),
        ("cpp", "c"),  # C++ caller → C header (the motivating case)
        ("objc", "c"),  # Objective-C is a superset of C
        ("objcpp", "c"),  # Objective-C++ → C
        ("objcpp", "cpp"),  # Objective-C++ → C++
        ("objcpp", "objc"),  # Objective-C++ → Objective-C
        ("python", ""),  # unknown callee → never block
        ("", "swift"),  # unknown caller → never block
    ],
)
def test_compatible_pairs(caller: str, callee: str) -> None:
    assert languages_compatible(caller, callee) is True


@pytest.mark.parametrize(
    "caller,callee",
    [
        ("python", "javascript"),
        ("python", "swift"),
        ("c", "python"),
        ("cpp", "javascript"),
        ("java", "kotlin"),  # interop in practice, but kept distinct for binding
        # Directional C-family gates: pure-C and Objective-C must not bind to C++
        ("c", "cpp"),  # C caller must not bind to C++ definitions
        ("c", "objc"),  # C caller must not bind to Objective-C
        ("c", "objcpp"),
        ("objc", "cpp"),  # Objective-C must not bind to C++ (Codex P2 #302)
        ("objc", "objcpp"),
    ],
)
def test_incompatible_pairs(caller: str, callee: str) -> None:
    assert languages_compatible(caller, callee) is False


def test_language_from_path_covers_c_cpp_headers() -> None:
    assert language_from_path("src/util.cpp") == "cpp"
    # A C++ project's headers index as `c`; cpp→c is directionally compatible.
    assert language_from_path("src/util.h") == "c"
    assert language_from_path("a/b/lib.ts") == "typescript"
    assert language_from_path("x.py") == "python"
    assert language_from_path("noext") == ""
