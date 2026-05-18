"""Runnable-test predicates for language-aware test discovery."""

from __future__ import annotations

from pathlib import Path


def is_existing_test_file(path: Path, root: Path, language: str) -> bool:
    """Return True when the queried file is itself a runnable test target."""
    if not path.exists() or not path.is_file():
        return False

    name = path.name
    if name in {"conftest.py", "__init__.py"}:
        return False

    in_test_dir = _is_in_test_dir(path, root)
    if language == "python":
        return name.endswith(("_test.py", "_tests.py")) or (
            in_test_dir and name.startswith("test_") and name.endswith(".py")
        )
    if language == "go":
        return name.endswith("_test.go")
    if language == "rust":
        return name.endswith(("_test.rs", "_tests.rs"))
    if language == "java":
        return name.endswith(("Test.java", "Tests.java")) and in_test_dir
    if language == "javascript":
        return name.endswith((".test.js", ".spec.js", ".test.jsx", ".spec.jsx"))
    if language == "typescript":
        return name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
    if language in {"c", "cpp"}:
        return in_test_dir and name.startswith("test_")
    if language in {"csharp", "kotlin", "php"}:
        return name.endswith(("Test.cs", "Tests.cs", "Test.kt", "Tests.kt", "Test.php"))
    if language == "ruby":
        return name.endswith(("_test.rb", "_spec.rb")) or (
            in_test_dir and name.startswith("test_")
        )
    return in_test_dir and (name.startswith("test_") or ".test." in name)


def _is_in_test_dir(path: Path, root: Path) -> bool:
    """Return True when a path is under a known test directory."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    test_dir_parts = {"tests", "test", "spec", "__tests__"}
    return any(part in test_dir_parts for part in rel.parts[:-1])
