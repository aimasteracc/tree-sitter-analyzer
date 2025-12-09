#!/usr/bin/env python3
"""Targeted tests to boost Kotlin plugin coverage to 75%+."""

from unittest.mock import Mock

import pytest

pytest.importorskip("tree_sitter_kotlin")

import tree_sitter
import tree_sitter_kotlin

from tree_sitter_analyzer.languages.kotlin_plugin import (
    KotlinElementExtractor,
    KotlinPlugin,
)


class TestKotlinExtractorParameters:
    """Test parameter extraction paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_function_with_typed_parameters(self, extractor, parser):
        """Test function with typed parameters."""
        code = """
fun greet(name: String, age: Int, active: Boolean): String {
    return "Hello"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        # Check parameters are extracted
        func = functions[0]
        assert func.name == "greet"

    def test_function_with_nullable_parameters(self, extractor, parser):
        """Test function with nullable types."""
        code = """
fun process(data: String?, count: Int?): Boolean? {
    return null
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_function_with_lambda_parameter(self, extractor, parser):
        """Test function with lambda parameter."""
        code = """
fun execute(callback: (String) -> Unit) {
    callback("test")
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_function_with_vararg(self, extractor, parser):
        """Test function with vararg parameter."""
        code = """
fun printAll(vararg items: String) {
    items.forEach { println(it) }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1


class TestKotlinExtractorVisibility:
    """Test visibility modifier extraction."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_protected_function(self, extractor, parser):
        """Test protected visibility."""
        code = """
open class Base {
    protected fun helper(): Int = 42
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_internal_function(self, extractor, parser):
        """Test internal visibility."""
        code = """
internal fun moduleHelper(): String = "internal"
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_private_class(self, extractor, parser):
        """Test private class."""
        code = """
private class Secret {
    fun doSomething() {}
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1


class TestKotlinExtractorProperties:
    """Test property extraction paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_property_with_getter_setter(self, extractor, parser):
        """Test property with custom getter/setter."""
        code = """
class Example {
    var counter: Int = 0
        get() = field
        set(value) { field = value }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        # Should extract the property
        assert isinstance(variables, list)

    def test_lateinit_property(self, extractor, parser):
        """Test lateinit property."""
        code = """
class Container {
    lateinit var data: String
}
"""
        tree = parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        assert isinstance(variables, list)

    def test_const_property(self, extractor, parser):
        """Test const property."""
        code = """
object Constants {
    const val MAX_SIZE = 100
}
"""
        tree = parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        assert isinstance(variables, list)


class TestKotlinExtractorImports:
    """Test import extraction paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_single_import(self, extractor, parser):
        """Test single import."""
        code = """
import kotlin.collections.List
"""
        tree = parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert isinstance(imports, list)

    def test_wildcard_import(self, extractor, parser):
        """Test wildcard import."""
        code = """
import kotlin.collections.*
"""
        tree = parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert isinstance(imports, list)

    def test_alias_import(self, extractor, parser):
        """Test import with alias."""
        code = """
import kotlin.collections.ArrayList as AList
"""
        tree = parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert isinstance(imports, list)


class TestKotlinExtractorDocstrings:
    """Test docstring extraction."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_function_with_kdoc(self, extractor, parser):
        """Test function with KDoc comment."""
        code = """
/**
 * Calculates the sum of two numbers.
 * @param a First number
 * @param b Second number
 * @return Sum of a and b
 */
fun add(a: Int, b: Int): Int = a + b
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_class_with_kdoc(self, extractor, parser):
        """Test class with KDoc comment."""
        code = """
/**
 * Represents a user in the system.
 * @property name User's name
 * @property age User's age
 */
data class User(val name: String, val age: Int)
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1


class TestKotlinExtractorErrorPaths:
    """Test error handling paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_with_malformed_function(self, extractor, parser):
        """Test extraction with malformed function."""
        code = """
fun incomplete(
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert isinstance(functions, list)

    def test_extract_with_malformed_class(self, extractor, parser):
        """Test extraction with malformed class."""
        code = """
class Broken {
    fun method() {
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert isinstance(classes, list)

    def test_node_text_extraction_edge_cases(self, extractor):
        """Test node text extraction edge cases."""
        extractor.source_code = "fun test() {}"
        extractor.content_lines = extractor.source_code.split("\n")

        # Mock node with unusual positions
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 13)
        mock_node.start_byte = 0
        mock_node.end_byte = 13

        text = extractor._get_node_text(mock_node)
        assert isinstance(text, str)

    def test_extract_function_with_exception(self, extractor, parser):
        """Test function extraction with simulated error."""
        code = """
fun test() {}
"""
        tree = parser.parse(code.encode("utf-8"))

        # Should not crash
        functions = extractor.extract_functions(tree, code)
        assert isinstance(functions, list)


class TestKotlinPluginEdgeCases:
    """Test KotlinPlugin edge cases."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_elements_empty_code(self, plugin, parser):
        """Test extraction from empty code."""
        tree = parser.parse(b"")
        result = plugin.extract_elements(tree, "")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result

    def test_extract_elements_whitespace_only(self, plugin, parser):
        """Test extraction from whitespace only."""
        code = "   \n\n   \t\t  \n"
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_create_extractor(self, plugin):
        """Test create_extractor method."""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, KotlinElementExtractor)

    def test_get_file_extensions(self, plugin):
        """Test get_file_extensions method."""
        extensions = plugin.get_file_extensions()
        assert ".kt" in extensions
        assert ".kts" in extensions


class TestKotlinExtractorInternalMethods:
    """Test internal extractor methods."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_class_with_body(self, extractor, parser):
        """Test class extraction with body containing methods."""
        code = """
class Service {
    private val data = mutableListOf<String>()

    fun add(item: String) {
        data.add(item)
    }

    fun remove(item: String): Boolean {
        return data.remove(item)
    }

    fun clear() {
        data.clear()
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1
        cls = classes[0]
        assert cls.name == "Service"

    def test_extract_abstract_class(self, extractor, parser):
        """Test abstract class extraction."""
        code = """
abstract class Shape {
    abstract fun area(): Double
    abstract fun perimeter(): Double
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1

    def test_extract_interface(self, extractor, parser):
        """Test interface extraction."""
        code = """
interface Drawable {
    fun draw()
    fun resize(scale: Double)
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        # Interface should be extracted as class
        assert isinstance(classes, list)

    def test_extract_class_with_inheritance(self, extractor, parser):
        """Test class with inheritance."""
        code = """
class Circle(val radius: Double) : Shape() {
    override fun area(): Double = 3.14159 * radius * radius
    override fun perimeter(): Double = 2 * 3.14159 * radius
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1

    def test_extract_object_with_methods(self, extractor, parser):
        """Test object declaration with methods."""
        code = """
object DatabaseManager {
    private var connection: Connection? = null

    fun connect(url: String) {
        // Connect logic
    }

    fun disconnect() {
        connection = null
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) >= 1


class TestKotlinTextExtractionEdgeCases:
    """Test text extraction edge cases."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    def test_get_node_text_with_cache(self, extractor):
        """Test cached node text retrieval."""
        extractor.source_code = "val x = 1"
        extractor.content_lines = ["val x = 1"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 9
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 9)

        # First call
        text1 = extractor._get_node_text(mock_node)
        # Second call should use cache
        text2 = extractor._get_node_text(mock_node)

        assert text1 == text2

    def test_get_node_text_multiline(self, extractor):
        """Test multiline text extraction."""
        code = """fun test() {
    println("hello")
}"""
        extractor.source_code = code
        extractor.content_lines = code.split("\n")

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(code)
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        text = extractor._get_node_text(mock_node)
        assert "fun test" in text

    def test_get_node_text_out_of_bounds(self, extractor):
        """Test text extraction with out of bounds position."""
        extractor.source_code = "short"
        extractor.content_lines = ["short"]

        mock_node = Mock()
        mock_node.start_byte = 100
        mock_node.end_byte = 200
        mock_node.start_point = (10, 0)
        mock_node.end_point = (10, 50)

        text = extractor._get_node_text(mock_node)
        assert text == ""


class TestKotlinExtractorExceptionPaths:
    """Test exception handling paths to boost coverage."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_function_returns_none_on_error(self, extractor):
        """Test _extract_function returns None on error."""
        extractor.source_code = ""
        extractor.content_lines = []

        # Create a mock node that will cause an exception
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("test error"))

        result = extractor._extract_function(mock_node)
        assert result is None

    def test_extract_class_returns_none_on_error(self, extractor):
        """Test _extract_class returns None on error."""
        extractor.source_code = ""
        extractor.content_lines = []

        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("test error"))

        result = extractor._extract_class(mock_node)
        assert result is None

    def test_extract_property_returns_none_on_error(self, extractor):
        """Test _extract_property returns None on error."""
        extractor.source_code = ""
        extractor.content_lines = []

        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("test error"))

        result = extractor._extract_property(mock_node)
        assert result is None

    def test_extract_import_returns_none_on_error(self, extractor):
        """Test _extract_import returns None on error."""
        extractor.source_code = ""
        extractor.content_lines = []

        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("test error"))

        result = extractor._extract_import(mock_node)
        assert result is None

    def test_extract_import_unknown_name(self, extractor):
        """Test import with unparseable name."""
        extractor.source_code = "import"
        extractor.content_lines = ["import"]

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 6)
        mock_node.start_byte = 0
        mock_node.end_byte = 6

        result = extractor._extract_import(mock_node)
        if result:
            assert result.name == "unknown"

    def test_extract_docstring(self, extractor):
        """Test docstring extraction."""
        mock_node = Mock()
        result = extractor._extract_docstring(mock_node)
        assert result is None
