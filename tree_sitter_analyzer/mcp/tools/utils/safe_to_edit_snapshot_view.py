"""Snapshot-bound (certified) dependency view and stale-edge labels."""

from __future__ import annotations

import contextlib
import json
import posixpath
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .safe_to_edit_import_parsing import _python_dynamic_loader_names_from_projection
from .safe_to_edit_inventory_resolver import (
    _import_targets_from_text,
    _resolve_import_spec_from_inventory,
)
from .safe_to_edit_live_deps import _import_needles_for_target
from .safe_to_edit_paths import (
    FileDependencyView,
    _module_path_without_suffix,
    _target_language,
    _typescript_emitted_import_paths,
)


def snapshot_inventory(conn: Any) -> frozenset[str]:
    """Return the snapshot's ``ast_index`` relative file set.

    Codex P1 (#1299 round-3): certified reads must derive facts only from
    inventory-covered paths (the source oracle prunes e.g. ``tests/vendor``
    from the generation). A missing legacy table degrades to the empty set;
    malformed rows in a present inventory fail closed as ``CORRUPT_INDEX``.
    """

    try:
        rows = conn.execute("SELECT file_path FROM ast_index").fetchall()
    except Exception:  # nosec B110 — legacy/partial schema
        return frozenset()
    inventory: set[str] = set()
    for row in rows:
        file_path = row["file_path"]
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("CORRUPT_INDEX")
        inventory.add(file_path)
    return frozenset(inventory)


def _require_edges_callee_name(conn: Any) -> None:
    """Raise ``CORRUPT_INDEX`` when ``edges`` exists but lacks ``callee_name``.

    The snapshot reader's pass 1 selects ``edges.callee_name``; a partially
    migrated or damaged index would otherwise make that query fail inside the
    broad degrade handler, returning an empty dependency view and
    undercounting risk instead of classifying the snapshot as incompatible.
    """

    try:
        table_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='edges' LIMIT 1"
        ).fetchone()
        if table_row is None:
            return  # legacy schema without the table: degrade to empty
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(edges)").fetchall()
        }
    except Exception:  # nosec B110 — unreadable conn degrades to legacy
        return
    if "callee_name" not in columns:
        raise ValueError("CORRUPT_INDEX")


def _strict_import_texts(raw_imports: Any) -> list[str]:
    """Decode one ``imports_json`` cell, failing closed as ``CORRUPT_INDEX``."""
    try:
        imports = json.loads(raw_imports)
    except (TypeError, ValueError) as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if not isinstance(imports, list):
        raise ValueError("CORRUPT_INDEX")
    import_texts: list[str] = []
    for item in imports:
        text = item.get("text") if isinstance(item, dict) else item
        if not isinstance(text, str):
            raise ValueError("CORRUPT_INDEX")
        import_texts.append(text)
    return import_texts


def _python_loaders_for(
    file_path: str, import_texts: list[str]
) -> frozenset[str] | None:
    """Return the dynamic-loader names in scope for one importer's texts.

    Non-Python importers get ``None``; a Python importer whose projection
    cannot be parsed gets the empty set (no loader call is trusted).
    """
    if _target_language(file_path) != "python":
        return None
    loaders = _python_dynamic_loader_names_from_projection(import_texts)
    return frozenset() if loaders is None else loaders


def _common_prefix_len(left: Sequence[str], right: Sequence[str]) -> int:
    common = 0
    for left_part, right_part in zip(left, right, strict=False):
        if left_part != right_part:
            break
        common += 1
    return common


def _relative_module_name(
    importer_parts: tuple[str, ...], target_parts: tuple[str, ...]
) -> str:
    """Spell *target_parts* as a Python relative import from *importer_parts*."""
    common = _common_prefix_len(importer_parts, target_parts)
    dots = "." * (len(importer_parts) - common + 1)
    return f"{dots}{'.'.join(target_parts[common:])}"


