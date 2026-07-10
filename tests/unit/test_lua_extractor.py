"""Unit tests for LuaElementExtractor.

Covers:
  1. Graceful degradation when tree_sitter_lua is absent (always runs).
  2. Actual function/import extraction with a real Lua parse tree
     (skipped automatically when tree_sitter_lua is not installed).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Availability guard — defined BEFORE any skipif that references it
# ---------------------------------------------------------------------------

def _tslua_available() -> bool:
    """Return True when tree_sitter_lua is importable in the current env."""
    try:
        import importlib

        importlib.import_module("tree_sitter_lua")
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Test 1: graceful degradation (always runs, no real Lua grammar needed)
# ---------------------------------------------------------------------------


def test_lua_extractor_graceful_when_no_tslua(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract_functions and extract_imports return [] without crashing when
    tree_sitter_lua is not available in sys.modules.
    """
    # Block the Lua grammar package.  Python treats a None entry in sys.modules
    # as a failed import and raises ImportError when the name is requested.
    monkeypatch.setitem(sys.modules, "tree_sitter_lua", None)

    # Import here (after the patch) so that any cached module object is still
    # safe — the lazy import inside _get_lua_language() re-checks sys.modules
    # at call time, which is what we rely on.
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    extractor = LuaElementExtractor()
    mock_tree = MagicMock()

    result_functions = extractor.extract_functions(mock_tree, "")
    result_imports = extractor.extract_imports(mock_tree, "")

    assert result_functions == [], (
        "extract_functions() must return [] when tree_sitter_lua is unavailable"
    )
    assert result_imports == [], (
        "extract_imports() must return [] when tree_sitter_lua is unavailable"
    )

    # extract_classes and extract_variables always return []; verify here too.
    assert extractor.extract_classes(mock_tree, "") == []
    assert extractor.extract_variables(mock_tree, "") == []


# ---------------------------------------------------------------------------
# Test 2: real extraction (skipped unless tree_sitter_lua is installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _tslua_available(), reason="tree_sitter_lua not installed")
def test_lua_extractor_extracts_functions_and_imports() -> None:
    """With tree_sitter_lua installed, named and local functions are extracted
    and require() calls appear as import elements.
    """
    import tree_sitter
    import tree_sitter_lua as tslua

    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    source = """\
local json = require("json")
local socket = require("socket.http")

function greet(name)
    print("Hello, " .. name)
end

local function add(a, b)
    return a + b
end
"""
    language = tree_sitter.Language(tslua.language())
    parser = tree_sitter.Parser()
    parser.language = language
    tree = parser.parse(bytes(source, "utf-8"))

    extractor = LuaElementExtractor()

    functions = extractor.extract_functions(tree, source)
    func_names = [f.name for f in functions]
    assert "greet" in func_names, f"Expected 'greet' in {func_names}"
    assert "add" in func_names, f"Expected 'add' in {func_names}"

    imports = extractor.extract_imports(tree, source)
    import_paths = [i.module_path for i in imports]
    assert "json" in import_paths, f"Expected 'json' in {import_paths}"
    assert "socket.http" in import_paths, f"Expected 'socket.http' in {import_paths}"
