"""Python-specific test discovery helpers."""

from __future__ import annotations

from pathlib import Path

from .test_discovery_stems import (
    fixture_test_stems,
    module_family_test_stems,
    python_package_test_stems,
    related_stem_matches,
)


def find_python_specific_tests(
    source_path: Path,
    root: Path,
    test_dirs: list[str],
    results: list[str],
) -> None:
    """Find Python tests that need project-aware conventions."""
    for finder in (
        _find_python_package_tests,
        _find_python_family_tests,
        _find_fixture_tests,
    ):
        finder(source_path, root, test_dirs, results)
        if len(results) >= 10:
            return


def _find_python_package_tests(
    source_path: Path,
    root: Path,
    test_dirs: list[str],
    results: list[str],
) -> None:
    """Find package-level tests for plugin-style source modules."""
    rel = _relative_to_root(source_path, root)
    if rel is None:
        return

    patterns = [
        pattern
        for package_stem in _unique_stems(python_package_test_stems(rel))
        for pattern in (f"test_{package_stem}.py", f"test_{package_stem}_*.py")
    ]
    _add_pattern_matches(root, test_dirs, patterns, results)


def _find_fixture_tests(
    source_path: Path,
    root: Path,
    test_dirs: list[str],
    results: list[str],
) -> None:
    """Find tests that name the domain of a file under tests/fixtures."""
    rel = _relative_to_root(source_path, root)
    if rel is None:
        return

    if "fixtures" not in rel.parts:
        return

    _add_stem_named_tests(root, test_dirs, fixture_test_stems(rel), results)


def _find_python_family_tests(
    source_path: Path,
    root: Path,
    test_dirs: list[str],
    results: list[str],
) -> None:
    """Find tests for extracted helper modules that share a family stem."""
    _add_stem_named_tests(
        root, test_dirs, module_family_test_stems(source_path), results
    )


def _add_pattern_matches(
    root: Path,
    test_dirs: list[str],
    patterns: list[str],
    results: list[str],
) -> None:
    """Add tests matching one of the provided glob patterns."""
    for candidate in _iter_pattern_matches(root, test_dirs, patterns):
        _add_result(results, candidate, root)
        if len(results) >= 10:
            return


def _add_stem_named_tests(
    root: Path,
    test_dirs: list[str],
    stems: list[str],
    results: list[str],
) -> None:
    """Add tests whose test module stem matches one of the source stems."""
    for candidate in _iter_python_test_files(root, test_dirs):
        if _matches_any_stem(candidate.stem, stems):
            _add_result(results, candidate, root)
        if len(results) >= 10:
            return


def _iter_pattern_matches(
    root: Path,
    test_dirs: list[str],
    patterns: list[str],
) -> list[Path]:
    """Return sorted test files matching any glob pattern."""
    return sorted(
        candidate
        for dir_path in _existing_test_dirs(root, test_dirs)
        for pattern in patterns
        for candidate in dir_path.rglob(pattern)
    )


def _iter_python_test_files(root: Path, test_dirs: list[str]) -> list[Path]:
    """Return sorted Python test files from existing test directories."""
    return sorted(
        candidate
        for dir_path in _existing_test_dirs(root, test_dirs)
        for candidate in dir_path.rglob("test_*.py")
    )


def _existing_test_dirs(root: Path, test_dirs: list[str]) -> list[Path]:
    """Return test directories that exist in the project."""
    return [root / test_dir for test_dir in test_dirs if (root / test_dir).is_dir()]


def _matches_any_stem(test_stem: str, stems: list[str]) -> bool:
    """Return True when a test stem is related to any source stem."""
    return any(related_stem_matches(test_stem, stem) for stem in stems)


def _unique_stems(stems: list[str]) -> list[str]:
    """Return non-empty stems without duplicates, preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for stem in stems:
        if not stem or stem in seen:
            continue
        seen.add(stem)
        unique.append(stem)
    return unique


def _relative_to_root(path: Path, root: Path) -> Path | None:
    """Return path relative to root, or None for external paths."""
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def _add_result(results: list[str], candidate: Path, root: Path) -> None:
    """Add a test file to results if not already present.

    Forward-slash paths on every platform — see _add_result in
    test_discovery.py for the same normalisation.
    """
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = str(candidate)
    rel = rel.replace("\\", "/")
    if rel not in results:
        results.append(rel)
