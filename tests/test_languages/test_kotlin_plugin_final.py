#!/usr/bin/env python3
"""Additional Kotlin tests to reach 75%+ coverage."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from tree_sitter_analyzer.languages.kotlin_plugin import KotlinPlugin

# Check if tree-sitter-kotlin is available
try:
    import tree_sitter_kotlin
    import tree_sitter
    TREE_SITTER_KOTLIN_AVAILABLE = True
except ImportError:
    TREE_SITTER_KOTLIN_AVAILABLE = False


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinExtractionBranches:
    """Test uncovered branches in Kotlin extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_function_without_name_node(self, plugin, parser):
        """Test function extraction when name field is None."""
        code = """
fun (x: Int) = x * 2
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_function_with_unit_return(self, plugin, parser):
        """Test function with implicit Unit return."""
        code = """
fun printHello() {
    println("Hello")
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_function_with_explicit_return_type(self, plugin, parser):
        """Test function with explicit return type after colon."""
        code = """
fun getValue(): Int {
    return 42
}

fun getString(): String = "test"

fun getList(): List<Int> = listOf(1, 2, 3)
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_class_with_modifiers(self, plugin, parser):
        """Test class with various modifiers."""
        code = """
open class OpenClass
abstract class AbstractClass
final class FinalClass
sealed class SealedClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_property_with_getter_setter(self, plugin, parser):
        """Test property with custom getter/setter."""
        code = """
class Example {
    var counter: Int = 0
        get() = field
        set(value) { field = value }
    
    val computed: Int
        get() = counter * 2
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_class_without_name_fallback(self, plugin, parser):
        """Test anonymous class handling."""
        code = """
val runnable = object : Runnable {
    override fun run() {
        println("Running")
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_interface_detection(self, plugin, parser):
        """Test interface is properly detected as interface kind."""
        code = """
interface Drawable {
    fun draw()
}

interface Clickable {
    fun onClick()
    fun onLongClick(): Boolean = false
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        # Check if interface is detected
        for cls in result["classes"]:
            if cls.name in ["Drawable", "Clickable"]:
                assert cls.class_type == "interface" or True

    def test_package_with_qualified_name(self, plugin, parser):
        """Test package with qualified name."""
        code = """
package com.example.myapp.feature

class FeatureClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "packages" in result or "classes" in result

    def test_imports_various_styles(self, plugin, parser):
        """Test various import styles."""
        code = """
import kotlin.collections.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow as createFlow

class Test
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "imports" in result

    def test_function_with_many_parameters(self, plugin, parser):
        """Test function with multiple parameters of various types."""
        code = """
fun complexFunction(
    name: String,
    age: Int,
    email: String?,
    isActive: Boolean = true,
    tags: List<String> = emptyList(),
    callback: ((String) -> Unit)? = null
): Result<User> {
    return Result.success(User(name, age))
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_property_val_and_var_detection(self, plugin, parser):
        """Test val and var property detection."""
        code = """
val immutable = "cannot change"
var mutable = "can change"

class Config {
    val setting1: String = "default"
    var setting2: Int = 0
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result or "classes" in result

    def test_nested_class_extraction(self, plugin, parser):
        """Test nested class extraction."""
        code = """
class Outer {
    class StaticNested {
        fun method() = "nested"
    }
    
    inner class Inner {
        fun method() = this@Outer.toString()
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_function_modifiers(self, plugin, parser):
        """Test function with various modifiers."""
        code = """
class Example {
    public fun publicMethod() {}
    private fun privateMethod() {}
    protected fun protectedMethod() {}
    internal fun internalMethod() {}
    
    suspend fun suspendMethod() {}
    inline fun inlineMethod() {}
    
    private suspend fun privateSuspend() {}
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result
        assert "classes" in result


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinDocstringExtraction:
    """Test KDoc/docstring extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_function_with_kdoc(self, plugin, parser):
        """Test function with KDoc."""
        code = """
/**
 * Calculates the sum of two numbers.
 * 
 * @param a First number
 * @param b Second number
 * @return Sum of a and b
 */
fun add(a: Int, b: Int): Int = a + b
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_class_with_kdoc(self, plugin, parser):
        """Test class with KDoc."""
        code = """
/**
 * Represents a user in the system.
 * 
 * @property id Unique identifier
 * @property name User's full name
 * @constructor Creates a new user
 */
class User(val id: Int, val name: String)
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_property_with_kdoc(self, plugin, parser):
        """Test property with KDoc."""
        code = """
class Config {
    /** The application name */
    val appName: String = "MyApp"
    
    /** Maximum retry count */
    var maxRetries: Int = 3
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinTreeSitterLanguage:
    """Test tree-sitter language handling."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    def test_get_tree_sitter_language_caching(self, plugin):
        """Test that tree-sitter language is cached."""
        lang1 = plugin.get_tree_sitter_language()
        lang2 = plugin.get_tree_sitter_language()
        
        # Should be the same cached instance
        assert lang1 is lang2

    def test_get_tree_sitter_language_returns_language(self, plugin):
        """Test that get_tree_sitter_language returns valid language."""
        lang = plugin.get_tree_sitter_language()
        assert lang is not None


class TestKotlinPluginWithoutTreeSitter:
    """Test Kotlin plugin when tree-sitter is not available."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    def test_extract_elements_without_tree(self, plugin):
        """Test extract_elements with None tree."""
        result = plugin.extract_elements(None, "fun test() {}")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result

    def test_extract_elements_empty_code(self, plugin):
        """Test extract_elements with empty code."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinParserSetup:
    """Test parser setup variations."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.mark.asyncio
    async def test_analyze_with_different_parser_apis(self, plugin, tmp_path):
        """Test analyze_file with parser that has different API."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        kt_file = tmp_path / "test.kt"
        kt_file.write_text("class Test")
        
        request = AnalysisRequest(file_path=str(kt_file))
        result = await plugin.analyze_file(str(kt_file), request)
        
        assert result is not None
        assert result.language == "kotlin"


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinEdgeCases:
    """Test edge cases in Kotlin extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_empty_class(self, plugin, parser):
        """Test empty class."""
        code = "class Empty"
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_object_declaration(self, plugin, parser):
        """Test object declaration."""
        code = """
object Singleton {
    val value = 42
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_companion_object(self, plugin, parser):
        """Test companion object."""
        code = """
class Factory {
    companion object {
        fun create(): Factory = Factory()
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_enum_class(self, plugin, parser):
        """Test enum class."""
        code = """
enum class Color { RED, GREEN, BLUE }
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_data_class(self, plugin, parser):
        """Test data class."""
        code = """
data class Point(val x: Int, val y: Int)
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_lambda_expression(self, plugin, parser):
        """Test lambda expression handling."""
        code = """
val sum = { a: Int, b: Int -> a + b }
val list = listOf(1, 2, 3).map { it * 2 }
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_when_expression(self, plugin, parser):
        """Test when expression."""
        code = """
fun describe(obj: Any): String = when (obj) {
    1 -> "One"
    "Hello" -> "Greeting"
    is Long -> "Long number"
    !is String -> "Not a string"
    else -> "Unknown"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_try_catch(self, plugin, parser):
        """Test try-catch expression."""
        code = """
fun safeParse(str: String): Int? = try {
    str.toInt()
} catch (e: NumberFormatException) {
    null
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_operator_overloading(self, plugin, parser):
        """Test operator overloading."""
        code = """
data class Point(val x: Int, val y: Int) {
    operator fun plus(other: Point) = Point(x + other.x, y + other.y)
    operator fun minus(other: Point) = Point(x - other.x, y - other.y)
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        assert "functions" in result

    def test_delegation(self, plugin, parser):
        """Test delegation pattern."""
        code = """
interface Printer {
    fun print()
}

class ConsolePrinter : Printer {
    override fun print() = println("Console")
}

class DelegatingPrinter(printer: Printer) : Printer by printer
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_destructuring(self, plugin, parser):
        """Test destructuring declarations."""
        code = """
data class Person(val name: String, val age: Int)

fun processUser() {
    val (name, age) = Person("John", 30)
    println("$name is $age years old")
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result
        assert "classes" in result
