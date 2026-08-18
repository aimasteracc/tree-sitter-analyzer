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


def _python_assignment_target_leaves(target: ast.expr) -> list[ast.expr]:
    """Return the binding leaves of one assignment target."""

    if isinstance(target, (ast.List, ast.Tuple)):
        return [
            leaf
            for element in target.elts
            for leaf in _python_assignment_target_leaves(element)
        ]
    if isinstance(target, ast.Starred):
        return _python_assignment_target_leaves(target.value)
    return [target]


def _python_module_control_bindings(statements: list[ast.stmt]) -> set[str]:
    """Return names rebound by module-level control-flow targets."""

    bindings: set[str] = set()

    def add_target(target: ast.expr) -> None:
        bindings.update(
            leaf.id
            for leaf in _python_assignment_target_leaves(target)
            if isinstance(leaf, ast.Name)
        )

    class BindingVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            del node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            del node

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            del node

        def visit_Lambda(self, node: ast.Lambda) -> None:
            del node

        def visit_ListComp(self, node: ast.ListComp) -> None:
            del node

        def visit_SetComp(self, node: ast.SetComp) -> None:
            del node

        def visit_DictComp(self, node: ast.DictComp) -> None:
            del node

        def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
            del node

        def visit_For(self, node: ast.For) -> None:
            add_target(node.target)
            self.generic_visit(node)

        def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
            add_target(node.target)
            self.generic_visit(node)

        def visit_With(self, node: ast.With) -> None:
            for item in node.items:
                if item.optional_vars is not None:
                    add_target(item.optional_vars)
            self.generic_visit(node)

        def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
            for item in node.items:
                if item.optional_vars is not None:
                    add_target(item.optional_vars)
            self.generic_visit(node)

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            if isinstance(node.name, str):
                bindings.add(node.name)
            self.generic_visit(node)

        def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
            add_target(node.target)
            self.generic_visit(node.value)

        def visit_MatchAs(self, node: ast.MatchAs) -> None:
            if node.name is not None:
                bindings.add(node.name)
            self.generic_visit(node)

        def visit_MatchStar(self, node: ast.MatchStar) -> None:
            if node.name is not None:
                bindings.add(node.name)

        def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
            if node.rest is not None:
                bindings.add(node.rest)
            self.generic_visit(node)

    visitor = BindingVisitor()
    for statement in statements:
        visitor.visit(statement)
    return bindings


def _python_loader_mapping_owner(node: ast.expr) -> str | None:
    """Return the module whose attribute dictionary *node* exposes."""

    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        return _python_reference_name(node.value)
    if (
        isinstance(node, ast.Call)
        and _python_reference_name(node.func) in {"vars", "builtins.vars"}
        and node.args
    ):
        return _python_reference_name(node.args[0])
    return None


def _python_owner_exposes_loader(owner: str | None, names: set[str]) -> bool:
    return owner is not None and any(name.startswith(f"{owner}.") for name in names)


