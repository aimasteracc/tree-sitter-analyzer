"""Language readiness record builders for parser roadmap advice."""

from __future__ import annotations

import importlib
import importlib.util
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cli.parser_readiness_package import (
    parser_distribution_signals,
)

LOADER_ALIASES = {
    "csharp": ("csharp", "cs"),
    "typescript": ("typescript", "tsx"),
    "yaml": ("yaml", "yml"),
}
SCORE_WEIGHTS = {
    "parser_dependency_declared": 25,
    "loader_mapping": 20,
    "plugin_entrypoint": 20,
    "parser_installed": 10,
    "unit_tests": 15,
    "golden_masters": 10,
}
NEXT_STEP_RULES = (
    (
        "parser_dependency_declared",
        "Add tree-sitter parser dependency for {language} to pyproject.toml.",
    ),
    ("loader_mapping", "Add {language} to LanguageLoader.LANGUAGE_MODULES."),
    (
        "plugin_entrypoint",
        "Add {language} plugin entry point and language plugin module.",
    ),
    ("unit_tests", "Add unit tests for the {language} language plugin."),
    (
        "golden_masters",
        "Add {language} golden-master fixtures for output stability.",
    ),
)


def build_language_records(
    root: Path,
    report_languages: list[str],
    inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build readiness records for selected languages."""
    return [
        _build_language_record(
            root,
            language,
            inputs["parser_packages"],
            inputs["plugin_entrypoints"],
            inputs["loader_modules"],
        )
        for language in report_languages
    ]


def _build_language_record(
    project_root: Path,
    language: str,
    parser_packages: dict[str, dict[str, Any]],
    plugin_entrypoints: dict[str, str],
    loader_modules: dict[str, str],
) -> dict[str, Any]:
    parser_info = parser_packages.get(language, {})
    module_name = _module_name_for_language(language, parser_info, loader_modules)
    signals = _build_language_signals(
        project_root,
        language,
        parser_info,
        plugin_entrypoints,
        loader_modules,
        module_name,
    )
    record = _language_record_metadata(
        language,
        parser_info,
        plugin_entrypoints,
        _readiness_status(signals),
        _readiness_score(signals),
    )
    record.update(_language_record_actions(language, signals))
    return record


def _language_record_metadata(
    language: str,
    parser_info: dict[str, Any],
    plugin_entrypoints: dict[str, str],
    status: str,
    score: int,
) -> dict[str, Any]:
    """Return non-action fields for a language readiness record."""
    return {
        "language": language,
        "status": status,
        "score": score,
        "parser_package": parser_info.get("package", ""),
        "requirements": parser_info.get("requirements", []),
        "requirement_sources": parser_info.get("sources", []),
        "plugin_entrypoint_target": plugin_entrypoints.get(language, ""),
    }


def _language_record_actions(
    language: str,
    signals: dict[str, Any],
) -> dict[str, Any]:
    """Return action fields for a language readiness record."""
    return {
        "signals": signals,
        "next_steps": _next_steps(language, signals),
        "verification_commands": _verification_commands(language),
    }


def _build_language_signals(
    project_root: Path,
    language: str,
    parser_info: dict[str, Any],
    plugin_entrypoints: dict[str, str],
    loader_modules: dict[str, str],
    module_name: str,
) -> dict[str, Any]:
    """Build local and upstream-to-verify readiness signals for one language."""
    return {
        **_metadata_signals(language, parser_info, plugin_entrypoints, loader_modules),
        "parser_module": module_name,
        "parser_installed": _module_is_installed(module_name),
        **_artifact_signals(project_root, language),
        **_local_parser_package_signals(module_name, parser_info),
    }


def _metadata_signals(
    language: str,
    parser_info: dict[str, Any],
    plugin_entrypoints: dict[str, str],
    loader_modules: dict[str, str],
) -> dict[str, Any]:
    """Build local metadata presence signals."""
    return {
        "parser_dependency_declared": bool(parser_info),
        "plugin_entrypoint": language in plugin_entrypoints,
        "loader_mapping": _has_loader_mapping(language, loader_modules),
    }


def _artifact_signals(project_root: Path, language: str) -> dict[str, Any]:
    """Build local test and fixture presence signals."""
    tests_count = _count_matching_files(
        project_root / "tests" / "unit" / "languages",
        language,
    )
    golden_count = _count_matching_files(
        project_root / "tests" / "golden_masters",
        language,
    )
    return {
        "unit_tests": tests_count > 0,
        "unit_test_count": tests_count,
        "golden_masters": golden_count > 0,
        "golden_master_count": golden_count,
    }


def _local_parser_package_signals(
    module_name: str,
    parser_info: dict[str, Any],
) -> dict[str, Any]:
    """Return upstream-risk signals that can be checked from the local package."""
    signals = _unknown_upstream_signals()
    signals.update(parser_distribution_signals(parser_info.get("package", "")))
    if not module_name:
        return signals

    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return signals

    package_root = _package_root(spec)
    signals.update(
        {
            "parser_module_origin": str(spec.origin or ""),
            "upstream_grammar_json": _packaged_file_signal(
                package_root, "grammar.json"
            ),
            "upstream_external_scanner": _scanner_signal(package_root),
            "upstream_maintenance": "requires_online_check",
        }
    )
    signals.update(_parser_language_signals(module_name))
    return signals


def _unknown_upstream_signals() -> dict[str, Any]:
    """Return upstream parser signals that still need parser availability."""
    return {
        "parser_module_origin": "",
        "parser_package_version": "",
        "parser_project_urls": {},
        "parser_maintenance_urls": {},
        "parser_semantic_version": "",
        "upstream_parser_abi": "unknown_local_only",
        "upstream_grammar_json": "unknown_local_only",
        "upstream_external_scanner": "unknown_local_only",
        "upstream_maintenance": "unknown_local_only",
    }


def _package_root(spec: Any) -> Path | None:
    origin = getattr(spec, "origin", None)
    return Path(origin).parent if origin else None


def _parser_language_signals(module_name: str) -> dict[str, str]:
    try:
        import tree_sitter

        module = importlib.import_module(module_name)
        language_factory = getattr(module, "language", None)
        if not callable(language_factory):
            return {"upstream_parser_abi": "unavailable:no_language_factory"}
        language = tree_sitter.Language(language_factory())
        abi_version = getattr(language, "abi_version", None)
        semantic_version = getattr(language, "semantic_version", None)
        return {
            "parser_semantic_version": _semantic_version_text(semantic_version),
            "upstream_parser_abi": (
                f"local_binding_abi_{abi_version}"
                if abi_version
                else "unavailable:no_abi"
            ),
        }
    except Exception as exc:
        return {"upstream_parser_abi": f"unavailable:{type(exc).__name__}"}


def _semantic_version_text(semantic_version: Any) -> str:
    if not semantic_version:
        return ""
    return ".".join(map(str, semantic_version))


def _packaged_file_signal(package_root: Path | None, filename: str) -> str:
    if package_root is None or not package_root.exists():
        return "unknown_local_only"
    matches = sorted(package_root.rglob(filename))
    if not matches:
        return "not_packaged"
    return f"packaged:{_relative_display(package_root, matches[0])}"


def _scanner_signal(package_root: Path | None) -> str:
    if package_root is None or not package_root.exists():
        return "unknown_local_only"
    scanner_files = sorted(
        path
        for path in package_root.rglob("*")
        if path.is_file()
        and path.name.lower() in {"scanner.c", "scanner.cc", "scanner.cpp"}
    )
    if not scanner_files:
        return "not_packaged"
    return f"packaged:{_relative_display(package_root, scanner_files[0])}"


def _relative_display(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _module_is_installed(module_name: str) -> bool:
    return bool(module_name and importlib.util.find_spec(module_name))


def _module_name_for_language(
    language: str,
    parser_info: dict[str, Any],
    loader_modules: dict[str, str],
) -> str:
    for key in _loader_keys(language):
        if key in loader_modules:
            return loader_modules[key]
    package = parser_info.get("package")
    return package.replace("-", "_") if package else ""


def _has_loader_mapping(language: str, loader_modules: dict[str, str]) -> bool:
    return any(key in loader_modules for key in _loader_keys(language))


def _loader_keys(language: str) -> tuple[str, ...]:
    return LOADER_ALIASES.get(language, (language,))


def _count_matching_files(root: Path, language: str) -> int:
    if not root.exists():
        return 0
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and _path_matches_language(path, language)
    )


def _path_matches_language(path: Path, language: str) -> bool:
    parts = re.split(r"[^A-Za-z0-9]+", path.stem.lower())
    return language in parts


def _readiness_score(signals: dict[str, Any]) -> int:
    return sum(weight for signal, weight in SCORE_WEIGHTS.items() if signals[signal])


def _readiness_status(signals: dict[str, Any]) -> str:
    if _is_supported(signals):
        return "supported"
    if signals["plugin_entrypoint"]:
        return "needs_hardening"
    if signals["parser_dependency_declared"]:
        return "candidate"
    return "missing_parser_package"


def _is_supported(signals: dict[str, Any]) -> bool:
    return all(
        signals[name] for name in ("plugin_entrypoint", "loader_mapping", "unit_tests")
    )


def _next_steps(language: str, signals: dict[str, Any]) -> list[str]:
    steps = [
        template.format(language=language)
        for signal, template in NEXT_STEP_RULES
        if not signals[signal]
    ]
    return [*steps, *_upstream_next_steps(signals)]


def _upstream_next_steps(signals: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    _append_unresolved_parser_artifact_steps(steps, signals)
    if signals.get("upstream_maintenance") == "requires_online_check":
        maintenance_url = _maintenance_check_url(signals)
        suffix = f" at {maintenance_url}" if maintenance_url else ""
        steps.append(f"Check upstream parser maintenance{suffix}.")
    return steps


def _append_unresolved_parser_artifact_steps(
    steps: list[str],
    signals: dict[str, Any],
) -> None:
    abi = str(signals.get("upstream_parser_abi", ""))
    grammar = str(signals.get("upstream_grammar_json", ""))
    scanner = str(signals.get("upstream_external_scanner", ""))

    if abi in {"", "unknown_local_only"} or abi.startswith("unavailable:"):
        steps.append("Verify parser ABI compatibility upstream.")
    if grammar in {"", "unknown_local_only"}:
        steps.append("Verify upstream grammar.json generation.")
    elif grammar == "not_packaged":
        steps.append(
            "Confirm upstream grammar.json is reproducible; it is not packaged locally."
        )
    if scanner in {"", "unknown_local_only"}:
        steps.append("Check upstream external scanner risk.")
    elif scanner == "not_packaged":
        steps.append(
            "Confirm upstream scanner requirements; no scanner source is packaged locally."
        )


def _first_project_url(project_urls: dict[str, str]) -> str:
    if not project_urls:
        return ""
    return next(iter(project_urls.values()))


def _maintenance_check_url(signals: dict[str, Any]) -> str:
    maintenance_urls = signals.get("parser_maintenance_urls", {})
    if maintenance_urls:
        return maintenance_urls.get("releases") or maintenance_urls.get(
            "repository", ""
        )
    return _first_project_url(signals.get("parser_project_urls", {}))


def _verification_commands(language: str) -> list[str]:
    return [
        f"uv run tree-sitter-analyzer parser-readiness {language} --format json",
        f"uv run pytest tests/unit/languages/test_{language}_plugin.py -q",
        "uv run pytest tests/unit/test_agent_contracts.py::test_registered_mcp_tools_have_cli_parity -q",
    ]
