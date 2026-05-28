#!/usr/bin/env python3
"""
Dead Code Analyzer — Transitive dead code, unused imports, unreferenced variables.

Extends the basic orphan detection in codegraph_overview_tool with:

- **Transitive dead code**: functions reachable only from dead functions.
  If A() calls B() calls C(), and nobody calls A(), then A, B, C are all dead.
- **Unused imports**: import statements whose imported names are never referenced
  in the same file.
- **Unreferenced file-level variables**: assignments at module/class top level
  that no function in the file references.

Leverages the existing CallGraph infrastructure for function-level analysis
and the core parser for import/variable extraction.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .call_graph import CachedCallGraph, CallGraph, FunctionRef
from .core.parser import Parser
from .import_extractors import walk_imports
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
}

_KNOWN_ENTRY_PATTERNS = {
    "python": re.compile(
        r"^(main|__main__|setup|run|app|create_app|wsgi|asgi"
        r"|pytest_configure|unittest_main)$"
    ),
    "javascript": re.compile(r"^(main|start|bootstrap|run|handler|exports\.default)$"),
    "typescript": re.compile(r"^(main|start|bootstrap|run|handler)$"),
    "java": re.compile(r"^(main|init|destroy|doGet|doPost|service)$"),
    "go": re.compile(r"^(main|init|TestMain)$"),
    "c": re.compile(r"^(main|WinMain)$"),
    "cpp": re.compile(r"^(main|WinMain)$"),
}

_TEST_FILE_PATTERNS = re.compile(
    r"(?:^test_|_test\.|\.test\.|\.spec\.|_spec\.|tests?/|Test\.py$)",
    re.IGNORECASE,
)

_VARIABLE_ASSIGN_TYPES = {
    "python": {"assignment"},
    "javascript": {"variable_declaration", "lexical_declaration"},
    "typescript": {"variable_declaration", "lexical_declaration"},
    "go": {"var_declaration", "short_var_declaration"},
    "java": {"field_declaration", "local_variable_declaration"},
    "c": {"declaration"},
    "cpp": {"declaration"},
}

_CLASS_DEF_TYPES = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "java": {"class_declaration"},
    "go": {"type_declaration"},
}


@dataclass
class DeadFunction:
    function: FunctionRef
    reason: str
    depth: int = 0
    dead_callees: list[str] = field(default_factory=list)


@dataclass
class UnusedImport:
    file: str
    line: int
    import_text: str
    unused_names: list[str]


@dataclass
class UnreferencedVariable:
    file: str
    name: str
    line: int
    language: str


@dataclass
class DeadCodeResult:
    dead_functions: list[DeadFunction]
    unused_imports: list[UnusedImport]
    unreferenced_variables: list[UnreferencedVariable]
    stats: dict[str, int] = field(default_factory=dict)


def _is_test_file(file_path: str) -> bool:
    return bool(_TEST_FILE_PATTERNS.search(file_path))


def _is_known_entry(name: str, language: str) -> bool:
    pattern = _KNOWN_ENTRY_PATTERNS.get(language)
    if pattern:
        return bool(pattern.match(name))
    return False


def find_transitive_dead_code(
    graph: CallGraph,
    *,
    include_test_files: bool = False,
    max_depth: int = 20,
) -> list[DeadFunction]:
    """
    Find transitive dead code using flood-fill from entry points.

    Algorithm:
    1. Mark all functions as potentially dead.
    2. Find entry points (zero callers) that are NOT dead:
       - functions in test files
       - known entry patterns (main, setup, etc.)
       - functions with external callers outside the graph
    3. BFS from entry points, marking reachable functions as alive.
    4. Remaining unmarked functions are transitively dead.
    """
    all_funcs = set(graph.function_refs())
    alive: set[FunctionRef] = set()

    for func in all_funcs:
        if not include_test_files and _is_test_file(func.file_path):
            alive.add(func)
            continue

        if _is_known_entry(func.name, func.language):
            alive.add(func)
            continue

    queue: deque[tuple[FunctionRef, int]] = deque((f, 0) for f in alive)
    while queue:
        func, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for callee in graph.callee_refs_of(func):
            if callee not in alive and callee in all_funcs:
                alive.add(callee)
                queue.append((callee, depth + 1))

    dead_funcs = all_funcs - alive
    results: list[DeadFunction] = []

    dead_by_qname = {f.qualified_name() for f in dead_funcs}

    for func in dead_funcs:
        dead_callee_names = []
        for callee in graph.callee_refs_of(func):
            if callee.qualified_name() in dead_by_qname:
                dead_callee_names.append(callee.name)

        callers = graph.caller_refs_of(func)
        if callers:
            reason = "unreachable_from_entry"
        else:
            callee_count = len(graph.callee_refs_of(func))
            if callee_count == 0:
                reason = "orphan_no_callers_no_callees"
            else:
                reason = "no_callers_has_dead_callees"

        results.append(
            DeadFunction(
                function=func,
                reason=reason,
                dead_callees=dead_callee_names,
            )
        )

    results.sort(key=lambda d: (d.function.file_path, d.function.start_line))
    return results


def find_unused_imports(
    project_root: str,
    *,
    include_test_files: bool = False,
    max_files: int = 500,
) -> list[UnusedImport]:
    """
    Find import statements whose imported names are never referenced in the same file.

    For each source file:
    1. Parse the file to extract import statements with their imported names.
    2. Collect all identifiers used in the file (in function bodies, decorators, etc.).
    3. Report imports where none of the imported names appear as identifiers.
    """
    parser = Parser()
    root = Path(project_root)
    results: list[UnusedImport] = []

    source_files: list[tuple[Path, str]] = []
    for p in root.rglob("*"):
        if any(part in _EXCLUDE_DIRS for part in p.parts):
            continue
        if p.is_file():
            lang = _language_from_ext(str(p))
            if lang and lang in (
                "python",
                "javascript",
                "typescript",
                "go",
                "java",
                "c",
                "cpp",
            ):
                source_files.append((p, lang))
        if len(source_files) >= max_files:
            break

    for file_path, language in source_files:
        rel = str(file_path.relative_to(root))

        if not include_test_files and _is_test_file(rel):
            continue

        try:
            source_bytes = file_path.read_bytes()
        except OSError:
            continue
        source = source_bytes.decode("utf-8", errors="replace")

        try:
            result = parser.parse_code(source, language)
        except Exception:
            continue
        if not result or not result.tree:
            continue

        imports: list[dict[str, Any]] = []
        root_node = result.tree.root_node
        walk_imports(root_node, source, language, imports)

        if not imports:
            continue

        all_identifiers = _collect_identifiers(
            root_node, source, language, skip_import_subtrees=True
        )
        identifier_names = {name for name, _ in all_identifiers}

        for imp in imports:
            unused = _check_import_unused(imp, identifier_names)
            if unused is None:
                continue
            line = imp.get("line", 0) or _infer_import_line(source, imp)
            if line == 0:
                continue
            import_text = imp.get("module_name", "") or ", ".join(imp.get("names", []))
            results.append(
                UnusedImport(
                    file=rel,
                    line=line,
                    import_text=import_text,
                    unused_names=unused,
                )
            )

    results.sort(key=lambda x: (x.file, x.line))
    return results


def _check_import_unused(
    imp: dict[str, Any], identifier_names: set[str]
) -> list[str] | None:
    """Return list of unused names for imp, or None if imp should be skipped."""
    imported_names = imp.get("names", [])
    if not imported_names:
        module_name = imp.get("module_name", "")
        if not module_name:
            return None
        top = module_name.split(".")[0].split("/")[0]
        imported_names = [top]
    unused = [n for n in imported_names if n not in identifier_names]
    return unused if unused else None


def _infer_import_line(source: str, imp: dict[str, Any]) -> int:
    """Best-effort line number fallback for extractors that omit line metadata."""
    module_name = imp.get("module_name", "")
    names = imp.get("names", [])
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if module_name and (
            stripped.startswith(f"import {module_name}")
            or stripped.startswith(f"from {module_name} import ")
        ):
            return line_number
        if (
            names
            and stripped.startswith("import ")
            and any(n in stripped for n in names)
        ):
            return line_number
    return 0


def find_unreferenced_variables(
    project_root: str,
    *,
    include_test_files: bool = False,
    max_files: int = 500,
) -> list[UnreferencedVariable]:
    """
    Find file-level variable assignments that no function in the file references.

    For each source file:
    1. Parse the file and extract top-level assignments (module scope).
    2. Collect all identifiers used inside function bodies.
    3. Report variables that no function references.
    """
    parser = Parser()
    root = Path(project_root)
    results: list[UnreferencedVariable] = []

    source_files: list[tuple[Path, str]] = []
    for p in root.rglob("*"):
        if any(part in _EXCLUDE_DIRS for part in p.parts):
            continue
        if p.is_file():
            lang = _language_from_ext(str(p))
            if lang and lang in ("python", "javascript", "typescript", "go", "java"):
                source_files.append((p, lang))
        if len(source_files) >= max_files:
            break

    for file_path, language in source_files:
        rel = str(file_path.relative_to(root))

        if not include_test_files and _is_test_file(rel):
            continue

        try:
            source = file_path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue

        try:
            result = parser.parse_code(source, language)
        except Exception:
            continue
        if not result or not result.tree:
            continue

        root_node = result.tree.root_node
        top_level_vars = _extract_top_level_variables(root_node, source, language)
        if not top_level_vars:
            continue

        body_identifiers = _collect_function_body_identifiers(
            root_node, source, language
        )

        for name, line in top_level_vars:
            if name not in body_identifiers and not name.startswith("_"):
                results.append(
                    UnreferencedVariable(
                        file=rel,
                        name=name,
                        line=line,
                        language=language,
                    )
                )

    results.sort(key=lambda x: (x.file, x.line))
    return results


_IDENTIFIER_NODE_TYPES = frozenset(
    ("identifier", "property_identifier", "type_identifier")
)


def _walk_identifiers(
    n: Any,
    source: str,
    skip_import_subtrees: bool,
    result: list[tuple[str, int]],
) -> None:
    """Recursive helper for _collect_identifiers; avoids closure nesting."""
    if not hasattr(n, "type"):
        return
    if skip_import_subtrees and "import" in n.type:
        return
    if n.type in _IDENTIFIER_NODE_TYPES:
        text = _node_text(n, source)
        if text:
            result.append((text, n.start_point[0] + 1))
    for child in getattr(n, "children", []):
        _walk_identifiers(child, source, skip_import_subtrees, result)


def _walk_func_body(
    n: Any,
    source: str,
    func_types: set[str],
    inside_func: bool,
    result: set[str],
) -> None:
    """Recursive helper for _collect_function_body_identifiers; avoids closure nesting."""
    if not hasattr(n, "type"):
        return
    ntype = n.type
    new_inside = inside_func or ntype in func_types
    if new_inside and ntype in _IDENTIFIER_NODE_TYPES:
        text = _node_text(n, source)
        if text:
            result.add(text)
    for child in getattr(n, "children", []):
        _walk_func_body(child, source, func_types, new_inside, result)


def _collect_identifiers(
    node: Any, source: str, language: str, *, skip_import_subtrees: bool = False
) -> list[tuple[str, int]]:
    """Collect all identifier nodes from the AST."""
    result: list[tuple[str, int]] = []
    _walk_identifiers(node, source, skip_import_subtrees, result)
    return result


def _collect_function_body_identifiers(
    tree: Any, source: str, language: str
) -> set[str]:
    """Collect identifiers that appear inside function bodies."""
    from .function_extraction import _FUNC_DEF_TYPES

    func_types = _FUNC_DEF_TYPES.get(language, set())
    result: set[str] = set()
    _walk_func_body(tree, source, func_types, False, result)
    return result


def _extract_python_top_level_vars(
    tree: Any,
    source: str,
    func_types: set[str],
    class_types: set[str],
) -> list[tuple[str, int]]:
    """Extract top-level variable assignments from Python AST nodes."""
    variables: list[tuple[str, int]] = []
    for child in getattr(tree, "children", []):
        if child.type in func_types or child.type in class_types:
            continue
        stmt = child
        if child.type == "expression_statement" and getattr(child, "children", []):
            stmt = child.children[0]
        assign_type = stmt.type
        if assign_type not in ("assignment", "augmented_assignment"):
            continue
        left = stmt.child_by_field_name("left")
        if not (left and left.type == "identifier"):
            continue
        text = _node_text(left, source)
        if text and not text.startswith("_"):
            variables.append((text, stmt.start_point[0] + 1))
    return variables


def _extract_js_top_level_vars(
    tree: Any,
    source: str,
    func_types: set[str],
    class_types: set[str],
    assign_types: set[str],
) -> list[tuple[str, int]]:
    """Extract top-level variable declarations from JavaScript/TypeScript AST nodes."""
    variables: list[tuple[str, int]] = []
    for child in getattr(tree, "children", []):
        if child.type in func_types or child.type in class_types:
            continue
        if child.type not in assign_types:
            continue
        for decl in child.children:
            if decl.type != "variable_declarator":
                continue
            name_node = decl.child_by_field_name("name")
            if not (name_node and name_node.type == "identifier"):
                continue
            text = _node_text(name_node, source)
            if text and not text.startswith("_"):
                variables.append((text, child.start_point[0] + 1))
    return variables


def _extract_top_level_variables(
    tree: Any, source: str, language: str
) -> list[tuple[str, int]]:
    """Extract variable names assigned at the top level (module scope)."""
    from .function_extraction import _FUNC_DEF_TYPES

    func_types = _FUNC_DEF_TYPES.get(language, set())
    class_types = _CLASS_DEF_TYPES.get(language, set())
    assign_types = _VARIABLE_ASSIGN_TYPES.get(language, set())

    if language == "python":
        return _extract_python_top_level_vars(tree, source, func_types, class_types)
    if language in ("javascript", "typescript"):
        return _extract_js_top_level_vars(
            tree, source, func_types, class_types, assign_types
        )
    return []


def _node_text(node: Any, source: str) -> str:
    """Extract text from a tree-sitter node."""
    try:
        text = node.text
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)
    except Exception:
        start = node.start_byte
        end = node.end_byte
        return source[start:end]


def analyze_dead_code(
    project_root: str,
    *,
    include_test_files: bool = False,
    include_unused_imports: bool = True,
    include_variables: bool = True,
    max_files: int = 500,
) -> DeadCodeResult:
    """
    Comprehensive dead code analysis.

    Combines transitive dead function detection with unused import
    and unreferenced variable analysis.
    """
    try:
        from .ast_cache import ASTCache

        cache = ASTCache(project_root)
        stats = cache.get_stats()
        if stats.get("total_files", 0) > 0:
            graph: CallGraph = CachedCallGraph(project_root, cache=cache)
        else:
            cache.close()
            graph = CallGraph(project_root)
    except Exception:
        graph = CallGraph(project_root)

    dead_funcs = find_transitive_dead_code(
        graph,
        include_test_files=include_test_files,
    )

    unused_imports: list[UnusedImport] = []
    if include_unused_imports:
        unused_imports = find_unused_imports(
            project_root,
            include_test_files=include_test_files,
            max_files=max_files,
        )

    unref_vars: list[UnreferencedVariable] = []
    if include_variables:
        unref_vars = find_unreferenced_variables(
            project_root,
            include_test_files=include_test_files,
            max_files=max_files,
        )

    graph_summary = graph.summary()

    return DeadCodeResult(
        dead_functions=dead_funcs,
        unused_imports=unused_imports,
        unreferenced_variables=unref_vars,
        stats={
            "total_functions": graph_summary.get("function_count", 0),
            "dead_functions": len(dead_funcs),
            "unused_imports": len(unused_imports),
            "unreferenced_variables": len(unref_vars),
            "total_call_edges": graph_summary.get("call_edge_count", 0),
        },
    )
