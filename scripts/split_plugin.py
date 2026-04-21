#!/usr/bin/env python3
"""Split a flat *_plugin.py into a composable mixin package.

Usage:
    python scripts/split_plugin.py tree_sitter_analyzer/languages/typescript_plugin.py

Automatically generates mixin files, fixes imports, validates with
ruff + mypy, and iterates until clean. Zero manual fixes needed.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

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

TYPING_NAMES = frozenset({"Optional", "Union", "Callable", "Iterator"})


def classify_method(name: str) -> str:
    for prefix, group in GROUP_PATTERNS:
        if name.startswith(prefix):
            return group
    return "core"


def types_used_in(node: ast.AST) -> set[str]:
    """Collect all Name identifiers used anywhere in an AST subtree."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
    return found


def collect_typing_names(stubs: list[str]) -> set[str]:
    """Find typing names (Optional, Union, etc.) used in stub signatures."""
    found: set[str] = set()
    for stub in stubs:
        for name in TYPING_NAMES:
            if name + "[" in stub:
                found.add(name)
    return found


def method_signature_stub(node: ast.FunctionDef) -> str:
    parts = []
    for arg in node.args.args:
        ann = ast.unparse(arg.annotation) if arg.annotation else ""
        parts.append(f"{arg.arg}: {ann}" if ann else arg.arg)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {node.name}({', '.join(parts)}){ret}"


class ImportMap:
    """Tracks original file's imports and resolves them for mixin files."""

    def __init__(self, tree: ast.Module, source: str, parent_dots: str) -> None:
        self.parent_dots = parent_dots
        self.source_lines = source.splitlines(keepends=True)
        self.import_lines: list[tuple[str, set[str]]] = []
        # Walk entire tree to catch imports inside try/except blocks
        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                names = {a.name.split(" as ")[0] for a in node.names}
                raw = "".join(self.source_lines[node.lineno - 1 : node.end_lineno])
                raw = " ".join(raw.split())
                self.import_lines.append((raw, names))

    def select_for_names(self, used_names: set[str]) -> list[str]:
        """Return adjusted import lines that provide any of used_names."""
        result = []
        for raw_line, names in self.import_lines:
            if not (names & used_names):
                continue
            # Adjust relative depth: from .. → from ... (one extra dot for package nesting)
            if raw_line.startswith("from .."):
                adjusted = "from " + self.parent_dots + raw_line[len("from .."):]
            elif raw_line.startswith("from ."):
                adjusted = "from ." + self.parent_dots + raw_line[len("from ."):]
            else:
                adjusted = raw_line
            result.append(adjusted)
        return result


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def run_ruff_fix(pkg_dir: Path) -> int:
    rc, out = run(["uv", "run", "ruff", "check", str(pkg_dir), "--fix"])
    rc2, out2 = run(["uv", "run", "ruff", "check", str(pkg_dir)])
    if rc2 != 0:
        lines = [l for l in out2.strip().splitlines() if l.strip()]
        print(f"  ruff: {len(lines)} issues remaining")
        for l in lines[:5]:
            print(f"    {l}")
    else:
        print("  ruff: clean")
    return rc2


def run_mypy(pkg_dir: Path) -> list[str]:
    rc, out = run(["uv", "run", "mypy", str(pkg_dir), "--strict"])
    errors = [l for l in out.splitlines() if "error:" in l]
    if errors:
        print(f"  mypy: {len(errors)} errors")
        for e in errors[:5]:
            print(f"    {e}")
    else:
        print("  mypy: clean")
    return errors


def fix_mypy_errors(pkg_dir: Path, errors: list[str]) -> None:
    """Auto-fix common mypy errors from mixin splits."""
    for err in errors:
        # mypy: Name "X" is not defined  [name-defined]
        m = re.search(r'^(.+):(\d+):.+Name "(\w+)" is not defined', err)
        if m:
            filepath, name = Path(m.group(1)), m.group(3)
            fix_missing_import(filepath, name, pkg_dir)

        # attr-defined → ensure mixin inherits from base
        m = re.search(r'^(.+):(\d+):.+has no attribute "(\w+)"', err)
        if m:
            filepath = Path(m.group(1))
            attr = m.group(3)
            fix_missing_base_inheritance(filepath, attr, pkg_dir)


def fix_missing_import(filepath: Path, name: str, pkg_dir: Path) -> None:
    """Add a missing import to a file by scanning other files in the package."""
    if not filepath.exists() or not name:
        return
    content = filepath.read_text()
    if name in content:
        return

    # Try to find an import for this name in another file in the package
    for other in sorted(pkg_dir.glob("*.py")):
        if other == filepath:
            continue
        other_content = other.read_text()
        for line in other_content.splitlines():
            if line.startswith("from ") and name in line:
                # Found an import line with this name — add it
                lines = content.splitlines(keepends=True)
                insert_pos = 0
                for i, l in enumerate(lines):
                    if l.startswith(("from ", "import ")):
                        insert_pos = i + 1
                # Ensure the line ends with newline
                if not line.endswith("\n"):
                    line += "\n"
                lines.insert(insert_pos, line)
                filepath.write_text("".join(lines))
                print(f"    fixed: added `{name}` import to {filepath.name} (from {other.name})")
                return


