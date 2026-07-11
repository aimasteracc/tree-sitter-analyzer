"""Unit tests for synapse_resolver/languages/scala.py.

Verifies that the Scala resolver:
- returns None context when no Scala files exist in the index
- builds a context when at least one Scala file is present
- resolves local symbols (tier a) to "local"
- resolves a uniquely project-wide symbol (tier c) to "project"
- falls back to "unknown" for unresolvable names
- does NOT bind a Scala call to a Python/Go symbol that shares the same bare
  name (M-1 fix: Scala-only filtering of file_symbols)
- registers under the "scala" language key so the cascade never accidentally
  reaches the Python builtin/stdlib tier for Scala callers
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._registry import registered_languages
from tree_sitter_analyzer.synapse_resolver.languages.scala import (
    ScalaResolverContext,
    build_scala_resolver_context,
    resolve_scala_callee,
)

# ---------------------------------------------------------------------------
# build_scala_resolver_context — context construction gating
# ---------------------------------------------------------------------------


class TestBuildScalaResolverContext:
    """build_scala_resolver_context must return None when no Scala files exist."""

    _common_kwargs: dict = {
        "imports_by_file": {},
        "file_symbols": {},
        "global_name_table": {},
        "file_class_methods": None,
    }

    def test_build_context_returns_none_for_non_scala_project(self) -> None:
        """Returns None for a Python-only project (zero cost for absent language)."""
        ctx = build_scala_resolver_context(
            file_languages={"main.py": "python", "util.go": "go"},
            **self._common_kwargs,
        )
        assert ctx is None

    def test_build_context_returns_context_for_scala_project(self) -> None:
        """Returns a ScalaResolverContext when at least one .scala file is indexed."""
        ctx = build_scala_resolver_context(
            file_languages={"App.scala": "scala", "util.py": "python"},
            **self._common_kwargs,
        )
        assert isinstance(ctx, ScalaResolverContext)


# ---------------------------------------------------------------------------
# resolve_scala_callee — resolution cascade
# ---------------------------------------------------------------------------


class TestResolveScalaCallee:
    """Verify each tier of the Scala resolution cascade."""

    def test_scala_resolver_local_cascade(self) -> None:
        """Tier (a): a name defined in the same file resolves to 'local'."""
        ctx = ScalaResolverContext(
            file_symbols={
                "src/Main.scala": [("parseArgs", "function", 7)],
            },
            global_name_table={},
            name_to_source={},
        )
        sym_id, resolution, resolved_file = resolve_scala_callee(
            "parseArgs", "", "src/Main.scala", ctx
        )
        assert resolution == "local"
        assert sym_id == 7
        assert resolved_file == "src/Main.scala"

    def test_scala_resolver_project_cascade(self) -> None:
        """Tier (c): a name with exactly one project-wide entry resolves to 'project'."""
        # "Helper" is defined only in utils.scala and that file is in file_symbols.
        ctx = ScalaResolverContext(
            file_symbols={
                "src/App.scala": [("run", "function", 1)],
                "src/utils.scala": [("Helper", "class", 99)],
            },
            global_name_table={
                "Helper": [("src/utils.scala", 99)],
            },
            name_to_source={},
        )
        sym_id, resolution, resolved_file = resolve_scala_callee(
            "Helper", "", "src/App.scala", ctx
        )
        assert resolution == "project"
        assert sym_id == 99
        assert resolved_file == "src/utils.scala"

    def test_scala_resolver_unknown_fallback(self) -> None:
        """Unresolvable name (not local, not in imports, not uniquely global) -> 'unknown'."""
        ctx = ScalaResolverContext(
            file_symbols={
                "src/App.scala": [("run", "function", 1)],
            },
            # "phantom" appears twice — ambiguous, no unique resolution.
            global_name_table={
                "phantom": [("src/A.scala", 10), ("src/B.scala", 20)],
            },
            name_to_source={},
        )
        sym_id, resolution, resolved_file = resolve_scala_callee(
            "phantom", "", "src/App.scala", ctx
        )
        assert resolution == "unknown"
        assert sym_id is None
        assert resolved_file == ""

    def test_scala_resolver_no_cross_language_binding(self) -> None:
        """Tier (c): a symbol that exists only in a Python file must NOT resolve to 'project'.

        This tests the M-1 fix: build_scala_resolver_context filters file_symbols
        to Scala-only, so a Python-defined 'MyClass' that happens to share a name
        with a Scala call target is never surfaced as a project-level match.
        """
        # Build context the same way the real pipeline does — via the builder.
        ctx = build_scala_resolver_context(
            # Only App.scala is Scala; main.py is Python.
            file_languages={"src/App.scala": "scala", "main.py": "python"},
            imports_by_file={},
            # MyClass lives in a Python file, not a Scala file.
            file_symbols={
                "main.py": [("MyClass", "class", 42)],
            },
            # global_name_table points the name to the Python file.
            global_name_table={
                "MyClass": [("main.py", 42)],
            },
            file_class_methods=None,
        )
        assert ctx is not None, "Context must be built (App.scala is present)"

        # Resolving "MyClass" from the Scala caller must NOT bind to main.py.
        sym_id, resolution, resolved_file = resolve_scala_callee(
            "MyClass", "", "src/App.scala", ctx
        )
        assert resolution != "project", (
            "Scala resolver must not bind to a Python-only symbol (M-1 fix)"
        )
        assert resolution == "unknown"
        assert sym_id is None


# ---------------------------------------------------------------------------
# Registry — scala is registered after module import
# ---------------------------------------------------------------------------


class TestScalaRegistered:
    """'scala' must appear in registered_languages() after the module is imported."""

    def test_scala_registered_after_import(self) -> None:
        """Importing scala.py registers 'scala' in the global language registry."""
        # The module is already imported (top-level import above) and calls
        # register_language at module level — so 'scala' must be in the registry.
        assert "scala" in registered_languages()
