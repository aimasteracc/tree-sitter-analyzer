from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.kotlin_plugin import (
    KotlinElementExtractor,
    KotlinPlugin,
)
from tree_sitter_analyzer.models import Class, Function


@pytest.fixture
def kotlin_plugin():
    return KotlinPlugin()


@pytest.fixture
def kotlin_extractor():
    return KotlinElementExtractor()


class TestKotlinPlugin:
    def test_get_language_name(self, kotlin_plugin):
        assert kotlin_plugin.get_language_name() == "kotlin"

    def test_get_file_extensions(self, kotlin_plugin):
        assert ".kt" in kotlin_plugin.get_file_extensions()
        assert ".kts" in kotlin_plugin.get_file_extensions()

    def test_create_extractor(self, kotlin_plugin):
        extractor = kotlin_plugin.create_extractor()
        assert isinstance(extractor, KotlinElementExtractor)

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.languages.kotlin_plugin.KotlinPlugin.get_tree_sitter_language"
    )
    @patch("tree_sitter.Parser")
    async def test_analyze_file_integration(
        self, mock_parser_cls, mock_get_lang, kotlin_plugin
    ):
        # Mock dependencies
        mock_parser = MagicMock()
        mock_parser_cls.return_value = mock_parser
        mock_tree = MagicMock()
        mock_parser.parse.return_value = mock_tree
        mock_get_lang.return_value = MagicMock()

        # Mock file content
        file_content = """
        fun main() {
            println("Hello")
        }
        """

        with patch("tree_sitter_analyzer.encoding_utils.read_file_safe") as mock_read:
            mock_read.return_value = (file_content, "utf-8")

            # Run analysis
            result = await kotlin_plugin.analyze_file("test.kt", None)

            assert result.language == "kotlin"


class TestKotlinElementExtractor:
    def test_extract_function(self, kotlin_extractor):
        pass

    def test_extract_class(self, kotlin_extractor):
        pass


# Basic integration test with sample code
@pytest.mark.asyncio
async def test_full_flow_kotlin():
    # This test attempts to load the real parser. If not available, skip.
    try:
        import tree_sitter_kotlin  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-kotlin not installed")

    plugin = KotlinPlugin()

    code = """
    package com.example

    data class User(val id: Int, var name: String)

    fun processUser(user: User): Boolean {
        return true
    }

    interface Processor {
        fun process()
    }
    """

    # We mock read_file_safe to return our code
    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.kt", None)

        assert result.language == "kotlin"
        assert len(result.elements) > 0

        # Check for specific elements
        funcs = [e for e in result.elements if isinstance(e, Function)]
        classes = [e for e in result.elements if isinstance(e, Class)]

        assert any(f.name == "processUser" for f in funcs)
        assert any(c.name == "User" for c in classes)
        assert any(c.name == "Processor" for c in classes)

        # Check package
        assert result.package.name == "com.example"
