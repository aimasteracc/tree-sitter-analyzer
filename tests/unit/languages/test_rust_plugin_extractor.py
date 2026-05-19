"""
Comprehensive tests for RustElementExtractor.

Covers unit-level extractor tests with mocked nodes
and additional coverage boost tests for uncovered branches.
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor, RustPlugin
from tree_sitter_analyzer.models import Import, Variable


@pytest.fixture
def rust_plugin():
    return RustPlugin()


@pytest.fixture
def rust_extractor():
    return RustElementExtractor()


# ---------------------------------------------------------------------------
# Mock node helpers
# ---------------------------------------------------------------------------


def _mock_node(
    type_name,
    start_byte=0,
    end_byte=50,
    start_point=(0, 0),
    end_point=(0, 10),
    children=None,
    text="mock",
    field_children=None,
):
    """Create a mock tree-sitter Node."""
    node = MagicMock()
    node.type = type_name
    node.start_byte = start_byte
    node.end_byte = end_byte
    node.start_point = start_point
    node.end_point = end_point
    node.children = children or []
    node.child_by_field_name = MagicMock(
        side_effect=lambda name: field_children.get(name) if field_children else None
    )
    node.text = text.encode("utf-8") if isinstance(text, str) else text
    return node


# ---------------------------------------------------------------------------
# Unit tests for RustElementExtractor with mocked nodes
# ---------------------------------------------------------------------------


class TestRustElementExtractorUnit:
    """Unit-level tests using mocked tree-sitter nodes."""

    def test_extract_import_success(self, rust_extractor):
        node = _mock_node(
            "use_declaration",
            text="use std::collections::HashMap;",
            start_point=(0, 0),
            end_point=(0, 29),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            return_value="use std::collections::HashMap;",
        ):
            result = rust_extractor._extract_import(node)
            assert result is not None
            assert isinstance(result, Import)
            assert "std::collections::HashMap" in result.name

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_import_error(self, mock_log, rust_extractor):
        node = _mock_node("use_declaration")
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_import(node)
            assert result is None
            mock_log.assert_called()

    def test_reset_caches_clears_when_no_source(self, rust_extractor):
        rust_extractor.modules = [{"name": "test"}]
        rust_extractor.impl_blocks = [{"type": "impl"}]
        rust_extractor.source_code = ""
        rust_extractor._reset_caches()
        assert rust_extractor.modules == []
        assert rust_extractor.impl_blocks == []

    def test_extract_enum(self, rust_extractor):
        node = _mock_node("enum_item")
        with patch.object(
            rust_extractor,
            "_extract_type_def",
            return_value=MagicMock(name="MyEnum", start_line=1, end_line=3),
        ):
            from tree_sitter_analyzer.models import Class

            with patch.object(
                rust_extractor,
                "_extract_type_def",
                return_value=Class(name="MyEnum", start_line=1, end_line=3),
            ):
                result = rust_extractor._extract_enum(node)
                assert result is not None
                assert result.name == "MyEnum"

    def test_extract_trait(self, rust_extractor):
        node = _mock_node("trait_item")
        with patch.object(
            rust_extractor,
            "_extract_type_def",
            return_value=MagicMock(name="MyTrait", start_line=1, end_line=3),
        ):
            from tree_sitter_analyzer.models import Class

            with patch.object(
                rust_extractor,
                "_extract_type_def",
                return_value=Class(name="MyTrait", start_line=1, end_line=3),
            ):
                result = rust_extractor._extract_trait(node)
                assert result is not None
                assert result.name == "MyTrait"

    def test_extract_type_def_no_name(self, rust_extractor):
        node = _mock_node("struct_item", field_children={})
        result = rust_extractor._extract_type_def(node, "struct")
        assert result is None

    def test_extract_type_def_with_derives(self, rust_extractor):
        name_node = _mock_node("identifier", text="MyStruct")
        node = _mock_node(
            "struct_item",
            text="pub struct MyStruct",
            field_children={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="pub"
            ):
                with patch.object(
                    rust_extractor, "_extract_derives", return_value=["Debug", "Clone"]
                ):
                    result = rust_extractor._extract_type_def(node, "struct")
                    assert result is not None
                    assert result.name == "MyStruct"
                    assert "Debug" in result.implements_interfaces
                    assert "Clone" in result.implements_interfaces

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_type_def_error(self, mock_log, rust_extractor):
        # Need a node WITH a name so we enter the try body before error triggers
        name_node = _mock_node("identifier", text="BadStruct")
        node = _mock_node(
            "struct_item",
            field_children={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_type_def(node, "struct")
            assert result is None
            mock_log.assert_called()

    def test_extract_impl_success(self, rust_extractor):
        type_node = _mock_node("type_identifier", text="Foo")
        node = _mock_node(
            "impl_item",
            text="impl Foo {}",
            field_children={"type": type_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            result = rust_extractor._extract_impl(node)
            assert result is None  # _extract_impl returns None (void)
            assert len(rust_extractor.impl_blocks) == 1
            assert rust_extractor.impl_blocks[0]["type"] == "Foo"

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_impl_error(self, mock_log, rust_extractor):
        type_node = _mock_node("type_identifier", text="BadImpl")
        node = _mock_node(
            "impl_item",
            field_children={"type": type_node},
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_impl(node)
            assert result is None
            mock_log.assert_called()

    def test_extract_field_no_name_or_type(self, rust_extractor):
        node = _mock_node("field_declaration", field_children={})
        result = rust_extractor._extract_field(node)
        assert result is None

    def test_extract_field_success(self, rust_extractor):
        name_node = _mock_node("identifier", text="field_name")
        type_node = _mock_node("type_identifier", text="i32")
        node = _mock_node(
            "field_declaration",
            field_children={"name": name_node, "type": type_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="pub"
            ):
                result = rust_extractor._extract_field(node)
                assert result is not None
                assert isinstance(result, Variable)
                assert result.name == "field_name"
                assert result.variable_type == "i32"

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_field_error(self, mock_log, rust_extractor):
        # Need name and type nodes to enter try body
        name_node = _mock_node("identifier", text="bad_field")
        type_node = _mock_node("type_identifier", text="i32")
        node = _mock_node(
            "field_declaration",
            field_children={"name": name_node, "type": type_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_field(node)
            assert result is None
            mock_log.assert_called()

    def test_extract_docstring_line_comment(self, rust_extractor):
        comment = _mock_node("line_comment", text="/// A doc comment")
        node = _mock_node("function_item", children=[comment])
        with patch.object(
            rust_extractor, "_get_node_text", return_value="/// A doc comment"
        ):
            result = rust_extractor._extract_docstring(node)
            assert result is not None
            assert "A doc comment" in result

    def test_extract_docstring_block_comment(self, rust_extractor):
        comment = _mock_node("block_comment", text="/** Block doc */")
        node = _mock_node("function_item", children=[comment])
        with patch.object(
            rust_extractor, "_get_node_text", return_value="/** Block doc */"
        ):
            result = rust_extractor._extract_docstring(node)
            assert result is not None
            assert "Block doc" in result

    def test_extract_docstring_empty(self, rust_extractor):
        node = _mock_node("function_item", children=[])
        result = rust_extractor._extract_docstring(node)
        assert result is None

    def test_extract_derives_found(self, rust_extractor):
        attr = _mock_node("attribute_item", text="#[derive(Debug, Clone, Copy)]")
        node = _mock_node("struct_item", children=[attr])
        with patch.object(
            rust_extractor,
            "_get_node_text",
            return_value="#[derive(Debug, Clone, Copy)]",
        ):
            result = rust_extractor._extract_derives(node)
            assert "Debug" in result
            assert "Clone" in result
            assert "Copy" in result

    def test_extract_derives_none(self, rust_extractor):
        node = _mock_node("struct_item", children=[])
        result = rust_extractor._extract_derives(node)
        assert result == []

    def test_get_node_text_cache_hit(self, rust_extractor):
        node = _mock_node("identifier", start_byte=0, end_byte=10, text="cached")
        rust_extractor._node_text_cache[(0, 10)] = "cached_value"
        result = rust_extractor._get_node_text(node)
        assert result == "cached_value"

    def test_get_node_text_error(self, rust_extractor):
        node = _mock_node("identifier", start_byte=0, end_byte=10)
        with patch(
            "tree_sitter_analyzer.languages.rust_plugin.extract_text_slice",
            side_effect=Exception("bad encoding"),
        ):
            result = rust_extractor._get_node_text(node)
            assert result == ""

    def test_extract_function_no_name(self, rust_extractor):
        node = _mock_node("function_item", field_children={})
        result = rust_extractor._extract_function(node)
        assert result is None

    def test_extract_function_async_detection(self, rust_extractor):
        name_node = _mock_node("identifier", text="my_async_fn")
        async_node = _mock_node("async", text="async")
        node = _mock_node(
            "function_item",
            field_children={"name": name_node},
            children=[async_node],
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="pub"
            ):
                result = rust_extractor._extract_function(node)
                assert result is not None
                assert result.name == "my_async_fn"
                assert result.is_async is True

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_function_error(self, mock_log, rust_extractor):
        # Need a name node to enter try body
        name_node = _mock_node("identifier", text="bad_fn")
        node = _mock_node(
            "function_item",
            field_children={"name": name_node},
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_function(node)
            assert result is None
            mock_log.assert_called()

    def test_extract_visibility_with_modifier(self, rust_extractor):
        vis_mod = _mock_node("visibility_modifier", text="pub")
        node = _mock_node("function_item", children=[vis_mod])
        with patch.object(rust_extractor, "_get_node_text", return_value="pub"):
            result = rust_extractor._extract_visibility(node)
            assert result == "pub"

    def test_extract_visibility_private_default(self, rust_extractor):
        node = _mock_node("function_item", children=[])
        result = rust_extractor._extract_visibility(node)
        assert result == "private"


# ---------------------------------------------------------------------------
# Additional coverage tests for uncovered lines
# ---------------------------------------------------------------------------


class TestRustExtractorCoverageBoost:
    """Tests targeting uncovered branches in rust_plugin.py."""

    def test_extract_import_body(self, rust_extractor):
        """Cover lines 142-145, 153: import extraction happy path."""
        node = _mock_node(
            "use_declaration",
            start_byte=0,
            end_byte=30,
            start_point=(0, 0),
            end_point=(0, 30),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            return_value="use std::collections::HashMap;",
        ):
            result = rust_extractor._extract_import(node)
            assert result is not None
            assert isinstance(result, Import)
            assert result.start_line == 1
            assert result.end_line == 1

    def test_extract_import_exception_path(self, rust_extractor):
        """Cover lines 161-163: import extraction error catch."""
        node = _mock_node("use_declaration", start_byte=0, end_byte=10)
        rust_extractor.source_code = "code"
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=ValueError("bad")
        ):
            result = rust_extractor._extract_import(node)
            assert result is None

    def test_reset_caches_preserves_modules_with_source(self, rust_extractor):
        """Cover line 173-174: modules/impls NOT cleared when source_code set."""
        rust_extractor.modules = [{"name": "test_mod"}]
        rust_extractor.impl_blocks = [{"type": "TestImpl"}]
        rust_extractor.source_code = "fn main() {}"
        rust_extractor._reset_caches()
        assert rust_extractor.modules == [{"name": "test_mod"}]
        assert rust_extractor.impl_blocks == [{"type": "TestImpl"}]

    def test_extract_module_error(self, rust_extractor):
        """Cover lines 217-218: module extraction error."""
        node = _mock_node("mod_item")
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("fail")
        ):
            rust_extractor._extract_module(node)
            assert len(rust_extractor.modules) == 0

    def test_extract_function_async_direct_child(self, rust_extractor):
        """Cover lines 266-267: async detected as direct child."""
        name_node = _mock_node("identifier", text="my_fn")
        params_node = _mock_node("parameters", text="()")
        ret_node = _mock_node("return_type", text="-> i32")
        async_child = _mock_node("async", text="async")
        node = _mock_node(
            "function_item",
            field_children={
                "name": name_node,
                "parameters": params_node,
                "return_type": ret_node,
            },
            children=[async_child],
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="private"
            ):
                with patch.object(
                    rust_extractor, "_extract_docstring", return_value=None
                ):
                    result = rust_extractor._extract_function(node)
                    assert result is not None
                    assert result.is_async is True

    def test_extract_struct_with_derives(self, rust_extractor):
        """Cover line 341: derives set on class."""
        name_node = _mock_node("identifier", text="MyStruct")
        attr_node = _mock_node("attribute_item", text="#[derive(Debug, Clone)]")
        node = _mock_node(
            "struct_item",
            field_children={"name": name_node},
            children=[attr_node],
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="pub"
            ):
                with patch.object(
                    rust_extractor, "_extract_derives", return_value=["Debug", "Clone"]
                ):
                    result = rust_extractor._extract_type_def(node, "struct")
                    assert result is not None
                    assert result.implements_interfaces == ["Debug", "Clone"]

    def test_extract_type_def_error_path(self, rust_extractor):
        """Cover lines 345-347: type_def error handling."""
        name_node = _mock_node("identifier", text="BadType")
        node = _mock_node(
            "enum_item",
            field_children={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("boom")
        ):
            result = rust_extractor._extract_type_def(node, "enum")
            assert result is None

    def test_extract_impl_error_path(self, rust_extractor):
        """Cover lines 369-370: impl extraction error."""
        type_node = _mock_node("type_identifier", text="Foo")
        node = _mock_node(
            "impl_item",
            field_children={"type": type_node},
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("fail")
        ):
            rust_extractor._extract_impl(node)
            assert len(rust_extractor.impl_blocks) == 0

    def test_extract_field_missing_type(self, rust_extractor):
        """Cover line 379: field with missing type node."""
        name_node = _mock_node("identifier", text="field1")
        node = _mock_node(
            "field_declaration",
            field_children={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(rust_extractor, "_get_node_text", return_value="field1"):
            result = rust_extractor._extract_field(node)
            assert result is None

    def test_extract_field_error_path(self, rust_extractor):
        """Cover lines 400-402: field extraction error."""
        name_node = _mock_node("identifier", text="f")
        type_node = _mock_node("type_identifier", text="i32")
        node = _mock_node(
            "field_declaration",
            field_children={"name": name_node, "type": type_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(
            rust_extractor, "_get_node_text", side_effect=RuntimeError("err")
        ):
            result = rust_extractor._extract_field(node)
            assert result is None

    def test_extract_docstring_multiple_line_comments(self, rust_extractor):
        """Cover lines 425, 435: docstring with multiple line comments joined."""
        c1 = _mock_node("line_comment", text="/// Line one")
        c2 = _mock_node("line_comment", text="/// Line two")
        node = _mock_node("function_item", children=[c1, c2])
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=[
                "/// Line one",
                "/// Line one",
                "/// Line two",
                "/// Line two",
            ],
        ):
            result = rust_extractor._extract_docstring(node)
            assert result is not None
            assert "Line one" in result
            assert "Line two" in result

    def test_extract_docstring_block_comment_with_markers(self, rust_extractor):
        """Cover lines 429, 431-432: block doc comment parsing."""
        c = _mock_node("block_comment", text="/** My doc */")
        node = _mock_node("function_item", children=[c])
        with patch.object(
            rust_extractor, "_get_node_text", return_value="/** My doc */"
        ):
            result = rust_extractor._extract_docstring(node)
            assert result is not None
            assert "My doc" in result

    def test_extract_derives_with_attribute(self, rust_extractor):
        """Cover lines 450-456: derives from attribute_item."""
        attr = _mock_node("attribute_item", text="#[derive(Serialize, Deserialize)]")
        node = _mock_node("struct_item", children=[attr])
        with patch.object(
            rust_extractor,
            "_get_node_text",
            return_value="#[derive(Serialize, Deserialize)]",
        ):
            result = rust_extractor._extract_derives(node)
            assert "Serialize" in result
            assert "Deserialize" in result

    def test_extract_derives_attribute_no_derive(self, rust_extractor):
        """Cover line 451: attribute without derive."""
        attr = _mock_node("attribute_item", text="#[allow(dead_code)]")
        node = _mock_node("struct_item", children=[attr])
        with patch.object(
            rust_extractor, "_get_node_text", return_value="#[allow(dead_code)]"
        ):
            result = rust_extractor._extract_derives(node)
            assert result == []

    def test_get_node_text_uncached(self, rust_extractor):
        """Cover line 463+: _get_node_text cache miss path."""
        node = _mock_node("identifier", start_byte=0, end_byte=5, text="hello")
        rust_extractor.content_lines = ["hello world"]
        rust_extractor._node_text_cache.clear()
        with patch(
            "tree_sitter_analyzer.languages.rust_plugin.safe_encode",
            return_value=b"hello world",
        ):
            with patch(
                "tree_sitter_analyzer.languages.rust_plugin.extract_text_slice",
                return_value="hello",
            ):
                result = rust_extractor._get_node_text(node)
                assert result == "hello"
                assert (0, 5) in rust_extractor._node_text_cache

    def test_get_node_text_exception_returns_empty(self, rust_extractor):
        """Cover lines 473-474: _get_node_text exception fallback."""
        node = _mock_node("identifier", start_byte=0, end_byte=5)
        rust_extractor.content_lines = ["hello"]
        rust_extractor._node_text_cache.clear()
        with patch(
            "tree_sitter_analyzer.languages.rust_plugin.safe_encode",
            side_effect=Exception("encoding fail"),
        ):
            result = rust_extractor._get_node_text(node)
            assert result == ""

    def test_extract_elements_captures_side_effects(self, rust_plugin):
        """Cover lines 659-661: extract_elements captures modules/impls."""
        mock_tree = MagicMock()
        mock_extractor = MagicMock(spec=RustElementExtractor)
        mock_extractor.extract_functions.return_value = []
        mock_extractor.extract_classes.return_value = []
        mock_extractor.extract_variables.return_value = []
        mock_extractor.extract_imports.return_value = []
        mock_extractor.modules = [{"name": "test_mod"}]
        mock_extractor.impl_blocks = [{"type": "Foo"}]
        with patch.object(rust_plugin, "create_extractor", return_value=mock_extractor):
            rust_plugin.extract_elements(mock_tree, "code")
            assert rust_plugin.extractor.modules == [{"name": "test_mod"}]
            assert rust_plugin.extractor.impl_blocks == [{"type": "Foo"}]

    def test_extract_type_def_no_name_returns_none(self, rust_extractor):
        """Cover line 316: type_def with no name node."""
        node = _mock_node("struct_item", field_children={})
        result = rust_extractor._extract_type_def(node, "struct")
        assert result is None

    def test_extract_function_with_parameters_and_return(self, rust_extractor):
        """Cover parameter extraction and return type handling."""
        name_node = _mock_node("identifier", text="my_func")
        param1 = _mock_node("parameter", text="a: i32")
        param2 = _mock_node("self_parameter", text="&self")
        params_node = _mock_node(
            "parameters",
            text="(a: i32, &self)",
            children=[param1, param2],
        )
        ret_node = _mock_node("return_type", text="-> String")
        node = _mock_node(
            "function_item",
            field_children={
                "name": name_node,
                "parameters": params_node,
                "return_type": ret_node,
            },
            children=[],
            start_point=(0, 0),
            end_point=(0, 50),
        )
        with patch.object(
            rust_extractor,
            "_get_node_text",
            side_effect=lambda n: (
                n.text.decode() if isinstance(n.text, bytes) else str(n.text)
            ),
        ):
            with patch.object(
                rust_extractor, "_extract_visibility", return_value="pub"
            ):
                with patch.object(
                    rust_extractor, "_extract_docstring", return_value=None
                ):
                    result = rust_extractor._extract_function(node)
                    assert result is not None
                    assert "a: i32" in result.parameters
                    assert "self" in result.parameters
                    assert result.return_type == "String"

    def test_supports_file_case_insensitive(self, rust_plugin):
        """Cover line 671: supports_file with uppercase extension."""
        assert rust_plugin.supports_file("MAIN.RS") is True
