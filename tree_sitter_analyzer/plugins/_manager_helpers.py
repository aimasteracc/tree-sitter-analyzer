"""Helper functions for :mod:`tree_sitter_analyzer.plugins.manager`."""

import importlib
import importlib.metadata
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..utils import log_debug, log_error, log_warning
from .base import LanguagePlugin

LogFn = Callable[[str], None]
SubClassCheck = Callable[[Any, type[LanguagePlugin]], bool]
ClassFinder = Callable[[Any], list[type[LanguagePlugin]]]


@dataclass(frozen=True)
class PluginLoggers:
    """Logger callbacks used by plugin manager helpers."""

    debug: LogFn = log_debug
    warning: LogFn = log_warning
    error: LogFn = log_error


PLUGIN_ALIASES = {
    "js": "javascript",
    "py": "python",
    "rb": "ruby",
    "ts": "typescript",
}
REQUIRED_PLUGIN_METHODS = (
    "get_language_name",
    "get_file_extensions",
    "create_extractor",
    "analyze_file",
    "get_tree_sitter_language",
)


def default_aliases() -> list[str]:
    """Return default language aliases."""
    return list(PLUGIN_ALIASES)


def discover_entry_points(
    entry_point_group: str,
    *,
    debug: LogFn = log_debug,
    warning: LogFn = log_warning,
) -> dict[str, Any]:
    """Discover entry point plugins by name without loading them."""
    entry_point_map: dict[str, Any] = {}

    try:
        for entry_point in entry_points_for_group(entry_point_group):
            lang_hint = entry_point.name.lower()
            entry_point_map[lang_hint] = entry_point
            debug(f"Discovered entry point plugin: {entry_point.name}")
    except Exception as e:
        warning(f"Failed to discover plugins from entry points: {e}")

    return entry_point_map


def entry_points_for_group(entry_point_group: str) -> Iterable[Any]:
    """Return entry points for a group across importlib.metadata API versions."""
    entry_points = importlib.metadata.entry_points()

    if hasattr(entry_points, "select"):
        return entry_points.select(group=entry_point_group)

    try:
        if hasattr(entry_points, "get"):
            result = entry_points.get(entry_point_group)
            return list(result) if result else []
    except (TypeError, AttributeError):
        return []

    return []


def discover_local_plugin_modules(
    languages_dir: Path,
    languages_package: str,
    *,
    warning: LogFn = log_warning,
) -> dict[str, str]:
    """Discover local language plugin modules without importing each plugin."""
    plugin_modules: dict[str, str] = {}

    try:
        if not languages_dir.exists():
            return plugin_modules

        languages_module = importlib.import_module(languages_package)
        for name in iter_language_module_names(languages_module):
            base_name = name.split(".")[-1]
            if base_name.endswith("_plugin"):
                plugin_modules[base_name[: -len("_plugin")]] = name
    except Exception as e:
        warning(f"Failed to discover local plugins: {e}")

    return plugin_modules


def iter_language_module_names(languages_module: Any) -> Iterable[str]:
    """Yield module names from the local languages package."""
    for _finder, name, _ispkg in pkgutil.iter_modules(
        languages_module.__path__, languages_module.__name__ + "."
    ):
        yield name


def lazy_load_local_plugin(
    language: str,
    module_name: str | None,
    loaded_plugins: dict[str, LanguagePlugin],
    class_finder: ClassFinder,
    loggers: PluginLoggers | None = None,
) -> LanguagePlugin | None:
    """Load a local plugin module and return the plugin matching *language*."""
    if not module_name:
        return None

    log = loggers or PluginLoggers()
    try:
        log.debug(f"Lazily loading local plugin for {language} from {module_name}")
        module = importlib.import_module(module_name)
        for plugin_class in class_finder(module):
            instance = plugin_class()
            loaded_plugins[instance.get_language_name()] = instance
            if plugin_matches_request(instance, language):
                return instance
    except Exception as e:
        log.error(f"Failed to lazily load local plugin {module_name}: {e}")

    return None


def plugin_module_for_language(
    plugin_modules: dict[str, str],
    language: str,
) -> str | None:
    """Resolve a direct plugin module name or a default alias target."""
    module_name = plugin_modules.get(language)
    if module_name:
        return module_name

    alias_target = PLUGIN_ALIASES.get(language)
    if alias_target:
        return plugin_modules.get(alias_target)

    return None


