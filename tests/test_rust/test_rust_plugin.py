from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor, RustPlugin
from tree_sitter_analyzer.models import Class, Function


@pytest.fixture
def rust_plugin():
    return RustPlugin()


@pytest.fixture
def rust_extractor():
    return RustElementExtractor()


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
    def test_extract_function(self, rust_extractor):
        # This requires mocking tree nodes which is complex.
        # We will rely on integration tests or simpler unit tests if possible.
        pass

    def test_extract_struct(self, rust_extractor):
        pass


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
