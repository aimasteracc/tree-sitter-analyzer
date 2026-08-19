"""Staged tree walker for cache symbol extraction."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from ._symbol_declarations import (
    _go_package_constants,
    _php_constants,
    _python_docstring,
    _python_module_constant,
)
from ._symbol_metrics import (
    _annotate_canonical_complexity,
    _count_decision_points,
    _count_nodes,
)
from ._symbol_rules import (
    _CLASS_LIKE,
    _ENUM_LIKE,
    _FUNCTION_LIKE,
    _GO_CONST_LIKE,
    _IMPORT_LIKE,
    _RUST_CONST_LIKE,
    _SCALA_CLASS_LIKE,
    _SCOPE_BODY_NODES,
    _VAR_DECL_LIKE,
    _WALK_MAX_DEPTH,
)
from ._symbol_syntax import (
    _bash_subscript_base,
    _c_function_def_name,
    _extract_parent_classes,
    _find_parent_class,
    _node_text,
    _scala_symbol_from_node,
)

_CPP_MODULE_IMPORT_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?import[ \t]+[^;\r\n]+[ \t]*;"
)


def _cpp_code_mask(source: str) -> list[bool]:
    """Mark C++ source positions that are outside comments and literals."""
    mask = [True] * len(source)
    i = 0
    while i < len(source):
        end = i
        if source.startswith("//", i):
            end = source.find("\n", i)
            while end >= 0:
                splice = end - 1
                if splice >= i and source[splice] == "\r":
                    splice -= 1
                if splice < i or source[splice] != "\\":
                    break
                end = source.find("\n", end + 1)
            end = len(source) if end < 0 else end
        elif source.startswith("/*", i):
            closing = source.find("*/", i + 2)
            end = len(source) if closing < 0 else closing + 2
        elif source.startswith('R"', i):
            opening = source.find("(", i + 2)
            delimiter = source[i + 2 : opening] if opening >= 0 else ""
            if opening >= 0 and len(delimiter) <= 16:
                marker = f'){delimiter}"'
                closing = source.find(marker, opening + 1)
                end = len(source) if closing < 0 else closing + len(marker)
        elif source[i] in {'"', "'"}:
            quote = source[i]
            end = i + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                elif source[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
        if end > i:
            mask[i:end] = [False] * (end - i)
            i = end
        else:
            i += 1
    return mask


def _python_module_scope_statements(module: ast.Module) -> list[ast.stmt]:
    """Return statements executed in module scope, excluding nested scopes."""
    statements: list[ast.stmt] = []
    scope_nodes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def visit_children(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                statements.append(child)
                if isinstance(child, scope_nodes):
                    continue
            visit_children(child)

    for statement in module.body:
        statements.append(statement)
        if not isinstance(statement, scope_nodes):
            visit_children(statement)
    return statements


_PYTHON_LOADER_SEED_NAMES = frozenset(
    {
        "__import__",
        "builtins.__import__",
        "importlib.import_module",
        "runpy.run_module",
        "runpy.run_path",
    }
)
_PYTHON_EVALUATOR_SEED_NAMES = frozenset(
    {"eval", "exec", "builtins.eval", "builtins.exec"}
)
_PYTHON_LOADER_MODULES: dict[str, tuple[str, ...]] = {
    "builtins": ("__import__",),
    "importlib": ("import_module",),
    "runpy": ("run_module", "run_path"),
}
_PYTHON_LOADER_ATTRIBUTES = frozenset(
    {"__import__", "import_module", "run_module", "run_path"}
)


@dataclass(frozen=True, slots=True)
class _PythonLoaderModel:
    """The loader vocabulary and the positions that are provably safe."""

    names: frozenset[str]
    evaluators: frozenset[str]
    roots: frozenset[str]
    safe: frozenset[int]


def _python_owner_exposes_loader(owner: str | None, names: frozenset[str]) -> bool:
    return owner is not None and any(name.startswith(f"{owner}.") for name in names)


def _python_module_alias_assignments(
    statements: list[ast.stmt],
) -> list[tuple[list[ast.Name], ast.expr]]:
    """Return module-scope assignments whose targets are all plain names."""

    pairs: list[tuple[list[ast.Name], ast.expr]] = []
    for statement in statements:
        targets: list[ast.expr]
        if isinstance(statement, ast.Assign):
            targets, value = list(statement.targets), statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        else:
            continue
        if all(isinstance(target, ast.Name) for target in targets):
            pairs.append(([t for t in targets if isinstance(t, ast.Name)], value))
    return pairs


def _python_loader_bindings(
    module: ast.Module,
) -> tuple[set[str], set[str], set[int]]:
    """Return loader names, evaluator names and the aliases that bind them."""

    names = set(_PYTHON_LOADER_SEED_NAMES)
    evaluators = set(_PYTHON_EVALUATOR_SEED_NAMES)
    established: set[int] = set()
    statements = _python_module_scope_statements(module)
    for statement in statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                members = _PYTHON_LOADER_MODULES.get(alias.name)
                if members is None:
                    continue
                bound = alias.asname or alias.name
                names.update(f"{bound}.{member}" for member in members)
                if alias.name == "builtins":
                    evaluators.update({f"{bound}.eval", f"{bound}.exec"})
                established.add(id(alias))
        elif isinstance(statement, ast.ImportFrom) and statement.level == 0:
            members = _PYTHON_LOADER_MODULES.get(statement.module or "")
            if members is None:
                continue
            for alias in statement.names:
                if alias.name in members:
                    names.add(alias.asname or alias.name)
                elif statement.module == "builtins" and alias.name in {"eval", "exec"}:
                    evaluators.add(alias.asname or alias.name)
                else:
                    continue
                established.add(id(alias))
    aliases = _python_module_alias_assignments(statements)
    changed = True
    while changed:
        changed = False
        for targets, value in aliases:
            reference = _python_reference_name(value)
            for target in targets:
                if reference in names and target.id not in names:
                    names.add(target.id)
                    changed = True
                if reference in evaluators and target.id not in evaluators:
                    evaluators.add(target.id)
                    changed = True
    return names, evaluators, established


def _python_static_loader_call(node: ast.Call, names: set[str]) -> bool:
    """Return whether a call loads a statically named module."""

    if _python_reference_name(node.func) not in names:
        return False
    if not node.args or isinstance(node.args[0], ast.Starred):
        return False
    return isinstance(node.args[0], ast.Constant) and isinstance(
        node.args[0].value, str
    )


def _python_safe_loader_nodes(module: ast.Module, names: set[str]) -> set[int]:
    """Return the loader references that are invoked or aliased, not retained."""

    safe: set[int] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and _python_static_loader_call(node, names):
            safe.add(id(node.func))
    statements = _python_module_scope_statements(module)
    for targets, value in _python_module_alias_assignments(statements):
        if _python_reference_name(value) not in names:
            continue
        safe.add(id(value))
        safe.update(id(target) for target in targets)
    return safe


def _python_static_bound_names(node: ast.AST) -> tuple[str, ...]:
    """Return the names a non-expression node binds in its enclosing scope."""

    if isinstance(node, ast.arg):
        return (node.arg,)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (node.name,)
    if isinstance(node, ast.ExceptHandler):
        return (node.name,) if isinstance(node.name, str) else ()
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return tuple(node.names)
    if isinstance(node, (ast.MatchAs, ast.MatchStar)):
        return (node.name,) if node.name is not None else ()
    if isinstance(node, ast.MatchMapping):
        return (node.rest,) if node.rest is not None else ()
    return ()


def _python_retains_loader_result(node: ast.AST, names: frozenset[str]) -> bool:
    """Return whether a node keeps the object a dynamic load produced."""

    def loads(candidate: ast.AST | None) -> bool:
        return isinstance(candidate, ast.Call) and (
            _python_reference_name(candidate.func) in names
        )

    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        return loads(node.value)
    if not isinstance(node, ast.expr):
        return False
    return any(loads(child) for child in ast.iter_child_nodes(node))


def _python_reference_is_safe(
    node: ast.Name | ast.Attribute, model: _PythonLoaderModel
) -> bool:
    """Return whether one loader-visible reference cannot hide a dependency."""

    reference = _python_reference_name(node)
    if reference is None:
        return not (
            isinstance(node, ast.Attribute) and node.attr in _PYTHON_LOADER_ATTRIBUTES
        )
    if reference in model.evaluators:
        return False
    if reference in model.names:
        return id(node) in model.safe
    if _python_owner_exposes_loader(reference, model.names):
        return False
    if isinstance(node, ast.Attribute) and node.attr in _PYTHON_LOADER_ATTRIBUTES:
        return False
    segments = reference.split(".")
    return not (
        segments[0] in model.roots
        and any(segment.startswith("_") for segment in segments[1:])
    )


def _python_projection_is_complete(
    module: ast.Module, model: _PythonLoaderModel, established: set[int]
) -> bool:
    """Return whether every loader-visible name sits in a projected position."""

    guarded = model.names | model.evaluators | model.roots

    def visit(node: ast.AST) -> bool:
        if isinstance(node, ast.ImportFrom) and node.module in _PYTHON_LOADER_MODULES:
            if any(alias.name == "*" for alias in node.names):
                return False
        if isinstance(node, ast.alias):
            if id(node) in established:
                return True
            return (node.asname or node.name.split(".", 1)[0]) not in guarded
        if _python_retains_loader_result(node, model.names):
            return False
        if isinstance(node, (ast.Name, ast.Attribute)):
            if not _python_reference_is_safe(node, model):
                return False
            if _python_reference_name(node) is not None:
                return True
        if any(name in guarded for name in _python_static_bound_names(node)):
            return False
        return all(visit(child) for child in ast.iter_child_nodes(node))

    return visit(module)


def _python_dynamic_loader_analysis(source: str) -> tuple[frozenset[str], bool]:
    """Return module loader aliases and whether every use is provably safe.

    The projection is certified only when each reference to a loader-visible
    name occupies a position the walker also projects: the callee of a call on
    a static module literal, or a module-scope alias binding. Every other
    position -- including syntax this walker does not model -- degrades the
    file to an honest ``unknown`` instead of a false claim of completeness.
    """

    try:
        module = ast.parse(source)
    except SyntaxError:
        return frozenset(_PYTHON_LOADER_SEED_NAMES), False
    names, evaluators, established = _python_loader_bindings(module)
    model = _PythonLoaderModel(
        names=frozenset(names),
        evaluators=frozenset(evaluators),
        roots=frozenset(name.split(".", 1)[0] for name in names if "." in name),
        safe=frozenset(_python_safe_loader_nodes(module, names)),
    )
    return model.names, _python_projection_is_complete(module, model, established)


def _python_dynamic_loader_names(source: str) -> frozenset[str]:
    """Return module-scoped Python dynamic-import call names."""

    return _python_dynamic_loader_analysis(source)[0]


def _python_reference_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _python_reference_name(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


_JSTS_MODULE_LOADER_ROOTS = frozenset({"module", "require"})
_JSTS_FILE_ALIAS_ANCESTORS = frozenset(
    {"program", "export_statement", "lexical_declaration", "variable_declaration"}
)
_JSTS_LOADER_OWNER_ROOTS = frozenset(
    {"global", "globalThis", "module", "self", "window"}
)
_JSTS_EVALUATOR_NAMES = frozenset({"Function", "eval"})
_JSTS_LOADER_FACTORY_NAME = "createRequire"
_JSTS_SHADOWABLE_GLOBALS = ("Function", "createRequire", "eval")
_JSTS_SAFE_LOADER_MEMBERS = frozenset({"meta", "resolve"})
_JSTS_NAME_NODES = frozenset(
    {
        "identifier",
        "import",
        "shorthand_property_identifier",
        "shorthand_property_identifier_pattern",
        "type_identifier",
    }
)
_JSTS_MEMBER_NODES = frozenset({"member_expression", "subscript_expression"})
_JSTS_ACCESSOR_NODES = frozenset(
    {
        "identifier",
        "private_property_identifier",
        "property_identifier",
        "shorthand_property_identifier",
        "shorthand_property_identifier_pattern",
        "string",
        "template_string",
    }
)


def _jsts_unwrap_parenthesized(node: Any) -> Any | None:
    """Return the single expression enclosed by any JS/TS parentheses."""

    while node.type == "parenthesized_expression":
        named_children = [
            child for child in node.children if getattr(child, "is_named", True)
        ]
        if len(named_children) != 1:
            return None
        node = named_children[0]
    return node


def _jsts_file_scoped_alias(node: Any) -> bool:
    """Return whether a declarator is unconditionally file scoped."""

    parent = getattr(node, "parent", None)
    while parent is not None:
        if parent.type not in _JSTS_FILE_ALIAS_ANCESTORS:
            return False
        if parent.type == "program":
            return True
        parent = getattr(parent, "parent", None)
    return False


def _jsts_file_scoped_declaration(node: Any) -> bool:
    """Return whether a named declaration binds in the program scope."""

    parent = getattr(node, "parent", None)
    while parent is not None and parent.type == "export_statement":
        parent = getattr(parent, "parent", None)
    return parent is not None and parent.type == "program"


def _jsts_pattern_binds_name(node: Any, source: str, target: str) -> bool:
    """Return whether one binding pattern introduces *target*."""

    if node.type in {
        "identifier",
        "shorthand_property_identifier_pattern",
        "type_identifier",
    }:
        return _node_text(node, source) == target
    if node.type == "import_specifier":
        local_name = node.child_by_field_name("alias") or node.child_by_field_name(
            "name"
        )
        return local_name is not None and _jsts_pattern_binds_name(
            local_name, source, target
        )
    field = (
        "value"
        if node.type == "pair_pattern"
        else "left"
        if node.type == "assignment_pattern"
        else "pattern"
        if node.type in {"optional_parameter", "required_parameter", "rest_parameter"}
        else None
    )
    if field is not None:
        pattern = node.child_by_field_name(field)
        return pattern is not None and _jsts_pattern_binds_name(pattern, source, target)
    return any(
        _jsts_pattern_binds_name(child, source, target)
        for child in node.children
        if getattr(child, "is_named", True)
    )


def _jsts_static_accessor_name(node: Any, source: str) -> str | None:
    """Return a member accessor that is statically known from syntax."""

    if node.type in {"property_identifier", "private_property_identifier"}:
        return _node_text(node, source).strip()
    text = _node_text(node, source).strip()
    if node.type == "string" and re.fullmatch(r"(['\"])[^'\"]*\1", text):
        return text[1:-1]
    if node.type == "template_string" and re.fullmatch(r"`[^`$]*`", text):
        return text[1:-1]
    return None


def _jsts_static_name(node: Any, source: str) -> str | None:
    """Return the static name a node contributes from any naming position."""

    if node.type in _JSTS_NAME_NODES:
        return _node_text(node, source).strip()
    return _jsts_static_accessor_name(node, source)


def _jsts_reference_path(node: Any, source: str) -> list[str | None] | None:
    """Return the dotted path of a reference, with None for dynamic segments."""

    node = _jsts_unwrap_parenthesized(node)
    if node is None:
        return None
    if node.type in _JSTS_NAME_NODES:
        return [_node_text(node, source).strip()]
    if node.type not in _JSTS_MEMBER_NODES:
        return None
    owner = node.child_by_field_name("object")
    accessor = node.child_by_field_name("property") or node.child_by_field_name("index")
    if owner is None or accessor is None:
        return None
    base = _jsts_reference_path(owner, source)
    if base is None:
        return None
    return [*base, _jsts_static_accessor_name(accessor, source)]


def _jsts_dotted(path: list[str | None]) -> str:
    """Return the dotted form of a fully static reference path."""

    return "" if None in path else ".".join(segment or "" for segment in path)


def _jsts_module_loader_reference(node: Any, source: str, loaders: set[str]) -> bool:
    """Return whether one syntax node is a tracked JS/TS module loader."""

    path = _jsts_reference_path(node, source)
    return path is not None and None not in path and _jsts_dotted(path) in loaders


def _jsts_enclosing_reference(node: Any) -> tuple[Any, Any]:
    """Return a reference's outermost parenthesised form and that form's parent."""

    current, parent = node, getattr(node, "parent", None)
    while parent is not None and parent.type == "parenthesized_expression":
        current, parent = parent, getattr(parent, "parent", None)
    return current, parent


def _jsts_reference_is_owner(node: Any) -> bool:
    """Return whether a reference only owns a longer reference around it."""

    current, parent = _jsts_enclosing_reference(node)
    if parent is None or parent.type not in _JSTS_MEMBER_NODES:
        return False
    return bool(parent.child_by_field_name("object") == current)


def _jsts_is_import_keyword(node: Any) -> bool:
    """Return whether a node is the ``import`` keyword of a static import."""

    parent = getattr(node, "parent", None)
    return (
        node.type == "import"
        and parent is not None
        and parent.type == "import_statement"
    )


def _jsts_renames_imported_name(node: Any) -> bool:
    """Return whether a node is a specifier's remote name, not a local binding."""

    parent = getattr(node, "parent", None)
    if parent is None or parent.type not in {"export_specifier", "import_specifier"}:
        return False
    return (
        parent.child_by_field_name("alias") is not None
        and parent.child_by_field_name("name") == node
    )