def plugin_matches_request(plugin: LanguagePlugin, requested_language: str) -> bool:
    """Return whether a plugin instance satisfies a requested language or alias."""
    plugin_language = plugin.get_language_name()
    return plugin_language == requested_language or (
        PLUGIN_ALIASES.get(requested_language) == plugin_language
    )


def lazy_load_entry_point_plugin(
    language: str,
    entry_point_map: dict[str, Any] | None,
    loaded_plugins: dict[str, LanguagePlugin],
    subclass_check: SubClassCheck,
    loggers: PluginLoggers | None = None,
) -> LanguagePlugin | None:
    """Load one plugin from a previously discovered entry point map."""
    if not entry_point_map or language not in entry_point_map:
        return None

    log = loggers or PluginLoggers()
    try:
        entry_point = entry_point_map[language]
        log.debug(
            f"Lazily loading entry point plugin for {language}: {entry_point.name}"
        )
        plugin_class = entry_point.load()
        if subclass_check(plugin_class, LanguagePlugin):
            instance = plugin_class()
            loaded_plugins[instance.get_language_name()] = instance
            return cast(LanguagePlugin, instance)
    except Exception as e:
        log.error(f"Failed to lazily load entry point plugin {language}: {e}")

    return None


def find_loaded_plugin_case_insensitive(
    language: str, loaded_plugins: dict[str, LanguagePlugin]
) -> LanguagePlugin | None:
    """Find an already-loaded plugin by case-insensitive language name."""
    for loaded_language, plugin in loaded_plugins.items():
        if loaded_language.lower() == language:
            return plugin
    return None


def load_plugins_from_entry_points(
    entry_point_group: str,
    subclass_check: SubClassCheck,
    *,
    debug: LogFn = log_debug,
    warning: LogFn = log_warning,
    error: LogFn = log_error,
) -> list[LanguagePlugin]:
    """Load plugin instances from setuptools entry points."""
    plugins: list[LanguagePlugin] = []

    try:
        for entry_point in entry_points_for_group(entry_point_group):
            plugin = load_plugin_from_entry_point(
                entry_point,
                subclass_check,
                debug=debug,
                warning=warning,
                error=error,
            )
            if plugin is not None:
                plugins.append(plugin)
    except Exception as e:
        warning(f"Failed to load plugins from entry points: {e}")

    return plugins


def load_plugin_from_entry_point(
    entry_point: Any,
    subclass_check: SubClassCheck,
    *,
    debug: LogFn = log_debug,
    warning: LogFn = log_warning,
    error: LogFn = log_error,
) -> LanguagePlugin | None:
    """Load and validate a single entry point plugin."""
    try:
        plugin_class = entry_point.load()
        if not subclass_check(plugin_class, LanguagePlugin):
            warning(f"Entry point {entry_point.name} is not a LanguagePlugin")
            return None

        plugin_instance = plugin_class()
        debug(f"Loaded plugin from entry point: {entry_point.name}")
        return cast(LanguagePlugin, plugin_instance)
    except Exception as e:
        error(f"Failed to load plugin from entry point {entry_point.name}: {e}")
        return None


def load_plugins_from_local_directory(
    languages_dir: Path,
    languages_package: str,
    class_finder: ClassFinder,
    loggers: PluginLoggers | None = None,
) -> list[LanguagePlugin]:
    """Load plugin instances from the local languages directory."""
    plugins: list[LanguagePlugin] = []
    log = loggers or PluginLoggers()
    module_names = local_language_module_names_for_loading(
        languages_dir,
        languages_package,
        debug=log.debug,
        warning=log.warning,
    )

    for module_name in module_names:
        plugins.extend(
            load_plugins_from_module(
                module_name,
                class_finder,
                debug=log.debug,
                error=log.error,
            )
        )

    return plugins


def local_language_module_names_for_loading(
    languages_dir: Path,
    languages_package: str,
    *,
    debug: LogFn = log_debug,
    warning: LogFn = log_warning,
) -> list[str]:
    """Return local language module names that should be imported for loading."""
    try:
        if not ensure_languages_directory(languages_dir, debug=debug):
            return []

        languages_module = import_languages_package(languages_package, warning=warning)
        if languages_module is None:
            return []

        return list(iter_language_module_names(languages_module))
    except Exception as e:
        warning(f"Failed to load plugins from local directory: {e}")
        return []


