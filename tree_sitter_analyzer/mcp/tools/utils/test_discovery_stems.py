"""Stem derivation helpers for language-aware test discovery."""

from __future__ import annotations

import re
from pathlib import Path

__test__ = False


def related_test_stems_for_path(file_path: str | Path) -> list[str]:
    """Return non-filename stems that can connect a file to tests."""
    stems = python_package_test_stems(file_path)
    stems.extend(module_family_test_stems(file_path))
    stems.extend(fixture_test_stems(file_path))
    return _unique_nonempty_stems(stems)


def source_subsystem_stems(
    file_path: str | Path,
    known_files: set[str] | None = None,
) -> list[str]:
    """Return generic source-path scopes for disambiguating test matches."""
    normalized = Path(str(file_path).replace("\\", "/"))
    parents = list(normalized.parts[:-1])
    source_roots = {"app", "apps", "lib", "package", "packages", "pkg", "src"}
    strict_root_indexes = [
        index for index, part in enumerate(parents) if part.lower() in {"lib", "src"}
    ]
    root_index = next(
        (
            index
            for index, part in enumerate(parents)
            if part.lower() in source_roots
        ),
        None,
    )
    if strict_root_indexes:
        root_index = strict_root_indexes[0]
    if root_index is not None:
        package_prefix = parents[:root_index]
        nested_package_markers = {"app", "apps", "package", "packages", "pkg"}
        marker_indexes = [
            index
            for index, part in enumerate(package_prefix)
            if part.lower() in nested_package_markers
        ]
        if marker_indexes:
            package_scope = package_prefix[marker_indexes[-1] + 1 :]
        else:
            package_scope = package_prefix[-1:]
        parents = [*package_scope, *parents[root_index + 1 :]]
    elif len(parents) > 1:
        # A leading package directory is not a subsystem. This covers both this
        # repository and arbitrary projects without hard-coding a package name.
        parents = parents[1:]
    elif parents and known_files is not None:
        package_init = f"{parents[0]}/__init__.py"
        windows_package_init = package_init.replace("/", "\\")
        if package_init in known_files or windows_package_init in known_files:
            parents = []

    structural_parts = {"mcp", "tool", "tools", "util", "utils"}
    stems: list[str] = []
    structural_stems: list[str] = []
    for part in reversed(parents):
        if not part or part.startswith("."):
            continue
        normalized_part = _normalize_module_identifier(part)
        if normalized_part in structural_parts:
            structural_stems.append(normalized_part)
            continue
        stems.append(normalized_part)
        if normalized_part.endswith("s") and len(normalized_part) > 4:
            stems.append(normalized_part[:-1])
    return _unique_nonempty_stems(stems or structural_stems)


