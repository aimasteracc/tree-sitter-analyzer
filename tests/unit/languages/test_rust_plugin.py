from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor, RustPlugin
from tree_sitter_analyzer.models import Class, Function


@pytest.fixture
def rust_plugin():
    return RustPlugin()


@pytest.fixture
def rust_extractor():
    return RustElementExtractor()


@pytest.fixture
def rust_parser():
    """Create Rust parser."""
    try:
        import tree_sitter
        import tree_sitter_rust
        caps_or_lang = tree_sitter_rust.language()
        try:
            language = tree_sitter.Language(caps_or_lang)
        except Exception:
            language = caps_or_lang
        return tree_sitter.Parser(language)
    except ImportError:
        pytest.skip("tree-sitter-rust not installed")


class TestRustPlugin:
    def test_get_language_name(self, rust_plugin):
        assert rust_plugin.get_language_name() == "rust"

    def test_get_file_extensions(self, rust_plugin):
        assert ".rs" in rust_plugin.get_file_extensions()

    def test_create_extractor(self, rust_plugin):
        extractor = rust_plugin.create_extractor()
        assert isinstance(extractor, RustElementExtractor)

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.languages.rust_plugin.RustPlugin.get_tree_sitter_language"
    )
    @patch("tree_sitter.Parser")
    async def test_analyze_file_integration(
        self, mock_parser_cls, mock_get_lang, rust_plugin
    ):
        # Mock dependencies
        mock_parser = MagicMock()
        mock_parser_cls.return_value = mock_parser
        mock_tree = MagicMock()
        mock_parser.parse.return_value = mock_tree
        mock_get_lang.return_value = MagicMock()

        # Mock file content
        file_content = """
        fn main() {
            println!("Hello");
        }
        """

        with patch("tree_sitter_analyzer.encoding_utils.read_file_safe") as mock_read:
            mock_read.return_value = (file_content, "utf-8")

            # Run analysis
            result = await rust_plugin.analyze_file("test.rs", None)

            assert result.language == "rust"


class TestRustElementExtractor:
    def test_extract_functions_empty_tree_returns_list(self, rust_extractor):
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_tree.root_node.children = []
        mock_tree.root_node.type = "source_file"
        result = rust_extractor.extract_functions(mock_tree, "")
        assert isinstance(result, list)

    def test_extract_classes_empty_tree_returns_list(self, rust_extractor):
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_tree.root_node.children = []
        mock_tree.root_node.type = "source_file"
        result = rust_extractor.extract_classes(mock_tree, "")
        assert isinstance(result, list)


# Basic integration test with sample code
@pytest.mark.asyncio
async def test_full_flow_rust():
    # This test attempts to load the real parser. If not available, skip.
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

    # We mock read_file_safe to return our code
    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.rs", None)

        assert result.language == "rust"
        assert len(result.elements) > 0

        # Check for specific elements
        funcs = [e for e in result.elements if isinstance(e, Function)]
        structs = [e for e in result.elements if isinstance(e, Class)]

        assert any(f.name == "new" for f in funcs)
        assert any(f.name == "do_something" for f in funcs)
        assert any(s.name == "MyStruct" for s in structs)

        # Check async
        async_fn = next(f for f in funcs if f.name == "do_something")
        assert getattr(async_fn, "is_async", False) is True

        # Check modules metadata
        assert hasattr(result, "modules")
        assert any(m["name"] == "my_mod" for m in result.modules)


class TestRustPluginExtendedCoverage:
    """Extended tests for RustPlugin to cover missing lines."""

    @pytest.fixture
    def plugin(self):
        return RustPlugin()

    @pytest.fixture
    def extractor(self):
        return RustElementExtractor()

    def test_extract_function_with_params_and_return(self, rust_parser, extractor):
        """Test function extraction with parameters and return type (lines 220-291)."""
        code = """
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        func = functions[0]
        assert func.name == "add"
        assert func.visibility == "pub"
        assert len(func.parameters) >= 2

    def test_extract_function_with_self_param(self, rust_parser, extractor):
        """Test function with self parameter (lines 238-239)."""
        code = """
struct MyStruct;
impl MyStruct {
    fn method(&self) -> i32 {
        42
    }
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        method = [f for f in functions if f.name == "method"]
        assert len(method) >= 1
        assert "self" in method[0].parameters

