"""Completeness checks over a snapshot's recorded import projections.

Each ``*_projection_complete`` predicate answers whether the snapshot's
import facts for one language are complete and unambiguous enough to
certify causal (dependents / exercising-test) facts. They fail closed.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .safe_to_edit_import_parsing import (
    _import_module_name,
    _jsts_projected_alias_spec,
    _python_dynamic_loader_names_from_projection,
    _python_projected_call,
    _python_projected_call_has_simple_arguments,
    _python_static_import_specs,
)
from .safe_to_edit_inventory_resolver import (
    _quoted_include_matches,
    _resolve_import_spec_from_inventory,
)
from .safe_to_edit_paths import _target_language


def _snapshot_import_texts(
    conn: Any, inventory: frozenset[str]
) -> dict[str, list[str]] | None:
    """Read and validate every inventory-covered imports projection."""

    try:
        rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()
    except Exception:
        return None
    projected: dict[str, list[str]] = {}
    for row in rows:
        file_path, raw_imports = row[0], row[1]
        if not isinstance(file_path, str) or file_path not in inventory:
            continue
        texts = _lenient_import_texts(raw_imports)
        if texts is None:
            return None
        projected[file_path] = texts
    return projected


def _lenient_import_texts(raw_imports: Any) -> list[str] | None:
    """Decode one ``imports_json`` cell, returning None when malformed."""
    try:
        imports = json.loads(raw_imports)
    except (TypeError, ValueError):
        return None
    if not isinstance(imports, list):
        return None
    texts: list[str] = []
    for item in imports:
        text = item.get("text") if isinstance(item, dict) else item
        if not isinstance(text, str):
            return None
        texts.append(text)
    return texts


def _symbol_walk_projections_complete(
    conn: Any,
    inventory: frozenset[str],
    languages: set[str],
) -> bool:
    """Reject current projections whose bounded symbol walk was truncated."""

    from tree_sitter_analyzer.ast_cache import _AST_CACHE_EXTRACTOR_VERSION

    try:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(ast_index)")}
        if not {"extractor_version", "symbols_json"}.issubset(columns):
            return False
        rows = conn.execute(
            "SELECT file_path, symbols_json, extractor_version FROM ast_index"
        ).fetchall()
    except Exception:
        return False
    for row in rows:
        file_path, raw_symbols, extractor_version = row[0], row[1], row[2]
        if (
            not isinstance(file_path, str)
            or file_path not in inventory
            or _target_language(file_path) not in languages
        ):
            continue
        if (
            type(extractor_version) is not int
            or extractor_version != _AST_CACHE_EXTRACTOR_VERSION
        ):
            return False
        if not _symbol_payload_complete(raw_symbols):
            return False
    return True


def _symbol_payload_complete(raw_symbols: Any) -> bool:
    """Return whether one ``symbols_json`` cell records a complete walk."""
    try:
        payload = json.loads(raw_symbols)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    truncated = payload.get("truncated_depth")
    projection_complete = payload.get("import_projection_complete")
    syntax_error = payload.get("syntax_error")
    return (
        isinstance(truncated, bool)
        and not truncated
        and isinstance(projection_complete, bool)
        and projection_complete
        and isinstance(syntax_error, bool)
        and not syntax_error
    )


def _jsts_import_projection_complete(conn: Any, inventory: frozenset[str]) -> bool:
    """Reject certified JS/TS facts when a bare specifier may be an alias."""

    projected = _snapshot_import_texts(conn, inventory)
    if projected is None:
        return False
    folded_inventory = frozenset(path.casefold() for path in inventory)
    casefold_counts: dict[str, int] = {}
    for path in inventory:
        folded_path = path.casefold()
        casefold_counts[folded_path] = casefold_counts.get(folded_path, 0) + 1
    for file_path, import_texts in projected.items():
        if _target_language(file_path) not in {"javascript", "typescript"}:
            continue
        if not all(
            _jsts_import_text_certifiable(
                import_text, file_path, inventory, folded_inventory, casefold_counts
            )
            for import_text in import_texts
        ):
            return False
    return True


def _jsts_import_text_certifiable(
    import_text: str,
    file_path: str,
    inventory: frozenset[str],
    folded_inventory: frozenset[str],
    casefold_counts: dict[str, int],
) -> bool:
    """Return whether one JS/TS projected import resolves unambiguously."""
    alias_spec = _jsts_projected_alias_spec(import_text)
    spec = _import_module_name(import_text) or alias_spec
    normalized = re.split(r"[?#]", spec, maxsplit=1)[0] if spec else None
    if normalized is None or not normalized.startswith(("./", "../")):
        return False
    if "\\" in normalized:
        return False
    resolved = _resolve_import_spec_from_inventory(normalized, file_path, inventory)
    folded_resolved = _resolve_import_spec_from_inventory(
        normalized.casefold(), file_path.casefold(), folded_inventory
    )
    if (resolved is None and folded_resolved is not None) or (
        resolved is not None and casefold_counts.get(resolved.casefold(), 0) > 1
    ):
        return False
    commonjs_call = alias_spec is not None or re.search(
        r"(?:\brequire|module(?:\?\.)?\s*\[\s*['\"`]require['\"`]\s*\])"
        r"(?:\?\.)?\s*\(",
        import_text,
    )
    if not commonjs_call or Path(normalized).suffix:
        return True
    return resolved is not None and Path(resolved).parent.name != Path(normalized).name


def _python_inventory_matches(
    spec: str, importer: str, inventory: frozenset[str]
) -> set[str]:
    """Return all Python snapshot candidates at the resolver's chosen tier."""

    if spec in {"builtins", "__future__"}:
        return set()
    if spec.startswith("."):
        resolved = _resolve_import_spec_from_inventory(spec, importer, inventory)
        return {resolved} if resolved else set()
    module_path = spec.replace(".", "/")
    candidates = (f"{module_path}/__init__.py", f"{module_path}.py")
    matches_by_candidate = [
        (
            candidate,
            {
                indexed
                for indexed in inventory
                if indexed == candidate or indexed.endswith(f"/{candidate}")
            },
        )
        for candidate in candidates
    ]
    source_roots = {
        Path(indexed).parts[: -len(Path(candidate).parts)]
        for candidate, matches in matches_by_candidate
        for indexed in matches
    }
    if len(source_roots) > 1:
        return {
            indexed
            for _candidate, matches in matches_by_candidate
            for indexed in matches
        }
    for _candidate, matches in matches_by_candidate:
        if matches:
            return matches
    return set()


