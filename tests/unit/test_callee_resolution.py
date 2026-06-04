"""Contracts for shared callee resolution."""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter_analyzer.callee_resolution import CalleeResolver


@dataclass(frozen=True)
class Func:
    name: str
    file: str
    line: int = 1


def test_resolver_prefers_same_file_then_import_then_global() -> None:
    local = Func("run", "main.py")
    imported = Func("format_user", "utils.py")
    global_only = Func("cleanup", "tasks.py")
    resolver = CalleeResolver(
        functions_by_name={
            "run": [local, Func("run", "other.py")],
            "format_user": [imported],
            "cleanup": [global_only],
        },
        functions_by_file={
            "main.py": [local],
            "utils.py": [imported],
            "tasks.py": [global_only],
        },
        name_to_source={"main.py": {"format_user": "utils.py"}},
    )

    assert resolver.resolve_items("run", "main.py") == [(local, 1.0)]
    assert resolver.resolve_items("format_user", "main.py") == [(imported, 0.9)]
    assert resolver.resolve_items("cleanup", "main.py") == [(global_only, 0.5)]


def test_resolver_supports_qualified_import_aliases_and_file_results() -> None:
    target = Func("render", "views.py")
    resolver = CalleeResolver(
        functions_by_name={"render": [target]},
        functions_by_file={"views.py": [target]},
        name_to_source={"main.py": {"views": "views.py"}},
    )

    assert resolver.resolve_items("views.render", "main.py") == [(target, 0.9)]
    assert resolver.resolve_files("views.render", "main.py") == [("views.py", 0.9)]


def test_resolver_can_return_import_file_without_matching_symbol() -> None:
    resolver = CalleeResolver(
        functions_by_name={},
        functions_by_file={"models.py": []},
        name_to_source={"main.py": {"User": "models.py"}},
    )

    assert resolver.resolve_files(
        "User",
        "main.py",
        include_unmatched_import=True,
    ) == [("models.py", 0.7)]
    assert resolver.resolve_items("User", "main.py") == []


def test_resolver_can_limit_resolution_to_specific_phases() -> None:
    local = Func("run", "main.py")
    imported = Func("run", "imported.py")
    global_only = Func("run", "global.py")
    resolver = CalleeResolver(
        functions_by_name={"run": [local, imported, global_only]},
        functions_by_file={
            "main.py": [local],
            "imported.py": [imported],
            "global.py": [global_only],
        },
        name_to_source={"main.py": {"run": "imported.py"}},
    )

    assert resolver.resolve_items(
        "run",
        "main.py",
        include_local=False,
        include_global=False,
    ) == [(imported, 0.9)]
    assert resolver.resolve_items(
        "run",
        "main.py",
        include_local=False,
        include_import=False,
    ) == [(local, 0.5), (imported, 0.5), (global_only, 0.5)]


def test_resolver_first_match_helpers_avoid_collecting_all_candidates() -> None:
    local = Func("run", "main.py")
    imported = Func("run", "imported.py")
    resolver = CalleeResolver(
        functions_by_name={"run": [local, imported]},
        functions_by_file={"main.py": [local], "imported.py": [imported]},
        name_to_source={"main.py": {"alias": "imported.py"}},
    )

    assert resolver.resolve_first_item("run", "main.py") == (local, 1.0)
    assert resolver.resolve_first_file(
        "alias.run",
        "main.py",
        include_local=False,
        include_global=False,
    ) == ("imported.py", 0.9)
    assert (
        resolver.resolve_first_file(
            "missing",
            "main.py",
            include_unmatched_import=True,
            include_local=False,
            include_global=False,
        )
        is None
    )


def test_global_fallback_gated_by_language_for_function_less_file() -> None:
    """Codex P2 #301: a caller file with no indexed functions is still gated.

    The caller language is derived from the file extension, so a Python module
    -level call must not fall through to a same-named JavaScript symbol.
    """
    js = {"name": "get", "file": "widget.js", "language": "javascript", "line": 1}
    resolver = CalleeResolver(
        functions_by_name={"get": [js]},
        functions_by_file={},  # caller.py has no indexed functions
        name_to_source={},
    )
    # ``caller.py`` -> python (by extension); the JS ``get`` must be gated out.
    assert resolver.resolve_items("get", "caller.py") == []


def test_global_fallback_allows_js_ts_family() -> None:
    """Codex P2 #301: JavaScript and TypeScript are one interop family.

    A ``.js`` caller resolving to a ``.ts`` definition (gradual migration) is
    valid and must NOT be rejected by the cross-language gate.
    """
    ts_target = {"name": "foo", "file": "lib.ts", "language": "typescript", "line": 1}
    resolver = CalleeResolver(
        functions_by_name={"foo": [ts_target]},
        functions_by_file={},
        name_to_source={},
    )
    assert resolver.resolve_items("foo", "app.js") == [(ts_target, 0.5)]
