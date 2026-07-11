"""Unit tests for synapse_resolver/languages/bash.py.

Verifies that the Bash resolver:
- always returns ``unknown`` for every callee (the moat contract)
- builds a context only when Bash files are present in the index
- registers under the ``"bash"`` language key so the cascade never reaches the
  Python builtin/stdlib tier for shell callers
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._registry import registered_languages
from tree_sitter_analyzer.synapse_resolver.languages.bash import (
    BashResolverContext,
    build_bash_resolver_context,
    resolve_bash_callee,
)

# ---------------------------------------------------------------------------
# resolve_bash_callee — always returns unknown
# ---------------------------------------------------------------------------


class TestResolveBashCallee:
    """resolve_bash_callee must always return (None, "unknown", "")."""

    def _ctx(self) -> BashResolverContext:
        return BashResolverContext()

    def test_bash_resolver_returns_unknown_for_print(self) -> None:
        """``print`` (a Python builtin) must stay unknown for Bash callers."""
        _sym_id, resolution, _resolved_file = resolve_bash_callee(
            "print", "", "script.sh", self._ctx()
        )
        assert resolution == "unknown"

    def test_bash_resolver_returns_unknown_for_list(self) -> None:
        """``list`` (a Python builtin) must stay unknown for Bash callers."""
        _sym_id, resolution, _resolved_file = resolve_bash_callee(
            "list", "", "script.sh", self._ctx()
        )
        assert resolution == "unknown"

    def test_bash_resolver_returns_none_symbol_id(self) -> None:
        """symbol_id component of the tuple must be None (no binding)."""
        sym_id, _resolution, _resolved_file = resolve_bash_callee(
            "map", "", "deploy.sh", self._ctx()
        )
        assert sym_id is None

    def test_bash_resolver_returns_empty_resolved_file(self) -> None:
        """resolved_file must be an empty string (no cross-file binding)."""
        _sym_id, _resolution, resolved_file = resolve_bash_callee(
            "type", "", "run.sh", self._ctx()
        )
        assert resolved_file == ""

    def test_bash_resolver_returns_unknown_for_arbitrary_command(self) -> None:
        """Any shell command name (e.g. ``echo``) returns unknown."""
        _sym_id, resolution, _resolved_file = resolve_bash_callee(
            "echo", "echo", "bootstrap.sh", self._ctx()
        )
        assert resolution == "unknown"


# ---------------------------------------------------------------------------
# build_bash_resolver_context — context construction gating
# ---------------------------------------------------------------------------


class TestBuildBashResolverContext:
    """build_bash_resolver_context must return None when no Bash files exist."""

    _common_kwargs = {
        "imports_by_file": {},
        "file_symbols": {},
        "global_name_table": {},
        "file_class_methods": None,
    }

    def test_bash_context_none_when_no_bash_files(self) -> None:
        """Returns None for a Python-only project (zero cost)."""
        ctx = build_bash_resolver_context(
            file_languages={"main.py": "python"},
            **self._common_kwargs,
        )
        assert ctx is None

    def test_bash_context_built_when_bash_present(self) -> None:
        """Returns a BashResolverContext when at least one Bash file is indexed."""
        ctx = build_bash_resolver_context(
            file_languages={"deploy.sh": "bash"},
            **self._common_kwargs,
        )
        assert isinstance(ctx, BashResolverContext)

    def test_bash_context_built_when_bash_mixed_with_other_languages(self) -> None:
        """Returns context when Bash is mixed with Python/JS (common CI project)."""
        ctx = build_bash_resolver_context(
            file_languages={"main.py": "python", "build.sh": "bash"},
            **self._common_kwargs,
        )
        assert isinstance(ctx, BashResolverContext)

    def test_bash_context_none_when_empty_file_languages(self) -> None:
        """Returns None for an empty file_languages map."""
        ctx = build_bash_resolver_context(
            file_languages={},
            **self._common_kwargs,
        )
        assert ctx is None


# ---------------------------------------------------------------------------
# Registry — bash is registered after module import
# ---------------------------------------------------------------------------


class TestBashRegistered:
    """``bash`` must appear in registered_languages() after the module is imported."""

    def test_bash_registered_after_import(self) -> None:
        """Importing bash.py registers 'bash' in the global language registry."""
        # The module is already imported (top-level import above) and calls
        # register_language at module level — so 'bash' must be in the registry.
        assert "bash" in registered_languages()
