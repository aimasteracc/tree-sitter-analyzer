"""Code smell detection analyzer.

Detects code anti-patterns:
  - circular_dependency: mutual imports between modules
  - god_class: classes with excessive methods
  - deep_inheritance: overly deep class hierarchy
  - long_parameter_list: functions with too many parameters
  - unused_import: import statements with no apparent usage
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import CodeSmell, ModuleInfo, SymbolInfo

_GOD_CLASS_METHOD_THRESHOLD = 15
_DEEP_INHERITANCE_THRESHOLD = 3
_LONG_PARAM_LIST_THRESHOLD = 5


def detect_code_smells(
    modules: list[ModuleInfo],
    symbols: list[SymbolInfo],
    module_dependencies: list[tuple[str, str]],
) -> list[CodeSmell]:
    """Detect code smells / anti-patterns in the project."""
    from tree_sitter_analyzer_v2.core.code_map.types import CodeSmell

    smells: list[CodeSmell] = []

    # 1. Circular dependency detection
    dep_graph: dict[str, set[str]] = {}
    for src, dst in module_dependencies:
        dep_graph.setdefault(src, set()).add(dst)

    reported_pairs: set[tuple[str, str]] = set()
    for src, targets in dep_graph.items():
        for dst in targets:
            if dst in dep_graph and src in dep_graph.get(dst, set()):
                pair = tuple(sorted([src, dst]))
                if pair not in reported_pairs:
                    reported_pairs.add(pair)
                    smells.append(CodeSmell(
                        kind="circular_dependency",
                        severity="warning",
                        message=f"Circular import: {pair[0]} <-> {pair[1]}",
                        file_path=pair[0],
                        detail=f"{pair[0]} <-> {pair[1]}",
                    ))

    # 2. God class detection
    for module in modules:
        for cls in module.classes:
            methods = cls.get("methods", [])
            if len(methods) >= _GOD_CLASS_METHOD_THRESHOLD:
                name = cls.get("name", "unknown")
                smells.append(CodeSmell(
                    kind="god_class",
                    severity="warning",
                    message=f"Class '{name}' has {len(methods)} methods",
                    file_path=module.path,
                    detail=f"methods={len(methods)}",
                ))

    # 3. Deep inheritance chain detection (DP-cached to avoid redundant traversal)
    class_by_name: dict[str, SymbolInfo] = {
        s.name: s for s in symbols if s.kind == "class"
    }
    _depth_cache: dict[str, int] = {}

    def _inheritance_depth(name: str, seen: frozenset[str] = frozenset()) -> int:
        """Compute max inheritance depth with memoization."""
        if name in _depth_cache:
            return _depth_cache[name]
        cls = class_by_name.get(name)
        if not cls or not cls.bases:
            _depth_cache[name] = 0
            return 0
        max_d = 0
        for base_name in cls.bases:
            if base_name in seen or base_name not in class_by_name:
                continue
            max_d = max(max_d, 1 + _inheritance_depth(base_name, seen | {name}))
        _depth_cache[name] = max_d
        return max_d

    for sym in symbols:
        if sym.kind != "class" or not sym.bases:
            continue
        depth = _inheritance_depth(sym.name)

        if depth > _DEEP_INHERITANCE_THRESHOLD:
            smells.append(CodeSmell(
                kind="deep_inheritance",
                severity="info",
                message=(
                    f"Class '{sym.name}' has inheritance depth {depth} "
                    f"(threshold: {_DEEP_INHERITANCE_THRESHOLD})"
                ),
                file_path=sym.file,
                detail=f"depth={depth}",
            ))

    # 4. Long parameter list detection
    for sym in symbols:
        if sym.kind not in ("function", "method"):
            continue
        if not sym.params or not sym.params.strip():
            continue
        param_count = len([p for p in sym.params.split(",") if p.strip()])
        if param_count > _LONG_PARAM_LIST_THRESHOLD:
            smells.append(CodeSmell(
                kind="long_parameter_list",
                severity="warning",
                message=(
                    f"{sym.kind} '{sym.name}' has {param_count} parameters "
                    f"(threshold: {_LONG_PARAM_LIST_THRESHOLD})"
                ),
                file_path=sym.file,
                detail=f"params={param_count}",
            ))

    # 5. Unused import detection
    # Build a set of all referenced names (symbols + call sites)
    all_used_names: set[str] = set()
    for sym in symbols:
        all_used_names.add(sym.name)
    for module in modules:
        for caller, callees in module.call_sites.items():
            all_used_names.add(caller)
            for callee in callees:
                all_used_names.add(callee)

    for module in modules:
        for imp in module.imports:
            if not isinstance(imp, dict):
                continue
            imported_names: list[str] = imp.get("names", [])
            mod_name: str = imp.get("module", "")
            line_num: int = imp.get("line_start", imp.get("line", 0))

            for name in imported_names:
                if not name or name == "*":
                    continue
                # Check if the name is used anywhere in the project
                if name not in all_used_names:
                    source_desc = f"from {mod_name}" if mod_name else "import"
                    smells.append(CodeSmell(
                        kind="unused_import",
                        severity="info",
                        message=(
                            f"'{name}' imported {source_desc} "
                            f"appears unused in {module.path}"
                        ),
                        file_path=module.path,
                        detail=f"name={name} line={line_num}",
                    ))

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    smells.sort(key=lambda s: severity_order.get(s.severity, 9))
    return smells
