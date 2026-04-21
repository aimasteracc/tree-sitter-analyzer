#!/usr/bin/env python3
"""Split a flat *_plugin.py into a composable mixin package.

Usage:
    python scripts/split_plugin.py tree_sitter_analyzer/languages/typescript_plugin.py

This script:
1. Parses the source file to find classes and methods
2. Groups methods into logical mixins by naming patterns
3. Generates correctly-imported mixin files with exact method signatures
4. Creates __init__.py with composed class + original plugin class
5. Produces a _base.py with precise stub signatures (from AST, not guessing)
6. Handles relative import depth automatically (..  -> ... for packages)
7. Preserves backward-compatible exports

After running:
    ruff check <pkg>/ --fix
    mypy <pkg>/ --strict
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Method grouping heuristics: prefix -> mixin name
GROUP_PATTERNS: list[tuple[str, str]] = [
    ("_extract_table", "tables"),
    ("_extract_sql_table", "tables"),
    ("_split_column", "tables"),
    ("_parse_column", "tables"),
    ("_extract_view", "views"),
    ("_extract_sql_view", "views"),
    ("_extract_procedure", "procedures"),
    ("_extract_sql_procedure", "procedures"),
    ("_extract_function", "functions"),
    ("_extract_sql_function", "functions"),
    ("_extract_trigger", "triggers"),
    ("_extract_sql_trigger", "triggers"),
    ("_extract_index", "indexes"),
    ("_extract_sql_index", "indexes"),
    ("_extract_indexes_with", "indexes"),
    ("_extract_dml", "dml"),
    ("_extract_expression", "dml"),
    ("_extract_query", "dml"),
    ("_extract_window", "dml"),
    ("_extract_transaction", "dml"),
    ("_extract_comment", "dml"),
    ("_extract_select", "dml"),
    ("_extract_schema", "dml"),
    ("_extract_import", "imports"),
    ("_extract_export", "imports"),
    ("_extract_class", "classes"),
    ("_extract_interface", "classes"),
    ("_extract_type", "types"),
    ("_extract_enum", "types"),
    ("_extract_decorator", "decorators"),
    ("_extract_namespace", "namespaces"),
    ("_extract_module", "modules"),
    ("_extract_variable", "variables"),
    ("_extract_constant", "constants"),
]


def classify_method(name: str) -> str:
    """Classify a method name into a mixin group."""
    for prefix, group in GROUP_PATTERNS:
        if name.startswith(prefix):
            return group
    return "core"


def get_method_signature_stub(node: ast.FunctionDef) -> str:
    """Generate a precise method signature string from an AST node."""
    args_parts = []
    for arg in node.args.args:
        ann = ast.unparse(arg.annotation) if arg.annotation else ""
        args_parts.append(f"{arg.arg}: {ann}" if ann else arg.arg)

    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {node.name}({', '.join(args_parts)}){ret}"


def extract_imports_before_class(source: str, class_lineno: int) -> str:
    """Extract all import statements before the first class definition."""
    lines = source.splitlines()
    import_lines = []
    for i, line in enumerate(lines[: class_lineno - 1], 1):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) or stripped.startswith("#"):
            import_lines.append(line)
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            import_lines.append(line)
        elif stripped == "" and import_lines:
            import_lines.append(line)
    return "\n".join(import_lines)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/plugin.py>")
        sys.exit(1)

    source_path = Path(sys.argv[1])
    if not source_path.exists():
        print(f"File not found: {source_path}")
        sys.exit(1)

    source = source_path.read_text()
    tree = ast.parse(source)

    # Find classes
    classes: list[tuple[str, ast.ClassDef]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            classes.append((node.name, node))

    if not classes:
        print("No classes found in source file")
        sys.exit(1)

    # Find the main extractor class (the big one)
    extractor_class = max(classes, key=lambda c: c[1].end_lineno - c[1].lineno)
    plugin_classes = [c for c in classes if c[0] != extractor_class[0]]

    # Group extractor methods
    methods: dict[str, list[ast.FunctionDef]] = {}
    for node in ast.iter_child_nodes(extractor_class[1]):
        if isinstance(node, ast.FunctionDef):
            group = classify_method(node.name)
            methods.setdefault(group, []).append(node)

    # Create package directory
    pkg_name = source_path.stem  # e.g., typescript_plugin
    pkg_dir = source_path.parent / pkg_name
    if pkg_dir.exists():
        print(f"Package directory already exists: {pkg_dir}")
        sys.exit(1)

    pkg_dir.mkdir()
    print(f"Creating package: {pkg_dir}")

    # Compute relative import depth
    # languages/xxx_plugin/ -> need ... for tree_sitter_analyzer imports
    parts = source_path.parts
    lang_idx = list(parts).index("languages")
    dot_depth = len(parts) - lang_idx  # languages=1, plugin_dir=1 extra
    parent_dots = "." * (dot_depth + 1)  # e.g., ...

    # Step 1: Generate _base.py with precise stubs
    stub_methods: list[tuple[str, str]] = []  # (signature, method_name)
    for group_name, group_methods in sorted(methods.items()):
        if group_name == "core":
            continue
        for m in group_methods:
            sig = get_method_signature_stub(m)
            stub_methods.append((m.name, sig))

    base_imports = set()
    for group_name, group_methods in methods.items():
        if group_name == "core":
            continue
        for m in group_methods:
            for node in ast.walk(m):
                if isinstance(node, ast.Name) and node.id in (
                    "Class",
                    "Expression",
                    "Function",
                    "Import",
                    "Variable",
                    "SQLColumn",
                    "SQLConstraint",
                    "SQLElement",
                    "SQLFunction",
                    "SQLIndex",
                    "SQLParameter",
                    "SQLProcedure",
                    "SQLTable",
                    "SQLTrigger",
                    "SQLView",
                ):
                    base_imports.add(node.id)

    base_content = f'''"""Shared method stubs — satisfies mypy strict attr-defined checks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter
