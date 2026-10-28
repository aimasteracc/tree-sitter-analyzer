"""Certified (snapshot-owned) exercising-test discovery for safe-to-edit."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .safe_to_edit_import_parsing import _import_module_name
from .safe_to_edit_inventory_resolver import (
    _import_targets_from_text,
    _resolve_import_spec_from_inventory,
)
from .safe_to_edit_paths import _CERTIFIED_IMPORT_LANGUAGES, _target_language
from .safe_to_edit_projection import _snapshot_import_texts
from .safe_to_edit_snapshot_view import (
    _python_loaders_for,
    _require_edges_callee_name,
    _strict_import_texts,
    snapshot_inventory,
)

#: File-name suffixes that mark a test per language (any one suffices).
_TEST_NAME_SUFFIXES: dict[str, tuple[str, ...]] = {
    "python": ("_test.py", "_tests.py"),
    "go": ("_test.go",),
    "rust": ("_test.rs", "_tests.rs"),
    "java": ("Test.java", "Tests.java"),
    "javascript": (
        ".test.js",
        ".spec.js",
        ".test.jsx",
        ".spec.jsx",
        ".test.mjs",
        ".spec.mjs",
        ".test.cjs",
        ".spec.cjs",
    ),
    "typescript": (
        ".test.ts",
        ".spec.ts",
        ".test.tsx",
        ".spec.tsx",
        ".test.mts",
        ".spec.mts",
        ".test.cts",
        ".spec.cts",
    ),
    "csharp": ("Test.cs", "Tests.cs"),
    "kotlin": ("Test.kt", "Tests.kt"),
    "ruby": ("_test.rb", "_spec.rb"),
    "php": ("Test.php", "test.php"),
}
#: Languages whose tests are ``test_*`` files with one of these extensions.
_PREFIXED_TEST_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp"),
}
_TEST_DIR_NAMES = frozenset({"tests", "test", "spec", "__tests__"})
#: Importer languages whose snapshot projections have resolver-backed
#: ownership semantics, so a symbol-text match may count as a reference.
_SYMBOL_FALLBACK_LANGUAGES = frozenset({"python", "javascript", "typescript", "java"})
_JSTS_LANGUAGES = frozenset({"javascript", "typescript"})


def _looks_like_test_name(name: str, language: str) -> bool:
    """Mirror is_existing_test_file's NAME conventions over certified inputs.

    The certified route has no filesystem to probe (and oracle-excluded
    paths must not influence facts), so only the file-name conventions of
    :func:`test_discovery_predicates.is_existing_test_file` are applied.
    Unknown languages (never produced by the current extension map, but
    possible after a future plugin addition) return False — the honest
    "not recognized as a test" answer.
    """

    prefixed_extensions = _PREFIXED_TEST_EXTENSIONS.get(language)
    if prefixed_extensions is not None:
        return name.startswith("test_") and name.endswith(prefixed_extensions)
    suffixes = _TEST_NAME_SUFFIXES.get(language)
    if suffixes is None:
        return False
    if name.endswith(suffixes):
        return True
    if language in {"python", "ruby"}:
        return name.startswith("test_")
    if language == "java":
        return name.startswith("Test") and name.endswith(".java")
    return False


def _looks_like_test_path(rel_path: str, language: str) -> bool:
    """Mirror the live runnable-test predicate over one snapshot path."""

    path = Path(rel_path)
    name = path.name
    if name in {"conftest.py", "__init__.py"}:
        return False
    in_test_dir = any(part in _TEST_DIR_NAMES for part in path.parts[:-1])
    if language == "python":
        return name.endswith(("_test.py", "_tests.py")) or (
            (in_test_dir or len(path.parts) == 1)
            and name.startswith("test_")
            and name.endswith(".py")
        )
    if language == "java":
        return in_test_dir and _looks_like_test_name(name, language)
    if language in {"c", "cpp"}:
        return in_test_dir and name.startswith("test_")
    if language == "ruby":
        return name.endswith(("_test.rb", "_spec.rb")) or (
            in_test_dir and name.startswith("test_")
        )
    return _looks_like_test_name(name, language)


def _indexed_symbol_entries(conn: Any, file_path: str) -> list[dict[str, Any]]:
    """Return one file's validated ``symbols_json`` entries (fail closed)."""
    try:
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if row is None:
        raise ValueError("CORRUPT_INDEX")
    try:
        payload = json.loads(str(row["symbols_json"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if not isinstance(payload, dict):
        raise ValueError("CORRUPT_INDEX")
    entries = payload.get("symbols", [])
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) for entry in entries
    ):
        raise ValueError("CORRUPT_INDEX")
    return entries


def _file_defines_any(conn: Any, file_path: str, symbols: list[str]) -> bool:
    """Return whether one indexed file defines ANY of the given symbols."""

    entries = _indexed_symbol_entries(conn, file_path)
    defined = {
        entry.get("name") for entry in entries if isinstance(entry.get("name"), str)
    }
    return bool(defined.intersection(symbols))


def _python_package_symbol_providers(
    conn: Any,
    package_file: str,
    symbols: list[str],
    inventory: frozenset[str],
) -> dict[str, set[str]]:
    """Bind package-level names to snapshot-proven defining modules.

    A test importing ``from pkg import run`` resolves first to
    ``pkg/__init__.py``.  When the initializer re-exports ``run``, its
    recorded import projection is the only certified evidence that can bind
    the name to ``pkg/a.py`` rather than another sibling defining the same
    public symbol.  Multiple possible providers stay ambiguous and therefore
    cannot certify a match.
    """

    projections = _snapshot_import_texts(conn, inventory) or {}

    def provider_files(
        module_file: str, exported_symbol: str, stack: frozenset[tuple[str, str]]
    ) -> set[str]:
        key = (module_file, exported_symbol)
        if key in stack:
            return set()
        next_stack = stack | {key}
        providers = (
            {module_file}
            if _file_defines_any(conn, module_file, [exported_symbol])
            else set()
        )
        for import_text in projections.get(module_file, []):
            for source, source_symbol in _reexport_sources(
                import_text, module_file, exported_symbol, inventory
            ):
                providers.update(provider_files(source, source_symbol, next_stack))
        return providers

    return {
        symbol: provider_files(package_file, symbol, frozenset()) for symbol in symbols
    }


def _reexport_sources(
    import_text: str,
    module_file: str,
    exported_symbol: str,
    inventory: frozenset[str],
) -> list[tuple[str, str]]:
    """Return ``(source_file, source_symbol)`` pairs re-exporting one name."""
    sources: list[tuple[str, str]] = []
    for statement in ast.parse(import_text).body:
        if not isinstance(statement, ast.ImportFrom):
            continue
        spec = "." * statement.level + (statement.module or "")
        source = _resolve_import_spec_from_inventory(spec, module_file, inventory)
        if source is None:
            continue
        for alias in statement.names:
            exposed = alias.asname or alias.name
            if alias.name != "*" and exposed != exported_symbol:
                continue
            source_symbol = exported_symbol if alias.name == "*" else alias.name
            sources.append((source, source_symbol))
    return sources


@dataclass(frozen=True)
class _SymbolReferenceScope:
    """One (target, candidate test importer) pair under symbol-reference scan."""

    conn: Any
    inventory: frozenset[str]
    rel_path: str
    language: str
    importer: str
    importer_language: str
    symbols: frozenset[str]


def _certified_symbol_reference_tests(
    conn: Any, inventory: frozenset[str], rel_path: str, language: str
) -> list[str]:
    """Symbol-reference test discovery over snapshot-owned data.

    The legacy ``_find_symbol_reference_tests`` scans live test bytes for
    the target's public symbols; the certified variant (Codex P2 #1299
    round-7, C31) scans the snapshot's recorded import statements
    (``imports_json``) of inventory-covered, test-named files for the
    target's INDEXED public symbol names — tests that use ``from pkg
    import public_fn`` are found even when they import a package, not the
    defining file.
    """

    symbols = _public_indexed_symbols(conn, rel_path)
    if not symbols:
        return []

    results: list[str] = []
    for rel in sorted(inventory):
        if rel == rel_path:
            continue
        importer_language = _target_language(rel)
        if not _looks_like_test_path(rel, importer_language):
            continue
        scope = _SymbolReferenceScope(
            conn=conn,
            inventory=inventory,
            rel_path=rel_path,
            language=language,
            importer=rel,
            importer_language=importer_language,
            symbols=symbols,
        )
        if _importer_references_target(scope):
            results.append(rel)
    return _with_call_reference_tests(conn, inventory, rel_path, symbols, results)


def _public_indexed_symbols(conn: Any, rel_path: str) -> frozenset[str]:
    """Return the target's indexed public (non-underscore) symbol names."""
    entries = _indexed_symbol_entries(conn, rel_path)
    return frozenset(
        name
        for name in (entry.get("name") for entry in entries)
        if isinstance(name, str) and not name.startswith("_")
    )


def _importer_import_records(conn: Any, rel: str) -> list[Any]:
    """Fetch one importer's ``imports_json`` records (list shape validated)."""
    try:
        row = conn.execute(
            "SELECT imports_json FROM ast_index WHERE file_path = ?",
            (rel,),
        ).fetchone()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if row is None:
        raise ValueError("CORRUPT_INDEX")
    # Codex P2 (#1299 round-8, C33): match symbols against the PARSED
    # import identifiers, never the serialized cell — substrings and
    # JSON keys (e.g. a symbol 'text' matching every record's "text"
    # key) would otherwise produce false has_tests=True.
    try:
        records = json.loads(str(row["imports_json"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if not isinstance(records, list):
        raise ValueError("CORRUPT_INDEX")
    return records


def _record_text(record: Any) -> str:
    if not isinstance(record, dict):
        raise ValueError("CORRUPT_INDEX")
    text = record.get("text")
    if not isinstance(text, str):
        raise ValueError("CORRUPT_INDEX")
    return text


def _importer_references_target(scope: _SymbolReferenceScope) -> bool:
    """Return whether any of the importer's records references the target.

    Records are validated lazily, in order: scanning stops at the first
    referencing record, exactly like the original single-loop scan.
    """
    for record in _importer_import_records(scope.conn, scope.importer):
        if _record_references_target(scope, _record_text(record)):
            return True
    return False


def _record_references_target(scope: _SymbolReferenceScope, text: str) -> bool:
    """Decide whether one recorded import statement references the target."""
    if scope.importer_language == "python":
        member_verdict = _python_package_member_verdict(scope, text)
        if member_verdict is not None:
            # A package member import was resolved; it either proved or
            # disproved attribution — never fall back to a textual match.
            return member_verdict
    if scope.importer_language in {"c", "cpp"}:
        return scope.rel_path in _import_targets_from_text(
            text, scope.importer, scope.inventory
        )
    matched = [
        symbol
        for symbol in scope.symbols
        if re.search(rf"\b{re.escape(symbol)}\b", text)
    ]
    if not matched:
        return False
    # Symbol-text fallback is valid only for importer languages whose
    # snapshot projections have resolver-backed ownership semantics.
    # Other languages (for example Go) must arrive through a resolved
    # dependency edge; a same-named package segment is not evidence.
    if scope.importer_language not in _SYMBOL_FALLBACK_LANGUAGES:
        return False
    if scope.importer_language != scope.language and {
        scope.importer_language,
        scope.language,
    } != {"javascript", "typescript"}:
        return False
    return _symbol_import_binds_target(scope, text, matched)


def _python_package_member_verdict(
    scope: _SymbolReferenceScope, text: str
) -> bool | None:
    """Resolve ``from pkg import name`` through the package's re-exports.

    Returns None when *text* is not a member import of a package
    initializer (the caller continues with the generic checks).
    """
    import_module = _import_module_name(text)
    resolved_module = (
        _resolve_import_spec_from_inventory(
            import_module, scope.importer, scope.inventory
        )
        if import_module
        else None
    )
    if not resolved_module or Path(resolved_module).name != "__init__.py":
        return None
    imported_names = _imported_member_names(text, scope.symbols)
    if not imported_names:
        return None
    providers = _python_package_symbol_providers(
        scope.conn, resolved_module, imported_names, scope.inventory
    )
    return any(providers[name] == {scope.rel_path} for name in imported_names)


def _imported_member_names(text: str, symbols: frozenset[str]) -> list[str]:
    """Return the package-exported names a ``from ... import`` binds."""
    imported_names: list[str] = []
    for statement in ast.parse(text).body:
        if not isinstance(statement, ast.ImportFrom):
            continue
        for alias in statement.names:
            if alias.name == "*":
                imported_names.extend(symbols)
            else:
                # Resolve the package's exported name.  A local alias
                # (``execute as invoke``) is irrelevant to which defining
                # module supplied the symbol.
                imported_names.append(alias.name)
    return imported_names


def _symbol_import_binds_target(
    scope: _SymbolReferenceScope, text: str, matched: list[str]
) -> bool:
    """Bind a symbol-matching import to the target module.

    A test doing ``from pkg import run`` must follow pkg/__init__.py's
    certified re-export projection, not count every sibling defining ``run``.
    """
    import_module = _import_module_name(text)
    if not import_module:
        return True
    # Codex P2 (#1299 round-13, C58): relative imports resolve
    # from the IMPORTING TEST's directory, never the target's.
    resolved_module = _resolve_import_spec_from_inventory(
        import_module, scope.importer, scope.inventory
    )
    language = scope.importer_language
    if language in _JSTS_LANGUAGES:
        return resolved_module == scope.rel_path
    if language in {"python", "java"} and resolved_module is None:
        return False
    if language == "python" and resolved_module != scope.rel_path:
        # Package member imports were resolved above; every other
        # Python module mismatch disproves attribution to target.
        return False
    return not (
        language == "java"
        and resolved_module
        and resolved_module != scope.rel_path
        and _file_defines_any(scope.conn, resolved_module, matched)
    )


def _with_call_reference_tests(
    conn: Any,
    inventory: frozenset[str],
    rel_path: str,
    symbols: frozenset[str],
    results: list[str],
) -> list[str]:
    """Append tests that reach the target's symbols through CALL edges.

    Codex P2 (#1299 round-10, C42): snapshot CALL references too — a test
    doing 'import pkg; pkg.public_fn()' references the symbol through a
    call edge even though imports_json carries only 'import pkg'.
    *symbols* is guaranteed non-empty here (the caller's early return).
    """
    placeholders = ",".join("?" for _ in symbols)  # nosec B608
    try:
        # Codex P2 (#1299 round-11, C48): bind by the resolved callee file,
        # not the bare name — a same-named symbol exported by another module
        # must not attribute its tests to this target.
        call_rows = conn.execute(
            f"SELECT DISTINCT file_path FROM edges "
            f"WHERE kind = 'calls' AND callee_name IN ({placeholders}) "
            f"AND callee_resolved_file = ?",
            (*tuple(symbols), rel_path),
        ).fetchall()
    except Exception:  # nosec B110 — legacy schema degrades per call
        call_rows = []
    combined = list(results)
    for row in call_rows:
        rel = str(row["file_path"])
        if (
            rel
            and rel != rel_path
            and rel in inventory
            and _looks_like_test_path(rel, _target_language(rel))
            and rel not in combined
        ):
            combined.append(rel)
    return combined


def _in_test_dirs(rel: str, test_dirs: list[str]) -> bool:
    return any(
        test_dir == "." or rel.startswith(f"{test_dir}/") for test_dir in test_dirs
    )


def _certified_test_files(
    inventory: frozenset[str],
    rel_path: str,
    dependents: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Find inventory-covered test files for one target (RELATIVE posix path).

    Codex P1 (#1299 round-3/4): snapshot-certified test discovery walks the
    snapshot's ``ast_index`` file set instead of the live filesystem, so
    oracle-excluded paths (e.g. ``tests/vendor/``) can never influence
    ``has_tests`` and the discovery cap cannot be filled by un-certified
    candidates. Pattern and colocated conventions mirror the live axis:
    basenames are matched with the patterns' GLOB semantics (round-5, e.g.
    ``test_app_*.py``) and ``test_dirs`` of ``"."`` (Go's co-located
    convention) accept any inventory path (round-5). The legacy
    ``_is_existing_test_file`` and ``_find_symbol_reference_tests`` modes are
    preserved over certified inputs: a target that is itself a test file
    counts, and inventory-covered dependents whose names match the test
    patterns (tests that import the target) count (round-6).
    """

    import fnmatch

    from .test_discovery import (
        _TEST_DIRS,
        _TEST_PATTERNS,
        _format_pattern,
        detect_language_from_ext,
    )

    p = Path(rel_path)
    stem = p.stem
    language = detect_language_from_ext(p.suffix.lower()) or "python"
    patterns = _TEST_PATTERNS.get(language, ["test_{stem}.py"])
    test_dirs = _TEST_DIRS.get(language, ["tests"])
    filenames = [_format_pattern(pattern, stem) for pattern in patterns]

    results: list[str] = []
    if _looks_like_test_path(rel_path, language):
        # The target itself is a test file (legacy _is_existing_test_file).
        results.append(rel_path)
    results.extend(
        rel
        for rel in sorted(inventory)
        if rel != rel_path
        and any(fnmatch.fnmatchcase(Path(rel).name, pattern) for pattern in filenames)
        and _in_test_dirs(rel, test_dirs)
    )
    parent = p.parent.as_posix()
    # Codex P2 (#1299 round-11, C47): a root-level target's parent is '.',
    # which would build './test_app.py' while inventory keys are normalized
    # without the leading './'.
    parent = "" if parent == "." else parent
    for filename in filenames:
        if "*" in filename:
            continue
        colocated = filename if not parent else f"{parent}/{filename}"
        if colocated in inventory and colocated not in results:
            results.append(colocated)
    if language == "python":
        _append_python_package_family_tests(results, inventory, rel_path, test_dirs)
    for dep in dependents:
        # Symbol-reference mode over certified inputs: inventory-covered
        # dependents that import the target and look like tests count —
        # an IMPORTS edge left for an excluded/unindexed path must NOT be
        # served as a certified test (Codex P2 #1299 round-12, C54).
        if (
            dep in inventory
            and _looks_like_test_path(dep, _target_language(dep))
            and dep not in results
        ):
            results.append(dep)
    return results


def _append_python_package_family_tests(
    results: list[str],
    inventory: frozenset[str],
    rel_path: str,
    test_dirs: list[str],
) -> None:
    """Codex P2 (#1299 round-8, C36): package-family ``test_<plugin>.py``.

    Preserves the live route's package-family convention over the inventory.
    """
    import fnmatch

    from .test_discovery_stems import python_package_test_stems

    ordered_inventory = sorted(inventory)
    for package_stem in python_package_test_stems(rel_path):
        for pattern in (
            f"test_{package_stem}.py",
            f"test_{package_stem}_*.py",
        ):
            for rel in ordered_inventory:
                if (
                    rel != rel_path
                    and fnmatch.fnmatchcase(Path(rel).name, pattern)
                    and _in_test_dirs(rel, test_dirs)
                    and rel not in results
                ):
                    results.append(rel)


def _snapshot_reverse_dependencies(
    conn: Any, inventory: frozenset[str]
) -> dict[str, set[str]]:
    """Build the snapshot's reverse adjacency with bounded full-table passes."""

    reverse: dict[str, set[str]] = {}
    _require_edges_callee_name(conn)
    try:
        _reverse_from_resolved_edges(conn, inventory, reverse)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy schema may lack resolved edges
        pass
    try:
        _reverse_from_import_edges(conn, inventory, reverse)
    except Exception:  # nosec B110 — legacy schema may lack import edges
        pass
    try:
        _reverse_from_import_projections(conn, inventory, reverse)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy schema degrades to edge facts
        pass
    return reverse


def _add_reverse_edge(
    reverse: dict[str, set[str]],
    inventory: frozenset[str],
    caller: str,
    dependency: str,
) -> None:
    if caller in inventory and dependency in inventory and caller != dependency:
        reverse.setdefault(dependency, set()).add(caller)


def _reverse_from_resolved_edges(
    conn: Any, inventory: frozenset[str], reverse: dict[str, set[str]]
) -> None:
    rows = conn.execute(
        "SELECT file_path, callee_resolved_file FROM edges "
        "WHERE callee_resolved_file != ''"
    ).fetchall()
    for caller, dependency in rows:
        if not isinstance(caller, str) or not isinstance(dependency, str):
            raise ValueError("CORRUPT_INDEX")
        _add_reverse_edge(reverse, inventory, caller, dependency)


def _reverse_from_import_edges(
    conn: Any, inventory: frozenset[str], reverse: dict[str, set[str]]
) -> None:
    rows = conn.execute(
        "SELECT file_path, callee_name FROM edges WHERE kind = 'imports'"
    ).fetchall()
    for caller, spec in rows:
        if not isinstance(caller, str) or not isinstance(spec, str):
            continue
        resolved = _resolve_import_spec_from_inventory(spec, caller, inventory)
        if resolved is not None:
            _add_reverse_edge(reverse, inventory, caller, resolved)


def _reverse_from_import_projections(
    conn: Any, inventory: frozenset[str], reverse: dict[str, set[str]]
) -> None:
    rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()
    for caller, raw_imports in rows:
        if not isinstance(caller, str) or not caller:
            raise ValueError("CORRUPT_INDEX")
        if caller not in inventory:
            continue
        import_texts = _strict_import_texts(raw_imports)
        dynamic_loaders = _python_loaders_for(caller, import_texts)
        for import_text in import_texts:
            for dependency in _import_targets_from_text(
                import_text,
                caller,
                inventory,
                python_dynamic_loaders=dynamic_loaders,
            ):
                _add_reverse_edge(reverse, inventory, caller, dependency)


def _certified_exercising_tests(
    conn: Any,
    rel_path: str,
    dependents: list[str] | tuple[str, ...],
    *,
    inventory: frozenset[str] | None = None,
    reverse_dependencies: dict[str, set[str]] | None = None,
) -> list[str]:
    """Return complete convention-matched tests when collection is provable."""
    if inventory is None:
        inventory = snapshot_inventory(conn)
    if reverse_dependencies is None:
        reverse_dependencies = _snapshot_reverse_dependencies(conn, inventory)
    test_files: list[str] = []
    for dependent in _walk_reverse_closure(
        rel_path, dependents, inventory, reverse_dependencies
    ):
        if Path(dependent).name == "conftest.py":
            test_files.extend(_conftest_scoped_tests(dependent, inventory))
        if _looks_like_test_path(dependent, _target_language(dependent)):
            test_files.append(dependent)
    if _looks_like_test_path(rel_path, _target_language(rel_path)):
        test_files.insert(0, rel_path)
    test_files.extend(
        _certified_symbol_reference_tests(
            conn, inventory, rel_path, _target_language(rel_path)
        )
    )
    return list(dict.fromkeys(test_files))


def _walk_reverse_closure(
    rel_path: str,
    dependents: list[str] | tuple[str, ...],
    inventory: frozenset[str],
    reverse_dependencies: dict[str, set[str]],
) -> Iterator[str]:
    """Yield inventory-covered transitive dependents in BFS visit order.

    Lazy, so a consumer that stops early (``all``) stops the walk too.
    """
    seen = {rel_path}
    queue = list(dependents)
    cursor = 0
    while cursor < len(queue):
        dependent = queue[cursor]
        cursor += 1
        if dependent in seen or dependent not in inventory:
            continue
        seen.add(dependent)
        yield dependent
        queue.extend(sorted(reverse_dependencies.get(dependent, set())))


def _conftest_scoped_tests(conftest: str, inventory: frozenset[str]) -> list[str]:
    """Return Python tests collected under one ``conftest.py``'s directory."""
    scope = Path(conftest).parent.as_posix()
    return [
        path
        for path in sorted(inventory)
        if path != conftest
        and _target_language(path) == "python"
        and _looks_like_test_path(path, "python")
        and (scope == "." or path.startswith(f"{scope}/"))
    ]


def _pytest_exercising_projection_complete(
    rel_path: str,
    dependents: list[str] | tuple[str, ...],
    inventory: frozenset[str],
    *,
    reverse_dependencies: dict[str, set[str]],
) -> bool:
    """Reject certified test facts when custom collection could hide a module."""

    return all(
        _is_collectable_dependent(dependent)
        for dependent in _walk_reverse_closure(
            rel_path, dependents, inventory, reverse_dependencies
        )
    )


def _is_collectable_dependent(dependent: str) -> bool:
    """Return whether a transitive dependent is a test or support file."""
    language = _target_language(dependent)
    if language not in _CERTIFIED_IMPORT_LANGUAGES:
        return True
    conventional_support_file = language == "python" and Path(dependent).name in {
        "__init__.py",
        "conftest.py",
    }
    return conventional_support_file or _looks_like_test_path(dependent, language)
