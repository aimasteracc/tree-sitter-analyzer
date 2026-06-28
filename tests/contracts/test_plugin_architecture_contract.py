"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}
PLUGINS_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "languages"


def _discover_plugin_files() -> list[tuple[str, Path]]:
    """Return [(language_name, path), ...] for all plugin files."""
    result = []
    for p in sorted(PLUGINS_DIR.iterdir()):
        if p.name.startswith("_") or p.name.startswith(".") or p.name == "__init__.py":
            continue
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py"):
            result.append((p.stem.replace("_plugin", ""), p))
        elif p.is_dir() and p.name.endswith("_plugin"):
            plugin_py = p / "plugin.py"
            if plugin_py.exists():
                result.append((p.stem.replace("_plugin", ""), plugin_py))
    return result


def test_every_plugin_class_inherits_language_plugin() -> None:
    """All XxxPlugin classes must inherit from LanguagePlugin (not ElementExtractor)."""

    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                base_names = [
                    b.id if isinstance(b, ast.Name) else getattr(b, "attr", "?")
                    for b in node.bases
                ]
                if "ElementExtractor" in base_names:
                    msg = f"{rel}:{node.lineno} {node.name} inherits ElementExtractor (should only inherit LanguagePlugin)"
                    violations.append(msg)
    assert violations == [], "\n".join(violations)


def test_extract_elements_returns_dict() -> None:
    """extract_elements on any class must return dict[str, list[Any]], not list."""
    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "extract_elements":
                ret = node.returns
                if ret is None:
                    continue
                ret_str = ast.unparse(ret)
                if ret_str.startswith("list") and "dict" not in ret_str:
                    msg = f"{rel}:{node.lineno} extract_elements returns {ret_str} (must be dict[str, list[...]])"
                    violations.append(msg)
    assert violations == [], "\n".join(violations)


def test_plugin_has_required_abstract_methods() -> None:
    """Each plugin must implement: get_language_name, get_file_extensions, create_extractor, analyze_file."""
    REQUIRED = {
        "get_language_name",
        "get_file_extensions",
        "create_extractor",
        "analyze_file",
    }
    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                missing = REQUIRED - methods
                if missing:
                    msg = f"{rel}:{node.lineno} {node.name} missing methods: {missing}"
                    violations.append(msg)
    assert violations == [], "\n".join(violations)


def test_no_new_single_file_plugins_in_languages_root() -> None:
    """Prevent adding new single-file plugins. New languages must use package structure.

    Existing single-file plugins are grandfathered; this test only blocks NEW ones.
    """
    GRANDFATHERED = {
        "bash_plugin.py",
        "c_plugin.py",
        "cpp_plugin.py",
        "csharp_plugin.py",
        "css_plugin.py",
        "go_plugin.py",
        "html_plugin.py",
        "java_plugin.py",
        "json_plugin.py",
        "kotlin_plugin.py",
        "php_plugin.py",
        "ruby_plugin.py",
        "rust_plugin.py",
        "scala_plugin.py",
        "swift_plugin.py",
        "yaml_plugin.py",
    }
    single_file_plugins = {
        p.name
        for p in PLUGINS_DIR.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py")
    }
    new_plugins = single_file_plugins - GRANDFATHERED
    assert not new_plugins, (
        f"New single-file plugins detected: {new_plugins}. "
        f"Use languages/<lang>_plugin/ package structure instead."
    )


def test_analyze_file_uses_create_extractor() -> None:
    """All analyze_file methods must use create_extractor(), not self.extractor.

    self.extractor creates hidden side-effect coupling. create_extractor()
    ensures each analysis gets a fresh, isolated extractor instance.
    """
    violations = []
    plugin_paths = []
    for p in sorted(PLUGINS_DIR.iterdir()):
        if p.name.startswith("_") or p.name.startswith(".") or p.name == "__init__.py":
            continue
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py"):
            plugin_paths.append(p)
        elif p.is_dir() and p.name.endswith("_plugin"):
            pp = p / "plugin.py"
            if pp.exists():
                plugin_paths.append(pp)
    for path in plugin_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "analyze_file"
            ):
                body = ast.get_source_segment(source, node)
                if body and "self.extractor" in body and "create_extractor" not in body:
                    violations.append(f"{path.name}:{node.lineno}")
    assert not violations, (
        f"analyze_file uses self.extractor without create_extractor in: {violations}"
    )