'''
    if base_imports:
        sorted_imports = sorted(base_imports)
        base_content += f'\n    from {parent_dots}models import (\n'
        for imp in sorted_imports:
            base_content += f"        {imp},\n"
        base_content += "    )\n"

    base_class_name = f"_{extractor_class[0].replace('Extractor', '').replace('Plugin', '')}Base"
    base_content += f"\n\nclass {base_class_name}:\n"
    base_content += '    """Cross-mixin method declarations."""\n\n'

    # Add instance attributes used across mixins
    core_init = next(
        (m for m in methods.get("core", []) if m.name == "__init__"), None
    )
    if core_init:
        for node in ast.walk(core_init):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                if isinstance(node.targets[0], ast.Attribute):
                    attr = node.targets[0].attr
                    if not attr.startswith("_"):
                        ann = ast.unparse(node.value) if node.value else "Any"
                        base_content += f"    {attr}: Any\n"

    for m_name, sig in sorted(stub_methods):
        base_content += f"\n    {sig}:\n        raise NotImplementedError\n"

    (pkg_dir / "_base.py").write_text(base_content)
    print(f"  _base.py ({len(base_content.splitlines())} lines)")

    # Step 2: Generate mixin files
    all_groups = sorted(methods.keys())
    mixin_class_names: dict[str, str] = {}

    for group_name in all_groups:
        group_methods = methods[group_name]
        mixin_cls = f"{group_name.title()}Mixin"
        mixin_class_names[group_name] = mixin_cls

        # Collect source lines for each method
        method_sources = []
        for m in group_methods:
            start, end = m.lineno, m.end_lineno
            method_lines = source.splitlines(keepends=True)[start - 1 : end]
            method_sources.append("".join(method_lines))

        # Generate imports: find what the methods actually use
        needed_types: set[str] = set()
        for m in group_methods:
            for node in ast.walk(m):
                if isinstance(node, ast.Name):
                    needed_types.add(node.id)
                elif isinstance(node, ast.Attribute) and isinstance(
                    node.value, ast.Name
                ):
                    needed_types.add(node.value.id)

        # Build file
        file_content = f'"""{pkg_name} extraction mixin — {group_name}."""\n'
        file_content += "from __future__ import annotations\n\n"
        file_content += "from typing import TYPE_CHECKING, Any\n\n"
        file_content += "if TYPE_CHECKING:\n    import tree_sitter\n\n"

        # Add model imports that are actually used
        model_types = needed_types & {
            "Class",
            "Expression",
            "Function",
            "Import",
            "Variable",
            "SQLColumn",
            "SQLConstraint",
            "SQLElement",
            "SQLFunction",
            "SQLIndex",
            "SQLParameter",
            "SQLProcedure",
            "SQLTable",
            "SQLTrigger",
            "SQLView",
        }
        if model_types:
            sorted_m = sorted(model_types)
            file_content += f"from {parent_dots}models import (\n"
            for t in sorted_m:
                file_content += f"    {t},\n"
            file_content += ")\n"

        file_content += f"from {parent_dots}utils import log_debug, log_error\n"
        file_content += f"from ._base import {base_class_name}\n\n"

        inherits = base_class_name
        if group_name == "core":
            # Core might inherit from ElementExtractor
            base_classes = [
                ast.unparse(b) for b in extractor_class[1].bases
            ]
            if base_classes:
                inherits = f"{base_class_name}, {', '.join(base_classes)}"

        file_content += f"class {mixin_cls}({inherits}):\n"
        for ms in method_sources:
            file_content += "\n" + ms

        filename = f"_{group_name}.py"
        (pkg_dir / filename).write_text(file_content)
        print(f"  {filename} ({len(file_content.splitlines())} lines)")

    # Step 3: Generate __init__.py
    init_content = f'"""{pkg_name} — composable mixin architecture."""\n'
    init_content += "from __future__ import annotations\n\n"
    init_content += "import importlib.util\n"
    init_content += "from typing import TYPE_CHECKING, Any\n\n"
    init_content += "if TYPE_CHECKING:\n"
    init_content += f"    from {parent_dots}core.request import AnalysisRequest\n"
    init_content += f"    from {parent_dots}models import AnalysisResult\n\n"

    # Collect all imports needed by plugin classes
    # Re-scan the plugin class source for imports
    for cls_name, cls_node in plugin_classes:
        cls_source = "".join(
            source.splitlines(keepends=True)[
                cls_node.lineno - 1 : cls_node.end_lineno
            ]
        )
        # Extract import statements from the original file that are used by plugin class
        pass

    # Add all model imports that plugin classes might need
    init_content += f"from {parent_dots}models import (\n"
    for t in sorted(base_imports):
        init_content += f"    {t},\n"
    init_content += ")\n"
    init_content += f"from {parent_dots}plugins.base import ElementExtractor, LanguagePlugin\n"
    init_content += f"from {parent_dots}utils import log_debug, log_error\n"

    for group_name in all_groups:
        mixin_cls = mixin_class_names[group_name]
        init_content += f"from ._{group_name} import {mixin_cls}\n"

    # Check for TREE_SITTER_AVAILABLE in original
    if "TREE_SITTER_AVAILABLE" in source:
        init_content += (
            "\nTREE_SITTER_AVAILABLE = "
            'importlib.util.find_spec("tree_sitter") is not None\n'
        )

    init_content += f"\n__all__ = ['{extractor_class[0]}']"
    for cls_name, _ in plugin_classes:
        init_content += f", '{cls_name}'"
    init_content += "\n\n"

    # Composed extractor class
    mixin_order = [g for g in all_groups if g != "core"] + ["core"]
    init_content += f"class {extractor_class[0]}(\n"
    for g in mixin_order:
        init_content += f"    {mixin_class_names[g]},\n"
    init_content += "):\n"
    init_content += f'    """Composed from language-specific mixins."""\n\n\n'

    # Plugin classes (verbatim from source)
    for cls_name, cls_node in plugin_classes:
        cls_lines = source.splitlines(keepends=True)[
            cls_node.lineno - 1 : cls_node.end_lineno
        ]
        cls_source = "".join(cls_lines)
        # Fix relative imports in the class: .. -> ...
        cls_source = cls_source.replace(f"from ..", f"from {parent_dots}")
        init_content += cls_source + "\n\n"

    (pkg_dir / "__init__.py").write_text(init_content)
    print(f"  __init__.py ({len(init_content.splitlines())} lines)")

    print(f"\nPackage created: {pkg_dir}/")
    print(f"Files: {list(p.name for p in sorted(pkg_dir.glob('*.py')))}")
    print(f"\nNext steps:")
    print(f"  git rm {source_path}")
    print(f"  uv run ruff check {pkg_dir}/ --fix")
    print(f"  uv run mypy {pkg_dir}/ --strict")
    print(f"  uv run pytest tests/ -x -q -k {pkg_name.replace('_plugin', '')}")


if __name__ == "__main__":
    main()
