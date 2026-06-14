#!/usr/bin/env python3
"""
Language-aware test file discovery.

Finds test files for a given source file using language-specific naming
conventions (test_*.py, *Test.java, *_test.go, etc.).
"""

import ast
import re
from pathlib import Path

from .test_discovery_languages import find_language_specific_tests
from .test_discovery_predicates import is_existing_test_file as _is_existing_test_file
from .test_discovery_stems import (
    fixture_test_stems,
    module_family_test_stems,
    python_package_test_stems,
    related_stem_matches,
    related_test_stems_for_path,
)

__all__ = [
    "detect_language_from_ext",
    "find_test_files",
    "fixture_test_stems",
    "module_family_test_stems",
    "python_package_test_stems",
    "related_stem_matches",
    "related_test_stems_for_path",
]

# Language → test file naming patterns
_TEST_PATTERNS: dict[str, list[str]] = {
    "python": [
        "test_{stem}.py",
        "test_{stem}_*.py",
        "{stem}_test.py",
        "{stem}_tests.py",
    ],
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
    if _is_existing_test_file(p, root, language):
        _add_result(results, p, root)

    patterns = _TEST_PATTERNS.get(language, ["test_{stem}.py"])
    test_dirs = _TEST_DIRS.get(language, ["tests"])

    _find_pattern_tests(root, stem, patterns, test_dirs, results)
    _find_colocated_tests(p, stem, patterns, root, results)
    _find_symbol_reference_tests(p, language, root, results)
    find_language_specific_tests(
        p,
        stem,
        language,
        root,
        _TEST_DIRS.get("python", ["tests"]),
        results,
    )

    return results[:10]


def _find_pattern_tests(
    root: Path,
    stem: str,
    patterns: list[str],
    test_dirs: list[str],
    results: list[str],
) -> None:
    """Find tests in common test directories using language patterns."""
    for pattern in patterns:
        test_filename = _format_pattern(pattern, stem)
        for test_dir in test_dirs:
            _add_direct_test_candidate(root / test_dir / test_filename, root, results)
            _find_recursive_test_candidates(
                root / test_dir, test_filename, root, results
            )


def _add_direct_test_candidate(candidate: Path, root: Path, results: list[str]) -> None:
    """Add a candidate path when it exists."""
    if candidate.exists():
        _add_result(results, candidate, root)


def _find_recursive_test_candidates(
    test_dir: Path,
    test_filename: str,
    root: Path,
    results: list[str],
) -> None:
    """Find matching tests recursively within a test directory."""
    if not test_dir.is_dir():
        return
    for candidate in test_dir.rglob(test_filename):
        _add_result(results, candidate, root)
        if len(results) >= 10:
            break


def _find_colocated_tests(
    source_path: Path,
    stem: str,
    patterns: list[str],
    root: Path,
    results: list[str],
) -> None:
    """Find tests next to the source file."""
    for pattern in patterns:
        candidate = source_path.parent / _format_pattern(pattern, stem)
        _add_direct_test_candidate(candidate, root, results)


def _format_pattern(pattern: str, stem: str) -> str:
    """Format a test file pattern with the source file stem."""
    return pattern.replace("{stem}", stem).replace("{Stem}", stem.capitalize())


def _add_result(results: list[str], candidate: Path, root: Path) -> None:
    """Add a test file to results if not already present.

    Returned paths use forward slashes on every platform so callers
    (agent prompts, MCP envelopes, tests) get a stable shape regardless
    of host OS.
    """
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = str(candidate)
    rel = rel.replace("\\", "/")
    if rel not in results:
        results.append(rel)


def _find_symbol_reference_tests(
    source_path: Path,
    language: str,
    root: Path,
    results: list[str],
) -> None:
    """Union proximity matches with tests that reference public source symbols."""
    if language != "python" or not source_path.exists():
        return
    symbols = _python_public_symbols(source_path)
    if not symbols:
        return
    source_modules = _python_source_module_names(source_path, root)
    if not source_modules:
        return
    symbol_re = re.compile(
        r"\b(?:" + "|".join(re.escape(sym) for sym in symbols) + r")\b"
    )
    matches: list[tuple[int, str, Path]] = []
    for test_dir in _TEST_DIRS.get("python", ["tests"]):
        base = root / test_dir
        if not base.is_dir():
            continue
        for candidate in base.rglob("test_*.py"):
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not _file_imports_source_module(text, source_modules, source_path):
                continue
            hit_count = len(symbol_re.findall(text))
            if hit_count:
                matches.append((-hit_count, candidate.as_posix(), candidate))
    for _, _, candidate in sorted(matches):
        _add_result(results, candidate, root)


def _python_public_symbols(source_path: Path) -> list[str]:
    """Extract public Python def/class names with a cheap line-based scan."""
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    symbols: list[str] = []
    for match in re.finditer(
        r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_]\w*)\b", text, re.M
    ):
        name = match.group(1)
        if not name.startswith("_") and name not in symbols:
            symbols.append(name)
    return symbols


def _python_source_module_names(source_path: Path, root: Path) -> set[str]:
    """Return likely Python import module names for the source file."""
    source_rel = source_path.resolve()
    try:
        rel = source_rel.relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = source_rel.name

    parts = rel.removesuffix(".py").split("/")
    if not parts or parts == ["."]:
        return set()
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()

    modules: set[str] = set()
    for idx in range(len(parts)):
        modules.add(".".join(parts[idx:]))
    modules.add(parts[-1])
    return modules


def _file_imports_source_module(
    text: str,
    source_modules: set[str],
    source_path: Path,
) -> bool:
    """Return True when AST imports explicitly reference the source module.

    This keeps symbol-reference matches tied to real Python imports.
    """
    try:
        root = ast.parse(text)
    except SyntaxError:
        return False
    source_stem = source_path.stem
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for name in node.names:
                if _matches_import_name(name.name, source_modules):
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.module is not None and _matches_import_name(module, source_modules):
                return True
            if node.level > 0 and node.module is None:
                for alias in node.names:
                    if alias.name in source_modules or alias.name == source_stem:
                        return True
    return False


def _matches_import_name(import_name: str, source_modules: set[str]) -> bool:
    """Return whether an import target matches a source module variant."""
    for module in source_modules:
        if import_name == module:
            return True
        if import_name.startswith(module + "."):
            return True
        if import_name.endswith("." + module):
            return True
    return False