def _jsts_accessor_owner_is_global(node: Any, source: str) -> bool:
    """Return whether a member accessor selects from a known JS global object."""

    parent = getattr(node, "parent", None)
    if parent is None or parent.type not in _JSTS_MEMBER_NODES:
        return False
    accessor = parent.child_by_field_name("property") or parent.child_by_field_name(
        "index"
    )
    if accessor != node:
        return False
    owner = parent.child_by_field_name("object")
    if owner is None:
        return False
    path = _jsts_reference_path(owner, source)
    return path is not None and len(path) == 1 and path[0] in _JSTS_LOADER_OWNER_ROOTS


@dataclass(slots=True)
class _SymbolWalker:
    source: str
    symbols: list[dict[str, Any]]
    language: str
    truncated_flag: list[bool] | None
    python_dynamic_loaders: set[str] = field(init=False, repr=False)
    jsts_module_loaders: set[str] = field(init=False, repr=False)
    jsts_shadowed_globals: set[str] = field(init=False, repr=False)
    import_projection_complete: bool = field(init=False, repr=False, default=True)
    java_static_for_name: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        self.python_dynamic_loaders = set()
        self.jsts_module_loaders = {"require", "module.require", "import"}
        self.jsts_shadowed_globals = set()
        if self.language == "python":
            loaders, self.import_projection_complete = _python_dynamic_loader_analysis(
                self.source
            )
            self.python_dynamic_loaders.update(loaders)
        if self.language == "java":
            self.java_static_for_name = bool(
                re.search(
                    r"(?m)^\s*import\s+static\s+java\.lang\.Class\.forName\s*;",
                    self.source,
                )
            )

    def walk(self, node: Any, depth: int = 0, enclosed: bool = False) -> None:
        if depth == 0:
            self._discover_jsts_module_loaders(node)
        if depth > _WALK_MAX_DEPTH:
            if self.truncated_flag is not None:
                self.truncated_flag[0] = True
            return
        self._collect_node(node, depth, enclosed)
        child_enclosed = enclosed or node.type in _SCOPE_BODY_NODES.get(
            self.language, frozenset()
        )
        for child in node.children:
            self.walk(child, depth + 1, child_enclosed)

    def _discover_jsts_module_loaders(self, root: Any) -> None:
        """Collect direct JS/TS loader aliases before projecting any calls."""

        if self.language not in {"javascript", "typescript"}:
            return
        candidates: list[tuple[str, Any]] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "variable_declarator" and _jsts_file_scoped_alias(node):
                name = node.child_by_field_name("name")
                value = node.child_by_field_name("value")
                if name is not None:
                    self._shadow_jsts_globals(name, _JSTS_SHADOWABLE_GLOBALS)
                if name is not None and value is not None and name.type == "identifier":
                    candidates.append((_node_text(name, self.source), value))
            elif node.type in {
                "class_declaration",
                "function_declaration",
                "generator_function_declaration",
            } and _jsts_file_scoped_declaration(node):
                name = node.child_by_field_name("name")
                if name is not None:
                    self._shadow_jsts_globals(name, _JSTS_SHADOWABLE_GLOBALS)
            elif node.type == "import_clause":
                # An import of ``createRequire`` IS the loader factory, so an
                # import never shadows it away.
                self._shadow_jsts_globals(node, tuple(_JSTS_EVALUATOR_NAMES))
            stack.extend(node.children)
        changed = True
        while changed:
            changed = False
            for name, value in candidates:
                if name not in self.jsts_module_loaders and (
                    _jsts_module_loader_reference(
                        value, self.source, self.jsts_module_loaders
                    )
                ):
                    self.jsts_module_loaders.add(name)
                    changed = True

    def _shadow_jsts_globals(self, pattern: Any, candidates: tuple[str, ...]) -> None:
        """Record globals a file-scoped binding replaces with its own value."""

        self.jsts_shadowed_globals.update(
            candidate
            for candidate in candidates
            if _jsts_pattern_binds_name(pattern, self.source, candidate)
        )

    def _collect_node(self, node: Any, depth: int, enclosed: bool) -> None:
        self._mark_jsts_loader_reference(node)
        name_node = node.child_by_field_name("name")
        function_name = self._function_name(node, name_node)
        if function_name is not None:
            self._append_function(node, function_name)
            return
        if self._append_scala(node, enclosed):
            return
        if node.type in _CLASS_LIKE:
            self._append_class(node, name_node)
            return
        if node.type in _IMPORT_LIKE:
            self._append_import(node)
            return
        self._append_python_loader_assignment(node)
        if self._append_include_next(node):
            return
        if self._append_jsts_reexport(node):
            return
        if self._append_typescript_path_reference(node):
            return
        if self._append_jsts_module_call(node):
            return
        if self._append_python_module_call(node):
            return
        if self._append_java_reflective_load(node):
            return
        if self._is_variable(node, name_node, enclosed):
            self._append_variable(node, name_node, depth)
            return
        self._append_constant(node, name_node, enclosed)

    def _mark_jsts_loader_reference(self, node: Any) -> None:
        """Fail closed unless a loader-visible name sits in a projected position.

        Every reference to a module loader, to an object that owns one, or to
        the evaluator must be either invoked on a static module literal or
        bound as a file-scoped alias the walker follows. Any other position --
        including syntax this walker does not model -- degrades the file to an
        honest ``unknown``.
        """

        if self.language not in {"javascript", "typescript"}:
            return
        if not self.import_projection_complete:
            return
        if self._jsts_exposes_global(node) or self._jsts_retains_loader(node):
            self.import_projection_complete = False

    def _jsts_exposes_global(self, node: Any) -> bool:
        """Return whether a name hands out the evaluator or the loader factory."""

        if node.type not in _JSTS_ACCESSOR_NODES:
            return False
        name = _jsts_static_name(node, self.source)
        if name is None or name in self.jsts_shadowed_globals:
            return False
        if name == _JSTS_LOADER_FACTORY_NAME:
            return True
        if name not in _JSTS_EVALUATOR_NAMES:
            return False
        if node.type in _JSTS_NAME_NODES:
            return True
        return _jsts_accessor_owner_is_global(node, self.source)

    def _jsts_retains_loader(self, node: Any) -> bool:
        """Return whether a reference keeps a module loader out of projection."""

        if node.type not in _JSTS_NAME_NODES | _JSTS_MEMBER_NODES:
            return False
        if _jsts_is_import_keyword(node) or _jsts_reference_is_owner(node):
            return False
        if _jsts_renames_imported_name(node):
            return False
        path = _jsts_reference_path(node, self.source)
        if path is None:
            return False
        for index in range(1, len(path) + 1):
            if path[index - 1] is None:
                owner = _jsts_dotted(path[: index - 1])
                return (
                    owner in self.jsts_module_loaders
                    or owner in _JSTS_LOADER_OWNER_ROOTS
                )
            dotted = _jsts_dotted(path[:index])
            if dotted in self.jsts_module_loaders:
                if index == len(path):
                    return not self._jsts_loader_position_is_projected(node)
                return path[index] not in _JSTS_SAFE_LOADER_MEMBERS
            if index == len(path) and dotted in _JSTS_LOADER_OWNER_ROOTS:
                return True
        return False

    def _jsts_loader_position_is_projected(self, node: Any) -> bool:
        """Return whether a loader reference is invoked or aliased, not stored."""

        current, parent = _jsts_enclosing_reference(node)
        if parent is None:
            return False
        if parent.type == "call_expression":
            return bool(parent.child_by_field_name("function") == current)
        if parent.type != "variable_declarator" or not _jsts_file_scoped_alias(parent):
            return False
        name = parent.child_by_field_name("name")
        value = parent.child_by_field_name("value")
        if name is None or name.type != "identifier" or value is None:
            return False
        if value == current:
            return True
        return (
            name == node
            and _node_text(name, self.source).strip() not in _JSTS_MODULE_LOADER_ROOTS
            and _jsts_module_loader_reference(
                value, self.source, self.jsts_module_loaders
            )
        )

    def _function_name(self, node: Any, name_node: Any) -> str | None:
        if node.type not in _FUNCTION_LIKE:
            return None
        if name_node is not None:
            return _node_text(name_node, self.source)
        if node.type == "function_definition" and self.language == "c":
            return _c_function_def_name(node, self.source)
        return None

    def _append_function(self, node: Any, name: str) -> None:
        params_node = node.child_by_field_name("parameters")
        symbol: dict[str, Any] = {
            "kind": "function",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "params": _node_text(params_node, self.source) if params_node else "",
            "language": self.language,
        }
        decision_points = _count_decision_points(node, self.language)
        if decision_points:
            symbol["decision_points"] = decision_points
        return_type = node.child_by_field_name("return_type")
        if return_type is not None:
            symbol["return_type"] = _node_text(return_type, self.source).lstrip(": ")
        self._add_python_docstring(symbol, node)
        parent_class = _find_parent_class(node, self.source)
        if parent_class:
            symbol["kind"] = "method"
            symbol["class"] = parent_class
        self.symbols.append(symbol)

    def _add_python_docstring(self, symbol: dict[str, Any], node: Any) -> None:
        if self.language != "python":
            return
        docstring = _python_docstring(node, self.source)
        if docstring is not None:
            symbol["docstring"] = docstring

    def _append_scala(self, node: Any, enclosed: bool) -> bool:
        if self.language != "scala" or node.type not in _SCALA_CLASS_LIKE or enclosed:
            return False
        symbol = _scala_symbol_from_node(node, self.source)
        if symbol is not None:
            self.symbols.append(symbol)
        return True

    def _append_class(self, node: Any, name_node: Any) -> None:
        effective_name = self._class_name_node(node, name_node)
        if effective_name is None:
            return
        name = _node_text(effective_name, self.source)
        if not name:
            return
        symbol: dict[str, Any] = {
            "kind": "enum" if node.type in _ENUM_LIKE else "class",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "language": self.language,
        }
        parents = _extract_parent_classes(node, self.source, self.language)
        if parents:
            symbol["parents"] = parents
        self._add_python_docstring(symbol, node)
        self.symbols.append(symbol)

    @staticmethod
    def _class_name_node(node: Any, name_node: Any) -> Any:
        if name_node is not None:
            return name_node
        for child in node.children:
            if child.type in ("type_identifier", "constant", "identifier"):
                return child
        return None

    def _append_import(self, node: Any) -> None:
        text = _node_text(node, self.source)
        if self.language == "python":
            self.python_dynamic_loaders.update(_python_dynamic_loader_names(text))
        self.symbols.append(
            {
                "kind": "import",
                "text": text,
                "line": node.start_point[0] + 1,
                "language": self.language,
            }
        )

    def _append_jsts_module_call(self, node: Any) -> bool:
        """Project JS/TS module loads so unresolved calls fail closed."""
        if self.language not in {"javascript", "typescript"}:
            return False
        if node.type != "call_expression":
            return False
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return False
        if _jsts_unwrap_parenthesized(function) is None:
            self.import_projection_complete = False
            return False
        if not _jsts_module_loader_reference(
            function, self.source, self.jsts_module_loaders
        ):
            return False
        self._append_import(node)
        return True

    def _append_include_next(self, node: Any) -> bool:
        """Retain compiler search-path includes as fail-closed evidence."""
        if self.language not in {"c", "cpp"} or node.type != "preproc_call":
            return False
        if re.match(r"^\s*#\s*include_next\b", _node_text(node, self.source)) is None:
            return False
        self._append_import(node)
        return True

    def _append_jsts_reexport(self, node: Any) -> bool:
        """Project JS/TS re-exports that introduce module dependencies."""
        if self.language not in {"javascript", "typescript"}:
            return False
        if node.type != "export_statement":
            return False
        if node.child_by_field_name("source") is None:
            return False
        self._append_import(node)
        return True

    def _append_typescript_path_reference(self, node: Any) -> bool:
        """Project triple-slash declaration-file references as dependencies."""
        if self.language != "typescript" or node.type != "comment":
            return False
        text = _node_text(node, self.source)
        if (
            re.fullmatch(
                r"\s*///\s*<reference\b"
                r"(?=[^>]*\bpath\s*=\s*(['\"])[^'\"]+\1)[^>]*?/?>\s*",
                text,
            )
            is None
        ):
            return False
        self._append_import(node)
        return True

    def _append_python_module_call(self, node: Any) -> bool:
        """Project Python dynamic loads so unresolved calls fail closed."""
        if self.language != "python" or node.type != "call":
            return False
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return False
        while function.type == "parenthesized_expression":
            named_children = [
                child for child in function.children if getattr(child, "is_named", True)
            ]
            if len(named_children) != 1:
                self.import_projection_complete = False
                return False
            function = named_children[0]
        if _node_text(function, self.source) not in self.python_dynamic_loaders:
            return False
        self._append_import(node)
        return True

    def _append_python_loader_assignment(self, node: Any) -> bool:
        """Project simple aliases so snapshot readers can verify loader calls."""
        if self.language != "python" or node.type not in {
            "assignment",
            "annotated_assignment",
        }:
            return False
        try:
            body = ast.parse(_node_text(node, self.source)).body
        except SyntaxError:
            return False
        if len(body) != 1:
            return False
        statement = body[0]
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        else:
            return False
        if _python_reference_name(value) not in self.python_dynamic_loaders or not any(
            isinstance(target, ast.Name) for target in targets
        ):
            return False
        self._append_import(node)
        return True

    def _append_java_reflective_load(self, node: Any) -> bool:
        """Project Class.forName calls so reflection cannot hide dependencies."""
        if self.language != "java" or node.type != "method_invocation":
            return False
        name = node.child_by_field_name("name")
        object_node = node.child_by_field_name("object")
        arguments = node.child_by_field_name("arguments")
        if name is None or arguments is None:
            return False
        if _node_text(name, self.source) != "forName":
            return False
        if object_node is None:
            if not self.java_static_for_name:
                return False
        elif _node_text(object_node, self.source) not in {
            "Class",
            "java.lang.Class",
        }:
            return False
        self._append_import(node)
        return True

    def _is_variable(self, node: Any, name_node: Any, enclosed: bool) -> bool:
        if node.type not in _VAR_DECL_LIKE or name_node is None:
            return False
        if self.language in ("javascript", "typescript", "java", "csharp"):
            if enclosed:
                return False
        return not (
            node.type == "variable_assignment"
            and node.parent is not None
            and node.parent.type == "command"
        )

    def _append_variable(self, node: Any, name_node: Any, depth: int) -> None:
        if name_node.type == "subscript":
            name_node = _bash_subscript_base(name_node)
        name = _node_text(name_node, self.source) if name_node is not None else ""
        if name and (not name.startswith("_") or depth < 3):
            self.symbols.append(
                {
                    "kind": "variable",
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "language": self.language,
                }
            )

    def _append_constant(self, node: Any, name_node: Any, enclosed: bool) -> None:
        if node.type == "assignment" and self.language == "python" and not enclosed:
            symbol = _python_module_constant(node, self.source)
            if symbol is not None:
                self.symbols.append(symbol)
            return
        if node.type in _GO_CONST_LIKE and self.language == "go" and not enclosed:
            self.symbols.extend(_go_package_constants(node, self.source))
            return
        if self._is_rust_constant(node, name_node, enclosed):
            self.symbols.append(
                {
                    "kind": "constant",
                    "name": _node_text(name_node, self.source),
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "language": "rust",
                }
            )
            return
        if node.type == "const_declaration" and self.language == "php" and not enclosed:
            self.symbols.extend(_php_constants(node, self.source))

    def _is_rust_constant(self, node: Any, name_node: Any, enclosed: bool) -> bool:
        return (
            node.type in _RUST_CONST_LIKE
            and self.language == "rust"
            and not enclosed
            and name_node is not None
            and _node_text(name_node, self.source) != "_"
        )


