"""
Comprehensive tests for Rust language plugin.

Covers RustPlugin class and integration tests,
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
# RustPlugin tests
# ---------------------------------------------------------------------------


class TestRustPlugin:
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
        # Patch tree_sitter_rust BEFORE the import inside get_tree_sitter_language
        with patch(
            "tree_sitter_analyzer.languages.rust_plugin.tree_sitter",
            create=True,
        ) as _mock_ts:
            import tree_sitter_rust

            # Make tree_sitter_rust.language() return a non-Language object
            # so it enters the else branch where tree_sitter.Language() is called
            with patch.object(
                tree_sitter_rust, "language", side_effect=RuntimeError("boom")
            ):
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
    async def test_analyze_file_integration(self, mock_parser_cls, rust_plugin):
        with patch.object(
            rust_plugin, "get_tree_sitter_language", return_value=MagicMock()
        ):
            mock_parser = MagicMock()
            mock_parser_cls.return_value = mock_parser
            mock_tree = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_parser.set_language = MagicMock()

            file_content = 'fn main() { println!("Hello"); }'

            with patch("tree_sitter_analyzer.encoding_utils.read_file_safe") as m:
                m.return_value = (file_content, "utf-8")
                result = await rust_plugin.analyze_file("test.rs", None)
                assert result.language == "rust"


# ---------------------------------------------------------------------------
# Integration tests with real tree-sitter-rust parser
# ---------------------------------------------------------------------------


_TS_RUST_AVAILABLE = False
try:
    import tree_sitter_rust  # noqa: F401

    _TS_RUST_AVAILABLE = True
except ImportError:
    pass


def _parse_rust(code: str):
    """Parse Rust code with tree-sitter-rust. Returns tree or None."""
    if not _TS_RUST_AVAILABLE:
        return None
    import tree_sitter
    import tree_sitter_rust

    caps = tree_sitter_rust.language()
    lang = tree_sitter.Language(caps)
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


@pytest.mark.skipif(not _TS_RUST_AVAILABLE, reason="tree-sitter-rust not installed")
class TestRustIntegration:
    @pytest.mark.asyncio
    async def test_full_flow(self):
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
            assert len(result.elements) == 5

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
    async def test_import_extraction(self):
        plugin = RustPlugin()
        code = """use std::collections::HashMap;
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
            assert len(imports) == 2, f"Expected 2 imports, got {len(imports)}"
            assert any("std::collections::HashMap" in imp.name for imp in imports)

    @pytest.mark.asyncio
    async def test_enum_trait_extraction(self):
        plugin = RustPlugin()
        code = """
        #[derive(Debug, Clone)]
        pub enum Color {
            Red, Green, Blue,
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
            assert any(c.name == "Color" for c in classes), (
                f"Expected Color in classes: {[c.name for c in classes]}"
            )
            assert any(c.name == "Drawable" for c in classes), (
                f"Expected Drawable in classes: {[c.name for c in classes]}"
            )

            color = next(c for c in classes if c.name == "Color")
            assert color.class_type == "enum"

            drawable = next(c for c in classes if c.name == "Drawable")
            assert drawable.class_type == "trait"

    @pytest.mark.asyncio
    async def test_impl_block_extraction(self):
        plugin = RustPlugin()
        code = """pub struct Rectangle { pub width: f64, pub height: f64 }

impl Rectangle {
    pub fn area(&self) -> f64 { self.width * self.height }
}
"""
        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe",
            return_value=(code, "utf-8"),
        ):
            result = await plugin.analyze_file("test.rs", None)
            assert result.language == "rust"
            classes = [e for e in result.elements if isinstance(e, Class)]
            assert any(
                c.name == "Rectangle" and c.class_type == "struct" for c in classes
            )
            funcs = [e for e in result.elements if isinstance(e, Function)]
            assert any(f.name == "area" for f in funcs)

    @pytest.mark.asyncio
    async def test_field_extraction(self):
        plugin = RustPlugin()
        code = """pub struct Config {
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
            assert len(variables) == 3, f"Expected 3 variables, got {len(variables)}"
            names = {v.name for v in variables}
            assert "name" in names
            assert "version" in names
            assert "active" in names

    @pytest.mark.asyncio
    async def test_async_function_detection(self):
        plugin = RustPlugin()
        code = """pub async fn fetch_data(url: &str) -> String { String::from("data") }
pub fn sync_func() -> i32 { 42 }
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
    async def test_visibility_extraction(self):
        plugin = RustPlugin()
        code = """pub fn public_func() {}
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
            # tree-sitter-rust visibility_modifier text is "pub"
            assert pub_fn.visibility == "pub", (
                f"Expected 'pub', got '{pub_fn.visibility}'"
            )
            assert priv_fn is not None
            assert priv_fn.visibility == "private"

    @pytest.mark.asyncio
    async def test_extract_elements_full(self):
        """Test extract_elements directly with parsed tree."""
        code = """fn add(a: i32, b: i32) -> i32 { a + b }
struct Point { x: f64, y: f64 }
"""
        tree = _parse_rust(code)
        if tree is None:
            pytest.skip("tree-sitter-rust parse failed")
        plugin = RustPlugin()
        result = plugin.extract_elements(tree, code)
        assert len(result["functions"]) == 1
        assert len(result["classes"]) == 1
        assert any(f.name == "add" for f in result["functions"])
