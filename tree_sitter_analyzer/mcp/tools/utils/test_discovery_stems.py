"""Stem derivation helpers for language-aware test discovery."""

from __future__ import annotations

from pathlib import Path


def related_test_stems_for_path(file_path: str | Path) -> list[str]:
    """Return non-filename stems that can connect a file to tests."""
    stems = python_package_test_stems(file_path)
    stems.extend(module_family_test_stems(file_path))
    stems.extend(fixture_test_stems(file_path))
    return _unique_nonempty_stems(stems)


def python_package_test_stems(file_path: str | Path) -> list[str]:
    """Return package-level test stems for Python plugin-style source modules."""
    normalized = Path(str(file_path).replace("\\", "/"))
    if normalized.suffix != ".py":
        return []

    stems: list[str] = []
    for index, part in enumerate(normalized.parts[:-1]):
        if part.endswith("_plugin"):
            stems.append(part)
        if index > 0 and normalized.parts[index - 1] == "languages":
            stems.append(part)

    return _unique_nonempty_stems(stems)


def module_family_test_stems(file_path: str | Path) -> list[str]:
    """Return broader stems for extracted Python implementation modules."""
    normalized = Path(str(file_path).replace("\\", "/"))
    if normalized.suffix != ".py":
        return []

    suffixes = (
        "_agent_summary",
        "_analysis",
        "_analyzer",
        "_blocks",
        "_classes",
        "_execution",
        "_helper",
        "_helpers",
        "_git",
        "_implementation",
        "_impl",
        "_languages",
        "_logic",
        "_mode",
        "_modes",
        "_predicates",
        "_python",
        "_response",
        "_risk",
        "_smells",
        "_stems",
        "_treesitter",
        "_validation",
        "_validator",
        "_validators",
        "_verification",
    )
    stems = _special_module_family_stems(normalized.stem)
    stems.extend(_strip_family_suffixes(normalized.stem, suffixes))
    return _unique_nonempty_stems(stems)


def fixture_test_stems(file_path: str | Path) -> list[str]:
    """Return test-name stems implied by a tests/fixtures path."""
    normalized = Path(str(file_path).replace("\\", "/"))
    parts = normalized.parts
    if "fixtures" not in parts:
        return []

    fixture_index = parts.index("fixtures")
    fixture_parts = list(parts[fixture_index + 1 : -1])
    fixture_parts.append(normalized.stem)

    stems: list[str] = []
    for part in fixture_parts:
        if not part:
            continue
        stems.append(part)
        stems.extend(_stripped_fixture_stems(part))

    return _unique_nonempty_stems(stems)


def related_stem_matches(test_stem: str, related_stem: str) -> bool:
    """Return True when a derived stem is specific enough for a test name."""
    if "_" in related_stem or len(related_stem) > 6:
        return related_stem in test_stem
    return test_stem == f"test_{related_stem}" or test_stem.startswith(
        f"test_{related_stem}_"
    )


def _special_module_family_stems(stem: str) -> list[str]:
    """Return family stems for helper modules that do not share a direct name."""
    if stem.lstrip("_") == "refactoring_plan_builder":
        return ["refactoring_suggestions"]
    return []


def _stripped_fixture_stems(part: str) -> list[str]:
    """Return useful stems after removing common fixture suffixes."""
    stems: list[str] = []
    for suffix in (
        "_fixture",
        "_fixtures",
        "_sample",
        "_samples",
        "_data",
        "_project",
    ):
        if part.endswith(suffix):
            stripped = part[: -len(suffix)]
            if len(stripped) >= 3:
                stems.append(stripped)
    return stems


def _strip_family_suffixes(stem: str, suffixes: tuple[str, ...]) -> list[str]:
    """Return stems produced by peeling one or more helper suffixes."""
    stripped_stems: list[str] = []
    frontier = [stem]
    seen = {stem}

    while frontier:
        current = frontier.pop(0)
        for suffix in suffixes:
            if not current.endswith(suffix):
                continue
            stripped = current[: -len(suffix)]
            if len(stripped) < 3 or stripped in seen:
                continue
            seen.add(stripped)
            stripped_stems.append(stripped)
            frontier.append(stripped)

    return stripped_stems


def _unique_nonempty_stems(stems: list[str]) -> list[str]:
    """Return stems without duplicates while preserving order."""
    unique_stems: list[str] = []
    for stem in stems:
        if stem and stem not in unique_stems:
            unique_stems.append(stem)
    return unique_stems
