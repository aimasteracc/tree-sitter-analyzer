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

import os
import re
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .call_graph import CachedCallGraph, CallGraph, FunctionRef
from .call_graph_binding import ref_identity
from .constants import EXCLUDE_DIRS
from .core.parser import Parser
from .dead_code_references import (
    ReferenceIndex,
    build_reference_index,
    module_path_unresolvable,
)
from .import_extractors import walk_imports
from .module_scope_caller import is_module_caller
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

# Single-source the excluded-dir set from the canonical ``constants.EXCLUDE_DIRS``
# rather than carrying a private near-duplicate that drifts. The canonical set is
# a strict superset of the dirs this module historically excluded, so every
# previously-pruned tree is still pruned (behavior unchanged) — it just also
# covers the vendored/build dirs (vendor, target, obj, Pods, ...) that this
# walker should skip too. Dot-prefixed dirs are pruned separately via the
# ``startswith(".")`` check in ``_iter_candidate_files``.
_EXCLUDE_DIRS = EXCLUDE_DIRS


def _iter_candidate_files(root: Path) -> Iterator[Path]:
    """Yield files under ``root``, PRUNING excluded and hidden (dot-prefixed)
    directories so large vendored / generated trees never get walked.

    Uses ``os.walk`` + in-place ``dirnames[:]`` pruning — the same approach as
    the CallGraph / ASTCache walkers — rather than filtering ``rglob`` results.
    Filtering rglob still enumerates every descendant of an excluded tree before
    it can be skipped, so a large cloned repo (``.benchmark-repos/excalidraw``)
    or cache (``.ast-cache``) made the walk slow/hang on the exact trees this
    exclusion is meant to skip (Codex P2 #329). Pruning never descends into them.
    The dot-prefix rule mirrors the indexer's scope; pruning ``dirnames`` is
    inherently below-root, so the absolute prefix is never matched.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            yield Path(dirpath) / filename


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
    # Added alongside call_graph.py's language-parity fix (Codex P1 #1157):
    # rust/csharp/kotlin/swift all have one unambiguous entry-point
    # convention. ruby/php/lua are intentionally NOT added here — they
    # execute top-level script code directly rather than via a single named
    # entry function, so a regex guess would be as likely to be wrong as
    # right; dead-code detection for those three remains a known follow-up.
    "rust": re.compile(r"^(main)$"),
    "csharp": re.compile(r"^(Main)$"),
    "kotlin": re.compile(r"^(main)$"),
    "swift": re.compile(r"^(main)$"),
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


CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"
#: 文件的点分模块路径无法导入（如 ``agent-tasks/``），
#: 指向它的跨文件调用 / 引用连不上（#1790）。
LOW_CONFIDENCE_UNRESOLVED_MODULE = "module_path_unresolvable"

_PY_DUNDER = re.compile(r"^__\w+__$")
# 框架按命名约定分派的方法（``ast.NodeVisitor`` / docutils 访问器、``http.server``
# 处理器）：源码里从不按名字调用。
_PY_CONVENTION_CALLBACK = re.compile(r"^(?:visit_\w+|depart_\w+|do_[A-Z]+)$")


@dataclass
class DeadFunction:
    function: FunctionRef
    reason: str
    depth: int = 0
    dead_callees: list[str] = field(default_factory=list)
    confidence: str = CONFIDENCE_HIGH
    confidence_reason: str | None = None


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
    return bool(_TEST_FILE_PATTERNS.search(file_path.replace("\\", "/")))


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
       - 运行时隐式调用的方法（dunder、``visit_*`` 等；#1790）
       - 模块作用域（``<module>`` 伪调用方）调用到的函数（#1790）
    3. BFS from entry points, marking reachable functions as alive.
    4. 对仍未标记的函数扫描项目里的非调用使用（分发表、实参、属性、登记型
       装饰器；#1790），沿这些引用边继续 BFS。
    5. 剩余未标记的函数即传递性死代码；模块路径无法解析的文件里的结论为
       ``confidence="low"``。
    """
    all_funcs = set(graph.function_refs())
    roots = {
        func
        for func in all_funcs
        if (not include_test_files and _is_test_file(func.file_path))
        or _is_known_entry(func.name, func.language)
        or _is_implicit_entry(func)
    }
    # #1790：模块作用域（导入时执行）的调用点调用到的函数也是根。
    roots.update(_module_scope_callees(graph) & all_funcs)
    # 键为存活函数，值为它离最近的根的深度（BFS 层数）。
    depth: dict[FunctionRef, int] = dict.fromkeys(roots, 0)

    def successors(func: FunctionRef) -> Iterable[FunctionRef]:
        # #1559/#1560：模糊的同名候选也算可达，不能把它们判为死代码。
        return graph.reachable_callee_refs_of(func)

    _flood(depth, all_funcs, successors, max_depth, list(depth))

    # #1790：分发表 / 实参 / 属性 / 装饰器登记等“作为值”的使用不是调用边，单独补上。
    references = _reference_index(graph, all_funcs - set(depth))
    if references is not None:
        seeds = _reference_seeds(references, depth, all_funcs, max_depth)

        def successors_with_refs(func: FunctionRef) -> Iterable[FunctionRef]:
            return [
                *graph.reachable_callee_refs_of(func),
                *references.edges.get(func, ()),
            ]

        _flood(depth, all_funcs, successors_with_refs, max_depth, seeds)

    alive = set(depth)
    dead_funcs = all_funcs - alive
    results: list[DeadFunction] = []

    # #1619：按身份判断被调方是否已死；qualified_name 会让活的同名函数被误判。
    dead_ids = {ref_identity(f) for f in dead_funcs}

    for func in dead_funcs:
        dead_callee_names = []
        for callee in graph.callee_refs_of(func):
            if ref_identity(callee) in dead_ids:
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

        confidence, confidence_reason = _confidence_for(func)
        results.append(
            DeadFunction(
                function=func,
                reason=reason,
                dead_callees=dead_callee_names,
                confidence=confidence,
                confidence_reason=confidence_reason,
            )
        )

    # #1790：高置信度在前，避免低置信度条目占满展示上限。
    results.sort(
        key=lambda d: (
            d.confidence != CONFIDENCE_HIGH,
            d.function.file_path,
            d.function.start_line,
        )
    )
    return results


