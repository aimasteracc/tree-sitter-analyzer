#!/usr/bin/env python3
"""
Language-aware test file discovery.

Finds test files for a given source file using language-specific naming
conventions (test_*.py, *Test.java, *_test.go, etc.).
"""

from pathlib import Path

# Language → test file naming patterns
_TEST_PATTERNS: dict[str, list[str]] = {
    "python": ["test_{stem}.py"],
    "java": ["{Stem}Test.java", "{Stem}Tests.java", "Test{Stem}.java"],
    "go": ["{stem}_test.go"],
    "rust": ["{stem}_test.rs", "{stem}_tests.rs"],
    "javascript": ["{stem}.test.js", "{stem}.spec.js", "{stem}.test.jsx"],
    "typescript": ["{stem}.test.ts", "{stem}.spec.ts", "{stem}.test.tsx"],
    "c": ["test_{stem}.c", "test_{stem}.h"],
    "cpp": ["test_{stem}.cpp", "test_{stem}.hpp"],
    "csharp": ["{Stem}Test.cs", "{Stem}Tests.cs"],
    "kotlin": ["{Stem}Test.kt", "{Stem}Tests.kt"],
    "ruby": ["{stem}_test.rb", "test_{stem}.rb"],
    "php": ["{Stem}Test.php", "{stem}Test.php"],
}

# Language → common test directory names
_TEST_DIRS: dict[str, list[str]] = {
    "python": ["tests", "test"],
    "java": ["src/test/java", "test"],
    "go": ["."],  # Go tests are co-located
    "rust": ["tests"],
    "javascript": ["__tests__", "tests", "test"],
    "typescript": ["__tests__", "tests", "test"],
    "c": ["tests", "test"],
    "cpp": ["tests", "test"],
    "csharp": ["Tests", "tests"],
    "kotlin": ["src/test/kotlin", "test"],
    "ruby": ["test", "tests", "spec"],
    "php": ["tests", "tests/Unit"],
}

# File extension → language name
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
}


def detect_language_from_ext(ext: str) -> str | None:
    """Map file extension to language name."""
    return _EXT_TO_LANG.get(ext.lower())


def find_test_files(
    file_path: str,
    project_root: str,
) -> list[str]:
    """Find test files for the given source file, language-aware.

    Returns relative paths to test files found within the project.
    """
    p = Path(file_path)
    root = Path(project_root)
    stem = p.stem
    ext = p.suffix.lower()
    language = detect_language_from_ext(ext) or "python"

    results: list[str] = []

    # Pattern-based discovery in common test directories
    patterns = _TEST_PATTERNS.get(language, ["test_{stem}.py"])
    test_dirs = _TEST_DIRS.get(language, ["tests"])

    for pattern in patterns:
        test_filename = _format_pattern(pattern, stem)
        for test_dir in test_dirs:
            candidate = root / test_dir / test_filename
            if candidate.exists():
                _add_result(results, candidate, root)

            # Also search recursively within test directories (capped)
            dir_path = root / test_dir
            if dir_path.is_dir():
                for candidate in dir_path.rglob(test_filename):
                    _add_result(results, candidate, root)
                    if len(results) >= 10:
                        break

    # Co-located test (same directory)
    for pattern in patterns:
        test_filename = _format_pattern(pattern, stem)
        candidate = p.parent / test_filename
        if candidate.exists():
            _add_result(results, candidate, root)

    # Language-specific: Java Maven/Gradle structure
    if language == "java":
        _find_java_tests(p, stem, root, results)

    # Language-specific: Go tests are always co-located
    if language == "go":
        candidate = p.parent / f"{stem}_test.go"
        if candidate.exists():
            _add_result(results, candidate, root)

    # Language-specific: Ruby spec files
    if language == "ruby":
        spec_dir = root / "spec"
        if spec_dir.exists():
            for spec_file in spec_dir.rglob(f"{stem}_spec.rb"):
                _add_result(results, spec_file, root)

    return results[:10]


def _format_pattern(pattern: str, stem: str) -> str:
    """Format a test file pattern with the source file stem."""
    return pattern.replace("{stem}", stem).replace("{Stem}", stem.capitalize())


def _add_result(results: list[str], candidate: Path, root: Path) -> None:
    """Add a test file to results if not already present."""
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = str(candidate)
    if rel not in results:
        results.append(rel)


def _find_java_tests(
    source_path: Path,
    stem: str,
    root: Path,
    results: list[str],
) -> None:
    """Find Java test files using Maven/Gradle directory conventions."""
    # Try mirroring the source path under test
    try:
        rel = source_path.relative_to(root)
    except ValueError:
        return

    parts = list(rel.parts)
    # Replace src/main/java → src/test/java
    new_parts = []
    replaced = False
    for part in parts:
        if part == "main" and not replaced:
            new_parts.append("test")
            replaced = True
        else:
            new_parts.append(part)

    if replaced:
        new_parts[-1] = f"{stem}Test.java"
        candidate = root / Path(*new_parts)
        if candidate.exists():
            _add_result(results, candidate, root)

        new_parts[-1] = f"{stem}Tests.java"
        candidate = root / Path(*new_parts)
        if candidate.exists():
            _add_result(results, candidate, root)
