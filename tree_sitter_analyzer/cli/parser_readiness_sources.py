"""Local metadata source helpers for parser readiness advice."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Python 3.11+ ships tomllib in the stdlib; mypy under py3.10 target
# doesn't know about it. The runtime project requires-python is >=3.10
# so we fall back to the third-party `tomli` (already a transitive dep)
# on 3.10. The conditional import is fully resolved at module load.
if sys.version_info >= (3, 11):
    import tomllib  # noqa: I001
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from tree_sitter_analyzer.language_loader import LanguageLoader

TREE_SITTER_PREFIX = "tree-sitter-"
PACKAGE_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
PACKAGE_LANGUAGE_ALIASES = {
    "c-sharp": "csharp",
}
LANGUAGE_ALIASES = {
    "c#": "csharp",
    "c-sharp": "csharp",
    "cs": "csharp",
    "js": "javascript",
    "py": "python",
    "rb": "ruby",
    "ts": "typescript",
    "tsx": "typescript",
    "yml": "yaml",
}
WIKI_READINESS_SIGNALS = {
    "parser_abi": "verify upstream parser ABI compatibility",
    "grammar_json": "verify grammar.json is generated or reproducible",
    "external_scanner": "check scanner.c/scanner.cc install and portability risk",
    "maintenance": "check recent parser maintenance before committing roadmap work",
}


def collect_readiness_inputs(root: Path) -> dict[str, Any]:
    """Collect local metadata sources used by the readiness advisor."""
    pyproject = _load_pyproject(root)
    return {
        "parser_packages": _collect_parser_packages(pyproject),
        "plugin_entrypoints": _collect_plugin_entrypoints(pyproject),
        "loader_modules": _collect_loader_modules(),
    }


def parser_package_requirements(
    parser_packages: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Return parser package requirements keyed by normalized language."""
    return {
        language: info["requirements"]
        for language, info in sorted(parser_packages.items())
    }


def normalize_language(language: str) -> str:
    """Normalize aliases and punctuation in user-facing language names."""
    normalized = language.strip().lower().replace("_", "-")
    return LANGUAGE_ALIASES.get(normalized, normalized.replace("-", ""))


def select_report_languages(
    parser_packages: dict[str, dict[str, Any]],
    plugin_entrypoints: dict[str, str],
    *,
    requested_language: str | None,
    include_supported: bool,
) -> list[str]:
    """Choose which normalized languages should appear in the report."""
    if requested_language:
        return [requested_language]
    candidate_languages = set(parser_packages) - set(plugin_entrypoints)
    if include_supported:
        candidate_languages |= set(plugin_entrypoints)
    return sorted(candidate_languages)


def _load_pyproject(project_root: Path) -> dict[str, Any]:
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return {}
    with pyproject_path.open("rb") as handle:
        return tomllib.load(handle)


def _collect_parser_packages(pyproject: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    project = pyproject.get("project", {})
    for requirement in project.get("dependencies", []):
        _add_parser_requirement(packages, requirement, "core")
    optional = project.get("optional-dependencies", {})
    for extra_name, requirements in optional.items():
        _add_extra_parser_requirements(packages, extra_name, requirements)
    return packages


def _add_extra_parser_requirements(
    packages: dict[str, dict[str, Any]],
    extra_name: str,
    requirements: list[str],
) -> None:
    for requirement in requirements:
        _add_parser_requirement(packages, requirement, f"extra:{extra_name}")


def _add_parser_requirement(
    packages: dict[str, dict[str, Any]],
    requirement: str,
    source: str,
) -> None:
    package_name = _requirement_package_name(requirement)
    if not _is_parser_package(package_name):
        return
    language = _package_language(package_name)
    entry = packages.setdefault(
        language,
        {"package": package_name, "requirements": [], "sources": []},
    )
    _append_unique(entry["requirements"], requirement)
    _append_unique(entry["sources"], source)


def _is_parser_package(package_name: str) -> bool:
    return bool(package_name and package_name.startswith(TREE_SITTER_PREFIX))


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _requirement_package_name(requirement: str) -> str:
    match = PACKAGE_NAME_RE.match(requirement)
    return match.group(1).lower().replace("_", "-") if match else ""


def _package_language(package_name: str) -> str:
    raw = package_name.removeprefix(TREE_SITTER_PREFIX)
    return PACKAGE_LANGUAGE_ALIASES.get(raw, raw)


def _collect_plugin_entrypoints(pyproject: dict[str, Any]) -> dict[str, str]:
    project = pyproject.get("project", {})
    entry_points = project.get("entry-points", {})
    plugins = entry_points.get("tree_sitter_analyzer.plugins", {})
    return {
        normalize_language(language): target
        for language, target in plugins.items()
        if isinstance(target, str)
    }


def _collect_loader_modules() -> dict[str, str]:
    return {
        normalize_language(language): module
        for language, module in LanguageLoader.LANGUAGE_MODULES.items()
    }
