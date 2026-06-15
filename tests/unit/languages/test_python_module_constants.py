"""Issue #639 — module-level constants visible on the structure surface.

#612 made the ast_cache walker emit kind="constant" rows for Python
module-level assignments (const-style ∪ annotated-with-value ∪ dunder,
module scope only), so ``search action=symbol`` sees them — but the
structure surface (analyze/outline/signatures) walks the PLUGIN path,
whose ``extract_variables`` only ever emitted class attributes.

These tests pin plugin-path parity: the Python plugin emits module
constants as Variable elements (``is_constant=True``) under the exact
#612 scope rule, and the structure/outline tools surface them as fields.
Fixture and negative pins mirror ``tests/unit/test_ast_extraction.py``
(TestPythonModuleConstants).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.languages.python_plugin._element_builders import (
    extract_module_constants,
)
from tree_sitter_analyzer.languages.python_plugin.extractor import (
    PythonElementExtractor,
)
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

# Mirrors _CONST_SRC in tests/unit/test_ast_extraction.py (#610/#612 rule):
# 5 module constants + 1 class attribute; logger / bare_decl / RETRIES are
# negative pins.
_SRC = """\
_STOP_WORDS = frozenset({"the"})
CONFIG: dict = {}
__version__ = "1.0"
logger = get_logger()
paths: list = []
bare_decl: int

if True:
    WRAPPED_FLAG = 1


class Settings:
    TIMEOUT = 30

    def method(self):
        RETRIES = 3
        return RETRIES