def test_path_is_unscoped(test_file: str) -> bool:
    """Return whether a test sits directly in a generic test collection root."""
    parts = list(Path(test_file.replace("\\", "/")).parts[:-1])
    test_roots = {"__tests__", "spec", "test", "tests"}
    root_indexes = [
        index for index, part in enumerate(parts) if part.lower() in test_roots
    ]
    if root_indexes:
        test_root_index = root_indexes[-1]
        if test_root_index > 0:
            return False
        parts = parts[test_root_index + 1 :]

    generic_tiers = {
        "acceptance",
        "benchmark",
        "benchmarks",
        "contract",
        "contracts",
        "e2e",
        "fast",
        "functional",
        "governance",
        "integration",
        "performance",
        "regression",
        "slow",
        "smoke",
        "system",
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
    changed_package = _monorepo_package_identity(changed_file)
    test_package = _monorepo_package_identity(test_file)
    if test_package is not None and (
        changed_package is None or changed_package != test_package
    ):
        return None
    test_parts: set[str] = set()
    for part in normalized_test.parts[:-1]:
        normalized_part = _normalize_module_identifier(part)
        test_parts.add(normalized_part)
        if normalized_part.startswith("test_"):
            test_parts.add(normalized_part[len("test_") :])
    test_stem = _normalize_module_identifier(normalized_test.stem)
    for rank, subsystem_stem in enumerate(subsystem_stems):
        if subsystem_stem in test_parts or related_stem_matches(
            test_stem,
            subsystem_stem,
        ):
            return rank
    return None


def test_paths_have_compatible_package_scope(
    test_file: str,
    changed_file: str,
) -> bool:
    """Return whether a test can cover the changed path's package scope."""
    changed_package = _monorepo_package_identity(changed_file)
    test_package = _monorepo_package_identity(test_file)
    return test_package is None or (
        changed_package is not None and changed_package == test_package
    )


def test_file_subject_stem(test_file: str) -> str:
    """Return the source-module subject encoded by a runnable test filename."""
    return _normalize_module_identifier(raw_test_file_subject_stem(test_file))


def raw_test_file_subject_stem(test_file: str) -> str:
    """Return a test's source-module subject while preserving identifier case."""
    normalized = Path(test_file.replace("\\", "/"))
    stem = normalized.stem
    if normalized.suffix.lower() == ".java" and stem.endswith("Test"):
        stem = stem[: -len("Test")]
    elif stem.startswith("test_"):
        stem = stem[len("test_") :]
    else:
        for suffix in (".test", ".spec", "_test", "_spec"):
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
    return stem


def module_stem_for_path(file_path: str | Path) -> str:
    """Return a cross-language normalized source-module stem."""
    return _normalize_module_identifier(raw_module_stem_for_path(file_path))


def raw_module_stem_for_path(file_path: str | Path) -> str:
    """Return a source module stem while preserving identifier case."""
    normalized = Path(str(file_path).replace("\\", "/"))
    return normalized.stem


def _normalize_module_identifier(stem: str) -> str:
    """Normalize snake, kebab, dotted, and CamelCase module identifiers."""
    if stem.startswith("__") and stem.endswith("__"):
        return stem.lower()
    acronym_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", stem)
    snake_stem = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", acronym_split)
    return snake_stem.lower().replace("-", "_").replace(".", "_").lstrip("_")


def _monorepo_package_identity(file_path: str | Path) -> str | None:
    """Return the full package lineage encoded by monorepo containers."""
    normalized = Path(str(file_path).replace("\\", "/"))
    parts = normalized.parts[:-1]
    test_roots = {"__tests__", "spec", "test", "tests"}
    test_root_index = next(
        (
            index
            for index, part in enumerate(parts)
            if part.lower() in test_roots
        ),
        len(parts),
    )
    package_lineage: list[str] = []
    for index, part in enumerate(parts[:-1]):
        if part.lower() not in {"apps", "packages"}:
            continue
        if index > test_root_index:
            continue
        package_part = parts[index + 1]
        if not package_part or package_part.startswith("."):
            continue
        package_parts = [package_part]
        if package_part.startswith("@") and index + 2 < len(parts):
            scoped_name = parts[index + 2]
            if scoped_name and not scoped_name.startswith("."):
                package_parts.append(scoped_name)
        container = _normalize_module_identifier(part)
        package = "/".join(
            _normalize_module_identifier(component) for component in package_parts
        )
        package_lineage.append(f"{container}/{package}")
    return "/".join(package_lineage) or None


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
    is_repository_source = "tree_sitter_analyzer" in normalized.parts[:-1]
    if (
        is_repository_source
        and normalized.stem == "evaluator"
        and "constraints" in normalized.parts[:-1]
    ):
        stems.append("constraint_dsl")
    if (
        is_repository_source
        and "edge_extractors" in normalized.parts[:-1]
        and normalized.stem == "java"
    ):
        stems.append("project_summary_pagerank")
    if is_repository_source and normalized.stem == "test_discovery_stems":
        stems.append("change_impact_tool_execute_and_mapping")
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
