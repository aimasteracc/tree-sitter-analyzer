"""Unit tests for synapse_resolver/_context.py — ResolverContext and helpers.

All tests use mocks for ASTCache so no real DB is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.synapse_resolver._context import (
    ResolverContext,
    _build_module_to_file,
    _resolve_absolute_module,
    _resolve_relative_module,
    build_resolver_context,
    is_enabled,
)
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(project_root: str = "/repo", db_path: str = "") -> MagicMock:
    """Return a minimal ASTCache mock."""
    cache = MagicMock()
    cache.project_root = project_root
    cache.db_path = db_path
    return cache


def _prebuilt_ctx(**kwargs) -> ResolverContext:
    """Build a ResolverContext with all maps pre-supplied (no DB needed)."""
    defaults: dict[str, object] = {
        "project_root": "/repo",
        "cache": None,
        "file_symbols": {"a.py": [("run", "function", 1)]},
        "name_to_source": {"a.py": {"baz": "b.py"}},
        "file_class_methods": {"a.py": {"MyClass": {"method_a": 10}}},
        "global_name_table": {"run": [("a.py", 1)]},
        "import_alias_target": {"a.py": {"bb": "b.py"}},
        "imports_by_file": {},
        "builtins": {"python": frozenset(["len", "print"])},
        "stdlib_modules": {"python": frozenset(["os", "pathlib"])},
        "callee_resolver": None,
    }
    defaults.update(kwargs)
    return ResolverContext(**defaults)


# ---------------------------------------------------------------------------
# Construction — no cache, no pre-built maps
# ---------------------------------------------------------------------------


class TestResolverContextConstruction:
    """ResolverContext builds correctly in both construction modes."""

    def test_no_cache_empty_maps(self):
        ctx = ResolverContext(project_root="/repo", cache=None)
        # All maps default to empty without triggering _ensure_loaded
        assert ctx._file_symbols == {}
        assert ctx._name_to_source == {}
        assert ctx._file_class_methods == {}
        assert ctx._global_name_table == {}
        assert ctx._import_alias_target == {}
        assert ctx._imports_by_file == {}
        assert ctx._builtins == {}
        assert ctx._stdlib_modules == {}
        assert ctx._callee_resolver is None

    def test_no_cache_loaded_flag_false(self):
        ctx = ResolverContext(project_root="/repo", cache=None)
        assert not ctx._loaded

    def test_prebuilt_maps_loaded_flag_true(self):
        ctx = _prebuilt_ctx()
        assert ctx._loaded

    def test_project_root_stored(self):
        ctx = ResolverContext(project_root="/my/project", cache=None)
        assert ctx.project_root == "/my/project"

    def test_cache_stored(self):
        cache = _make_cache()
        ctx = ResolverContext(project_root="/repo", cache=cache)
        assert ctx.cache is cache

    def test_single_prebuilt_map_sets_loaded(self):
        """Even one non-None kwarg marks the context as loaded."""
        ctx = ResolverContext(
            project_root="/repo",
            cache=None,
            file_symbols={"x.py": []},
        )
        assert ctx._loaded

    def test_all_maps_none_not_loaded(self):
        ctx = ResolverContext(project_root="/repo", cache=None)
        assert not ctx._loaded

    def test_file_class_methods_loaded_flag_with_prebuilt(self):
        ctx = _prebuilt_ctx(file_class_methods={"f.py": {}})
        assert ctx._file_class_methods_loaded

    def test_file_class_methods_loaded_flag_without_prebuilt(self):
        ctx = ResolverContext(project_root="/repo", cache=None)
        assert not ctx._file_class_methods_loaded


# ---------------------------------------------------------------------------
# Properties — pre-built mode (no DB call expected)
# ---------------------------------------------------------------------------


class TestResolverContextProperties:
    """Properties return the pre-built maps directly."""

    def test_file_symbols_property(self):
        ctx = _prebuilt_ctx()
        assert ctx.file_symbols == {"a.py": [("run", "function", 1)]}

    def test_name_to_source_property(self):
        ctx = _prebuilt_ctx()
        assert ctx.name_to_source == {"a.py": {"baz": "b.py"}}

    def test_file_class_methods_property(self):
        ctx = _prebuilt_ctx()
        assert ctx.file_class_methods == {"a.py": {"MyClass": {"method_a": 10}}}

    def test_global_name_table_property(self):
        ctx = _prebuilt_ctx()
        assert ctx.global_name_table == {"run": [("a.py", 1)]}

    def test_import_alias_target_property(self):
        ctx = _prebuilt_ctx()
        assert ctx.import_alias_target == {"a.py": {"bb": "b.py"}}

    def test_imports_by_file_property(self):
        imports = {
            "a.py": [
                ImportEntry(
                    file_path="a.py",
                    language="python",
                    module_path=".b",
                    local_name="baz",
                    is_relative=True,
                )
            ]
        }
        ctx = _prebuilt_ctx(imports_by_file=imports)
        assert ctx.imports_by_file == imports

    def test_builtins_property(self):
        ctx = _prebuilt_ctx()
        assert "len" in ctx.builtins["python"]
        assert "print" in ctx.builtins["python"]

    def test_stdlib_modules_property(self):
        ctx = _prebuilt_ctx()
        assert "os" in ctx.stdlib_modules["python"]
        assert "pathlib" in ctx.stdlib_modules["python"]

    def test_callee_resolver_property_none(self):
        ctx = _prebuilt_ctx(callee_resolver=None)
        assert ctx.callee_resolver is None

    def test_callee_resolver_property_set(self):
        resolver = MagicMock()
        ctx = _prebuilt_ctx(callee_resolver=resolver)
        assert ctx.callee_resolver is resolver


# ---------------------------------------------------------------------------
# _ensure_loaded — lazy loading behaviour
# ---------------------------------------------------------------------------


class TestEnsureLoaded:
    """_ensure_loaded triggers build_resolver_context when cache is present."""

    def test_no_cache_marks_loaded_without_build(self):
        ctx = ResolverContext(project_root="/repo", cache=None)
        assert not ctx._loaded
        ctx._ensure_loaded()
        assert ctx._loaded
        # Maps remain empty — no build happened
        assert ctx._file_symbols == {}

    def test_with_cache_calls_build(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        built = _prebuilt_ctx(
            file_symbols={"x.py": [("go", "function", 7)]},
        )
        mock_build = MagicMock(return_value=built)
        monkeypatch.setattr(_context, "_build_resolver_context_uncached", mock_build)
        # Isolate LRU cache so it doesn't return a stale hit.
        _context.clear_resolver_context_cache()

        cache = _make_cache(db_path="")
        ctx = ResolverContext(project_root="/repo", cache=cache)
        assert not ctx._loaded

        # Access a property — triggers _ensure_loaded
        _ = ctx.file_symbols
        assert ctx._loaded
        assert ctx._file_symbols == {"x.py": [("go", "function", 7)]}
        mock_build.assert_called_once()

    def test_second_property_access_does_not_rebuild(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from tree_sitter_analyzer.synapse_resolver import _context

        built = _prebuilt_ctx()
        mock_build = MagicMock(return_value=built)
        monkeypatch.setattr(_context, "_build_resolver_context_uncached", mock_build)
        _context.clear_resolver_context_cache()

        cache = _make_cache(db_path="")
        ctx = ResolverContext(project_root="/repo", cache=cache)

        _ = ctx.file_symbols
        _ = ctx.name_to_source
        assert mock_build.call_count == 1


# ---------------------------------------------------------------------------
# file_class_methods — lazy population from cache
# ---------------------------------------------------------------------------


class TestFileClassMethodsLazy:
    """file_class_methods triggers _build_file_class_methods_from_cache lazily."""

    def test_lazy_load_from_cache(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        expected = {"c.py": {"SomeClass": {"do_it": 42}}}
        mock_fcm = MagicMock(return_value=expected)
        monkeypatch.setattr(_context, "_build_file_class_methods_from_cache", mock_fcm)

        cache = _make_cache()
        # file_class_methods=None triggers the lazy path; builtins != None → loaded=True
        ctx = ResolverContext(
            project_root="/repo",
            cache=cache,
            file_class_methods=None,
            builtins={"python": frozenset()},
            stdlib_modules={"python": frozenset()},
        )
        assert not ctx._file_class_methods_loaded

        result = ctx.file_class_methods
        assert result == expected
        assert ctx._file_class_methods_loaded
        mock_fcm.assert_called_once_with(cache)

    def test_no_double_load(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        mock_fcm = MagicMock(return_value={})
        monkeypatch.setattr(_context, "_build_file_class_methods_from_cache", mock_fcm)

        cache = _make_cache()
        ctx = ResolverContext(
            project_root="/repo",
            cache=cache,
            file_class_methods=None,
            builtins={"python": frozenset()},
        )
        _ = ctx.file_class_methods
        _ = ctx.file_class_methods
        assert mock_fcm.call_count == 1


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------


class TestIsEnabled:
    """is_enabled() respects the TSA_SYNAPSE environment variable."""

    def test_enabled_by_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TSA_SYNAPSE", raising=False)
        assert is_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_disabled_values(self, val: str, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TSA_SYNAPSE", val)
        assert is_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "  1  "])
    def test_enabled_values(self, val: str, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TSA_SYNAPSE", val)
        assert is_enabled() is True


# ---------------------------------------------------------------------------
# _build_module_to_file
# ---------------------------------------------------------------------------


class TestBuildModuleToFile:
    """_build_module_to_file maps Python file paths to dotted module names."""

    def test_regular_module(self):
        result = _build_module_to_file(["pkg/foo.py"])
        assert result["pkg.foo"] == "pkg/foo.py"

    def test_init_module(self):
        result = _build_module_to_file(["pkg/__init__.py"])
        assert result["pkg"] == "pkg/__init__.py"

    def test_nested_module(self):
        result = _build_module_to_file(["a/b/c.py"])
        assert result["a.b.c"] == "a/b/c.py"

    def test_multiple_files(self):
        result = _build_module_to_file(["a.py", "pkg/__init__.py", "pkg/bar.py"])
        assert result["a"] == "a.py"
        assert result["pkg"] == "pkg/__init__.py"
        assert result["pkg.bar"] == "pkg/bar.py"

    def test_empty_list(self):
        assert _build_module_to_file([]) == {}

    def test_non_py_file_excluded(self):
        result = _build_module_to_file(["foo.js", "bar.ts"])
        assert result == {}


# ---------------------------------------------------------------------------
# _resolve_absolute_module
# ---------------------------------------------------------------------------


class TestResolveAbsoluteModule:
    """_resolve_absolute_module walks the dotted name to find the file."""

    def test_exact_match(self):
        m2f = {"pkg.foo": "pkg/foo.py"}
        assert _resolve_absolute_module("pkg.foo", m2f) == "pkg/foo.py"

    def test_partial_match(self):
        m2f = {"pkg": "pkg/__init__.py"}
        assert _resolve_absolute_module("pkg.foo", m2f) == "pkg/__init__.py"

    def test_no_match(self):
        m2f = {"other": "other.py"}
        assert _resolve_absolute_module("pkg.foo", m2f) == ""

    def test_empty_module_to_file(self):
        assert _resolve_absolute_module("pkg", {}) == ""


# ---------------------------------------------------------------------------
# _resolve_relative_module
# ---------------------------------------------------------------------------


class TestResolveRelativeModule:
    """_resolve_relative_module handles leading-dot relative imports."""

    def _m2f(self, paths: list[str]) -> dict[str, str]:
        return {p: p for p in paths}

    def test_single_dot_sibling(self):
        m2f = self._m2f(["pkg/b.py"])
        result = _resolve_relative_module(".b", "pkg/a.py", m2f)
        assert result == "pkg/b.py"

    def test_single_dot_init(self):
        m2f = self._m2f(["pkg/__init__.py"])
        result = _resolve_relative_module(".", "pkg/a.py", m2f)
        assert result == "pkg/__init__.py"

    def test_double_dot_parent(self):
        m2f = self._m2f(["top/b.py"])
        result = _resolve_relative_module("..b", "top/sub/a.py", m2f)
        assert result == "top/b.py"

    def test_no_match_returns_empty(self):
        result = _resolve_relative_module(".nonexistent", "pkg/a.py", {})
        assert result == ""


# ---------------------------------------------------------------------------
# build_resolver_context — LRU caching
# ---------------------------------------------------------------------------


class TestBuildResolverContextCache:
    """build_resolver_context reuses LRU-cached results for same cache snapshot."""

    def test_lru_cache_hit(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        built = _prebuilt_ctx()
        mock_build = MagicMock(return_value=built)
        monkeypatch.setattr(_context, "_build_resolver_context_uncached", mock_build)
        monkeypatch.setattr(_context, "_cache_identity", lambda _c: ("key", 1, 2))
        _context.clear_resolver_context_cache()

        cache = _make_cache()
        r1 = build_resolver_context(cache)
        r2 = build_resolver_context(cache)
        assert r1 is r2
        assert mock_build.call_count == 1

    def test_lru_cache_miss_different_identity(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        counter = {"n": 0}

        def _build(_cache):
            counter["n"] += 1
            return _prebuilt_ctx()

        monkeypatch.setattr(_context, "_build_resolver_context_uncached", _build)
        _context.clear_resolver_context_cache()

        identities = [("k1", 1, 1), ("k2", 2, 2)]
        idx = {"i": 0}

        def _identity(_c):
            val = identities[idx["i"] % 2]
            idx["i"] += 1
            return val

        monkeypatch.setattr(_context, "_cache_identity", _identity)

        cache = _make_cache()
        build_resolver_context(cache)
        build_resolver_context(cache)
        assert counter["n"] == 2

    def test_clear_cache_forces_rebuild(self, monkeypatch: pytest.MonkeyPatch):
        from tree_sitter_analyzer.synapse_resolver import _context

        built = _prebuilt_ctx()
        call_count = {"n": 0}

        def _build(_cache):
            call_count["n"] += 1
            return built

        monkeypatch.setattr(_context, "_build_resolver_context_uncached", _build)
        monkeypatch.setattr(_context, "_cache_identity", lambda _c: ("k", 1, 1))
        _context.clear_resolver_context_cache()

        cache = _make_cache()
        build_resolver_context(cache)
        assert call_count["n"] == 1

        _context.clear_resolver_context_cache()
        build_resolver_context(cache)
        assert call_count["n"] == 2