def _python_value_stores_loader(node: ast.expr, names: set[str]) -> bool:
    """Return whether a value retains a loader reference for later use."""

    if _python_reference_name(node) in names:
        return True
    mapping_owner = _python_loader_mapping_owner(node)
    if _python_owner_exposes_loader(mapping_owner, names):
        return True
    if isinstance(node, ast.Subscript):
        key = node.slice.value if isinstance(node.slice, ast.Constant) else None
        dynamic_key = not isinstance(node.slice, ast.Constant)
        owner = _python_loader_mapping_owner(node.value)
        if owner is not None:
            if (dynamic_key and _python_owner_exposes_loader(owner, names)) or (
                isinstance(key, str) and f"{owner}.{key}" in names
            ):
                return True
            return _python_value_stores_loader(node.slice, names)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"get", "__getitem__", "pop", "setdefault"}
        and node.args
    ):
        owner = _python_loader_mapping_owner(node.func.value)
        key = node.args[0].value if isinstance(node.args[0], ast.Constant) else None
        if owner is not None:
            if (
                not isinstance(node.args[0], ast.Constant)
                and _python_owner_exposes_loader(owner, names)
            ) or (isinstance(key, str) and f"{owner}.{key}" in names):
                return True
            return any(
                _python_value_stores_loader(child, names)
                for child in (*node.args, *(kw.value for kw in node.keywords))
            )
    if (
        isinstance(node, ast.Call)
        and _python_reference_name(node.func) in {"getattr", "builtins.getattr"}
        and len(node.args) >= 2
    ):
        owner = _python_reference_name(node.args[0])
        attribute = (
            node.args[1].value if isinstance(node.args[1], ast.Constant) else None
        )
        if _python_owner_exposes_loader(owner, names) and (
            not isinstance(node.args[1], ast.Constant)
            or (isinstance(attribute, str) and f"{owner}.{attribute}" in names)
        ):
            return True
    children: list[ast.expr]
    if isinstance(node, ast.Call):
        children = [*node.args, *(keyword.value for keyword in node.keywords)]
        if _python_reference_name(node.func) not in names:
            children.append(node.func)
    else:
        children = [
            child for child in ast.iter_child_nodes(node) if isinstance(child, ast.expr)
        ]
    return any(_python_value_stores_loader(child, names) for child in children)


def _python_function_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.expr, ...]:
    """Return evaluated parameter and return annotations for a function."""

    arguments = (
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    )
    annotations = tuple(
        argument.annotation for argument in arguments if argument.annotation is not None
    )
    if node.args.vararg is not None and node.args.vararg.annotation is not None:
        annotations += (node.args.vararg.annotation,)
    if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
        annotations += (node.args.kwarg.annotation,)
    if node.returns is not None:
        annotations += (node.returns,)
    return annotations


def _python_control_flow_header_values(statement: ast.stmt) -> tuple[ast.expr, ...]:
    """Return expressions evaluated by a control-flow statement's header."""

    if isinstance(statement, (ast.If, ast.While)):
        return (statement.test,)
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        return (statement.iter,)
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return tuple(item.context_expr for item in statement.items)
    if isinstance(statement, ast.Match):
        return (statement.subject,) + tuple(
            case.guard for case in statement.cases if case.guard is not None
        )
    if isinstance(statement, ast.Assert):
        return (statement.test,) + (() if statement.msg is None else (statement.msg,))
    return ()