def _flood(
    depth: dict[FunctionRef, int],
    universe: set[FunctionRef],
    successors: Callable[[FunctionRef], Iterable[FunctionRef]],
    max_depth: int,
    start: Iterable[FunctionRef],
) -> None:
    """从 ``start`` 出发做 BFS，就地把可达函数连同深度写入 ``depth``。

    深度达到 ``max_depth`` 的函数不再展开，与引用边共用同一个深度上限。
    """
    queue: deque[FunctionRef] = deque(start)
    while queue:
        func = queue.popleft()
        current = depth[func]
        if current >= max_depth:
            continue
        for callee in successors(func):
            if callee not in depth and callee in universe:
                depth[callee] = current + 1
                queue.append(callee)


def _reference_seeds(
    references: ReferenceIndex,
    depth: dict[FunctionRef, int],
    universe: set[FunctionRef],
    max_depth: int,
) -> list[FunctionRef]:
    """#1790：把引用补成新的存活函数并返回它们（就地写入 ``depth``）。

    模块作用域引用与装饰器登记是根（深度 0）；存活函数里的引用与调用边一样
    计一层，超过 ``max_depth`` 的不展开。
    """
    seeds: list[FunctionRef] = []
    for target in (*references.module_targets, *references.registered):
        if target in universe and target not in depth:
            depth[target] = 0
            seeds.append(target)
    for source, targets in references.edges.items():
        level = depth.get(source)
        if level is None or level >= max_depth:
            continue
        for target in targets:
            if target in universe and target not in depth:
                depth[target] = level + 1
                seeds.append(target)
    return seeds


def _is_implicit_entry(func: FunctionRef) -> bool:
    """#1790：由运行时隐式调用的方法（``__init__`` / ``__call__`` /
    ``__post_init__`` / JS ``constructor`` ...）没有显式调用点，但不是死代码。"""
    if func.language == "python":
        return bool(
            _PY_DUNDER.match(func.name) or _PY_CONVENTION_CALLBACK.match(func.name)
        )
    if func.language in ("javascript", "typescript"):
        return func.name == "constructor"
    return False


def _module_scope_callees(graph: CallGraph) -> set[FunctionRef]:
    """模块作用域（``<module>`` 伪调用方，#1622）调用到的函数。"""
    try:
        # ``Any``：测试替身可能给出非 dict 的映射，下面单独检查。
        callees_map: Any = graph.callees_map()
    except Exception:  # noqa: BLE001 — 取不到映射只会少几个根
        return set()
    if not isinstance(callees_map, dict):
        return set()
    roots: set[FunctionRef] = set()
    for caller in callees_map:
        if isinstance(caller, FunctionRef) and is_module_caller(caller.name):
            roots.update(graph.reachable_callee_refs_of(caller))
    return roots


def _reference_index(
    graph: CallGraph, candidates: set[FunctionRef]
) -> ReferenceIndex | None:
    """仍判为死的 ``candidates`` 的“作为值”引用；图没有可扫描的磁盘项目时为 None。"""
    if not candidates:
        return None
    project_root = getattr(graph, "project_root", None)
    if not isinstance(project_root, (str, os.PathLike)):
        return None
    if not Path(project_root).is_dir():
        return None
    return build_reference_index(project_root, graph.function_refs(), candidates)


def filter_value_referenced(
    graph: CallGraph, candidates: list[FunctionRef]
) -> list[FunctionRef]:
    """#1790：去掉运行时隐式调用、或在任何位置作为值使用（分发表、实参、
    装饰器）的候选。``codegraph_overview`` 的孤立函数列表共用此规则，两处结论一致。"""
    remaining = [func for func in candidates if not _is_implicit_entry(func)]
    pending = set(remaining)
    references = _reference_index(graph, pending)
    if references is None:
        return remaining
    # 只认可来自模块作用域、装饰器登记或非候选函数的引用；候选函数自己的引用
    # 要等该候选被认定为“在用”之后才生效，避免死函数把目标藏起来。
    used = set(references.module_targets) | set(references.registered)
    for source, targets in references.edges.items():
        if source not in pending:
            used.update(targets)
    frontier = list(used & pending)
    while frontier:
        source = frontier.pop()
        for target in references.edges.get(source, ()):
            if target in pending and target not in used:
                used.add(target)
                frontier.append(target)
    return [func for func in remaining if func not in used]


def _confidence_for(func: FunctionRef) -> tuple[str, str | None]:
    """#1790：模块路径无法解析的文件，跨文件引用连不上，结论只能是低置信度。"""
    if module_path_unresolvable(func.file_path):
        return CONFIDENCE_LOW, LOW_CONFIDENCE_UNRESOLVED_MODULE
    return CONFIDENCE_HIGH, None


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
    for p in _iter_candidate_files(root):
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
    for p in _iter_candidate_files(root):
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