def _walk_for_symbols(
    node: Any,
    source: str,
    symbols: list[dict[str, Any]],
    language: str,
    depth: int = 0,
    enclosed: bool = False,
    _truncated_flag: list[bool] | None = None,
) -> None:
    """Walk an AST while preserving the historical helper signature."""
    _SymbolWalker(source, symbols, language, _truncated_flag).walk(
        node, depth, enclosed
    )


def _extract_symbols(tree: Any, source_code: str, language: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    if tree is None:
        return {
            "symbols": symbols,
            "node_count": 0,
            "truncated_depth": False,
            "import_projection_complete": True,
            "syntax_error": True,
        }
    root = tree.root_node
    truncated_flag = [False]
    walker = _SymbolWalker(source_code, symbols, language, truncated_flag)
    walker.walk(root)
    if language == "cpp":
        code_mask = _cpp_code_mask(source_code)
        projected = {
            (symbol.get("text"), symbol.get("line"))
            for symbol in symbols
            if symbol.get("kind") == "import"
        }
        for match in _CPP_MODULE_IMPORT_RE.finditer(source_code):
            keyword = re.search(r"\bimport\b", match.group(0))
            if keyword is None or not code_mask[match.start() + keyword.start()]:
                continue
            text = match.group(0).strip()
            line = source_code.count("\n", 0, match.start()) + 1
            if (text, line) not in projected:
                symbols.append(
                    {
                        "kind": "import",
                        "text": text,
                        "line": line,
                        "language": language,
                    }
                )
    _annotate_canonical_complexity(symbols, tree, source_code, language)
    return {
        "symbols": symbols,
        "node_count": _count_nodes(root),
        "truncated_depth": truncated_flag[0],
        "import_projection_complete": walker.import_projection_complete,
        "syntax_error": bool(getattr(root, "has_error", False)),
    }


def _extract_imports(symbols: dict[str, Any]) -> list[dict[str, Any]]:
    """Return per-statement import entries carrying the source line.

    Entries are dicts with text and line keys so the ast_imports table can
    record the statement line instead of a constant zero; string consumers
    are still served by the text key (dogfood F5, #1275).
    """
    return [
        {
            "text": symbol["text"],
            "line": symbol.get("line", 0),
        }
        for symbol in symbols.get("symbols", [])
        if symbol.get("kind") == "import"
    ]


def _extract_structure(symbols: dict[str, Any]) -> dict[str, Any]:
    functions = [
        {"name": symbol["name"], "line": symbol["line"]}
        for symbol in symbols.get("symbols", [])
        if symbol["kind"] in ("function", "method")
    ]
    classes = [
        {"name": symbol["name"], "line": symbol["line"]}
        for symbol in symbols.get("symbols", [])
        if symbol["kind"] in ("class", "enum")
    ]
    return {"functions": functions, "classes": classes}
