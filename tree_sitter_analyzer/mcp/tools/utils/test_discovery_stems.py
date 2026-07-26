"""Stem derivation helpers for language-aware test discovery."""

from __future__ import annotations

from pathlib import Path


def related_test_stems_for_path(file_path: str | Path) -> list[str]:
    """Return non-filename stems that can connect a file to tests."""
    stems = python_package_test_stems(file_path)
    stems.extend(module_family_test_stems(file_path))
    stems.extend(fixture_test_stems(file_path))
    return _unique_nonempty_stems(stems)


def source_subsystem_stems(file_path: str | Path) -> list[str]:
    """Return generic source-path scopes for disambiguating test matches."""
    normalized = Path(str(file_path).replace("\\", "/"))
    parents = list(normalized.parts[:-1])
    source_roots = {"app", "apps", "lib", "package", "packages", "pkg", "src"}
    root_indexes = [
        index for index, part in enumerate(parents) if part.lower() in source_roots
    ]
    if root_indexes:
        parents = parents[root_indexes[-1] + 1 :]
    elif parents:
        # A leading package directory is not a subsystem. This covers both this
        # repository and arbitrary projects without hard-coding a package name.
        parents = parents[1:]

    structural_parts = {"mcp", "tool", "tools", "util", "utils"}
    stems: list[str] = []
    for part in reversed(parents):
        normalized_part = part.lower().replace("-", "_")
        if (
            not normalized_part
            or normalized_part.startswith(".")
            or normalized_part in structural_parts
        ):
            continue
        stems.append(normalized_part)
        if normalized_part.endswith("s") and len(normalized_part) > 4:
            stems.append(normalized_part[:-1])
    return _unique_nonempty_stems(stems)


def test_path_is_unscoped(test_file: str) -> bool:
    """Return whether a test sits directly in a generic test collection root."""
    parts = list(Path(test_file.replace("\\", "/")).parts[:-1])
    test_roots = {"__tests__", "spec", "test", "tests"}
    root_indexes = [
        index for index, part in enumerate(parts) if part.lower() in test_roots
    ]
    if root_indexes:
        parts = parts[root_indexes[-1] + 1 :]

    generic_tiers = {
        "benchmark",
        "benchmarks",
        "contract",
        "contracts",
        "e2e",
        "functional",
        "governance",
        "integration",
        "performance",
        "regression",
        "unit",
    }
    while parts and parts[0].lower() in generic_tiers:
        parts.pop(0)
    return not parts


def test_path_subsystem_affinity_rank(
    test_file: str,
    changed_file: str,
) -> int | None:
    """Return the nearest matching source-subsystem rank for a test."""
    subsystem_stems = source_subsystem_stems(changed_file)
    if not subsystem_stems:
        return None

    normalized_test = Path(test_file.replace("\\", "/"))
    test_parts = {
        part.lower().replace("-", "_") for part in normalized_test.parts[:-1]
    }
    test_stem = normalized_test.stem.lower().replace("-", "_")
    for rank, subsystem_stem in enumerate(subsystem_stems):
        if subsystem_stem in test_parts or related_stem_matches(
            test_stem,
            subsystem_stem,
        ):
            return rank
    return None


def test_file_has_exact_module_stem(test_file: str, changed_file: str) -> bool:
    """Return whether a test filename exactly names the changed module."""
    changed_stem = Path(changed_file).stem.lower()
    test_stem = Path(test_file).stem.lower()
    if test_stem.endswith(".test"):
        test_stem = test_stem[: -len(".test")]
    if test_stem.endswith(".spec"):
        test_stem = test_stem[: -len(".spec")]
    return test_stem in {
        f"test_{changed_stem}",
        f"{changed_stem}_test",
        f"{changed_stem}_spec",
    }


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
        # r37q (dogfood): ``parser_readiness_records.py`` is exercised
        # via ``test_parser_readiness_records.py`` AND via
        # ``test_parser_readiness.py`` (indirect). Without this
        # suffix safe_to_edit reports ``tests=no`` for split helper
        # modules like ``*_records`` and ``*_sources`` even when their
        # parent module is well-tested.
        "_records",
        "_response",
        "_risk",
        "_smells",
        "_sources",
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