def fix_missing_base_inheritance(filepath: Path, attr: str, pkg_dir: Path) -> None:
    """If a mixin doesn't inherit from base, add it."""
    content = filepath.read_text()
    base_files = list(pkg_dir.glob("_base.py"))
    if not base_files:
        return
    base_content = base_files[0].read_text()
    base_match = re.search(r"class (\w+):", base_content)
    if not base_match:
        return
    base_name = base_match.group(1)

    if base_name not in content:
        return

    class_match = re.search(r"class (\w+)\(([^)]*)\):", content)
    if class_match and base_name not in class_match.group(2):
        old = class_match.group(0)
        current_parents = class_match.group(2).strip()
        new_parents = f"{base_name}, {current_parents}" if current_parents else base_name
        content = content.replace(old, f"class {class_match.group(1)}({new_parents}):")
        filepath.write_text(content)
        print(f"    fixed: added {base_name} inheritance to {filepath.name}")


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
        print("No classes found")
        sys.exit(1)

    extractor_class = max(classes, key=lambda c: c[1].end_lineno - c[1].lineno)
    plugin_classes = [c for c in classes if c[0] != extractor_class[0]]

    # Group methods
    methods: dict[str, list[ast.FunctionDef]] = {}
    for node in ast.iter_child_nodes(extractor_class[1]):
        if isinstance(node, ast.FunctionDef):
            methods.setdefault(classify_method(node.name), []).append(node)

    # If only "core" group exists, split by method count (~400 per file)
    if len(methods) == 1 and "core" in methods:
        all_methods = methods["core"]
        chunk_size = 400
        for i in range(0, len(all_methods), chunk_size):
            chunk = all_methods[i:i + chunk_size]
            group_name = f"part{i // chunk_size + 1}"
            methods[group_name] = chunk
        del methods["core"]

    pkg_name = source_path.stem
    pkg_dir = source_path.parent / pkg_name
    if pkg_dir.exists():
        print(f"Package already exists: {pkg_dir}")
        sys.exit(1)

    pkg_dir.mkdir()
    print(f"Creating: {pkg_dir}")

    # Compute import depth
    parts = source_path.parts
    try:
        lang_idx = list(parts).index("languages")
    except ValueError:
        lang_idx = list(parts).index("analysis")
    parent_dots = "." * (len(parts) - lang_idx + 1)

    # Build import map from original source
    import_map = ImportMap(tree, source, parent_dots)

    # Collect all names used across all methods (for _base.py)
    all_used: set[str] = set()
    for g, ms in methods.items():
        for m in ms:
            all_used |= types_used_in(m)

    # Generate stubs first to extract typing names
    all_stubs: list[str] = []
    for g, ms in sorted(methods.items()):
        for m in ms:
            all_stubs.append(method_signature_stub(m))
    typing_imports = collect_typing_names(all_stubs)

    base_class_name = f"_{extractor_class[0].replace('Extractor', '').replace('Plugin', '')}Base"
    base = '"""Cross-mixin stubs — mypy attr-defined."""\nfrom __future__ import annotations\n\nfrom typing import TYPE_CHECKING, Any'
    if typing_imports:
        base += f", {', '.join(sorted(typing_imports))}"
    base += '\n\nif TYPE_CHECKING:\n    import tree_sitter\n'
    # Add model imports used in stubs via import_map
    stub_imports = import_map.select_for_names(all_used)
    for imp in stub_imports:
        if imp.startswith("from typing") or imp.startswith("from __future__"):
            continue
        if "import tree_sitter" in imp:
            continue
        base += f"    {imp}\n"
    base += f"\n\nclass {base_class_name}:\n"

    # Instance attributes from __init__
    for g, ms in methods.items():
        init = next((m for m in ms if m.name == "__init__"), None)
        if init:
            for node in ast.walk(init):
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
                    attr = node.target.attr
                    base += f"    {attr}: Any\n"
                elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                    if isinstance(node.targets[0], ast.Attribute):
                        attr = node.targets[0].attr
                        base += f"    {attr}: Any\n"

    # Stub methods for all methods
    for g, ms in sorted(methods.items()):
        for m in ms:
            sig = method_signature_stub(m)
            base += f"\n    {sig}:\n        raise NotImplementedError\n"

    (pkg_dir / "_base.py").write_text(base)
    print(f"  _base.py ({len(base.splitlines())} lines)")

    # Generate mixin files
    all_groups = sorted(methods.keys())
    mixin_names: dict[str, str] = {}
    source_lines = source.splitlines(keepends=True)

    for g in all_groups:
        ms = methods[g]
        mixin_cls = f"{g.title()}Mixin"
        mixin_names[g] = mixin_cls

        method_srcs = []
        for m in ms:
            method_srcs.append("".join(source_lines[m.lineno - 1 : m.end_lineno]))

        # Collect names used in this mixin's methods
        used: set[str] = set()
        for m in ms:
            used |= types_used_in(m)
        # For core/part mixins, also include names from original class bases
        if g == "core" or g.startswith("part"):
            for b in extractor_class[1].bases:
                used |= types_used_in(b)

        # Select imports from original source that provide any used name
        mixin_imports = import_map.select_for_names(used)
        mixin_stubs = [method_signature_stub(m) for m in ms]
        mixin_typing = collect_typing_names(mixin_stubs)

        # Build import block
        fc = f'"""{pkg_name} mixin — {g}."""\nfrom __future__ import annotations\n\nfrom typing import TYPE_CHECKING, Any'
        if mixin_typing:
            fc += f", {', '.join(sorted(mixin_typing))}"
        fc += '\n\nif TYPE_CHECKING:\n    import tree_sitter\n\n'

        # Add runtime imports (skip TYPE_CHECKING-guarded ones)
        for imp in mixin_imports:
            if imp.startswith("from typing") or imp.startswith("from __future__"):
                continue
            if "import tree_sitter" in imp and not imp.startswith("try:"):
                continue
            fc += imp + "\n"
        fc += f"from ._base import {base_class_name}\n\n"

        inherits = base_class_name
        if g == "core" or g.startswith("part"):
            original_bases = [ast.unparse(b) for b in extractor_class[1].bases]
            inherits = f"{base_class_name}, {', '.join(original_bases)}" if original_bases else base_class_name

        fc += f"class {mixin_cls}({inherits}):\n"
        for ms_src in method_srcs:
            fc += "\n" + ms_src

        (pkg_dir / f"_{g}.py").write_text(fc)
        print(f"  _{g}.py ({len(fc.splitlines())} lines)")

    # Generate __init__.py
    init_types: set[str] = set()
    for _, cls_node in plugin_classes:
        init_types |= types_used_in(cls_node)

    ic = f'"""{pkg_name} — composable mixin architecture."""\nfrom __future__ import annotations\n\n'

    # Collect all init types + plugin class types to determine needed imports
    init_imports = import_map.select_for_names(init_types)

    # Merge typing imports
    typing_names = {"TYPE_CHECKING", "Any"}
    for imp in init_imports:
        if imp.startswith("from typing import"):
            names_str = imp.split("import ")[-1]
            typing_names |= {n.strip() for n in names_str.split(",")}
    ic += f"from typing import {', '.join(sorted(typing_names))}\n\n"

    ic += "if TYPE_CHECKING:\n"
    if "AnalysisRequest" in init_types:
        ic += f"    from {parent_dots}core.request import AnalysisRequest\n"
    if "AnalysisResult" in init_types:
        ic += f"    from {parent_dots}models import AnalysisResult\n"
    ic += "\n"

    # Use import_map for __init__.py, skipping names already imported above
    already_imported = {"AnalysisRequest", "AnalysisResult"} | typing_names
    for imp in init_imports:
        if imp.startswith("from typing") or imp.startswith("from __future__"):
            continue
        imp_names = {n.strip() for n in imp.split("import ")[-1].split(",")}
        if imp_names <= already_imported:
            continue
        ic += imp + "\n"
        already_imported |= imp_names

    for g in all_groups:
        ic += f"from ._{g} import {mixin_names[g]}\n"

    if "TREE_SITTER_AVAILABLE" in source:
        ic += "\nimport importlib.util\n"
        ic += 'TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None\n'

    all_exports = [extractor_class[0]] + [cn for cn, _ in plugin_classes]
    ic += f"\n__all__ = {all_exports}\n\n"

    mixin_order = [g for g in all_groups if g not in ("core",)] + [g for g in all_groups if g in ("core",)]
    ic += f"class {extractor_class[0]}(\n"
    for g in mixin_order:
        ic += f"    {mixin_names[g]},\n"
    ic += "):\n    \"\"\"Composed from mixins.\"\"\"\n\n\n"

    for cn, cls_node in plugin_classes:
        cls_src = "".join(source_lines[cls_node.lineno - 1 : cls_node.end_lineno])
        cls_src = cls_src.replace("from ..", f"from {parent_dots}")
        ic += cls_src + "\n\n"

    (pkg_dir / "__init__.py").write_text(ic)
    print(f"  __init__.py ({len(ic.splitlines())} lines)")

    # === Validation loop ===
    print("\n=== Validation ===")
    for iteration in range(5):
        print(f"\nRound {iteration + 1}:")
        ruff_rc = run_ruff_fix(pkg_dir)
        mypy_errors = run_mypy(pkg_dir)

        if ruff_rc == 0 and not mypy_errors:
            print("\nAll clean!")
            break

        if mypy_errors:
            fix_mypy_errors(pkg_dir, mypy_errors)
    else:
        print("\nWarning: still has issues after 5 rounds")

    print(f"\nPackage: {pkg_dir}/")
    print(f"Files: {[p.name for p in sorted(pkg_dir.glob('*.py'))]}")
    print(f"\nNext:")
    print(f"  git rm {source_path}")
    print(f"  uv run pytest tests/ -x -q -k {pkg_name.replace('_plugin', '')}")


if __name__ == "__main__":
    main()