"""

_MODULE_CONSTANT_NAMES = [
    "CONFIG",
    "WRAPPED_FLAG",
    "_STOP_WORDS",
    "__version__",
    "paths",
]


def _variables() -> list:
    result = Parser().parse_code(_SRC, "python")
    assert result.success and result.tree is not None
    return PythonElementExtractor().extract_variables(result.tree, _SRC)


class TestPluginModuleConstants:
    """Plugin path: extract_variables emits module constants (#612 parity)."""

    def test_exactly_the_five_module_constants_extracted(self):
        consts = [v for v in _variables() if v.is_constant]
        assert sorted(v.name for v in consts) == _MODULE_CONSTANT_NAMES

    def test_total_variable_count_is_six(self):
        # 5 module constants + 1 class attribute (TIMEOUT).
        assert len(_variables()) == 6

    def test_class_attribute_unchanged(self):
        # TIMEOUT stays a class attribute: extracted, NOT flagged constant.
        timeout = [v for v in _variables() if v.name == "TIMEOUT"]
        assert len(timeout) == 1
        assert timeout[0].is_constant is False

    def test_function_local_not_extracted(self):
        # RETRIES lives in a function body — module-level only (#612 rule).
        assert "RETRIES" not in {v.name for v in _variables()}

    def test_lowercase_unannotated_not_extracted(self):
        # `logger = get_logger()` — mutable module state, excluded.
        assert "logger" not in {v.name for v in _variables()}

    def test_bare_annotation_not_extracted(self):
        # `bare_decl: int` has no right-hand side — not a definition site.
        assert "bare_decl" not in {v.name for v in _variables()}

    def test_constant_lines_pinned(self):
        by_name = {v.name: v for v in _variables() if v.is_constant}
        assert (by_name["_STOP_WORDS"].start_line, by_name["_STOP_WORDS"].end_line) == (
            1,
            1,
        )
        assert by_name["CONFIG"].start_line == 2
        assert by_name["__version__"].start_line == 3
        assert by_name["paths"].start_line == 5
        assert by_name["WRAPPED_FLAG"].start_line == 9

    def test_constant_types_and_visibility(self):
        by_name = {v.name: v for v in _variables() if v.is_constant}
        assert by_name["CONFIG"].variable_type == "dict"
        assert by_name["paths"].variable_type == "list"
        assert by_name["_STOP_WORDS"].variable_type is None
        assert by_name["_STOP_WORDS"].visibility == "private"
        assert by_name["__version__"].visibility == "magic"
        assert by_name["CONFIG"].visibility == "public"

    def test_variables_sorted_by_line(self):
        lines = [v.start_line for v in _variables()]
        assert lines == sorted(lines)

    def test_chained_assignment_captures_both_names(self):
        result = Parser().parse_code("A_ONE = B_TWO = 5\n", "python")
        names = sorted(
            v.name
            for v in PythonElementExtractor().extract_variables(
                result.tree, "A_ONE = B_TWO = 5\n"
            )
        )
        assert names == ["A_ONE", "B_TWO"]

    def test_none_tree_yields_no_constants(self):
        assert extract_module_constants(None, "") == []

    def test_constant_extraction_failure_degrades_to_class_attrs(self, monkeypatch):
        # The module-constant walk failing must not take down class-attribute
        # extraction (mirrors the existing degradation contract).
        import tree_sitter_analyzer.languages.python_plugin._class_extractor_mixin as mixin_mod

        def _boom(tree, source):
            raise RuntimeError("forced failure")

        monkeypatch.setattr(mixin_mod, "extract_module_constants", _boom)
        result = Parser().parse_code(_SRC, "python")
        names = [
            v.name
            for v in PythonElementExtractor().extract_variables(result.tree, _SRC)
        ]
        assert names == ["TIMEOUT"]


class TestStructureSurfaceSeesModuleConstants:
    """structure action=analyze / outline expose the constants as fields."""

    @pytest.mark.asyncio
    async def test_analyze_fields_contain_module_constants(self, tmp_path):
        test_file = tmp_path / "mod_consts.py"
        test_file.write_text(_SRC, newline="\n")
        tool = AnalyzeCodeStructureTool()
        result = await tool.execute(
            {
                "file_path": str(test_file),
                "format_type": "full",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        field_names = sorted(f["name"] for f in result["fields"])
        assert field_names == sorted([*_MODULE_CONSTANT_NAMES, "TIMEOUT"])
        assert result["metadata"]["fields_count"] == 6

    @pytest.mark.asyncio
    async def test_analyze_fields_exclude_locals_and_mutables(self, tmp_path):
        test_file = tmp_path / "mod_consts.py"
        test_file.write_text(_SRC, newline="\n")
        tool = AnalyzeCodeStructureTool()
        result = await tool.execute(
            {
                "file_path": str(test_file),
                "format_type": "full",
                "output_format": "json",
            }
        )
        field_names = {f["name"] for f in result["fields"]}
        assert "RETRIES" not in field_names
        assert "logger" not in field_names
        assert "bare_decl" not in field_names

    @pytest.mark.asyncio
    async def test_outline_field_count_includes_module_constants(self, tmp_path):
        test_file = tmp_path / "mod_consts.py"
        test_file.write_text(_SRC, newline="\n")
        tool = GetCodeOutlineTool()
        result = await tool.execute(
            {
                "file_path": str(test_file),
                "include_fields": True,
                "output_format": "json",
            }
        )
        assert result["field_count"] == 6
        # Class outline keeps exactly its own attribute — module constants
        # do not leak into the class fields list.
        (settings_cls,) = (c for c in result["classes"] if c["name"] == "Settings")
        assert [f["name"] for f in settings_cls["fields"]] == ["TIMEOUT"]


class TestOutlineTopLevelFields:
    """Codex P2 on #645: field_count included module constants but no
    rendered outline section showed them — top_level_fields closes the gap."""

    def test_outline_surfaces_module_constants(self, tmp_path):
        import asyncio

        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        p = tmp_path / "consts.py"
        p.write_text(
            "MAX_RETRIES = 3\n\n\nclass C:\n    TIMEOUT = 5\n\n    def m(self):\n        return 1\n",
            newline="\n",
        )
        tool = GetCodeOutlineTool(str(tmp_path))
        result = asyncio.run(
            tool.execute({"file_path": str(p), "output_format": "json"})
        )
        top = result["top_level_fields"]
        assert [f["name"] for f in top] == ["MAX_RETRIES"]
        cls_fields = result["classes"][0].get("fields")
        if cls_fields is not None:
            assert [f["name"] for f in cls_fields] == ["TIMEOUT"]
        assert result["field_count"] == 2
