#!/usr/bin/env python3
"""Plugin architecture consistency checker.

Exit 0 if all plugins pass, exit 1 with diagnostics otherwise.
Intended for CI and pre-commit hooks.

Usage:
    python scripts/check_plugin_consistency.py
    python scripts/check_plugin_consistency.py --verbose
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "languages"
BASE_PLUGIN = PROJECT_ROOT / "tree_sitter_analyzer" / "plugins" / "base.py"

REQUIRED_PLUGIN_METHODS = {
    "get_language_name",
    "get_file_extensions",
    "create_extractor",
    "analyze_file",
}

GRANDFATHERED_SINGLE_FILE = {
    "c_plugin.py",
    "cpp_plugin.py",
    "csharp_plugin.py",
    "css_plugin.py",
    "go_plugin.py",
    "html_plugin.py",
    "java_plugin.py",
    "kotlin_plugin.py",
    "php_plugin.py",
    "ruby_plugin.py",
    "rust_plugin.py",
    "swift_plugin.py",
    "yaml_plugin.py",
}


def _discover_plugins() -> list[tuple[str, Path]]:
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


def check_extract_elements_return_type(lang: str, path: Path) -> list[str]:
    violations = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "extract_elements":
            ret = node.returns
            if ret is None:
                violations.append(
                    f"  {path.name}:{node.lineno} extract_elements has no return annotation"
                )
                continue
            ret_str = ast.unparse(ret)
            if ret_str.startswith("list") and "dict" not in ret_str:
                violations.append(
                    f"  {path.name}:{node.lineno} extract_elements returns "
                    f"{ret_str} (must be dict[str, list[...]])"
                )
    return violations


def check_plugin_inheritance(lang: str, path: Path) -> list[str]:
    violations = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
            base_names = [
                b.id if isinstance(b, ast.Name) else getattr(b, "attr", "?")
                for b in node.bases
            ]
            if "ElementExtractor" in base_names:
                violations.append(
                    f"  {path.name}:{node.lineno} {node.name} inherits "
                    f"ElementExtractor (should only inherit LanguagePlugin)"
                )
    return violations


def check_required_methods(lang: str, path: Path) -> list[str]:
    violations = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
            methods = {
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            missing = REQUIRED_PLUGIN_METHODS - methods
            if missing:
                violations.append(
                    f"  {path.name}:{node.lineno} {node.name} missing: {sorted(missing)}"
                )
    return violations


def check_no_new_single_file_plugins() -> list[str]:
    violations = []
    for p in PLUGINS_DIR.iterdir():
        if (
            p.is_file()
            and p.suffix == ".py"
            and p.name.endswith("_plugin.py")
            and p.name not in GRANDFATHERED_SINGLE_FILE
        ):
            violations.append(
                f"  {p.name}: New single-file plugin. Use languages/<lang>_plugin/ package."
            )
    return violations


def check_analyze_file_delegation(lang: str, path: Path) -> list[str]:
    violations = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "analyze_file"
        ):
            body_src = ast.get_source_segment(source, node)
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "extract_elements"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "self"
                    ):
                        violations.append(
                            f"  {path.name}:{child.lineno} analyze_file calls "
                            f"self.extract_elements() (must use extractor.extract_xxx delegation)"
                        )
            if "self.extractor" in body_src and "create_extractor" not in body_src:
                violations.append(
                    f"  {path.name}:{node.lineno} analyze_file uses self.extractor "
                    f"instead of create_extractor()"
                )
    return violations


CHECKS = [
    ("extract_elements return type", check_extract_elements_return_type),
    ("plugin inheritance", check_plugin_inheritance),
    ("required methods", check_required_methods),
    ("analyze_file delegation", check_analyze_file_delegation),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check plugin architecture consistency"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    all_violations: list[str] = []

    plugins = _discover_plugins()
    if args.verbose:
        print(f"Checking {len(plugins)} plugins...")

    for lang, path in plugins:
        for check_name, check_fn in CHECKS:
            violations = check_fn(lang, path)
            if violations:
                all_violations.append(f"[{lang}] {check_name}:")
                all_violations.extend(violations)

    new_file_violations = check_no_new_single_file_plugins()
    if new_file_violations:
        all_violations.append("[global] new single-file plugins:")
        all_violations.extend(new_file_violations)

    if all_violations:
        print("FAIL: plugin architecture violations found:\n")
        for v in all_violations:
            print(v)
        print(f"\nTotal: {len(all_violations)} violation(s)")
        return 1

    if args.verbose:
        print(f"PASS: all {len(plugins)} plugins consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