def ensure_languages_directory(
    languages_dir: Path, *, debug: LogFn = log_debug
) -> bool:
    """Ensure the local languages directory exists before loading plugins."""
    if languages_dir.exists():
        return True

    debug("Languages directory does not exist, creating it")
    languages_dir.mkdir(exist_ok=True)
    (languages_dir / "__init__.py").touch()
    return False


def import_languages_package(
    languages_package: str,
    *,
    warning: LogFn = log_warning,
) -> Any | None:
    """Import the local languages package, returning None on ImportError."""
    try:
        return importlib.import_module(languages_package)
    except ImportError as e:
        warning(f"Could not import languages package: {e}")
        return None


def load_plugins_from_module(
    module_name: str,
    class_finder: ClassFinder,
    *,
    debug: LogFn = log_debug,
    error: LogFn = log_error,
) -> list[LanguagePlugin]:
    """Import one language module and instantiate its plugin classes."""
    plugins: list[LanguagePlugin] = []

    try:
        module = importlib.import_module(module_name)
        for plugin_class in class_finder(module):
            try:
                plugin_instance = plugin_class()
                plugins.append(plugin_instance)
                debug(f"Loaded local plugin: {plugin_class.__name__}")
            except Exception as e:
                error(f"Failed to instantiate plugin {plugin_class.__name__}: {e}")
    except Exception as e:
        error(f"Failed to load plugin module {module_name}: {e}")

    return plugins


def find_plugin_classes(module: Any) -> list[type[LanguagePlugin]]:
    """Find LanguagePlugin subclasses in a module."""
    plugin_classes: list[type[LanguagePlugin]] = []

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, LanguagePlugin)
            and attr is not LanguagePlugin
        ):
            plugin_classes.append(attr)

    return plugin_classes


def build_plugin_info(
    plugin: LanguagePlugin,
    *,
    language: str,
    error: LogFn = log_error,
) -> dict[str, Any] | None:
    """Build a serializable information dictionary for a plugin."""
    try:
        return {
            "language": plugin.get_language_name(),
            "extensions": plugin.get_file_extensions(),
            "class_name": plugin.__class__.__name__,
            "module": plugin.__class__.__module__,
            "has_extractor": hasattr(plugin, "create_extractor"),
        }
    except Exception as e:
        error(f"Failed to get plugin info for {language}: {e}")
        return None


def validate_plugin_instance(
    plugin: LanguagePlugin,
    *,
    error: LogFn = log_error,
) -> bool:
    """Validate that a plugin implements the required interface correctly."""
    try:
        if not has_required_plugin_methods(plugin, error=error):
            return False

        if not has_valid_language_name(plugin, error=error):
            return False

        if not has_valid_extensions(plugin, error=error):
            return False

        if not plugin.create_extractor():
            error("Plugin create_extractor() must return an extractor instance")
            return False

        return True
    except Exception as e:
        error(f"Plugin validation failed: {e}")
        return False


def has_required_plugin_methods(plugin: LanguagePlugin, *, error: LogFn) -> bool:
    """Return whether a plugin exposes all required callable methods."""
    for method_name in REQUIRED_PLUGIN_METHODS:
        if not hasattr(plugin, method_name):
            error(f"Plugin missing required method: {method_name}")
            return False

        method = getattr(plugin, method_name)
        if not callable(method):
            error(f"Plugin method {method_name} is not callable")
            return False

    return True


def has_valid_language_name(plugin: LanguagePlugin, *, error: LogFn) -> bool:
    """Validate the language name returned by a plugin."""
    language = plugin.get_language_name()
    if not language or not isinstance(language, str):
        error("Plugin get_language_name() must return a non-empty string")
        return False
    return True


def has_valid_extensions(plugin: LanguagePlugin, *, error: LogFn) -> bool:
    """Validate file extensions returned by a plugin."""
    extensions = plugin.get_file_extensions()
    if not isinstance(extensions, list):
        error("Plugin get_file_extensions() must return a list")
        return False
    return True