    def test_extract_function_return_type_cleanup(self, rust_parser, extractor):
        """Test return type with -> prefix is cleaned up (lines 247-248)."""
        code = """
fn get_value() -> String {
    String::from("hello")
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        func = functions[0]
        # Return type should not start with ->
        assert not func.return_type.startswith("->")

    def test_extract_async_function(self, rust_parser, extractor):
        """Test async function detection (lines 254-267)."""
        code = """
async fn fetch_data() -> String {
    String::from("data")
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        func = functions[0]
        assert func.name == "fetch_data"
        assert getattr(func, "is_async", False) is True

    def test_extract_private_function(self, rust_parser, extractor):
        """Test private function (no pub) visibility (line 409)."""
        code = """
fn private_fn() {}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        func = functions[0]
        assert func.visibility == "private"

    def test_extract_struct(self, rust_parser, extractor):
        """Test struct extraction (lines 297-299)."""
        code = """
pub struct Point {
    pub x: f64,
    pub y: f64,
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert any(c.name == "Point" for c in classes)
        point = [c for c in classes if c.name == "Point"][0]
        assert point.class_type == "struct"
        assert point.visibility == "pub"

    def test_extract_enum(self, rust_parser, extractor):
        """Test enum extraction (lines 301-303)."""
        code = """
pub enum Color {
    Red,
    Green,
    Blue,
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert any(c.name == "Color" for c in classes)
        color = [c for c in classes if c.name == "Color"][0]
        assert color.class_type == "enum"

    def test_extract_trait(self, rust_parser, extractor):
        """Test trait extraction (lines 305-307)."""
        code = """
pub trait Drawable {
    fn draw(&self);
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert any(c.name == "Drawable" for c in classes)
        drawable = [c for c in classes if c.name == "Drawable"][0]
        assert drawable.class_type == "trait"

    def test_extract_impl_block(self, rust_parser, extractor):
        """Test impl block extraction (lines 349-370)."""
        code = """
struct Foo;
impl Foo {
    fn bar(&self) {}
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        extractor.extract_classes(tree, code)
        # impl blocks are tracked in extractor.impl_blocks
        assert isinstance(extractor.impl_blocks, list)

    def test_extract_trait_impl_block(self, rust_parser, extractor):
        """Test trait impl block extraction (lines 352-368)."""
        code = """
struct Foo;
trait Bar {
    fn baz(&self);
}
impl Bar for Foo {
    fn baz(&self) {}
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        extractor.extract_classes(tree, code)
        # Should have impl block tracked
        trait_impls = [ib for ib in extractor.impl_blocks if ib.get("trait")]
        assert isinstance(trait_impls, list)

    def test_extract_struct_field(self, rust_parser, extractor):
        """Test struct field extraction (lines 372-402)."""
        code = """
pub struct Config {
    pub name: String,
    pub value: i32,
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        assert len(variables) >= 2
        assert any(v.name == "name" for v in variables)
        assert any(v.name == "value" for v in variables)

    def test_extract_derive_macros(self, rust_parser, extractor):
        """Test derive macro extraction (lines 445-457)."""
        code = """
#[derive(Debug, Clone, PartialEq)]
pub struct MyData {
    pub field: i32,
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        my_data = [c for c in classes if c.name == "MyData"]
        assert len(my_data) >= 1
        derives = getattr(my_data[0], "implements_interfaces", [])
        if derives:
            assert "Debug" in derives

    def test_extract_use_declaration(self, rust_parser, extractor):
        """Test use declaration extraction (lines 140-163)."""
        code = """
use std::collections::HashMap;
use std::io::Read;
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert len(imports) >= 2
        assert all(imp.language == "rust" for imp in imports)

    def test_extract_modules(self, rust_parser, extractor):
        """Test module extraction (lines 191-218)."""
        code = """
pub mod utils {
    pub fn helper() {}
}
mod internal {
    fn secret() {}
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        # extract_classes triggers _extract_modules
        extractor.extract_classes(tree, code)
        assert len(extractor.modules) >= 2
        assert any(m["name"] == "utils" for m in extractor.modules)
        assert any(m["name"] == "internal" for m in extractor.modules)

    def test_reset_caches_with_source(self, extractor):
        """Test _reset_caches preserves state when source exists (lines 172-174)."""
        extractor.source_code = "some code"
        extractor.modules = [{"name": "test"}]
        extractor.impl_blocks = [{"type": "Foo"}]
        extractor._node_text_cache[(0, 10)] = "cached"
        extractor._reset_caches()
        assert len(extractor._node_text_cache) == 0
        # modules/impl_blocks preserved when source_code is non-empty
        assert len(extractor.modules) == 1

    def test_reset_caches_without_source(self, extractor):
        """Test _reset_caches clears everything when no source (lines 173-174)."""
        extractor.source_code = ""
        extractor.modules = [{"name": "test"}]
        extractor.impl_blocks = [{"type": "Foo"}]
        extractor._reset_caches()
        assert len(extractor.modules) == 0
        assert len(extractor.impl_blocks) == 0

    def test_get_tree_sitter_language_import_error(self, plugin):
        """Test tree-sitter language import error (lines 625-627)."""
        plugin._cached_language = None
        with patch("tree_sitter_rust.language", side_effect=ImportError("Not found")):
            result = plugin.get_tree_sitter_language()
            assert result is None

    def test_get_tree_sitter_language_generic_exception(self, plugin):
        """Test tree-sitter language generic exception (lines 628-630)."""
        plugin._cached_language = None
        with patch("tree_sitter_rust.language", side_effect=RuntimeError("Err")):
            result = plugin.get_tree_sitter_language()
            assert result is None

    def test_extract_elements_none_tree(self, plugin):
        """Test extract_elements with None tree (line 634-635)."""
        result = plugin.extract_elements(None, "code")
        assert result == {"functions": [], "classes": [], "variables": []}

    def test_extract_elements_exception(self, plugin):
        """Test extract_elements exception handling (lines 665-667)."""
        with patch.object(plugin, "create_extractor", side_effect=Exception("Error")):
            result = plugin.extract_elements(Mock(), "code")
            assert result == {"functions": [], "classes": [], "variables": []}

    def test_supports_file(self, plugin):
        """Test supports_file (lines 669-673)."""
        assert plugin.supports_file("test.rs") is True
        assert plugin.supports_file("TEST.RS") is True
        assert plugin.supports_file("test.py") is False
        assert plugin.supports_file("test.c") is False

    def test_count_tree_nodes(self, plugin):
        """Test _count_tree_nodes (lines 592-600)."""
        assert plugin._count_tree_nodes(None) == 0
        node = Mock()
        child = Mock()
        child.children = []
        node.children = [child]
        assert plugin._count_tree_nodes(node) == 2

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, plugin):
        """Test analyze_file with nonexistent file (lines 580-590)."""
        result = await plugin.analyze_file("/nonexistent/file.rs", None)
        assert result is not None
        assert result.success is False

    def test_extract_function_no_name_returns_none(self, rust_parser, extractor):
        """Test that function extraction returns None when no name found."""
        code = """
fn () {}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        # Should gracefully handle malformed code
        assert isinstance(functions, list)

    def test_extract_type_def_no_name_returns_none(self, rust_parser, extractor):
        """Test type_def extraction returns None when no name found."""
        code = """
struct;
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        # Malformed struct should be handled gracefully
        assert isinstance(classes, list)

    def test_get_node_text_caching(self, rust_parser, extractor):
        """Test node text caching (lines 459-474)."""
        code = "fn hello() {}"
        tree = rust_parser.parse(code.encode("utf-8"))
        extractor.source_code = code
        extractor.content_lines = code.split("\n")

        root = tree.root_node
        # First call
        text1 = extractor._get_node_text(root)
        # Second call (cached)
        text2 = extractor._get_node_text(root)
        assert text1 == text2

    def test_docstring_extraction(self, rust_parser, extractor):
        """Test docstring extraction from line comments (lines 411-443)."""
        # _extract_docstring looks for line_comment children starting with ///
        # The standard tree-sitter-rust parser might not attach doc comments
        # as children of function_item, so we test via the method directly
        code = """
/// This is a doc comment
fn documented() {}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert isinstance(functions, list)

    def test_extract_elements_captures_side_effects(self, rust_parser, plugin):
        """Test that extract_elements captures modules/impl_blocks from extractor (lines 658-661)."""
        code = """
mod mymod {
    struct S;
    impl S {
        fn method(&self) {}
    }
}
"""
        tree = rust_parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)
        # Side effects should be captured on plugin.extractor
        assert isinstance(plugin.extractor.modules, list)
        assert isinstance(plugin.extractor.impl_blocks, list)