def _edge_import_names_for_target(
    rel_path: str,
    inventory: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Return bounded unresolved-edge names that could identify *rel_path*."""

    path = Path(rel_path)
    module_path = _module_path_without_suffix(path)
    specifier_paths = (path, *_typescript_emitted_import_paths(path))
    target_module_parts = (
        path.parent.parts if path.name == "__init__.py" else module_path.parts
    )
    target_parent_parts = target_module_parts[:-1]
    names = _absolute_edge_names(path, module_path, specifier_paths)
    for offset in range(len(target_module_parts)):
        names.add(".".join(target_module_parts[offset:]))
    if path.suffix == ".java":
        for offset in range(len(target_parent_parts)):
            names.add(".".join(target_parent_parts[offset:]))
    for importer in inventory:
        for specifier_path in specifier_paths:
            relative_file = posixpath.relpath(
                specifier_path.as_posix(), Path(importer).parent.as_posix()
            )
            names.add(
                relative_file
                if relative_file.startswith("../")
                else f"./{relative_file}"
            )
        importer_parts = tuple(
            part for part in Path(importer).parent.parts if part != "."
        )
        names.add(_relative_module_name(importer_parts, target_module_parts))
        names.add(_relative_module_name(importer_parts, target_parent_parts))
    if path.name == "__init__.py":
        names.discard("__init__")
    return tuple(sorted(name for name in names if name and name != ".")) + (".",)


def _absolute_edge_names(
    path: Path, module_path: Path, specifier_paths: tuple[Path, ...]
) -> set[str]:
    """Importer-independent spellings of one target file."""
    without_suffix = module_path.as_posix()
    names = {
        path.as_posix(),
        path.name,
        without_suffix,
        without_suffix.replace("/", "."),
        module_path.name,
        path.parent.as_posix().replace("/", "."),
        ".",
        f".{module_path.name}",
        f"./{module_path.name}",
        f"./{path.name}",
    }
    for specifier_path in specifier_paths:
        names.update(
            {
                specifier_path.as_posix(),
                specifier_path.name,
                f"./{specifier_path.name}",
            }
        )
    if path.parent.name:
        names.add(f".{path.parent.name}")
    return names


def _projection_search_tokens(rel_path: str) -> tuple[str, ...]:
    """Return coarse SQL tokens; exact import parsing is the trust boundary."""

    path = Path(rel_path)
    module_path = _module_path_without_suffix(path)
    tokens = _import_needles_for_target(rel_path)
    module_parts = (
        path.parent.parts if path.name == "__init__.py" else module_path.parts
    )
    for offset in range(len(module_parts)):
        tokens.add(".".join(module_parts[offset:]))
    if module_path.name and module_path.name != "__init__":
        tokens.add(f"./{module_path.name}")
    if module_path.name == "index":
        if path.parent.name:
            tokens.add(path.parent.as_posix())
            tokens.add(path.parent.name)
            tokens.add(f"./{path.parent.name}")
        else:
            tokens.add("./")
    if path.suffix == ".java":
        for offset in range(max(len(module_parts) - 1, 0)):
            tokens.add(f"{'.'.join(module_parts[offset:-1])}.*")
    return tuple(sorted(tokens))


def _escape_sql_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_snapshot_file_dependency_view(
    conn: Any,
    rel_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> FileDependencyView:
    """Build the one-file import view from the snapshot connection.

    RFC-0022 P0.4 read_existing: the live ``build_file_dependency_view``
    re-parses the filesystem; this variant reads only the immutable snapshot
    connection. Two passes mirror the legacy axis:

    1. ``edges`` IMPORTS rows: exact module-path resolution (``callee_name``
       resolved against the indexed files).
    2. ``ast_index.imports_json`` needle pass: ``from pkg import app`` and
       ``from . import app`` store the module path (``pkg`` / ``.``), which
       exact resolution cannot map to the member file ``pkg/app.py``; the
       legacy axis scans source text for import needles, so the snapshot
       variant matches the same needles against each importer's recorded
       import-statement text instead (no live bytes are consulted).

    A missing/legacy schema degrades to an empty view so the route can still
    classify honestly. A current-version but damaged ``edges`` table (present
    yet missing the ``callee_name`` column this reader requires) raises
    ``CORRUPT_INDEX`` instead of degrading silently — an empty view would
    undercount risk (Codex P2 #1299).

    Each pass accumulates into the shared sets, so facts gathered before a
    degrading schema error in a later step of the same pass are kept.
    """
    _require_edges_callee_name(conn)
    if inventory is None:
        inventory = snapshot_inventory(conn)
    dependencies: set[str] = set()
    dependents: set[str] = set()
    try:
        _collect_resolved_edges(conn, rel_path, inventory, dependencies, dependents)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy schema degrades to import facts
        pass
    # Snapshot schema drift degrades to the facts gathered so far.
    with contextlib.suppress(Exception):
        _collect_import_edges(conn, rel_path, inventory, dependencies, dependents)
    try:
        _collect_projection_edges(conn, rel_path, inventory, dependencies, dependents)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy snapshot schema degrades to empty
        pass
    return FileDependencyView(
        rel_path=rel_path,
        dependencies=dependencies,
        dependents=dependents,
    )


def _collect_resolved_edges(
    conn: Any,
    rel_path: str,
    inventory: frozenset[str],
    dependencies: set[str],
    dependents: set[str],
) -> None:
    """P1 causal envelope: include resolved CALLS/IMPLEMENTS/etc. edges.

    ``file_path`` is the caller and ``callee_resolved_file`` is the
    definition file for every resolved cross-file edge.
    """
    resolved_rows = conn.execute(
        "SELECT file_path, callee_resolved_file FROM edges "
        "WHERE callee_resolved_file != '' "
        "AND (file_path = ? OR callee_resolved_file = ?)",
        (rel_path, rel_path),
    ).fetchall()
    for caller_file, callee_file in resolved_rows:
        if not isinstance(caller_file, str) or not isinstance(callee_file, str):
            raise ValueError("CORRUPT_INDEX")
        if caller_file not in inventory or callee_file not in inventory:
            continue
        if caller_file == rel_path and callee_file != rel_path:
            dependencies.add(callee_file)
        elif callee_file == rel_path and caller_file != rel_path:
            dependents.add(caller_file)


def _collect_import_edges(
    conn: Any,
    rel_path: str,
    inventory: frozenset[str],
    dependencies: set[str],
    dependents: set[str],
) -> None:
    """Resolve IMPORTS edge rows in both directions against the inventory."""
    import_rows = conn.execute(
        "SELECT callee_name FROM edges WHERE kind = 'imports' AND file_path = ?",
        (rel_path,),
    ).fetchall()
    for (module,) in import_rows:
        if not isinstance(module, str):
            # Codex P2 (#1299 round-10, C44): a BLOB callee_name would
            # raise TypeError at startswith and abandon the whole pass.
            continue
        resolved = _resolve_import_spec_from_inventory(module, rel_path, inventory)
        if resolved:
            dependencies.add(resolved)
    candidate_names = _edge_import_names_for_target(rel_path, inventory)
    placeholders = ", ".join("?" for _ in candidate_names)
    all_rows = conn.execute(
        "SELECT file_path, callee_name FROM edges WHERE kind = 'imports' "
        f"AND callee_name IN ({placeholders})",
        candidate_names,
    ).fetchall()
    for file_path, module in all_rows:
        if (
            not isinstance(file_path, str)
            or not file_path
            or file_path == rel_path
            or file_path not in inventory
        ):
            continue
        resolved = _resolve_import_spec_from_inventory(module, file_path, inventory)
        if resolved == rel_path:
            dependents.add(file_path)


def _collect_projection_edges(
    conn: Any,
    rel_path: str,
    inventory: frozenset[str],
    dependencies: set[str],
    dependents: set[str],
) -> None:
    """Match recorded import texts of the target and its candidate importers.

    Fetch the target's own projection for outgoing dependencies and only
    coarse candidate importers for the incoming direction.  Exact parsing
    below remains the trust boundary; LIKE is only a bounded SQL prefilter.
    """
    tokens = _projection_search_tokens(rel_path)
    like_terms = " OR ".join("imports_json LIKE ? ESCAPE '\\'" for _ in tokens)
    rows = conn.execute(
        "SELECT file_path, imports_json FROM ast_index WHERE file_path = ? "
        f"OR (file_path != ? AND ({like_terms}))",
        (
            rel_path,
            rel_path,
            *(f"%{_escape_sql_like(token)}%" for token in tokens),
        ),
    ).fetchall()
    for row in rows:
        file_path = row["file_path"]
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("CORRUPT_INDEX")
        import_texts = _strict_import_texts(row["imports_json"])
        dynamic_loaders = _python_loaders_for(file_path, import_texts)
        for imp_text in import_texts:
            targets = _import_targets_from_text(
                imp_text,
                file_path,
                inventory,
                python_dynamic_loaders=dynamic_loaders,
            )
            if file_path == rel_path:
                dependencies.update(target for target in targets if target != rel_path)
            elif rel_path in targets:
                dependents.add(file_path)


def snapshot_stale_edges(
    conn: Any,
    rel_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> list[str]:
    """Return snapshot-bound labels for edge rows an edit may invalidate.

    An edit always invalidates its outgoing rows; it may also invalidate
    incoming rows when definitions move, disappear, or change signature.  P1
    therefore reports both directions conservatively.  A missing edge schema
    fails closed instead of reporting a misleading empty set.
    """

    if inventory is None:
        inventory = snapshot_inventory(conn)
    rows = _stale_edge_candidate_rows(conn, rel_path, inventory)
    unresolved_callers = {
        caller_file
        for _, kind, caller_file, _, resolved_file in rows
        if kind == "imports"
        and resolved_file == ""
        and isinstance(caller_file, str)
        and caller_file in inventory
    }
    needle_importers = _snapshot_needle_importers(
        conn, rel_path, unresolved_callers, inventory=inventory
    )
    labels: list[str] = []
    for row in rows:
        edge_id, kind, caller_file, callee_name, resolved_file = _validated_edge_row(
            row
        )
        target_file = resolved_file
        if not target_file and kind == "imports":
            target_file = (
                _resolve_import_spec_from_inventory(callee_name, caller_file, inventory)
                or ""
            )
            # Member imports such as ``from . import app`` resolve the module
            # edge to ``pkg/__init__.py``.  The immutable imports projection
            # is the only snapshot-bound evidence that the row also touches
            # ``pkg/app.py``; mark it conservatively instead of dropping it.
            if caller_file in needle_importers:
                target_file = rel_path
        if caller_file != rel_path and target_file != rel_path:
            continue
        target = target_file or callee_name
        labels.append(f"{kind}:{caller_file}->{target}#{edge_id}")
    return labels


def _stale_edge_candidate_rows(
    conn: Any, rel_path: str, inventory: frozenset[str]
) -> list[Any]:
    """Fetch every edge row touching *rel_path*, plus unresolved import rows."""
    candidate_names = _edge_import_names_for_target(rel_path, inventory)
    placeholders = ", ".join("?" for _ in candidate_names)
    package_prefixes: tuple[str, ...] = ()
    if _target_language(rel_path) == "python" and Path(rel_path).name == "__init__.py":
        module_parts = Path(rel_path).parent.parts
        package_prefixes = tuple(
            ".".join(module_parts[offset:]) for offset in range(len(module_parts))
        )
    prefix_terms = " OR ".join(
        "callee_name LIKE ? ESCAPE '\\'" for _ in package_prefixes
    )
    unresolved_match = f"callee_name IN ({placeholders})"
    if prefix_terms:
        unresolved_match = f"({unresolved_match} OR {prefix_terms})"
    try:
        rows: list[Any] = conn.execute(
            "SELECT id, kind, file_path, callee_name, callee_resolved_file "
            "FROM edges WHERE file_path = ? OR callee_resolved_file = ? "
            "OR (kind = 'imports' AND callee_resolved_file = '' "
            f"AND {unresolved_match}) ORDER BY id",
            (
                rel_path,
                rel_path,
                *candidate_names,
                *(f"{_escape_sql_like(prefix)}.%" for prefix in package_prefixes),
            ),
        ).fetchall()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    return rows


def _validated_edge_row(row: Any) -> tuple[int, str, str, str, str]:
    """Unpack one edge row, failing closed on any malformed column."""
    edge_id, kind, caller_file, callee_name, resolved_file = row
    if (
        not isinstance(edge_id, int)
        or isinstance(edge_id, bool)
        or not isinstance(kind, str)
        or not kind
        or not isinstance(caller_file, str)
        or not caller_file
        or not isinstance(callee_name, str)
        or not isinstance(resolved_file, str)
    ):
        raise ValueError("CORRUPT_INDEX")
    return edge_id, kind, caller_file, callee_name, resolved_file


def _snapshot_needle_importers(
    conn: Any,
    rel_path: str,
    candidate_files: set[str] | set[bytes],
    *,
    inventory: frozenset[str] | None = None,
) -> set[str]:
    """Return unresolved importers whose recorded text names ``rel_path``."""
    if not candidate_files:
        return set()

    placeholders = ", ".join("?" for _ in candidate_files)
    try:
        rows = conn.execute(
            "SELECT file_path, imports_json FROM ast_index "
            f"WHERE file_path IN ({placeholders})",
            tuple(candidate_files),
        ).fetchall()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc

    if inventory is None:
        inventory = snapshot_inventory(conn)

    matched: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        file_path = row["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("CORRUPT_INDEX")
        seen.add(file_path)
        import_texts = _strict_import_texts(row["imports_json"])
        dynamic_loaders = _python_loaders_for(file_path, import_texts)
        if any(
            rel_path
            in _import_targets_from_text(
                text,
                file_path,
                inventory,
                python_dynamic_loaders=dynamic_loaders,
            )
            for text in import_texts
        ):
            matched.add(file_path)
    if seen != candidate_files:
        raise ValueError("CORRUPT_INDEX")
    return matched
