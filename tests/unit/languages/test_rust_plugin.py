"""
Comprehensive tests for Rust language plugin.

Covers RustElementExtractor and RustPlugin classes,
including edge cases, error paths, and all element types.
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor, RustPlugin
from tree_sitter_analyzer.models import Class, Function, Import, Variable


@pytest.fixture
def rust_plugin():
    return RustPlugin()


@pytest.fixture
def rust_extractor():
    return RustElementExtractor()


# ---------------------------------------------------------------------------
# Mock node helpers
# ---------------------------------------------------------------------------


def _mock_node(type_name, start_byte=0, end_byte=50,
               start_point=(0, 0), end_point=(0, 10),
               children=None, text="mock",
               field_children=None):
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
# RustPlugin tests
# ---------------------------------------------------------------------------


class TestRustPlugin:
    def test_get_language_name(self, rust_plugin):
        assert rust_plugin.get_language_name() == "rust"

    def test_get_file_extensions(self, rust_plugin):
        assert ".rs" in rust_plugin.get_file_extensions()

    def test_create_extractor(self, rust_plugin):
        extractor = rust_plugin.create_extractor()
        assert isinstance(extractor, RustElementExtractor)

    def test_supports_file_true(self, rust_plugin):
        assert rust_plugin.supports_file("main.rs") is True

    def test_supports_file_false(self, rust_plugin):
        assert rust_plugin.supports_file("main.py") is False

    def test_count_tree_nodes_none(self, rust_plugin):
        assert rust_plugin._count_tree_nodes(None) == 0

    def test_count_tree_nodes_with_children(self, rust_plugin):
        leaf = MagicMock()
        leaf.children = []
        parent = MagicMock()
        parent.children = [leaf, leaf]
        grandparent = MagicMock()
        grandparent.children = [parent]
        count = rust_plugin._count_tree_nodes(grandparent)
        assert count == 4  # grandparent + parent + 2 leaves

    # --- get_tree_sitter_language ---

    def test_get_tree_sitter_language_cached(self, rust_plugin):
        rust_plugin._cached_language = "cached_lang"
        result = rust_plugin.get_tree_sitter_language()
        assert result == "cached_lang"

    def test_get_tree_sitter_language_import_error(self, rust_plugin):
        rust_plugin._cached_language = None
        with patch.dict("sys.modules", {"tree_sitter_rust": None}):
            result = rust_plugin.get_tree_sitter_language()
            assert result is None

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_get_tree_sitter_language_exception(self, mock_log, rust_plugin):
        rust_plugin._cached_language = None
        with patch("tree_sitter_analyzer.languages.rust_plugin.tree_sitter_rust") as m:
            m.language.side_effect = RuntimeError("boom")
            result = rust_plugin.get_tree_sitter_language()
            assert result is None
            mock_log.assert_called()

    # --- extract_elements ---

    def test_extract_elements_none_tree(self, rust_plugin):
        result = rust_plugin.extract_elements(None, "")
        assert result == {"functions": [], "classes": [], "variables": []}

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_elements_error(self, mock_log, rust_plugin):
        mock_extractor = MagicMock()
        mock_extractor.extract_functions.side_effect = RuntimeError("boom")
        with patch.object(rust_plugin, "create_extractor", return_value=mock_extractor):
            result = rust_plugin.extract_elements(MagicMock(), "fn foo() {}")
            assert result == {"functions": [], "classes": [], "variables": []}
            mock_log.assert_called()

    # --- analyze_file ---

    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self, rust_plugin):
        with patch.object(rust_plugin, "get_tree_sitter_language", return_value=None):
            with patch(
                "tree_sitter_analyzer.encoding_utils.read_file_safe",
                return_value=("fn main() {}", "utf-8"),
            ):
                from tree_sitter_analyzer.models import AnalysisResult
                result = await rust_plugin.analyze_file("test.rs", None)
                assert isinstance(result, AnalysisResult)
                assert result.language == "rust"

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    async def test_analyze_file_exception(self, mock_log, rust_plugin):
        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe",
            side_effect=OSError("disk error"),
        ):
            from tree_sitter_analyzer.models import AnalysisResult
            result = await rust_plugin.analyze_file("test.rs", None)
            assert isinstance(result, AnalysisResult)
            assert result.success is False
            mock_log.assert_called()

    @pytest.mark.asyncio
    @patch("tree_sitter.Parser")
    async def test_analyze_file_integration(
        self, mock_parser_cls, rust_plugin
    ):
        with patch.object(
            rust_plugin, "get_tree_sitter_language", return_value=MagicMock()
        ):
            mock_parser = MagicMock()
            mock_parser_cls.return_value = mock_parser
            mock_tree = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_parser.set_language = MagicMock()

            file_content = "fn main() { println!(\"Hello\"); }"

            with patch("tree_sitter_analyzer.encoding_utils.read_file_safe") as m:
                m.return_value = (file_content, "utf-8")
                result = await rust_plugin.analyze_file("test.rs", None)
                assert result.language == "rust"


# ---------------------------------------------------------------------------
# RustElementExtractor tests - integration with real parser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow_rust():
    """Integration test with real tree-sitter-rust parser."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    pub mod my_mod {
        pub struct MyStruct {
            pub field: i32,
        }

        impl MyStruct {
            pub fn new() -> Self {
                MyStruct { field: 0 }
            }
        }

        pub async fn do_something() {}
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"
        assert len(result.elements) > 0

        funcs = [e for e in result.elements if isinstance(e, Function)]
        structs = [e for e in result.elements if isinstance(e, Class)]

        assert any(f.name == "new" for f in funcs)
        assert any(f.name == "do_something" for f in funcs)
        assert any(s.name == "MyStruct" for s in structs)

        async_fn = next(f for f in funcs if f.name == "do_something")
        assert getattr(async_fn, "is_async", False) is True

        assert hasattr(result, "modules")
        assert any(m["name"] == "my_mod" for m in result.modules)


