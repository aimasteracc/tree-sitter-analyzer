"""Canonical inventory of mechanically observable language pipeline surfaces.

Dimensions report registration/loadability evidence only. In particular, a
resolver slot and dispatch-key intersection do not prove positive cross-file
callee binding; that requires a dedicated end-to-end fixture.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.function_extraction import (
    _CALL_DISPATCH,
    _CALL_NODE_TYPES,
    _FUNC_DEF_TYPES,
    _FUNC_NAME_DISPATCH,
)
from tree_sitter_analyzer.import_extractors import IMPORT_DISPATCH
from tree_sitter_analyzer.languages.lang_extension_map import supported_languages
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.route_detector import ROUTE_LANGUAGE_DISPATCH
from tree_sitter_analyzer.synapse_resolver import (
    languages as _resolver_languages,  # noqa: F401
)
from tree_sitter_analyzer.synapse_resolver._registry import registered_languages

DISPLAY_NAMES = {
    "bash": "Bash",
    "c": "C",
    "cpp": "C++",
    "csharp": "C#",
    "css": "CSS",
    "go": "Go",
    "html": "HTML",
    "java": "Java",
    "javascript": "JavaScript",
    "json": "JSON",
    "kotlin": "Kotlin",
    "lua": "Lua",
    "markdown": "Markdown",
    "php": "PHP",
    "python": "Python",
    "ruby": "Ruby",
    "rust": "Rust",
    "scala": "Scala",
    "sql": "SQL",
    "swift": "Swift",
    "typescript": "TypeScript",
    "yaml": "YAML",
}
DATA_MARKUP_LANGUAGES = frozenset({"css", "html", "markdown", "sql", "yaml"})
SCAFFOLD_LANGUAGES = frozenset({"json"})

CAPABILITY_COLUMNS = (
    "plugin_discovery",
    "extractor_loadability",
    "index_admission",
    "import_dispatch",
    "call_dispatch",
    "resolver_slot",
    "framework_dispatch",
    "cross_file_call",
    "data_markup",
    "scaffold",
)
BOOLEAN_COLUMNS = tuple(c for c in CAPABILITY_COLUMNS if c != "cross_file_call")
CROSS_FILE_STATES = ("verified", "unknown", "not_applicable")
EVIDENCE = {
    "plugin_discovery": "PluginManager local discovery, checked against the built-in product list",
    "extractor_loadability": "PluginManager.get_plugin plus create_extractor (fail closed)",
    "index_admission": "languages.lang_extension_map.supported_languages",
    "import_dispatch": "import_extractors.IMPORT_DISPATCH keys",
    "call_dispatch": "function_extraction node tables plus executable definition/call handler registries",
    "resolver_slot": "synapse_resolver registration plus documented Python fallback",
    "framework_dispatch": "route_detector.ROUTE_LANGUAGE_DISPATCH keys",
    "cross_file_call": "tri-state: verified requires a positive end-to-end cross-file fixture; unknown means none is registered",
    "data_markup": "language_inventory.DATA_MARKUP_LANGUAGES",
    "scaffold": "language_inventory.SCAFFOLD_LANGUAGES",
}


def _load_builtin_plugins() -> dict[str, Any]:
    """Load every built-in plugin and extractor, raising on any discrepancy."""
    manager = PluginManager()
    manager.load_plugins()
    discovered = frozenset(manager._plugin_modules)  # canonical manager discovery
    expected = frozenset(DISPLAY_NAMES)
    if discovered != expected:
        raise RuntimeError(
            f"built-in plugin discovery mismatch: missing={sorted(expected - discovered)}, "
            f"unexpected={sorted(discovered - expected)}"
        )
    loaded: dict[str, Any] = {}
    for language in sorted(discovered):
        plugin = manager.get_plugin(language)
        if plugin is None or plugin.get_language_name() != language:
            raise RuntimeError(f"failed to load built-in plugin: {language}")
        expected_module = manager._plugin_modules[language]
        actual_module = plugin.__class__.__module__
        if actual_module != expected_module and not actual_module.startswith(
            f"{expected_module}."
        ):
            raise RuntimeError(
                f"wrong origin for built-in plugin {language}: "
                f"expected {expected_module} module tree, got {actual_module}"
            )
        try:
            extractor = plugin.create_extractor()
        except Exception as exc:
            raise RuntimeError(f"failed to create extractor: {language}") from exc
        if extractor is None:
            raise RuntimeError(f"plugin returned no extractor: {language}")
        loaded[language] = extractor
    return loaded


def build_inventory() -> dict[str, Any]:
    """Return the deterministic inventory without claiming unproved E2E binding."""
    extractors = _load_builtin_plugins()
    plugins = frozenset(extractors)
    index_languages = frozenset(supported_languages())
    import_languages = frozenset(IMPORT_DISPATCH)
    call_languages = (
        frozenset(_FUNC_DEF_TYPES)
        & frozenset(_CALL_NODE_TYPES)
        & frozenset(_FUNC_NAME_DISPATCH)
        & frozenset(_CALL_DISPATCH)
    )
    resolver_languages = frozenset(registered_languages()) | {"python"}
    pipeline_registered = (
        index_languages & import_languages & call_languages & resolver_languages
    )

    rows = []
    for language in sorted(plugins):
        capabilities: dict[str, Any] = {
            "plugin_discovery": True,
            "extractor_loadability": True,
            "index_admission": language in index_languages,
            "import_dispatch": language in import_languages,
            "call_dispatch": language in call_languages,
            "resolver_slot": language in resolver_languages,
            "framework_dispatch": language in ROUTE_LANGUAGE_DISPATCH,
            "cross_file_call": "unknown"
            if language in pipeline_registered
            else "not_applicable",
            "data_markup": language in DATA_MARKUP_LANGUAGES,
            "scaffold": language in SCAFFOLD_LANGUAGES,
        }
        rows.append(
            {
                "language": language,
                "display_name": DISPLAY_NAMES[language],
                "tier": _tier(capabilities),
                **capabilities,
            }
        )

    counts: dict[str, Any] = {
        column: sum(bool(row[column]) for row in rows) for column in BOOLEAN_COLUMNS
    }
    counts["cross_file_call"] = {
        state: sum(row["cross_file_call"] == state for row in rows)
        for state in CROSS_FILE_STATES
    }
    tier_names = (
        "pipeline_registered",
        "index_admitted",
        "call_dispatch_only",
        "data_markup",
        "scaffold",
    )
    tier_counts = {
        tier: sum(row["tier"] == tier for row in rows) for tier in tier_names
    }
    return {
        "schema_version": 2,
        "evidence": EVIDENCE,
        "counts": counts,
        "tier_counts": tier_counts,
        "languages": rows,
    }


def _tier(capabilities: dict[str, Any]) -> str:
    if capabilities["scaffold"]:
        return "scaffold"
    if capabilities["data_markup"]:
        return "data_markup"
    if all(
        capabilities[c]
        for c in (
            "index_admission",
            "import_dispatch",
            "call_dispatch",
            "resolver_slot",
        )
    ):
        return "pipeline_registered"
    if capabilities["index_admission"]:
        return "index_admitted"
    if capabilities["call_dispatch"]:
        return "call_dispatch_only"
    raise ValueError("plugin has no classified product tier")
