"""Tests for tree_sitter_analyzer.languages.scala_plugin.

Covers module-level helpers, ScalaPlugin, and ScalaElementExtractor using
mocked tree-sitter nodes (tree_sitter_scala not required).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.scala_plugin import (
    ScalaElementExtractor,
    ScalaPlugin,
    _flatten_scala_elements,
    _make_scala_parser,
    _parse_scaladoc_text,
    _scala_empty_result,
    _scala_error_result,
)

# ---------------------------------------------------------------------------
# Node mock factory
# ---------------------------------------------------------------------------


def _node(
    type_: str = "identifier",
    text: str = "x",
    children: list | None = None,
    start_point: tuple = (0, 0),
    end_point: tuple = (0, 1),
    start_byte: int = 0,
    end_byte: int = 1,
    parent: Any = None,
) -> MagicMock:
    """Build a minimal mock tree-sitter node."""
    n = MagicMock()
    n.type = type_
    n.text = text.encode("utf-8")
    n.children = children if children is not None else []
    n.start_point = start_point
    n.end_point = end_point
    n.start_byte = start_byte
    n.end_byte = end_byte
    n.parent = parent
    n.child_by_field_name = MagicMock(return_value=None)
    return n


def _tree(root_children: list | None = None) -> MagicMock:
    """Build a minimal mock tree-sitter tree."""
    t = MagicMock()
    root = _node(type_="compilation_unit", children=root_children or [])
    t.root_node = root
    return t


# ---------------------------------------------------------------------------
# _parse_scaladoc_text
# ---------------------------------------------------------------------------


class TestParseScaladocText:
    def test_valid_scaladoc_single_line(self) -> None:
        text = "/** Hello world */"
        result = _parse_scaladoc_text(text)
        assert result == "Hello world"

    def test_valid_scaladoc_multiline(self) -> None:
        text = "/**\n * First line\n * Second line\n */"
        result = _parse_scaladoc_text(text)
        assert "First line" in result
        assert "Second line" in result

    def test_not_scaladoc_returns_none_for_regular_comment(self) -> None:
        assert _parse_scaladoc_text("/* regular */") is None

    def test_triple_star_returns_none(self) -> None:
        assert _parse_scaladoc_text("/*** not scaladoc */") is None

    def test_empty_content_returns_none(self) -> None:
        # /** */ has no content lines after stripping
        assert _parse_scaladoc_text("/**  */") is None

    def test_strips_leading_asterisk_per_line(self) -> None:
        text = "/**\n * @param x the input\n */"
        result = _parse_scaladoc_text(text)
        assert result is not None
        assert "@param x the input" in result

    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_scaladoc_text("") is None


# ---------------------------------------------------------------------------
# _flatten_scala_elements
# ---------------------------------------------------------------------------


class TestFlattenScalaElements:
    def test_returns_all_elements_in_canonical_order(self) -> None:
        elements = {
            "functions": ["f1", "f2"],
            "classes": ["c1"],
            "variables": [],
            "imports": ["i1"],
            "packages": ["p1"],
            "comments": [],
            "annotations": ["a1"],
        }
        flat = _flatten_scala_elements(elements)
        # Order: functions, classes, variables, imports, packages, comments, annotations
        assert flat[0] == "f1"
        assert flat[1] == "f2"
        assert flat[2] == "c1"
        assert flat[3] == "i1"
        assert "p1" in flat
        assert "a1" in flat

    def test_missing_keys_silently_skipped(self) -> None:
        flat = _flatten_scala_elements({"functions": ["f"]})
        assert flat == ["f"]

    def test_empty_dict_returns_empty(self) -> None:
        assert _flatten_scala_elements({}) == []


# ---------------------------------------------------------------------------
# _scala_empty_result / _scala_error_result
# ---------------------------------------------------------------------------


class TestScalaEmptyResult:
    def test_line_count_uses_splitlines(self) -> None:
        result = _scala_empty_result("/tmp/f.scala", "line1\nline2\n")
        assert result.line_count == 2

    def test_language_is_scala(self) -> None:
        result = _scala_empty_result("/tmp/f.scala", "")
        assert result.language == "scala"

    def test_elements_empty(self) -> None:
        result = _scala_empty_result("/tmp/f.scala", "content")
        assert result.elements == []

    def test_file_path_preserved(self) -> None:
        result = _scala_empty_result("/my/file.scala", "x")
        assert result.file_path == "/my/file.scala"


class TestScalaErrorResult:
    def test_success_false(self) -> None:
        result = _scala_error_result("/tmp/f.scala", RuntimeError("boom"))
        assert result.success is False

    def test_error_message_captured(self) -> None:
        result = _scala_error_result("/tmp/f.scala", ValueError("bad value"))
        assert "bad value" in result.error_message

    def test_line_count_zero(self) -> None:
        result = _scala_error_result("/tmp/f.scala", Exception("x"))
        assert result.line_count == 0


# ---------------------------------------------------------------------------
# _make_scala_parser
# ---------------------------------------------------------------------------


class TestMakeScalaParser:
    def test_uses_set_language_when_available(self) -> None:
        lang = MagicMock()
        parser = MagicMock()
        parser.set_language = MagicMock()
        with patch("tree_sitter.Parser", return_value=parser):
            result = _make_scala_parser(lang)
        parser.set_language.assert_called_once_with(lang)
        assert result is parser

    def test_uses_language_property_when_no_set_language(self) -> None:
        lang = MagicMock()
        parser = MagicMock(spec=[])  # no set_language, but has language attr
        # Add language attribute via spec workaround
        parser.language = None
        with patch("tree_sitter.Parser", return_value=parser):
            result = _make_scala_parser(lang)
        assert result is parser
        assert parser.language == lang

    def test_falls_back_to_constructor_when_neither_attr(self) -> None:
        lang = MagicMock()
        parser_no_attrs = MagicMock(spec=[])  # neither set_language nor language

        new_parser = MagicMock()
        with patch("tree_sitter.Parser") as mock_cls:
            mock_cls.return_value = parser_no_attrs
            mock_cls.side_effect = [parser_no_attrs, new_parser]
            result = _make_scala_parser(lang)
        # The second call is Parser(language) fallback
        assert result is new_parser


# ---------------------------------------------------------------------------
# ScalaPlugin
# ---------------------------------------------------------------------------


class TestScalaPlugin:
    @pytest.fixture
    def plugin(self) -> ScalaPlugin:
        return ScalaPlugin()

    def test_count_tree_nodes_none(self, plugin: ScalaPlugin) -> None:
        assert plugin._count_tree_nodes(None) == 0

    def test_count_tree_nodes_single(self, plugin: ScalaPlugin) -> None:
        node = MagicMock()
        node.children = []
        assert plugin._count_tree_nodes(node) == 1

    def test_count_tree_nodes_nested(self, plugin: ScalaPlugin) -> None:
        child1 = MagicMock()
        child1.children = []
        child2 = MagicMock()
        child2.children = []
        root = MagicMock()
        root.children = [child1, child2]
        assert plugin._count_tree_nodes(root) == 3

    def test_get_tree_sitter_language_import_error(self, plugin: ScalaPlugin) -> None:
        with patch.dict("sys.modules", {"tree_sitter_scala": None}):
            result = plugin.get_tree_sitter_language()
        assert result is None

    def test_get_tree_sitter_language_cached(self, plugin: ScalaPlugin) -> None:
        fake_lang = MagicMock()
        plugin._cached_language = fake_lang
        assert plugin.get_tree_sitter_language() is fake_lang

    def test_extract_elements_none_tree(self, plugin: ScalaPlugin) -> None:
        result = plugin.extract_elements(None, "")
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["imports"] == []

    def test_extract_elements_exception_returns_empty(
        self, plugin: ScalaPlugin
    ) -> None:
        mock_extractor = MagicMock()
        mock_extractor.extract_functions.side_effect = RuntimeError("boom")
        with patch.object(plugin, "create_extractor", return_value=mock_extractor):
            result = plugin.extract_elements(_tree(), "")
        assert result["functions"] == []

    def test_extract_elements_with_mock_extractor(self, plugin: ScalaPlugin) -> None:
        mock_extractor = MagicMock()
        mock_extractor.extract_functions.return_value = []
        mock_extractor.extract_classes.return_value = []
        mock_extractor.extract_variables.return_value = []
        mock_extractor.extract_imports.return_value = []
        mock_extractor.extract_packages.return_value = []
        mock_extractor.extract_comments.return_value = []
        mock_extractor.extract_annotations.return_value = []
        with patch.object(plugin, "create_extractor", return_value=mock_extractor):
            result = plugin.extract_elements(_tree(), "some code")
        assert "functions" in result

    def test_scala_analysis_result_builds_result(self, plugin: ScalaPlugin) -> None:
        tree = MagicMock()
        tree.root_node = MagicMock()
        tree.root_node.children = []
        elements_dict = {
            k: []
            for k in (
                "functions",
                "classes",
                "variables",
                "imports",
                "packages",
                "comments",
                "annotations",
            )
        }
        with patch.object(plugin, "_count_tree_nodes", return_value=42):
            result = plugin._scala_analysis_result(
                "/f.scala", "line1\nline2", tree, elements_dict
            )
        assert result.language == "scala"
        assert result.line_count == 2
        assert result.file_path == "/f.scala"

    def test_scala_analysis_result_with_package(self, plugin: ScalaPlugin) -> None:
        tree = MagicMock()
        tree.root_node = MagicMock()
        tree.root_node.children = []
        fake_pkg = MagicMock()
        elements_dict = {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "packages": [fake_pkg],
            "comments": [],
            "annotations": [],
        }
        with patch.object(plugin, "_count_tree_nodes", return_value=0):
            result = plugin._scala_analysis_result("/f.scala", "", tree, elements_dict)
        assert result.package is fake_pkg

    @pytest.mark.asyncio
    async def test_analyze_file_returns_empty_when_no_language(
        self, plugin: ScalaPlugin, tmp_path: Any
    ) -> None:
        f = tmp_path / "Hello.scala"
        f.write_text("object Hello { def main() = {} }")
        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            result = await plugin.analyze_file(str(f), MagicMock())
        assert result.language == "scala"
        assert result.elements == []

    @pytest.mark.asyncio
    async def test_analyze_file_returns_error_on_read_failure(
        self, plugin: ScalaPlugin
    ) -> None:
        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe",
            side_effect=OSError("no such file"),
        ):
            result = await plugin.analyze_file("/no/such/file.scala", MagicMock())
        assert result.success is False
        assert "no such file" in result.error_message


# ---------------------------------------------------------------------------
# ScalaElementExtractor helpers
# ---------------------------------------------------------------------------


class TestScalaElementExtractorInit:
    def test_initial_state(self) -> None:
        e = ScalaElementExtractor()
        assert e.current_package == ""
        assert e.current_file == ""
        assert e.source_code == ""
        assert e.content_lines == []
        assert e._node_text_cache == {}

    def test_reset_caches_clears_cache(self) -> None:
        e = ScalaElementExtractor()
        e._node_text_cache[(0, 5)] = "hello"
        e.source_code = "hello"
        e._reset_caches()
        assert e._node_text_cache == {}

    def test_reset_caches_clears_package_when_no_source(self) -> None:
        e = ScalaElementExtractor()
        e.current_package = "com.example"
        e.source_code = ""
        e._reset_caches()
        assert e.current_package == ""

    def test_reset_caches_preserves_package_when_has_source(self) -> None:
        e = ScalaElementExtractor()
        e.current_package = "com.example"
        e.source_code = "object X {}"
        e._reset_caches()
        assert e.current_package == "com.example"


class TestGetNodeText:
    def test_returns_cached_value(self) -> None:
        e = ScalaElementExtractor()
        e._node_text_cache[(0, 5)] = "cached"
        node = _node(start_byte=0, end_byte=5)
        assert e._get_node_text(node) == "cached"

    def test_extracts_text_from_source(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["hello world"]
        node = _node(start_byte=0, end_byte=5)
        text = e._get_node_text(node)
        assert text == "hello"

    def test_returns_empty_on_exception(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []  # will cause index/slice issues
        node = MagicMock()
        node.start_byte = 0
        node.end_byte = 5
        node.start_byte = 0
        node.end_byte = 5
        # Force an exception in safe_encode by making content_lines raise
        with patch(
            "tree_sitter_analyzer.languages.scala_plugin.safe_encode",
            side_effect=RuntimeError("enc err"),
        ):
            result = e._get_node_text(node)
        assert result == ""


class TestTraverseAndExtract:
    def test_empty_tree_produces_no_results(self) -> None:
        e = ScalaElementExtractor()
        root = _node(type_="root", children=[])
        results: list = []
        e._traverse_and_extract(root, {}, results)
        assert results == []

    def test_matching_node_calls_extractor(self) -> None:
        e = ScalaElementExtractor()
        func_node = _node(type_="function_definition", children=[])
        root = _node(type_="root", children=[func_node])
        mock_fn = MagicMock(return_value=MagicMock())
        results: list = []
        e._traverse_and_extract(root, {"function_definition": mock_fn}, results)
        mock_fn.assert_called_once_with(func_node)
        assert len(results) == 1

    def test_extractor_returning_none_not_appended(self) -> None:
        e = ScalaElementExtractor()
        func_node = _node(type_="function_definition", children=[])
        root = _node(type_="root", children=[func_node])
        results: list = []
        e._traverse_and_extract(root, {"function_definition": lambda n: None}, results)
        assert results == []

    def test_nested_nodes_traversed(self) -> None:
        e = ScalaElementExtractor()
        inner = _node(type_="target_node", children=[])
        outer = _node(type_="wrapper", children=[inner])
        root = _node(type_="root", children=[outer])
        found = []
        e._traverse_and_extract(root, {"target_node": lambda n: "found"}, found)
        assert "found" in found


class TestScalaFunctionName:
    def test_uses_name_field_when_present(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["def myFunc"]
        name_node = _node(type_="identifier", start_byte=4, end_byte=10)
        func_node = _node(type_="function_definition")
        func_node.child_by_field_name = MagicMock(return_value=name_node)
        result = e._scala_function_name(func_node)
        assert result == "myFunc"

    def test_falls_back_to_identifier_child(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["def myFunc"]
        id_node = _node(type_="identifier", start_byte=4, end_byte=10)
        func_node = _node(type_="function_definition", children=[id_node])
        func_node.child_by_field_name = MagicMock(return_value=None)
        result = e._scala_function_name(func_node)
        assert result == "myFunc"

    def test_returns_anonymous_when_no_name(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        func_node = _node(type_="function_definition", children=[])
        func_node.child_by_field_name = MagicMock(return_value=None)
        result = e._scala_function_name(func_node)
        assert result == "anonymous"


class TestScalaClassLikeName:
    def test_uses_name_field_when_present(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["class MyClass"]
        name_node = _node(type_="type_identifier", start_byte=6, end_byte=13)
        cls_node = _node(type_="class_definition")
        cls_node.child_by_field_name = MagicMock(return_value=name_node)
        result = e._scala_class_like_name(cls_node)
        assert result == "MyClass"

    def test_falls_back_to_type_identifier_child(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["class MyClass"]
        type_id = _node(type_="type_identifier", start_byte=6, end_byte=13)
        cls_node = _node(type_="class_definition", children=[type_id])
        cls_node.child_by_field_name = MagicMock(return_value=None)
        assert e._scala_class_like_name(cls_node) == "MyClass"

    def test_returns_anonymous_when_no_name(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        cls_node = _node(type_="class_definition", children=[])
        cls_node.child_by_field_name = MagicMock(return_value=None)
        assert e._scala_class_like_name(cls_node) == "anonymous"


class TestScalaTypeAfterColon:
    def test_returns_type_after_colon(self) -> None:
        e = ScalaElementExtractor()
        # "val x: Int" → 'I'=7, 'n'=8, 't'=9 → bytes [7, 10)
        e.content_lines = ["val x: Int"]
        colon = _node(type_=":", start_byte=5, end_byte=6)
        type_node = _node(type_="type_identifier", start_byte=7, end_byte=10)
        node = _node(type_="val_definition", children=[colon, type_node])
        result = e._scala_type_after_colon(node, "Inferred")
        assert result == "Int"

    def test_returns_default_when_no_colon(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        node = _node(type_="val_definition", children=[])
        assert e._scala_type_after_colon(node, "Inferred") == "Inferred"

    def test_returns_default_when_colon_is_last_child(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        colon = _node(type_=":")
        node = _node(type_="val_definition", children=[colon])
        assert e._scala_type_after_colon(node, "Unit") == "Unit"


class TestScalaVisibility:
    def test_private_visibility(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["private"]
        mods = _node(type_="modifiers", start_byte=0, end_byte=7)
        node = _node(type_="function_definition", children=[mods])
        assert e._scala_visibility(node) == "private"

    def test_protected_visibility(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["protected"]
        mods = _node(type_="modifiers", start_byte=0, end_byte=9)
        node = _node(type_="function_definition", children=[mods])
        assert e._scala_visibility(node) == "protected"

    def test_public_by_default(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        node = _node(type_="function_definition", children=[])
        assert e._scala_visibility(node) == "public"

    def test_public_when_modifiers_has_no_keyword(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["override"]
        mods = _node(type_="modifiers", start_byte=0, end_byte=8)
        node = _node(type_="function_definition", children=[mods])
        assert e._scala_visibility(node) == "public"


class TestExtractParameters:
    def test_empty_param_node(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        node = _node(type_="parameters", children=[])
        assert e._extract_parameters(node) == []

    def test_parameter_with_name_and_type(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["(x: Int)"]
        id_node = _node(type_="identifier", start_byte=1, end_byte=2)
        type_node = _node(type_="type_identifier", start_byte=4, end_byte=7)
        param = _node(type_="parameter", children=[id_node, type_node])
        node = _node(type_="parameters", children=[param])
        result = e._extract_parameters(node)
        assert len(result) == 1
        assert "x" in result[0]
        assert "Int" in result[0]


class TestExtractFunctionsWithEmptyTree:
    def test_returns_empty_when_no_function_nodes(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        result = e.extract_functions(tree, "object X {}")
        assert result == []

    def test_returns_empty_when_non_function_nodes(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([_node(type_="class_definition")])
        result = e.extract_functions(tree, "class X {}")
        assert result == []


class TestExtractClassesWithEmptyTree:
    def test_returns_empty_for_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_classes(tree, "") == []


class TestExtractVariablesWithEmptyTree:
    def test_returns_empty_for_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_variables(tree, "") == []


class TestExtractImportsWithEmptyTree:
    def test_returns_empty_for_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_imports(tree, "") == []


class TestExtractPackagesWithEmptyTree:
    def test_returns_empty_for_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_packages(tree, "") == []


class TestExtractCommentsAnnotations:
    def test_comments_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_comments(tree, "") == []

    def test_annotations_empty_tree(self) -> None:
        e = ScalaElementExtractor()
        tree = _tree([])
        assert e.extract_annotations(tree, "") == []


class TestScalaPackageNameFromClause:
    def test_finds_package_identifier(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["com.example"]
        pkg_id = _node(type_="package_identifier", start_byte=0, end_byte=11)
        clause = _node(type_="package_clause", children=[pkg_id])
        result = e._scala_package_name_from_clause(clause)
        assert result == "com.example"

    def test_finds_plain_identifier(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = ["example"]
        id_node = _node(type_="identifier", start_byte=0, end_byte=7)
        clause = _node(type_="package_clause", children=[id_node])
        result = e._scala_package_name_from_clause(clause)
        assert result == "example"

    def test_returns_none_when_no_identifier(self) -> None:
        e = ScalaElementExtractor()
        e.content_lines = []
        clause = _node(type_="package_clause", children=[_node(type_="package")])
        assert e._scala_package_name_from_clause(clause) is None


class TestLastNearbyBlockComment:
    def test_returns_none_when_no_parent(self) -> None:
        e = ScalaElementExtractor()
        node = _node(parent=None)
        assert e._last_nearby_block_comment(node) is None

    def test_returns_none_when_no_block_comment(self) -> None:
        e = ScalaElementExtractor()
        parent = _node(type_="root")
        child = _node(type_="function_definition", parent=parent)
        parent.children = [child]
        assert e._last_nearby_block_comment(child) is None

    def test_returns_close_block_comment(self) -> None:
        e = ScalaElementExtractor()
        parent = _node(type_="root")
        comment = _node(
            type_="block_comment",
            start_point=(0, 0),
            end_point=(0, 10),
            parent=parent,
        )
        func = _node(
            type_="function_definition",
            start_point=(1, 0),
            end_point=(3, 0),
            parent=parent,
        )
        parent.children = [comment, func]
        result = e._last_nearby_block_comment(func)
        assert result is comment
