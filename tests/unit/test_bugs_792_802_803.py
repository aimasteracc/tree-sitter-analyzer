"""
RED tests for bugs #792, #802, #803.

#792 — Python: parent function inherits nested function's return_type.
#802 — class_tree mode=supers/parents/subs aliases not recognized.
#803 — 'Unknown mode' errors classified as 'internal' not 'validation',
        and the error message doesn't enumerate valid modes.
"""

from __future__ import annotations

import pytest
import tree_sitter

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_python(code: str):
    """Parse Python source with tree-sitter and return the tree."""
    plugin = PythonPlugin()
    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


def _stub_tool(tmp_path) -> ClassHierarchyTool:
    """Build a ClassHierarchyTool with a minimal stub hierarchy."""
    from tree_sitter_analyzer.class_hierarchy import ClassHierarchy, ClassInfo

    tool = ClassHierarchyTool(str(tmp_path))

    hierarchy = ClassHierarchy(cache=None)
    for name, parents in {"Child": ["Parent"], "Parent": []}.items():
        hierarchy._classes[name].append(
            ClassInfo(
                name=name,
                file="m.py",
                line=1,
                end_line=2,
                language="python",
                parents=parents,
            )
        )
        for p in parents:
            hierarchy._parent_map[name].append(p)
            hierarchy._children[p].append(name)
    hierarchy._built = True
    tool._hierarchy = hierarchy
    return tool


# ---------------------------------------------------------------------------
# Bug #792 — nested function's return_type must NOT bleed to parent
# ---------------------------------------------------------------------------


class TestNestedFunctionReturnTypeBleed:
    """#792: outer() has no annotation; inner() -> str must not bleed."""

    SOURCE = """\
def outer(x):
    def inner(y) -> str:
        return str(y)
    return inner(x)
"""

    def test_outer_does_not_inherit_inner_return_type(self):
        """outer() has no annotation — its return_type must NOT be 'str'
        (inherited from inner).  The builder defaults unannotated functions to
        'Any', so the expected value is 'Any' not 'str'."""
        extractor = PythonElementExtractor()
        tree = _parse_python(self.SOURCE)
        functions = extractor.extract_functions(tree, self.SOURCE)
        outer_funcs = [f for f in functions if f.name == "outer"]
        assert len(outer_funcs) == 1, f"Expected 1 outer function, got {outer_funcs}"
        outer_return = outer_funcs[0].return_type
        assert outer_return != "str", (
            f"outer.return_type must NOT be 'str' (inherited from inner), got {outer_return!r}"
        )
        # The builder converts None -> 'Any' for unannotated Python functions.
        assert outer_return == "Any", (
            f"outer.return_type should be 'Any' (unannotated), got {outer_return!r}"
        )

    def test_inner_return_type_is_preserved(self):
        """Inner function's own annotation must still be captured correctly."""
        extractor = PythonElementExtractor()
        tree = _parse_python(self.SOURCE)
        functions = extractor.extract_functions(tree, self.SOURCE)
        inner_funcs = [f for f in functions if f.name == "inner"]
        assert len(inner_funcs) == 1, f"Expected 1 inner function, got {inner_funcs}"
        assert inner_funcs[0].return_type == "str", (
            f"inner.return_type should be 'str', got {inner_funcs[0].return_type!r}"
        )


# ---------------------------------------------------------------------------
# Bug #802 — mode aliases: supers, parents, subs
# ---------------------------------------------------------------------------


class TestClassTreeModeAliases:
    """#802: mode=supers/parents must be treated as mode=superclasses;
    mode=subs must be treated as mode=subclasses."""

    @pytest.mark.asyncio
    async def test_mode_supers_is_alias_for_superclasses(self, tmp_path):
        tool = _stub_tool(tmp_path)
        result = await tool.execute(
            {"mode": "supers", "class_name": "Child", "output_format": "json"}
        )
        assert result.get("success") is True, f"Expected success, got: {result}"
        assert result.get("mode") == "superclasses", (
            f"mode should be 'superclasses', got {result.get('mode')!r}"
        )

    @pytest.mark.asyncio
    async def test_mode_parents_is_alias_for_superclasses(self, tmp_path):
        tool = _stub_tool(tmp_path)
        result = await tool.execute(
            {"mode": "parents", "class_name": "Child", "output_format": "json"}
        )
        assert result.get("success") is True, f"Expected success, got: {result}"
        assert result.get("mode") == "superclasses", (
            f"mode should be 'superclasses', got {result.get('mode')!r}"
        )

    @pytest.mark.asyncio
    async def test_mode_subs_is_alias_for_subclasses(self, tmp_path):
        tool = _stub_tool(tmp_path)
        result = await tool.execute(
            {"mode": "subs", "class_name": "Parent", "output_format": "json"}
        )
        assert result.get("success") is True, f"Expected success, got: {result}"
        assert result.get("mode") == "subclasses", (
            f"mode should be 'subclasses', got {result.get('mode')!r}"
        )


# ---------------------------------------------------------------------------
# Bug #803 — unknown mode error must be validation, list valid modes
# ---------------------------------------------------------------------------


class TestClassTreeUnknownModeValidation:
    """#803: unknown mode returns error with error_type='validation' and
    a message that enumerates valid modes."""

    @pytest.mark.asyncio
    async def test_unknown_mode_error_lists_valid_modes(self, tmp_path):
        tool = _stub_tool(tmp_path)
        result = await tool.execute(
            {"mode": "bogus_mode", "class_name": "Child", "output_format": "json"}
        )
        assert result.get("success") is False, f"Expected failure, got: {result}"
        error_msg = result.get("error", "")
        assert "Valid modes" in error_msg, (
            f"Error message should list valid modes, got: {error_msg!r}"
        )

    @pytest.mark.asyncio
    async def test_unknown_mode_error_type_is_validation(self, tmp_path):
        tool = _stub_tool(tmp_path)
        result = await tool.execute(
            {"mode": "bogus_mode", "class_name": "Child", "output_format": "json"}
        )
        assert result.get("success") is False
        error_type = result.get("error_type", "")
        assert error_type == "validation", (
            f"error_type should be 'validation', got {error_type!r}"
        )
