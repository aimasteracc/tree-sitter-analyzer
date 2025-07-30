#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin Loader for Tree-sitter Analyzer

Automatically loads and registers all available language plugins.
"""

from typing import List

from ..utils import log_debug, log_error, log_info
from . import plugin_registry


def load_all_plugins() -> List[str]:
    """Load and register all available language plugins"""
    loaded_plugins = []

    try:
        # Import and register Java plugin
        from .java_plugin import JavaPlugin

        java_plugin = JavaPlugin()
        plugin_registry.register_plugin(java_plugin)
        loaded_plugins.append("java")
        log_debug("Loaded Java plugin")
    except Exception as e:
        log_error(f"Failed to load Java plugin: {e}")

    try:
        # Import and register JavaScript plugin
        from .javascript_plugin import JavaScriptPlugin

        js_plugin = JavaScriptPlugin()
        plugin_registry.register_plugin(js_plugin)
        loaded_plugins.append("javascript")
        log_debug("Loaded JavaScript plugin")
    except Exception as e:
        log_error(f"Failed to load JavaScript plugin: {e}")

    try:
        # Import and register Python plugin
        from .python_plugin import PythonPlugin

        python_plugin = PythonPlugin()
        plugin_registry.register_plugin(python_plugin)
        loaded_plugins.append("python")
        log_debug("Loaded Python plugin")
    except Exception as e:
        log_error(f"Failed to load Python plugin: {e}")

    if loaded_plugins:
        log_info(
            f"Successfully loaded {len(loaded_plugins)} language plugins: {', '.join(loaded_plugins)}"
        )
    else:
        log_error("No language plugins were loaded successfully")

    return loaded_plugins


def get_supported_languages() -> List[str]:
    """Get list of all supported languages"""
    return plugin_registry.list_supported_languages()


def get_supported_extensions() -> List[str]:
    """Get list of all supported file extensions"""
    return plugin_registry.list_supported_extensions()


def get_plugin_for_file(file_path: str):
    """Get appropriate plugin for a file"""
    return plugin_registry.get_plugin_for_file(file_path)


def get_plugin_by_language(language: str):
    """Get plugin by language name"""
    return plugin_registry.get_plugin(language)


# Auto-load plugins when module is imported
_loaded_plugins = load_all_plugins()
