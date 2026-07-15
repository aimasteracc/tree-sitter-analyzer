"""Unit tests for LuaElementExtractor.

Covers:
  1. Graceful degradation when tree_sitter_lua is absent (always runs).
  2. Mock-grammar extraction tests (always runs — no real Lua grammar needed).
  3. Actual function/import extraction with a real Lua parse tree
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
# Test 2: mock-grammar extraction (always runs — covers function body lines)
# ---------------------------------------------------------------------------


def _make_name_node(
    name: bytes, start: tuple[int, int] = (0, 0), end: tuple[int, int] = (5, 0)
) -> MagicMock:
    """Build a mock name node whose parent is a valid function declaration node."""
    fn_node = MagicMock()
    fn_node.type = "function_declaration"
    fn_node.start_point = start
    fn_node.end_point = end
    fn_node.text = b"function " + name + b"() end"

    name_node = MagicMock()
    name_node.text = name
    name_node.parent = fn_node
    return name_node


def _make_path_node(path: bytes) -> MagicMock:
    """Build a mock path node (string_content) whose ancestor chain ends at a function_call."""
    call_node = MagicMock()
    call_node.type = "function_call"
    call_node.start_point = (0, 0)
    call_node.end_point = (0, len(path) + 10)
    call_node.text = b'require("' + path + b'")'

    string_node = MagicMock()
    string_node.parent = call_node

    path_node = MagicMock()
    path_node.text = path
    path_node.parent = string_node
    return path_node


def test_lua_extract_functions_with_mock_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_functions returns ModelFunction entries when the grammar mock yields name nodes."""
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    mock_lang = MagicMock()
    captures = [
        (_make_name_node(b"greet"), "name"),
        (_make_name_node(b"ignored"), "other"),
        (_make_name_node(b"add"), "name"),
    ]

    extractor = LuaElementExtractor()
    monkeypatch.setattr(extractor, "_get_lua_language", lambda: mock_lang)
    monkeypatch.setattr(
        "tree_sitter_analyzer.languages.lua_plugin.extractor."
        "TreeSitterQueryCompat.execute_query",
        MagicMock(return_value=captures),
    )

    mock_tree = MagicMock()
    result = extractor.extract_functions(mock_tree, "")

    assert len(result) == 2
    names = [f.name for f in result]
    assert "greet" in names
    assert "add" in names
    assert all(f.language == "lua" for f in result)


def test_lua_extract_functions_skips_none_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Name node with no parent (parent=None) must be skipped without crashing."""
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    orphan = MagicMock()
    orphan.text = b"orphan"
    orphan.parent = None

    extractor = LuaElementExtractor()
    monkeypatch.setattr(extractor, "_get_lua_language", MagicMock())
    monkeypatch.setattr(
        "tree_sitter_analyzer.languages.lua_plugin.extractor."
        "TreeSitterQueryCompat.execute_query",
        MagicMock(return_value=[(orphan, "name")]),
    )

    result = extractor.extract_functions(MagicMock(), "")
    assert result == [], "orphan name node must be silently skipped"


def test_lua_extract_functions_outer_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract_functions catches outer exception and returns empty list."""
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    extractor = LuaElementExtractor()
    monkeypatch.setattr(extractor, "_get_lua_language", MagicMock())
    monkeypatch.setattr(
        "tree_sitter_analyzer.languages.lua_plugin.extractor."
        "TreeSitterQueryCompat.execute_query",
        MagicMock(side_effect=RuntimeError("grammar broken")),
    )

    result = extractor.extract_functions(MagicMock(), "")
    assert result == []


def test_lua_extract_imports_with_mock_grammar(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract_imports returns ModelImport entries when the grammar mock yields path nodes."""
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    mock_lang = MagicMock()
    captures = [
        (_make_path_node(b"json"), "path"),
        (_make_path_node(b"ignored"), "callee"),
        (_make_path_node(b"socket.http"), "path"),
    ]

    extractor = LuaElementExtractor()
    monkeypatch.setattr(extractor, "_get_lua_language", lambda: mock_lang)
    monkeypatch.setattr(
        "tree_sitter_analyzer.languages.lua_plugin.extractor."
        "TreeSitterQueryCompat.execute_query",
        MagicMock(return_value=captures),
    )

    result = extractor.extract_imports(MagicMock(), "")

    assert len(result) == 2
    paths = [i.module_path for i in result]
    assert "json" in paths
    assert "socket.http" in paths


def test_lua_extract_imports_outer_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract_imports catches outer exception and returns empty list."""
    from tree_sitter_analyzer.languages.lua_plugin.extractor import LuaElementExtractor

    extractor = LuaElementExtractor()
    monkeypatch.setattr(extractor, "_get_lua_language", MagicMock())
    monkeypatch.setattr(
        "tree_sitter_analyzer.languages.lua_plugin.extractor."
        "TreeSitterQueryCompat.execute_query",
        MagicMock(side_effect=RuntimeError("query compile error")),
    )

    result = extractor.extract_imports(MagicMock(), "")
    assert result == []


# ---------------------------------------------------------------------------
# Test 3: real extraction (skipped unless tree_sitter_lua is installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _tslua_available(),
    reason="tree_sitter_lua not installed; tracked: optional-dep skip",
)
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
