"""Unit tests for synapse_resolver/languages/lua.py.

Verifies that the Lua resolver:
- always returns ``unknown`` for every callee (the moat contract)
- builds a context only when Lua files are present in the index
- registers under the ``"lua"`` language key so the cascade never reaches the
  Python builtin/stdlib tier for Lua callers
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._registry import registered_languages
from tree_sitter_analyzer.synapse_resolver.languages.lua import (
    LuaResolverContext,
    build_lua_resolver_context,
    resolve_lua_callee,
)


# ---------------------------------------------------------------------------
# resolve_lua_callee — always returns unknown
# ---------------------------------------------------------------------------


class TestResolveLuaCallee:
    """resolve_lua_callee must always return (None, "unknown", "")."""

    def _ctx(self) -> LuaResolverContext:
        return LuaResolverContext()

    def test_lua_resolver_returns_unknown_for_print(self) -> None:
        """``print`` (a Python builtin) must stay unknown for Lua callers."""
        _sym_id, resolution, _resolved_file = resolve_lua_callee(
            "print", "", "script.lua", self._ctx()
        )
        assert resolution == "unknown"

    def test_lua_resolver_returns_unknown_for_type(self) -> None:
        """``type`` (a Lua builtin / Python builtin) must stay unknown."""
        _sym_id, resolution, _resolved_file = resolve_lua_callee(
            "type", "", "game.lua", self._ctx()
        )
        assert resolution == "unknown"

    def test_lua_resolver_returns_unknown_for_pairs(self) -> None:
        """``pairs`` (Lua builtin) must stay unknown — not a Python name."""
        _sym_id, resolution, _resolved_file = resolve_lua_callee(
            "pairs", "", "init.lua", self._ctx()
        )
        assert resolution == "unknown"

    def test_lua_resolver_returns_none_symbol_id(self) -> None:
        """symbol_id component of the tuple must be None (no binding)."""
        sym_id, _resolution, _resolved_file = resolve_lua_callee(
            "require", "", "mod.lua", self._ctx()
        )
        assert sym_id is None

    def test_lua_resolver_returns_empty_resolved_file(self) -> None:
        """resolved_file must be an empty string (no cross-file binding)."""
        _sym_id, _resolution, resolved_file = resolve_lua_callee(
            "tostring", "", "util.lua", self._ctx()
        )
        assert resolved_file == ""

    def test_lua_resolver_returns_unknown_for_arbitrary_call(self) -> None:
        """Any Lua function name returns unknown."""
        _sym_id, resolution, _resolved_file = resolve_lua_callee(
            "my_func", "my_func", "main.lua", self._ctx()
        )
        assert resolution == "unknown"

    def test_lua_resolver_result_is_three_tuple(self) -> None:
        """Return value is always a 3-tuple (symbol_id, resolution, resolved_file)."""
        result = resolve_lua_callee("ipairs", "", "loop.lua", self._ctx())
        assert len(result) == 3


# ---------------------------------------------------------------------------
# build_lua_resolver_context — context construction gating
# ---------------------------------------------------------------------------


class TestBuildLuaResolverContext:
    """build_lua_resolver_context must return None when no Lua files exist."""

    _common_kwargs: dict = {
        "imports_by_file": {},
        "file_symbols": {},
        "global_name_table": {},
        "file_class_methods": None,
    }

    def test_lua_context_none_when_no_lua_files(self) -> None:
        """Returns None for a Python-only project (zero cost)."""
        ctx = build_lua_resolver_context(
            file_languages={"main.py": "python"},
            **self._common_kwargs,
        )
        assert ctx is None

    def test_lua_context_built_when_lua_present(self) -> None:
        """Returns a LuaResolverContext when at least one Lua file is indexed."""
        ctx = build_lua_resolver_context(
            file_languages={"init.lua": "lua"},
            **self._common_kwargs,
        )
        assert isinstance(ctx, LuaResolverContext)

    def test_lua_context_built_when_lua_mixed_with_other_languages(self) -> None:
        """Returns context when Lua is mixed with Python (common game/script project)."""
        ctx = build_lua_resolver_context(
            file_languages={"main.py": "python", "game.lua": "lua"},
            **self._common_kwargs,
        )
        assert isinstance(ctx, LuaResolverContext)

    def test_lua_context_none_when_empty_file_languages(self) -> None:
        """Returns None for an empty file_languages map."""
        ctx = build_lua_resolver_context(
            file_languages={},
            **self._common_kwargs,
        )
        assert ctx is None

    def test_lua_context_none_for_javascript_only_project(self) -> None:
        """Returns None when no Lua files are present (JS project)."""
        ctx = build_lua_resolver_context(
            file_languages={"app.js": "javascript", "index.ts": "typescript"},
            **self._common_kwargs,
        )
        assert ctx is None


# ---------------------------------------------------------------------------
# Registry — lua is registered after module import
# ---------------------------------------------------------------------------


class TestLuaRegistered:
    """``lua`` must appear in registered_languages() after the module is imported."""

    def test_lua_registered_after_import(self) -> None:
        """Importing lua.py registers 'lua' in the global language registry."""
        # The module is already imported (top-level import above) and calls
        # register_language at module level — so 'lua' must be in the registry.
        assert "lua" in registered_languages()
