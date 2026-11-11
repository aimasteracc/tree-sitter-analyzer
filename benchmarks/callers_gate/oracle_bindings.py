"""What a name is bound to in one file, and which import specifiers are external.

Everything here answers "provably X" questions; any doubt (an unparsable
config, an unresolvable module, a second binding of the name) answers "no",
which keeps the hit residual.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

from .oracle_syntax import CLASS_TYPES, TS_EXTS, Repo, is_field, text, walk

#: Package manifests whose dependency tables name the external packages.
DEPENDENCY_TABLES = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_JS_REWRITES = {
    ".js": (".ts", ".tsx"),
    ".mjs": (".mts",),
    ".cjs": (".cts",),
    ".jsx": (".tsx",),
}
_RESOLVE_EXTS = (*TS_EXTS, ".d.ts")
MAX_REEXPORT_DEPTH = 8


def parse_jsonc(raw: str) -> Any:
    """JSON with ``//`` / ``/* */`` comments and trailing commas (tsconfig, deno.jsonc)."""
    out: list[str] = []
    i, n, in_string = 0, len(raw), False
    while i < n:
        ch = raw[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(raw[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif raw.startswith("//", i):
            end = raw.find("\n", i)
            i = n if end < 0 else end
            continue
        elif raw.startswith("/*", i):
            end = raw.find("*/", i + 2)
            if end < 0:
                raise ValueError("unterminated comment")
            i = end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


@dataclass
class JsConfig:
    package_names: set[str] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)
    path_patterns: list[str] = field(default_factory=list)
    base_urls: list[str] = field(default_factory=list)
    import_map_keys: list[str] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)


def _config_files(repo: Repo) -> list[str]:
    names = re.compile(
        r"(^|/)(package\.json|jsr\.json|deno\.jsonc?|import_map\.json|[tj]sconfig[^/]*\.json)$"
    )
    return sorted(f for f in repo.tracked() if names.search(f))


def js_config(repo: Repo) -> JsConfig:
    if "js_config" in repo.memo:
        cached: JsConfig = repo.memo["js_config"]
        return cached
    config = JsConfig()
    for rel in _config_files(repo):
        try:
            data = parse_jsonc((repo.root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config.broken.append(rel)
            continue
        if not isinstance(data, dict):
            config.broken.append(rel)
            continue
        _absorb(config, rel, data)
    repo.memo["js_config"] = config
    return config


def _absorb(config: JsConfig, rel: str, data: dict[str, Any]) -> None:
    base = posixpath.basename(rel)
    folder = posixpath.dirname(rel)
    if isinstance(data.get("name"), str):
        config.package_names.add(data["name"])
    for table in DEPENDENCY_TABLES:
        deps = data.get(table)
        if isinstance(deps, dict):
            config.dependencies.update(str(k) for k in deps)
    imports = data.get("imports")
    if isinstance(imports, dict):
        config.import_map_keys.extend(str(k) for k in imports)
    if base.startswith(("tsconfig", "jsconfig")):
        options = data.get("compilerOptions")
        if isinstance(options, dict):
            if isinstance(options.get("baseUrl"), str):
                config.base_urls.append(
                    posixpath.normpath(posixpath.join(folder, options["baseUrl"]))
                )
            paths = options.get("paths")
            if isinstance(paths, dict):
                config.path_patterns.extend(str(k) for k in paths)
                if "baseUrl" not in options:
                    config.base_urls.append(folder or ".")


def _matches_pattern(spec: str, pattern: str) -> bool:
    if "*" not in pattern:
        return spec == pattern
    prefix, _, suffix = pattern.partition("*")
    return spec.startswith(prefix) and spec.endswith(suffix)


def _under_base_url(repo: Repo, spec: str, base_urls: list[str]) -> bool:
    tracked = repo.tracked()
    for base in base_urls:
        candidate = posixpath.normpath(posixpath.join(base, spec))
        if candidate in tracked or any(
            candidate + ext in tracked for ext in _RESOLVE_EXTS
        ):
            return True
        prefix = candidate.rstrip("/") + "/"
        if any(f.startswith(prefix) for f in tracked):
            return True
    return False


def package_of(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def is_external_js(repo: Repo, spec: str) -> bool:
    """A module specifier that provably names code outside the project.

    External only when it is a ``node:`` builtin, or its package is a declared
    dependency (or installed under ``node_modules``) and not one of the
    project's own packages; and no tsconfig ``paths`` / ``baseUrl`` or import
    map could map it into the project. Relative-looking specifiers and any
    repo with an unreadable config are never external.
    """
    config = js_config(repo)
    if not spec or config.broken or spec.startswith((".", "/", "~", "#", "@/")):
        return False
    if any(
        _matches_pattern(spec, key) or (key.endswith("/") and spec.startswith(key))
        for key in config.import_map_keys
    ):
        return False
    bare = re.sub(r"^(npm|jsr):", "", spec)
    if any(_matches_pattern(bare, p) for p in config.path_patterns):
        return False
    if _under_base_url(repo, bare, config.base_urls):
        return False
    if spec.startswith("node:"):
        return True
    package = package_of(bare)
    if package in config.package_names:
        return False
    return (
        package in config.dependencies
        or (repo.root / "node_modules" / package).is_dir()
    )


def resolve_module(repo: Repo, from_rel: str, spec: str) -> str | None:
    """The tracked file a relative specifier names, or None (non-relative / not found)."""
    if not spec.startswith("."):
        return None
    tracked = repo.tracked()
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_rel), spec))
    stem, ext = posixpath.splitext(base)
    candidates = [base, *(stem + e for e in _JS_REWRITES.get(ext, ()))]
    candidates += [base + e for e in _RESOLVE_EXTS]
    candidates += [f"{base}/index{e}" for e in _RESOLVE_EXTS]
    return next((c for c in candidates if c in tracked), None)


def _source(statement: Any) -> str:
    return text(statement.child_by_field_name("source")).strip("'\"`")


def _statement(node: Any, kind: str) -> Any | None:
    current = node
    while current is not None and current.type != kind:
        current = current.parent
    return current


_TS_VALUE_BINDERS = {
    ("variable_declarator", "name"),
    ("required_parameter", "pattern"),
    ("optional_parameter", "pattern"),
    ("arrow_function", "parameter"),
    ("catch_clause", "parameter"),
    ("for_in_statement", "left"),
    ("assignment_pattern", "left"),
    ("pair_pattern", "value"),
    ("function_declaration", "name"),
    ("generator_function_declaration", "name"),
    ("function_expression", "name"),
    ("enum_declaration", "name"),
    ("internal_module", "name"),
    ("type_alias_declaration", "name"),
    ("import_require_clause", None),
    ("formal_parameter", "name"),
    ("catch_formal_parameter", "name"),
    ("enhanced_for_statement", "name"),
    ("resource", "name"),
    ("inferred_parameters", None),
    ("lambda_expression", "parameters"),
}
_PATTERN_PARENTS = {"array_pattern", "rest_pattern", "object_pattern"}


def file_bindings(repo: Repo, rel: str) -> dict[str, list[tuple[str, Any]]]:
    """Every name file ``rel`` binds -> [(kind, identifier node)] (one walk, memoized).

    Kinds: ``class`` (class / interface name), ``import`` (un-aliased named
    import), ``other`` (anything else: variables, parameters, functions,
    aliased / default / namespace imports, enums, ...).
    """
    key = f"bindings:{rel}"
    if key in repo.memo:
        cached: dict[str, list[tuple[str, Any]]] = repo.memo[key]
        return cached
    out: dict[str, list[tuple[str, Any]]] = {}
    parsed = repo.tree(rel)
    for node in walk(parsed[0].root_node) if parsed is not None else ():
        if node.type == "shorthand_property_identifier_pattern":
            out.setdefault(text(node), []).append(("other", node))
            continue
        if node.type not in ("identifier", "type_identifier") or node.parent is None:
            continue
        kind = _binding_kind(node, node.parent)
        if kind is not None:
            out.setdefault(text(node), []).append((kind, node))
    repo.memo[key] = out
    return out


def bindings_of(repo: Repo, rel: str, name: str) -> list[tuple[str, Any]]:
    return file_bindings(repo, rel).get(name, [])


def _binding_kind(node: Any, parent: Any) -> str | None:
    if parent.type in CLASS_TYPES and is_field(node, parent, "name"):
        return "class"
    if parent.type == "import_specifier":
        alias = parent.child_by_field_name("alias")
        if alias is None:
            return "import"
        return "other" if alias.id == node.id else None
    if parent.type in ("import_clause", "namespace_import"):
        return "other"
    if parent.type in _PATTERN_PARENTS:
        return "other"
    for kind, fname in _TS_VALUE_BINDERS:
        if parent.type == kind and (fname is None or is_field(node, parent, fname)):
            return "other"
    return None


def module_provides_class(repo: Repo, rel: str, name: str, depth: int = 0) -> bool:
    """Module ``rel`` exports a class / interface declared under exactly ``name``."""
    if depth > MAX_REEXPORT_DEPTH:
        return False
    parsed = repo.tree(rel)
    if parsed is None:
        return False
    return any(
        _exports_class(repo, rel, statement, name, depth)
        for statement in parsed[0].root_node.children
        if statement.type == "export_statement"
    )


def _exports_class(repo: Repo, rel: str, statement: Any, name: str, depth: int) -> bool:
    declaration = statement.child_by_field_name("declaration")
    if declaration is not None:
        ident = declaration.child_by_field_name("name")
        return (
            declaration.type in CLASS_TYPES
            and ident is not None
            and text(ident) == name
            and not any(c.type == "default" for c in statement.children)
        )
    source = statement.child_by_field_name("source")
    clause = next((c for c in statement.children if c.type == "export_clause"), None)
    if clause is None:
        if source is None or not any(c.type == "*" for c in statement.children):
            return False
        target = resolve_module(repo, rel, _source(statement))
        return target is not None and module_provides_class(
            repo, target, name, depth + 1
        )
    for spec in (c for c in clause.children if c.type == "export_specifier"):
        local, alias = (
            spec.child_by_field_name("name"),
            spec.child_by_field_name("alias"),
        )
        exported = text(alias) if alias is not None else text(local)
        if exported != name:
            continue
        if text(local) != name:
            return False  # `export { A as name }`: another class under this name
        if source is not None:
            target = resolve_module(repo, rel, _source(statement))
            return target is not None and module_provides_class(
                repo, target, name, depth + 1
            )
        return name_binds_class_ts(repo, rel, name, depth + 1)
    return False


def name_binds_class_ts(repo: Repo, rel: str, name: str, depth: int = 0) -> bool:
    """In TS/JS file ``rel``, every binding of ``name`` is the project class ``name``.

    Accepted: a class / interface declaration of ``name`` in the file, or an
    un-aliased named import of ``name`` from a relative module that exports a
    class declared under exactly that name (re-export chains followed while
    every link keeps the name). Anything else -- an aliased, default or
    namespace import, a variable or parameter of that name, an import from a
    module the oracle cannot resolve -- is not provable.
    """
    if depth > MAX_REEXPORT_DEPTH:
        return False
    if repo.tree(rel) is None:
        return False
    found = bindings_of(repo, rel, name)
    if not found:
        return False
    for kind, node in found:
        if kind == "class":
            continue
        if kind != "import":
            return False
        statement = _statement(node, "import_statement")
        target = resolve_module(repo, rel, _source(statement)) if statement else None
        if target is None or not module_provides_class(repo, target, name, depth + 1):
            return False
    return True


def name_binds_class_java(repo: Repo, rel: str, name: str) -> bool:
    """In Java file ``rel``, ``name`` is a class declared there or imported by its exact name.

    A same-package class used without an import is not accepted (the file
    alone cannot prove it is not shadowed by a nested or imported type), nor
    is a name that a variable, field or parameter of the file also binds.
    """
    parsed = repo.tree(rel)
    if parsed is None:
        return False
    root = parsed[0].root_node
    found = bindings_of(repo, rel, name)
    if any(kind != "class" for kind, _n in found):
        return False
    if found:
        return True
    for node in walk(root):
        if node.type != "import_declaration":
            continue
        words = text(node).split()
        if "static" in words or text(node).rstrip(";").strip().endswith("*"):
            continue
        m = re.search(r"import\s+([A-Za-z0-9_.]+)\s*;", text(node))
        if m and m.group(1).rsplit(".", 1)[-1] == name:
            return True
    return False


def bound_only_by_external_imports(repo: Repo, rel: str, name: str) -> bool:
    """TS/JS: the file binds ``name``, and only through imports of external modules."""
    found = bindings_of(repo, rel, name)
    if not found:
        return False
    for _kind, node in found:
        statement = _statement(node, "import_statement")
        if statement is None or not is_external_js(repo, _source(statement)):
            return False
    return True