@pytest.mark.asyncio
async def test_import_extraction():
    """Test that use declarations are extracted as imports."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    use std::collections::HashMap;
    use std::io::{self, Read};

    fn main() {
        let _m: HashMap<String, String> = HashMap::new();
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"
        imports = [e for e in result.elements if isinstance(e, Import)]
        assert len(imports) >= 2
        assert any("std::collections::HashMap" in imp.name for imp in imports)


@pytest.mark.asyncio
async def test_enum_and_trait_extraction():
    """Test that enum and trait definitions are extracted."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    #[derive(Debug, Clone)]
    pub enum Color {
        Red,
        Green,
        Blue,
    }

    pub trait Drawable {
        fn draw(&self);
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        classes = [e for e in result.elements if isinstance(e, Class)]
        assert any(c.name == "Color" for c in classes)
        assert any(c.name == "Drawable" for c in classes)

        color = next(c for c in classes if c.name == "Color")
        assert hasattr(color, "implements_interfaces")
        assert "Debug" in color.implements_interfaces
        assert "Clone" in color.implements_interfaces


@pytest.mark.asyncio
async def test_impl_block_extraction():
    """Test that impl blocks are extracted."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    pub struct Rectangle {
        pub width: f64,
        pub height: f64,
    }

    impl Rectangle {
        pub fn area(&self) -> f64 {
            self.width * self.height
        }
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        classes = [e for e in result.elements if isinstance(e, Class)]
        assert any(c.name == "Rectangle" for c in classes)
        assert any(c.name == "Rectangle" and c.class_type == "struct" for c in classes)

        funcs = [e for e in result.elements if isinstance(e, Function)]
        assert any(f.name == "area" for f in funcs)


@pytest.mark.asyncio
async def test_field_extraction():
    """Test that struct fields are extracted as variables."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    pub struct Config {
        pub name: String,
        version: u32,
        active: bool,
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        variables = [e for e in result.elements if isinstance(e, Variable)]
        assert len(variables) >= 3
        assert any(v.name == "name" for v in variables)
        assert any(v.name == "version" for v in variables)
        assert any(v.name == "active" for v in variables)


@pytest.mark.asyncio
async def test_doc_comment_extraction():
    """Test that doc comments (///) are extracted."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    /// Adds two numbers together.
    ///
    /// # Examples
    /// ```
    /// let result = add(2, 3);
    /// assert_eq!(result, 5);
    /// ```
    pub fn add(a: i32, b: i32) -> i32 {
        a + b
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        funcs = [e for e in result.elements if isinstance(e, Function)]
        add_fn = next((f for f in funcs if f.name == "add"), None)
        assert add_fn is not None


@pytest.mark.asyncio
async def test_derive_extraction():
    """Test that #[derive(...)] attributes are extracted."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    #[derive(Debug, Clone, PartialEq, Eq, Hash)]
    pub struct Point {
        pub x: f64,
        pub y: f64,
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        classes = [e for e in result.elements if isinstance(e, Class)]
        point = next((c for c in classes if c.name == "Point"), None)
        assert point is not None
        assert "Debug" in point.implements_interfaces
        assert "Clone" in point.implements_interfaces
        assert "PartialEq" in point.implements_interfaces
        assert "Eq" in point.implements_interfaces
        assert "Hash" in point.implements_interfaces


@pytest.mark.asyncio
async def test_async_function_detection():
    """Test that async functions are properly detected."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    pub async fn fetch_data(url: &str) -> String {
        String::from("data")
    }

    pub fn sync_func() -> i32 {
        42
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        funcs = [e for e in result.elements if isinstance(e, Function)]
        fetch_fn = next((f for f in funcs if f.name == "fetch_data"), None)
        sync_fn = next((f for f in funcs if f.name == "sync_func"), None)

        assert fetch_fn is not None
        assert fetch_fn.is_async is True

        assert sync_fn is not None
        assert sync_fn.is_async is False


@pytest.mark.asyncio
async def test_visibility_extraction():
    """Test that pub/private visibility is extracted."""
    try:
        import tree_sitter_rust  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")

    plugin = RustPlugin()

    code = """
    pub fn public_func() {}

    fn private_func() {}

    pub struct PublicStruct {
        pub field1: i32,
        field2: i32,
    }
    """

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"

        funcs = [e for e in result.elements if isinstance(e, Function)]
        pub_fn = next((f for f in funcs if f.name == "public_func"), None)
        priv_fn = next((f for f in funcs if f.name == "private_func"), None)

        assert pub_fn is not None
        assert pub_fn.visibility == "public"

        assert priv_fn is not None
        assert priv_fn.visibility == "private"


# ---------------------------------------------------------------------------
# Unit tests for RustElementExtractor with mocked nodes
# ---------------------------------------------------------------------------


class TestRustElementExtractorUnit:
    """Unit-level tests using mocked tree-sitter nodes."""

    def test_extract_import_success(self, rust_extractor):
        """Test _extract_import with a valid use declaration node."""
        node = _mock_node(
            "use_declaration",
            text="use std::collections::HashMap;",
            start_point=(0, 0),
            end_point=(0, 29),
        )
        with patch.object(rust_extractor, "_get_node_text",
                          return_value="use std::collections::HashMap;"):
            result = rust_extractor._extract_import(node)
            assert result is not None
            assert isinstance(result, Import)
            assert "std::collections::HashMap" in result.name

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_import_error(self, mock_log, rust_extractor):
        """Test _extract_import error handling."""
        node = _mock_node("use_declaration")
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=RuntimeError("boom")):
            result = rust_extractor._extract_import(node)
            assert result is None
            mock_log.assert_called()

    def test_reset_caches_clears_when_no_source(self, rust_extractor):
        """Test _reset_caches clears modules/impls when source_code is empty."""
        rust_extractor.modules = [{"name": "test"}]
        rust_extractor.impl_blocks = [{"type": "impl"}]
        rust_extractor.source_code = ""
        rust_extractor._reset_caches()
        assert rust_extractor.modules == []
        assert rust_extractor.impl_blocks == []

    def test_extract_enum(self, rust_extractor):
        """Test _extract_enum calls _extract_type_def with 'enum'."""
        node = _mock_node("enum_item")
        with patch.object(rust_extractor, "_extract_type_def",
                          return_value=Class(name="MyEnum", start_line=1, end_line=3)) as mock_td:
            result = rust_extractor._extract_enum(node)
            mock_td.assert_called_once_with(node, "enum")
            assert result.name == "MyEnum"

    def test_extract_trait(self, rust_extractor):
        """Test _extract_trait calls _extract_type_def with 'trait'."""
        node = _mock_node("trait_item")
        with patch.object(rust_extractor, "_extract_type_def",
                          return_value=Class(name="MyTrait", start_line=1, end_line=3)) as mock_td:
            result = rust_extractor._extract_trait(node)
            mock_td.assert_called_once_with(node, "trait")
            assert result.name == "MyTrait"

    def test_extract_type_def_no_name(self, rust_extractor):
        """Test _extract_type_def returns None when no name node."""
        node = _mock_node("struct_item", field_children={})
        result = rust_extractor._extract_type_def(node, "struct")
        assert result is None

    def test_extract_type_def_with_derives(self, rust_extractor):
        """Test _extract_type_def attaches derive traits to class."""
        name_node = _mock_node("identifier", text="MyStruct")
        node = _mock_node(
            "struct_item",
            text="pub struct MyStruct",
            field_children={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 1),
            children=[
                _mock_node("attribute_item", text="#[derive(Debug, Clone)]"),
            ],
        )
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=lambda n: n.text.decode() if isinstance(n.text, bytes) else n.text):
            with patch.object(rust_extractor, "_extract_visibility",
                              return_value="public"):
                result = rust_extractor._extract_type_def(node, "struct")
                assert result is not None
                assert result.name == "MyStruct"
                assert "Debug" in result.implements_interfaces
                assert "Clone" in result.implements_interfaces

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_type_def_error(self, mock_log, rust_extractor):
        """Test _extract_type_def error handling."""
        node = _mock_node("struct_item")
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=RuntimeError("boom")):
            result = rust_extractor._extract_type_def(node, "struct")
            assert result is None
            mock_log.assert_called()

    def test_extract_impl_error(self, rust_extractor):
        """Test _extract_impl error handling."""
        node = _mock_node("impl_item")
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=RuntimeError("boom")):
            with patch("tree_sitter_analyzer.languages.rust_plugin.log_error"):
                result = rust_extractor._extract_impl(node)
                assert result is None

    def test_extract_field_no_name_or_type(self, rust_extractor):
        """Test _extract_field returns None when name or type is missing."""
        node = _mock_node("field_declaration", field_children={})
        result = rust_extractor._extract_field(node)
        assert result is None

    def test_extract_field_success(self, rust_extractor):
        """Test _extract_field with valid name and type."""
        name_node = _mock_node("identifier", text="field_name")
        type_node = _mock_node("type_identifier", text="i32")
        node = _mock_node(
            "field_declaration",
            field_children={"name": name_node, "type": type_node},
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=lambda n: n.text.decode() if isinstance(n.text, bytes) else n.text):
            with patch.object(rust_extractor, "_extract_visibility",
                              return_value="public"):
                result = rust_extractor._extract_field(node)
                assert result is not None
                assert isinstance(result, Variable)
                assert result.name == "field_name"
                assert result.variable_type == "i32"

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_field_error(self, mock_log, rust_extractor):
        """Test _extract_field error handling."""
        node = _mock_node("field_declaration")
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=RuntimeError("boom")):
            result = rust_extractor._extract_field(node)
            assert result is None
            mock_log.assert_called()

    def test_extract_docstring_line_comment(self, rust_extractor):
        """Test _extract_docstring with /// line comments."""
        comment = _mock_node("line_comment", text="/// A doc comment")
        node = _mock_node("function_item", children=[comment])
        result = rust_extractor._extract_docstring(node)
        assert result is not None
        assert "A doc comment" in result

    def test_extract_docstring_block_comment(self, rust_extractor):
        """Test _extract_docstring with block comments."""
        comment = _mock_node("block_comment", text="/** Block doc */")
        node = _mock_node("function_item", children=[comment])
        result = rust_extractor._extract_docstring(node)
        assert result is not None
        assert "Block doc" in result

    def test_extract_docstring_empty(self, rust_extractor):
        """Test _extract_docstring returns None when no doc comments."""
        node = _mock_node("function_item", children=[])
        result = rust_extractor._extract_docstring(node)
        assert result is None

    def test_extract_derives_found(self, rust_extractor):
        """Test _extract_derives extracts trait names from derive attributes."""
        attr = _mock_node("attribute_item", text="#[derive(Debug, Clone, Copy)]")
        node = _mock_node("struct_item", children=[attr])
        result = rust_extractor._extract_derives(node)
        assert "Debug" in result
        assert "Clone" in result
        assert "Copy" in result

    def test_extract_derives_none(self, rust_extractor):
        """Test _extract_derives returns empty list when no derive attrs."""
        node = _mock_node("struct_item", children=[])
        result = rust_extractor._extract_derives(node)
        assert result == []

    def test_get_node_text_cache_hit(self, rust_extractor):
        """Test _get_node_text returns cached value."""
        node = _mock_node("identifier", start_byte=0, end_byte=10, text="cached")
        rust_extractor._node_text_cache[(0, 10)] = "cached_value"
        result = rust_extractor._get_node_text(node)
        assert result == "cached_value"

    def test_get_node_text_error(self, rust_extractor):
        """Test _get_node_text returns empty string on error."""
        node = _mock_node("identifier", start_byte=0, end_byte=10)
        with patch("tree_sitter_analyzer.languages.rust_plugin.extract_text_slice",
                   side_effect=Exception("bad encoding")):
            result = rust_extractor._get_node_text(node)
            assert result == ""

    def test_extract_function_no_name(self, rust_extractor):
        """Test _extract_function returns None when name field missing."""
        node = _mock_node("function_item", field_children={})
        result = rust_extractor._extract_function(node)
        assert result is None

    def test_extract_function_async_detection(self, rust_extractor):
        """Test _extract_function detects async modifier."""
        name_node = _mock_node("identifier", text="my_async_fn")
        async_node = _mock_node("async", text="async")
        node = _mock_node(
            "function_item",
            field_children={"name": name_node},
            children=[async_node],
            start_point=(0, 0),
            end_point=(0, 1),
        )
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=lambda n: n.text.decode() if isinstance(n.text, bytes) else n.text):
            with patch.object(rust_extractor, "_extract_visibility",
                              return_value="public"):
                result = rust_extractor._extract_function(node)
                assert result is not None
                assert result.is_async is True

    def test_extract_visibility_public(self, rust_extractor):
        """Test _extract_visibility returns 'pub' when visibility_modifier present."""
        vis_mod = _mock_node("visibility_modifier", text="pub")
        node = _mock_node("function_item", children=[vis_mod])
        result = rust_extractor._extract_visibility(node)
        assert result == "pub"

    def test_extract_visibility_private_default(self, rust_extractor):
        """Test _extract_visibility returns 'private' by default."""
        node = _mock_node("function_item", children=[])
        result = rust_extractor._extract_visibility(node)
        assert result == "private"

    @patch("tree_sitter_analyzer.languages.rust_plugin.log_error")
    def test_extract_function_error(self, mock_log, rust_extractor):
        """Test _extract_function error handling."""
        node = _mock_node("function_item")
        with patch.object(rust_extractor, "_get_node_text",
                          side_effect=RuntimeError("boom")):
            result = rust_extractor._extract_function(node)
            assert result is None
            mock_log.assert_called()
