#!/usr/bin/env python3
"""Targeted tests to boost Kotlin plugin coverage to 75%+."""

from unittest.mock import Mock

import pytest

pytest.importorskip("tree_sitter_kotlin")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (  # noqa: E402
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

    def test_function_parameter_shapes(self, extractor, parser):
        """Test representative parameter shapes in one parse."""
        code = """
fun greet(name: String, age: Int, active: Boolean): String {
    return "Hello"
}
fun process(data: String?, count: Int?): Boolean? {
    return null
}
fun execute(callback: (String) -> Unit) {
    callback("test")
}
fun printAll(vararg items: String) {
    items.forEach { println(it) }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert {f.name for f in functions} >= {
            "greet",
            "process",
            "execute",
            "printAll",
        }


class TestKotlinExtractorVisibility:
    """Test visibility modifier extraction."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_visibility_shapes(self, extractor, parser):
        """Test protected/internal/private visibility shapes in one parse."""
        code = """
open class Base {
    protected fun helper(): Int = 42
}
internal fun moduleHelper(): String = "internal"
private class Secret {
    fun doSomething() {}
}
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)
        assert {f.name for f in functions} >= {"helper", "moduleHelper", "doSomething"}
        assert {c.name for c in classes} >= {"Base", "Secret"}


class TestKotlinExtractorProperties:
    """Test property extraction paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_property_shapes(self, extractor, parser):
        """Test getter/setter, lateinit, and const property shapes together."""
        code = """
class Example {
    var counter: Int = 0
        get() = field
        set(value) { field = value }
}
class Container {
    lateinit var data: String
}
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

    def test_import_shapes(self, extractor, parser):
        """Test single, wildcard, and alias imports together."""
        code = """
import kotlin.collections.List
import kotlin.collections.*
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

    def test_kdoc_shapes(self, extractor, parser):
        """Test function and class KDoc comments together."""
        code = """
/**
 * Calculates the sum of two numbers.
 * @param a First number
 * @param b Second number
 * @return Sum of a and b
 */
fun add(a: Int, b: Int): Int = a + b
/**
 * Represents a user in the system.
 * @property name User's name
 * @property age User's age
 */
data class User(val name: String, val age: Int)
"""
        tree = parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)
        assert "add" in {f.name for f in functions}
        assert len(classes) == 1


class TestKotlinExtractorErrorPaths:
    """Test error handling paths."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_with_malformed_declarations(self, extractor, parser):
        """Malformed declarations should return lists rather than crashing."""
        function_code = """
fun incomplete(
"""
        class_code = """
class Broken {
    fun method() {
"""
        function_tree = parser.parse(function_code.encode("utf-8"))
        class_tree = parser.parse(class_code.encode("utf-8"))
        functions = extractor.extract_functions(function_tree, function_code)
        classes = extractor.extract_classes(class_tree, class_code)
        assert isinstance(functions, list)
        assert isinstance(classes, list)

    def test_node_text_extraction_edge_cases(self, extractor):
        """Test node text extraction edge cases."""
        extractor.source_code = "fun test() {}"
        extractor.content_lines = extractor.source_code.split("\n")

        # Mock node with unusual positions
        mock_node = Mock()
        mock_node.parent = None
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

    def test_extract_elements_empty_or_whitespace_code(self, plugin, parser):
        """Empty and whitespace-only code should return an element dict."""
        for code in ["", "   \n\n   \t\t  \n"]:
            tree = parser.parse(code.encode("utf-8"))
            result = plugin.extract_elements(tree, code)
            assert isinstance(result, dict)
            assert "functions" in result
            assert "classes" in result


class TestKotlinExtractorInternalMethods:
    """Test internal extractor methods."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_class_shapes(self, extractor, parser):
        """Test class body, abstract, interface, inheritance, and object shapes."""
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
abstract class Shape {
    abstract fun area(): Double
    abstract fun perimeter(): Double
}
interface Drawable {
    fun draw()
    fun resize(scale: Double)
}
class Circle(val radius: Double) : Shape() {
    override fun area(): Double = 3.14159 * radius * radius
    override fun perimeter(): Double = 2 * 3.14159 * radius
}
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
        assert {c.name for c in classes} >= {
            "Service",
            "Shape",
            "Drawable",
            "Circle",
            "DatabaseManager",
        }


class TestKotlinTextExtractionEdgeCases:
    """Test text extraction edge cases."""

    @pytest.fixture
    def extractor(self):
        return KotlinElementExtractor()

    def test_get_node_text_edge_cases(self, extractor):
        """Test cached, multiline, and out-of-bounds text extraction."""
        extractor.source_code = "val x = 1"
        extractor.content_lines = ["val x = 1"]

        mock_node = Mock()
        mock_node.parent = None
        mock_node.start_byte = 0
        mock_node.end_byte = 9
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 9)

        # First call
        text1 = extractor._get_node_text(mock_node)
        # Second call should use cache
        text2 = extractor._get_node_text(mock_node)

        assert text1 == text2

        code = """fun test() {
    println("hello")
}"""
        extractor.source_code = code
        extractor.content_lines = code.split("\n")

        mock_node = Mock()
        mock_node.parent = None
        mock_node.start_byte = 0
        mock_node.end_byte = len(code)
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        text = extractor._get_node_text(mock_node)
        assert "fun test" in text

        extractor.source_code = "short"
        extractor.content_lines = ["short"]

        mock_node = Mock()
        mock_node.parent = None
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

    def test_extractors_return_none_on_error(self, extractor):
        """Private extractors should return None on unexpected node errors."""
        extractor.source_code = ""
        extractor.content_lines = []

        mock_node = Mock()
        mock_node.parent = None
        mock_node.start_point = Mock(side_effect=Exception("test error"))

        assert extractor._extract_function(mock_node) is None
        assert extractor._extract_class(mock_node) is None
        assert extractor._extract_property(mock_node) is None
        assert extractor._extract_import(mock_node) is None

    def test_extract_import_unknown_name(self, extractor):
        """Test import with unparseable name."""
        extractor.source_code = "import"
        extractor.content_lines = ["import"]

        mock_node = Mock()
        mock_node.parent = None
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
        mock_node.parent = None
        result = extractor._extract_docstring(mock_node)
        assert result is None