def _python_inventory_case_ambiguous(
    spec: str, importer: str, inventory: frozenset[str]
) -> bool:
    """Return whether only case-folded or colliding Python candidates resolve."""

    exact = _python_inventory_matches(spec, importer, inventory)
    folded_inventory = frozenset(path.casefold() for path in inventory)
    folded = _python_inventory_matches(
        spec.casefold(), importer.casefold(), folded_inventory
    )
    if {path.casefold() for path in exact} != folded:
        return bool(folded)
    counts: dict[str, int] = {}
    for path in inventory:
        folded_path = path.casefold()
        counts[folded_path] = counts.get(folded_path, 0) + 1
    return any(counts.get(path, 0) > 1 for path in folded)


def _python_relative_package_root_ambiguous(
    spec: str, importer: str, inventory: frozenset[str]
) -> bool:
    """Return whether a relative import has multiple initializer boundaries."""

    if not spec.startswith("."):
        return False
    parent = Path(importer).parent
    return any(
        ancestor != Path(".") and (ancestor / "__init__.py").as_posix() in inventory
        for ancestor in parent.parents
    )


def _python_absolute_inventory_match_is_rooted(spec: str, match: str) -> bool:
    """Return whether an absolute import match is rooted at the snapshot root."""

    module_path = spec.replace(".", "/")
    return match in {f"{module_path}/__init__.py", f"{module_path}.py"}


def _python_from_import_is_ambiguous(
    import_text: str, importer: str, inventory: frozenset[str]
) -> bool:
    """Detect package-attribute versus same-named-submodule ambiguity."""
    try:
        body = ast.parse(import_text).body
    except SyntaxError:
        return False
    if len(body) != 1 or not isinstance(body[0], ast.ImportFrom):
        return False
    statement = body[0]
    module = f"{'.' * statement.level}{statement.module or ''}"
    package_matches = _python_inventory_matches(module, importer, inventory)
    if not any(path.endswith("/__init__.py") for path in package_matches):
        return False
    separator = "" if module.endswith(".") else "."
    return any(
        alias.name != "*"
        and bool(
            _python_inventory_matches(
                f"{module}{separator}{alias.name}", importer, inventory
            )
        )
        for alias in statement.names
    )


def _python_import_projection_complete(conn: Any, inventory: frozenset[str]) -> bool:
    """Reject Python facts when a projected import is incomplete or ambiguous."""

    projected = _snapshot_import_texts(conn, inventory)
    if projected is None:
        return False
    for file_path, import_texts in projected.items():
        if _target_language(file_path) != "python":
            continue
        loaders = _python_dynamic_loader_names_from_projection(import_texts)
        if loaders is None:
            return False
        for import_text in import_texts:
            if not _python_static_import_certifiable(import_text, file_path, inventory):
                return False
            if not _python_dynamic_import_certifiable(
                import_text, file_path, inventory, loaders
            ):
                return False
    return True


