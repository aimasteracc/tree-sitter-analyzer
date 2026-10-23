"""Pure parsers for projected import-statement text (no I/O, no inventory)."""

from __future__ import annotations

import ast
import re

_DEFAULT_PYTHON_LOADERS = frozenset(
    {"__import__", "builtins.__import__", "importlib.import_module"}
)


def _import_module_name(import_text: str) -> str | None:
    """Return the imported module path from one import statement text."""

    if re.match(r"^\s*from\s+__future__\s+import\b", import_text):
        return None
    import_text = re.sub(
        r"\bmodule(?:\?\.)?\s*\[\s*(['\"`])require\1\s*\]",
        "module.require",
        import_text,
    )
    static_java = re.match(
        r"^\s*import\s+static\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)\s*;?\s*$",
        import_text,
    )
    if static_java:
        owner, _, _member = static_java.group(1).rpartition(".")
        return owner or None
    return _static_module_name(import_text) or _dynamic_module_name(import_text)


def _static_module_name(import_text: str) -> str | None:
    """Return the module named by a static ``from``/``import`` statement."""
    m = re.match(r"^\s*from\s+([.\w]+)\s+import\b", import_text)
    if m:
        return m.group(1)
    m = re.search(r"(?:\bfrom\s*|^\s*import\s*)['\"]([^'\"]+)['\"]", import_text)
    if m:
        return m.group(1)
    m = re.match(r"^\s*import\s+([.\w]+)", import_text)
    if m:
        return m.group(1)
    return None


def _dynamic_module_name(import_text: str) -> str | None:
    """Return the module named by a loader call or reference directive.

    The probe order is part of the contract: the first match wins.
    """
    m = re.search(
        r"\b(?:require|import)(?:\?\.)?\s*\(\s*['\"]([^'\"]+)['\"]",
        import_text,
    )
    if m:
        return m.group(1)
    m = re.search(r"\b(?:require|import)\s*\(\s*`([^`]*)`", import_text)
    if m and "${" not in m.group(1):
        return m.group(1)
    m = re.search(
        r"\b(?:importlib\.import_module|builtins\.__import__|__import__)\s*"
        r"\(\s*['\"]([^'\"]+)['\"]",
        import_text,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"\b(?:(?:java\.lang\.)?Class\.)?forName\s*"
        r"\(\s*['\"]([^'\"]+)['\"]",
        import_text,
    )
    if m:
        return m.group(1).split("$", 1)[0]
    m = re.search(
        r"^\s*///\s*<reference\b[^>]*\bpath\s*=\s*(['\"])([^'\"]+)\1",
        import_text,
    )
    if m:
        return m.group(2)
    return None


def _jsts_projected_alias_spec(import_text: str) -> str | None:
    """Return the static specifier from one trusted projected loader-alias call."""

    quoted = re.match(
        r"^\s*([A-Za-z_$][\w$]*)\s*(?:\?\.)?\s*\(\s*(['\"])([^'\"]+)\2"
        r"\s*\)\s*;?\s*$",
        import_text,
        re.S,
    )
    if quoted is not None and quoted.group(1) not in {"import", "require"}:
        return quoted.group(3)
    template = re.match(
        r"^\s*([A-Za-z_$][\w$]*)\s*(?:\?\.)?\s*\(\s*`([^`]*)`"
        r"\s*\)\s*;?\s*$",
        import_text,
        re.S,
    )
    if (
        template is not None
        and template.group(1) not in {"import", "require"}
        and "${" not in template.group(2)
    ):
        return template.group(2)
    return None


def _python_single_call(import_text: str) -> ast.Call | None:
    """Return the call when *import_text* is exactly one call expression."""
    try:
        body = ast.parse(import_text).body
    except SyntaxError:
        return None
    if len(body) != 1 or not isinstance(body[0], ast.Expr):
        return None
    call = body[0].value
    return call if isinstance(call, ast.Call) else None


def _python_projected_call(import_text: str) -> tuple[str, str | None] | None:
    """Parse one projected Python call and its literal first argument."""

    call = _python_single_call(import_text)
    if call is None:
        return None
    name = _python_ast_name(call.func)
    if name is None:
        return None
    spec = (
        call.args[0].value
        if call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        else None
    )
    return name, spec


def _python_projected_call_has_simple_arguments(import_text: str) -> bool:
    """Return whether a projected loader call has only its module argument."""

    call = _python_single_call(import_text)
    return call is not None and len(call.args) == 1 and not call.keywords


def _python_dynamic_loader_names_from_projection(
    import_texts: list[str],
) -> frozenset[str] | None:
    """Derive dynamic-import aliases from one file's static projections."""

    names = set(_DEFAULT_PYTHON_LOADERS)
    statements: list[ast.stmt] = []
    for import_text in import_texts:
        try:
            body = ast.parse(import_text).body
        except SyntaxError:
            return None
        if len(body) != 1:
            return None
        statement = body[0]
        statements.append(statement)
        names.update(_loader_aliases_from_import(statement))
    _propagate_loader_assignments(statements, names)
    return frozenset(names)


def _loader_aliases_from_import(statement: ast.stmt) -> set[str]:
    """Return loader names bound by one ``import``/``from`` statement."""
    aliases: set[str] = set()
    if isinstance(statement, ast.Import):
        for alias in statement.names:
            if alias.name == "importlib":
                aliases.add(f"{alias.asname or alias.name}.import_module")
            elif alias.name == "builtins":
                aliases.add(f"{alias.asname or alias.name}.__import__")
    elif (
        isinstance(statement, ast.ImportFrom)
        and statement.level == 0
        and statement.module in {"builtins", "importlib"}
    ):
        for alias in statement.names:
            if (statement.module, alias.name) in {
                ("builtins", "__import__"),
                ("importlib", "import_module"),
            }:
                aliases.add(alias.asname or alias.name)
    return aliases


def _assignment_parts(
    statement: ast.stmt,
) -> tuple[list[ast.expr], ast.expr] | None:
    """Return ``(targets, value)`` for plain or annotated assignments."""
    if isinstance(statement, ast.Assign):
        return statement.targets, statement.value
    if isinstance(statement, ast.AnnAssign) and statement.value is not None:
        return [statement.target], statement.value
    return None


def _propagate_loader_assignments(statements: list[ast.stmt], names: set[str]) -> None:
    """Grow *names* with simple ``alias = loader`` rebinds until a fixed point."""
    changed = True
    while changed:
        changed = False
        for statement in statements:
            parts = _assignment_parts(statement)
            if parts is None:
                continue
            targets, value = parts
            if _python_ast_name(value) not in names:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True


def _python_ast_name(node: ast.expr) -> str | None:
    """Return one dotted Python name without evaluating the expression."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _python_ast_name(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _python_static_import_specs(import_text: str) -> tuple[str, ...] | None:
    """Return module candidates named by one projected Python import."""

    try:
        body = ast.parse(import_text).body
    except SyntaxError:
        return None
    if len(body) != 1:
        return None
    statement = body[0]
    if isinstance(statement, ast.Import):
        return tuple(alias.name for alias in statement.names)
    if not isinstance(statement, ast.ImportFrom):
        return ()
    if statement.level == 0 and statement.module == "__future__":
        return ()
    prefix = "." * statement.level
    module = f"{prefix}{statement.module or ''}"
    specs = [module] if module else []
    for alias in statement.names:
        if alias.name == "*":
            continue
        separator = "" if module.endswith(".") else "."
        specs.append(f"{module}{separator}{alias.name}")
    return tuple(specs)