def _python_dynamic_loader_analysis(source: str) -> tuple[frozenset[str], bool]:
    """Return module loader aliases and whether their scope is unambiguous."""
    names = {"__import__", "builtins.__import__", "importlib.import_module"}
    try:
        module = ast.parse(source)
    except SyntaxError:
        return frozenset(names), False
    module_statements = _python_module_scope_statements(module)
    for statement in module_statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "importlib":
                    names.add(f"{alias.asname or alias.name}.import_module")
                elif alias.name == "builtins":
                    names.add(f"{alias.asname or alias.name}.__import__")
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module in {"builtins", "importlib"}
        ):
            for alias in statement.names:
                if statement.module == "importlib" and alias.name == "*":
                    return frozenset(names), False
                if (statement.module, alias.name) in {
                    ("builtins", "__import__"),
                    ("importlib", "import_module"),
                }:
                    names.add(alias.asname or alias.name)
    assignments: list[tuple[list[ast.expr], ast.expr]] = []
    for statement in module_statements:
        if isinstance(statement, ast.Assign):
            assignments.append((statement.targets, statement.value))
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            assignments.append(([statement.target], statement.value))
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            reference = _python_reference_name(value)
            if reference not in names:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    loader_roots = {name.split(".", 1)[0] for name in names}
    module_rebinding = any(
        (
            _python_reference_name(target) in names
            or (isinstance(target, ast.Name) and target.id in loader_roots)
        )
        and _python_reference_name(value) not in names
        for targets, value in assignments
        for outer_target in targets
        for target in _python_assignment_target_leaves(outer_target)
    )
    unsafe_loader_storage = any(
        (
            _python_reference_name(value) in names
            and any(not isinstance(target, ast.Name) for target in targets)
        )
        or (
            _python_reference_name(value) not in names
            and _python_value_stores_loader(value, names)
        )
        for targets, value in assignments
    )
    unsafe_loader_storage = unsafe_loader_storage or any(
        isinstance(statement, ast.AnnAssign)
        and _python_value_stores_loader(statement.annotation, names)
        for statement in module_statements
    )
    unsafe_loader_storage = unsafe_loader_storage or any(
        isinstance(statement, ast.Expr)
        and _python_value_stores_loader(statement.value, names)
        for statement in module_statements
    )
    unsafe_loader_storage = unsafe_loader_storage or any(
        isinstance(node, ast.NamedExpr)
        and _python_value_stores_loader(node.value, names)
        for statement in module_statements
        for node in ast.walk(statement)
    )
    unsafe_loader_storage = unsafe_loader_storage or any(
        _python_value_stores_loader(value, names)
        for statement in module_statements
        for value in _python_control_flow_header_values(statement)
    )
    dynamic_code_execution = any(
        isinstance(node, ast.Call)
        and _python_reference_name(node.func)
        in {"exec", "eval", "builtins.exec", "builtins.eval"}
        for statement in module_statements
        for node in ast.walk(statement)
    )
    module_rebinding = module_rebinding or unsafe_loader_storage
    module_rebinding = module_rebinding or bool(
        loader_roots.intersection(_python_module_control_bindings(module_statements))
    )
    for statement in module_statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                safe = (
                    alias.name == "importlib" and f"{bound_name}.import_module" in names
                ) or (alias.name == "builtins" and f"{bound_name}.__import__" in names)
                module_rebinding = module_rebinding or (
                    bound_name in loader_roots and not safe
                )
        elif isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                bound_name = alias.asname or alias.name
                safe = statement.level == 0 and (
                    (statement.module, alias.name)
                    in {
                        ("builtins", "__import__"),
                        ("importlib", "import_module"),
                    }
                )
                module_rebinding = module_rebinding or (
                    bound_name in loader_roots and not safe
                )
        elif isinstance(
            statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            module_rebinding = module_rebinding or statement.name in loader_roots
        elif isinstance(statement, ast.AugAssign):
            module_rebinding = module_rebinding or any(
                _python_reference_name(leaf) in names
                for leaf in _python_assignment_target_leaves(statement.target)
            )
        elif isinstance(statement, ast.Delete):
            module_rebinding = module_rebinding or any(
                _python_reference_name(leaf) in names
                for target in statement.targets
                for leaf in _python_assignment_target_leaves(target)
            )
    nested_bindings: set[str] = set()
    nested_loader_alias = False
    for statement in module_statements:
        nested_scopes: list[ast.AST] = []
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nested_scopes.append(statement)
        else:
            nested_scopes.extend(
                node
                for node in ast.walk(statement)
                if isinstance(
                    node,
                    (
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                )
            )
        for node in (child for scope in nested_scopes for child in ast.walk(scope)):
            if isinstance(node, ast.stmt):
                nested_loader_alias = nested_loader_alias or any(
                    _python_value_stores_loader(value, names)
                    for value in _python_control_flow_header_values(node)
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nested_loader_alias = nested_loader_alias or any(
                    _python_value_stores_loader(decorator, names)
                    for decorator in node.decorator_list
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                arguments = (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                nested_bindings.update(argument.arg for argument in arguments)
                if node.args.vararg is not None:
                    nested_bindings.add(node.args.vararg.arg)
                if node.args.kwarg is not None:
                    nested_bindings.add(node.args.kwarg.arg)
                defaults = (*node.args.defaults, *node.args.kw_defaults)
                nested_loader_alias = nested_loader_alias or any(
                    default is not None and _python_value_stores_loader(default, names)
                    for default in defaults
                )
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nested_loader_alias = nested_loader_alias or any(
                        _python_value_stores_loader(annotation, names)
                        for annotation in _python_function_annotations(node)
                    )
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                nested_bindings.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
                nested_bindings.add(node.name)
            elif isinstance(node, ast.Assign):
                leaves = {
                    leaf
                    for target in node.targets
                    for leaf in _python_assignment_target_leaves(target)
                }
                nested_bindings.update(
                    leaf.id for leaf in leaves if isinstance(leaf, ast.Name)
                )
                nested_loader_alias = nested_loader_alias or (
                    _python_value_stores_loader(node.value, names)
                    or any(_python_reference_name(leaf) in names for leaf in leaves)
                )
            elif isinstance(node, ast.AnnAssign):
                leaves = set(_python_assignment_target_leaves(node.target))
                nested_bindings.update(
                    leaf.id for leaf in leaves if isinstance(leaf, ast.Name)
                )
                nested_loader_alias = nested_loader_alias or any(
                    _python_reference_name(leaf) in names for leaf in leaves
                )
                nested_loader_alias = nested_loader_alias or (
                    node.value is not None
                    and _python_value_stores_loader(node.value, names)
                )
                nested_loader_alias = nested_loader_alias or (
                    _python_value_stores_loader(node.annotation, names)
                )
            elif isinstance(node, ast.AugAssign):
                leaves = set(_python_assignment_target_leaves(node.target))
                nested_bindings.update(
                    leaf.id for leaf in leaves if isinstance(leaf, ast.Name)
                )
                nested_loader_alias = nested_loader_alias or any(
                    _python_reference_name(leaf) in names for leaf in leaves
                )
            elif isinstance(node, ast.Delete):
                nested_loader_alias = nested_loader_alias or any(
                    _python_reference_name(leaf) in names
                    for target in node.targets
                    for leaf in _python_assignment_target_leaves(target)
                )
            elif isinstance(node, ast.NamedExpr):
                nested_loader_alias = nested_loader_alias or (
                    isinstance(node.target, ast.Name)
                    and _python_value_stores_loader(node.value, names)
                )
            elif isinstance(node, (ast.Expr, ast.Return, ast.Yield, ast.YieldFrom)):
                escaped_value = getattr(node, "value", None)
                nested_loader_alias = nested_loader_alias or (
                    isinstance(escaped_value, ast.expr)
                    and _python_value_stores_loader(escaped_value, names)
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    nested_bindings.add(alias.asname or alias.name.split(".", 1)[0])
                    nested_loader_alias = nested_loader_alias or alias.name in {
                        "builtins",
                        "importlib",
                    }
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    nested_bindings.add(alias.asname or alias.name)
                    nested_loader_alias = nested_loader_alias or (
                        node.level == 0
                        and (node.module, alias.name)
                        in {
                            ("builtins", "__import__"),
                            ("importlib", "import_module"),
                        }
                    )
    complete = (
        not module_rebinding
        and not nested_loader_alias
        and not dynamic_code_execution
        and not loader_roots.intersection(nested_bindings)
    )
    return frozenset(names), complete


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


def _jsts_pattern_binds_module_loader(
    node: Any, source: str, loaders: set[str]
) -> bool:
    """Return whether one JS/TS binding pattern shadows a module loader."""

    if node.type in {
        "identifier",
        "shorthand_property_identifier_pattern",
        "type_identifier",
    }:
        value = _node_text(node, source)
        return value in loaders or value in _JSTS_MODULE_LOADER_ROOTS
    if node.type == "import_specifier":
        local_name = node.child_by_field_name("alias") or node.child_by_field_name(
            "name"
        )
        return local_name is not None and _jsts_pattern_binds_module_loader(
            local_name, source, loaders
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
        return pattern is not None and _jsts_pattern_binds_module_loader(
            pattern, source, loaders
        )
    if node.type in {
        "array_pattern",
        "import_clause",
        "named_imports",
        "namespace_import",
        "object_pattern",
        "rest_pattern",
    }:
        return any(
            _jsts_pattern_binds_module_loader(child, source, loaders)
            for child in node.children
            if getattr(child, "is_named", True)
        )
    return False


def _jsts_module_loader_reference(node: Any, source: str, loaders: set[str]) -> bool:
    """Return whether one syntax node is a tracked JS/TS module loader."""

    while node.type == "parenthesized_expression":
        named_children = [
            child for child in node.children if getattr(child, "is_named", True)
        ]
        if len(named_children) != 1:
            return False
        node = named_children[0]
    value = _node_text(node, source)
    value = value.replace("?.", ".")
    return value in loaders or bool(
        re.fullmatch(
            r"module\s*(?:\.\s*require|\.?\s*\[\s*(['\"`])require\1\s*\])",
            value,
        )
    )


def _jsts_indirect_module_loader_call(
    node: Any, source: str, loaders: set[str]
) -> bool:
    """Return whether ``node`` is a tracked loader's ``call``/``apply`` member."""

    if node.type not in {"member_expression", "subscript_expression"}:
        return False
    owner = node.child_by_field_name("object")
    accessor = node.child_by_field_name("property") or node.child_by_field_name("index")
    if owner is None or accessor is None:
        return False
    method = _node_text(accessor, source).strip("'\"`")
    return method in {"call", "apply", "bind"} and _jsts_module_loader_reference(
        owner, source, loaders
    )


def _jsts_require_utility_member(node: Any, source: str, loaders: set[str]) -> bool:
    """Return whether *node* is a known non-loader CommonJS utility member."""

    if node.type not in {"member_expression", "subscript_expression"}:
        return False
    owner = node.child_by_field_name("object")
    accessor = node.child_by_field_name("property") or node.child_by_field_name("index")
    if owner is None or accessor is None:
        return False
    member = _node_text(accessor, source).strip("'\"`")
    return member in {"cache", "extensions", "main", "resolve"} and (
        _jsts_module_loader_reference(owner, source, loaders)
    )


def _jsts_dynamic_module_member(node: Any, source: str) -> bool:
    """Return whether *node* dynamically selects a property from ``module``."""

    if node.type != "subscript_expression":
        return False
    owner = node.child_by_field_name("object")
    index = node.child_by_field_name("index")
    if owner is None or index is None or _node_text(owner, source).strip() != "module":
        return False
    index_text = _node_text(index, source).strip()
    quoted_literal = re.fullmatch(r"(['\"])[^'\"]*\1", index_text)
    template_literal = re.fullmatch(r"`[^`$]*`", index_text)
    return quoted_literal is None and template_literal is None


def _jsts_value_stores_module_loader(node: Any, source: str, loaders: set[str]) -> bool:
    """Detect a loader retained or passed as a value rather than invoked."""

    if _jsts_dynamic_module_member(node, source):
        return True
    if _jsts_require_utility_member(node, source, loaders):
        return False
    if _jsts_module_loader_reference(node, source, loaders):
        return True
    if node.type == "call_expression":
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is not None and _jsts_module_loader_reference(
            function, source, loaders
        ):
            return arguments is not None and _jsts_value_stores_module_loader(
                arguments, source, loaders
            )
        return any(
            _jsts_value_stores_module_loader(child, source, loaders)
            for child in node.children
        )
    return any(
        _jsts_value_stores_module_loader(child, source, loaders)
        for child in node.children
    )


@dataclass(slots=True)
class _SymbolWalker:
    source: str
    symbols: list[dict[str, Any]]
    language: str
    truncated_flag: list[bool] | None
    python_dynamic_loaders: set[str] = field(init=False, repr=False)
    jsts_module_loaders: set[str] = field(init=False, repr=False)
    import_projection_complete: bool = field(init=False, repr=False, default=True)
    java_static_for_name: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        self.python_dynamic_loaders = set()
        self.jsts_module_loaders = {"require", "module.require", "import"}
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
                if name is not None and value is not None and name.type == "identifier":
                    candidates.append((_node_text(name, self.source), value))
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

    def _collect_node(self, node: Any, depth: int, enclosed: bool) -> None:
        self._mark_jsts_loader_binding(node)
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

    def _mark_jsts_loader_binding(self, node: Any) -> None:
        """Fail closed when a lexical binding can shadow require/module."""

        if self.language not in {"javascript", "typescript"}:
            return
        patterns: list[Any] = []
        if node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            if name is not None and value is not None and name.type == "identifier":
                name_text = _node_text(name, self.source)
                if _jsts_module_loader_reference(
                    value, self.source, self.jsts_module_loaders
                ):
                    file_scoped = _jsts_file_scoped_alias(node)
                    if not file_scoped:
                        self.import_projection_complete = False
                    else:
                        self.jsts_module_loaders.add(name_text)
                    if name_text in _JSTS_MODULE_LOADER_ROOTS or not file_scoped:
                        patterns.append(name)
                else:
                    patterns.append(name)
                if _jsts_value_stores_module_loader(
                    value, self.source, self.jsts_module_loaders
                ) and not _jsts_module_loader_reference(
                    value, self.source, self.jsts_module_loaders
                ):
                    self.import_projection_complete = False
            else:
                patterns.append(name)
        elif node.type == "formal_parameters":
            patterns.extend(node.children)
        elif node.type in {
            "arrow_function",
            "class_declaration",
            "function_declaration",
            "function_expression",
            "generator_function_declaration",
            "generator_function_expression",
        }:
            patterns.extend(
                node.child_by_field_name(field)
                for field in ("name", "parameter", "parameters")
            )
        elif node.type == "catch_clause":
            patterns.append(node.child_by_field_name("parameter"))
        elif node.type == "import_clause":
            patterns.append(node)
        elif node.type in {"assignment_expression", "augmented_assignment_expression"}:
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            patterns.append(left)
            if (
                left is not None
                and _jsts_module_loader_reference(
                    left, self.source, self.jsts_module_loaders
                )
            ) or (
                right is not None
                and _jsts_value_stores_module_loader(
                    right, self.source, self.jsts_module_loaders
                )
            ):
                self.import_projection_complete = False
        elif node.type == "for_in_statement":
            patterns.append(node.child_by_field_name("left"))
        elif node.type == "unary_expression" and re.match(
            r"^\s*delete\b", _node_text(node, self.source)
        ):
            operands = [
                child for child in node.children if getattr(child, "is_named", True)
            ]
            if any(
                _jsts_module_loader_reference(
                    operand, self.source, self.jsts_module_loaders
                )
                for operand in operands
            ):
                self.import_projection_complete = False
        self.import_projection_complete = self.import_projection_complete and not any(
            pattern is not None
            and _jsts_pattern_binds_module_loader(
                pattern, self.source, self.jsts_module_loaders
            )
            for pattern in patterns
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
        while function.type == "parenthesized_expression":
            named_children = [
                child for child in function.children if getattr(child, "is_named", True)
            ]
            if len(named_children) != 1:
                self.import_projection_complete = False
                return False
            function = named_children[0]
        if _jsts_indirect_module_loader_call(
            function, self.source, self.jsts_module_loaders
        ):
            self.import_projection_complete = False
            return False
        if _jsts_dynamic_module_member(function, self.source):
            self.import_projection_complete = False
            return False
        if not _jsts_module_loader_reference(
            function, self.source, self.jsts_module_loaders
        ):
            if _jsts_value_stores_module_loader(
                arguments, self.source, self.jsts_module_loaders
            ):
                self.import_projection_complete = False
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