def _python_static_import_certifiable(
    import_text: str, file_path: str, inventory: frozenset[str]
) -> bool:
    """Return whether one projected static import resolves unambiguously."""
    static_specs = _python_static_import_specs(import_text)
    if static_specs is None:
        return False
    if _python_from_import_is_ambiguous(import_text, file_path, inventory):
        return False
    for spec in static_specs:
        if _python_relative_package_root_ambiguous(spec, file_path, inventory):
            return False
        if _python_inventory_case_ambiguous(spec, file_path, inventory):
            return False
        matches = _python_inventory_matches(spec, file_path, inventory)
        if not spec.startswith(".") and any(
            not _python_absolute_inventory_match_is_rooted(spec, match)
            for match in matches
        ):
            return False
    return True


def _python_dynamic_import_certifiable(
    import_text: str,
    file_path: str,
    inventory: frozenset[str],
    loaders: frozenset[str],
) -> bool:
    """Return whether one projected loader call names a rooted literal module."""
    projected_call = _python_projected_call(import_text)
    if projected_call is None or projected_call[0] not in loaders:
        return True
    if not _python_projected_call_has_simple_arguments(import_text):
        return False
    dynamic_spec = projected_call[1]
    if dynamic_spec is None or dynamic_spec.startswith("."):
        return False
    if _python_inventory_case_ambiguous(dynamic_spec, file_path, inventory):
        return False
    dynamic_matches = _python_inventory_matches(dynamic_spec, file_path, inventory)
    return all(
        _python_absolute_inventory_match_is_rooted(dynamic_spec, match)
        for match in dynamic_matches
    )


def _java_inventory_matches(spec: str, inventory: frozenset[str]) -> set[str]:
    """Return Java source candidates for a binary or canonical class name."""

    owner = spec.split("$", 1)[0]
    candidate = f"{owner.replace('.', '/')}.java"
    if candidate in inventory:
        return {candidate}
    return {
        indexed
        for indexed in inventory
        if indexed == candidate or indexed.endswith(f"/{candidate}")
    }


def _java_reflection_projection_complete(conn: Any, inventory: frozenset[str]) -> bool:
    """Reject Java facts when a Class.forName target is dynamic or ambiguous."""

    projected = _snapshot_import_texts(conn, inventory)
    if projected is None:
        return False
    for file_path, import_texts in projected.items():
        if _target_language(file_path) != "java":
            continue
        static_for_name = any(
            re.fullmatch(
                r"\s*import\s+static\s+java\.lang\.Class\.forName\s*;\s*",
                text,
            )
            is not None
            for text in import_texts
        )
        if not all(
            _java_reflection_text_certifiable(import_text, inventory, static_for_name)
            for import_text in import_texts
        ):
            return False
    return True


def _java_reflection_text_certifiable(
    import_text: str, inventory: frozenset[str], static_for_name: bool
) -> bool:
    """Return whether one projected ``forName`` call names a unique class."""
    reflective_call = re.match(
        r"^\s*(?:(?:java\.lang\.)?Class\.)?forName\s*\(",
        import_text,
        re.S,
    )
    if reflective_call is None:
        return True
    if re.match(r"^\s*forName\s*\(", import_text) and not static_for_name:
        return False
    spec = _import_module_name(import_text)
    if spec is None:
        return False
    return len(_java_inventory_matches(spec, inventory)) <= 1


def _java_same_package_projection_complete(
    conn: Any,
    rel_path: str,
    inventory: frozenset[str],
) -> bool:
    """Fail closed until every Java type/member reference is projected."""

    del conn, rel_path
    java_files = {path for path in inventory if _target_language(path) == "java"}
    # One Java file cannot hide an incoming Java reference. With two or more,
    # fully-qualified cross-package references need no import and are absent
    # from the current projection, so completeness cannot yet be certified.
    return len(java_files) <= 1


def _quoted_include_projection_complete(
    conn: Any,
    rel_path: str,
    inventory: frozenset[str],
) -> bool:
    """Return whether ambiguous include-root matches cannot hide this target."""

    projected = _snapshot_import_texts(conn, inventory)
    if projected is None:
        return False
    source_files = {
        path for path in inventory if _target_language(path) in {"c", "cpp"}
    }
    if not source_files.issubset(projected):
        return False
    return all(
        _include_text_certifiable(text, importer, inventory)
        for importer in source_files
        for text in projected[importer]
    )


def _include_text_certifiable(
    text: str, importer: str, inventory: frozenset[str]
) -> bool:
    """Return whether one C/C++ include/import line resolves to one target."""
    if re.match(r"^\s*#\s*include_next\b", text):
        return False
    is_include = re.match(r"^\s*#\s*include\b", text) is not None
    cpp_import = (
        re.match(r"^\s*(?:export\s+)?import\s+(.+?)\s*;\s*$", text)
        if _target_language(importer) == "cpp"
        else None
    )
    if not is_include and cpp_import is None:
        return True
    match = re.match(
        r'^\s*(?:#\s*include|(?:export\s+)?import)\s*"([^"]+)"',
        text,
    )
    if match is None:
        return False
    return len(_quoted_include_matches(match.group(1), importer, inventory)) == 1
