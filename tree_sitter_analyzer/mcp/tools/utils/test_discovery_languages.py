"""Language-specific test discovery conventions."""

from __future__ import annotations

from pathlib import Path

from .test_discovery_python import find_python_specific_tests


def find_language_specific_tests(
    source_path: Path,
    stem: str,
    language: str,
    root: Path,
    python_test_dirs: list[str],
    results: list[str],
) -> None:
    """Run extra test discovery conventions for languages that need them."""
    if language == "java":
        _find_java_tests(source_path, stem, root, results)
    if language == "python":
        find_python_specific_tests(source_path, root, python_test_dirs, results)
    if language == "go":
        _add_direct_test_candidate(
            source_path.parent / f"{stem}_test.go", root, results
        )
    if language == "ruby":
        _find_ruby_spec_tests(stem, root, results)


def _find_ruby_spec_tests(
    stem: str,
    root: Path,
    results: list[str],
) -> None:
    """Find Ruby spec files under the project spec directory."""
    spec_dir = root / "spec"
    if not spec_dir.exists():
        return
    for spec_file in spec_dir.rglob(f"{stem}_spec.rb"):
        _add_result(results, spec_file, root)


def _find_java_tests(
    source_path: Path,
    stem: str,
    root: Path,
    results: list[str],
) -> None:
    """Find Java test files using Maven/Gradle directory conventions."""
    try:
        rel = source_path.relative_to(root)
    except ValueError:
        return

    mirrored_parts = _mirror_main_to_test_parts(rel.parts)
    if mirrored_parts is None:
        return

    for suffix in ("Test.java", "Tests.java"):
        candidate = root / Path(*mirrored_parts[:-1], f"{stem}{suffix}")
        _add_direct_test_candidate(candidate, root, results)


def _mirror_main_to_test_parts(parts: tuple[str, ...]) -> list[str] | None:
    """Mirror a Java source path from src/main/java to src/test/java."""
    mirrored: list[str] = []
    replaced = False
    for part in parts:
        if part == "main" and not replaced:
            mirrored.append("test")
            replaced = True
        else:
            mirrored.append(part)
    return mirrored if replaced else None


def _add_direct_test_candidate(candidate: Path, root: Path, results: list[str]) -> None:
    """Add a candidate path when it exists."""
    if candidate.exists():
        _add_result(results, candidate, root)


def _add_result(results: list[str], candidate: Path, root: Path) -> None:
    """Add a test file to results if not already present."""
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = str(candidate)
    if rel not in results:
        results.append(rel)
