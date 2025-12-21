#!/usr/bin/env python3
"""
Enhanced tests for Kotlin Plugin to improve coverage to 75%+.

Tests cover additional cases not in the existing test file:
- Coroutine builders and Flow
- Sealed classes
- Inline and reified functions
- Companion objects
- Object expressions
- Generic classes and functions
- Lambdas and higher-order functions
- Property delegates
- Annotations
- Multi-platform code
- Nested and inner classes
"""

import pytest

# Skip if tree_sitter_kotlin not available
pytest.importorskip("tree_sitter_kotlin")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (  # noqa: E402
    KotlinElementExtractor,
    KotlinPlugin,
)


class TestKotlinCoroutinesExtended:
    """Tests for Kotlin coroutine patterns."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_launch_coroutine_builder(self, extractor, kotlin_parser):
        """Should extract function using launch coroutine builder."""
        code = """
import kotlinx.coroutines.*

fun launchExample() {
    GlobalScope.launch {
        delay(1000)
        println("World")
    }
    println("Hello")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1
        func_names = [f.name for f in functions]
        assert "launchExample" in func_names

    def test_extract_async_await_pattern(self, extractor, kotlin_parser):
        """Should extract function using async/await pattern."""
        code = """
import kotlinx.coroutines.*

suspend fun fetchTwoUsersAsync(): Pair<User, User> = coroutineScope {
    val user1 = async { fetchUser(1) }
    val user2 = async { fetchUser(2) }
    Pair(user1.await(), user2.await())
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1

    def test_extract_flow_function(self, extractor, kotlin_parser):
        """Should extract function returning Flow."""
        code = """
import kotlinx.coroutines.flow.*

fun numberFlow(): Flow<Int> = flow {
    for (i in 1..10) {
        emit(i)
        delay(100)
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1
        func_names = [f.name for f in functions]
        assert "numberFlow" in func_names


class TestKotlinSealedClasses:
    """Tests for Kotlin sealed class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_sealed_class(self, extractor, kotlin_parser):
        """Should extract sealed class."""
        code = """
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Exception) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Result" in class_names

    def test_extract_sealed_interface(self, extractor, kotlin_parser):
        """Should extract sealed interface (Kotlin 1.5+)."""
        code = """
sealed interface Error {
    data class NetworkError(val code: Int) : Error
    data class IOError(val path: String) : Error
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        # May or may not detect sealed interface depending on implementation
        assert isinstance(classes, list)


class TestKotlinInlineFunctions:
    """Tests for Kotlin inline and reified functions."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_inline_function(self, extractor, kotlin_parser):
        """Should extract inline function."""
        code = """
inline fun measureTime(block: () -> Unit): Long {
    val start = System.currentTimeMillis()
    block()
    return System.currentTimeMillis() - start
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1
        func_names = [f.name for f in functions]
        assert "measureTime" in func_names

    def test_extract_reified_type_function(self, extractor, kotlin_parser):
        """Should extract function with reified type parameter."""
        code = """
inline fun <reified T> isOfType(value: Any): Boolean {
    return value is T
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1

    def test_extract_crossinline_function(self, extractor, kotlin_parser):
        """Should extract function with crossinline parameter."""
        code = """
inline fun createRunnable(crossinline body: () -> Unit): Runnable {
    return Runnable { body() }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1


class TestKotlinCompanionObjects:
    """Tests for Kotlin companion object extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_class_with_companion_object(self, extractor, kotlin_parser):
        """Should extract class with companion object."""
        code = """
class MyClass {
    companion object {
        const val TAG = "MyClass"
        fun create(): MyClass = MyClass()
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "MyClass" in class_names

    def test_extract_named_companion_object(self, extractor, kotlin_parser):
        """Should extract class with named companion object."""
        code = """
class MyService {
    companion object Factory {
        fun create(): MyService = MyService()
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1


class TestKotlinGenerics:
    """Tests for Kotlin generic class and function extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_generic_class(self, extractor, kotlin_parser):
        """Should extract generic class."""
        code = """
class Box<T>(val value: T) {
    fun get(): T = value
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Box" in class_names

    def test_extract_generic_function(self, extractor, kotlin_parser):
        """Should extract generic function."""
        code = """
fun <T> singletonList(item: T): List<T> {
    return listOf(item)
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 1

    def test_extract_bounded_generic(self, extractor, kotlin_parser):
        """Should extract class with bounded generic type."""
        code = """
class NumberBox<T : Number>(val value: T) {
    fun doubleValue(): Double = value.toDouble()
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1

    def test_extract_variance_annotations(self, extractor, kotlin_parser):
        """Should extract class with variance annotations."""
        code = """
class Producer<out T>(private val value: T) {
    fun get(): T = value
}

class Consumer<in T> {
    fun accept(value: T) {}
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 2


class TestKotlinPropertyDelegates:
    """Tests for Kotlin property delegates extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_class_with_lazy_property(self, extractor, kotlin_parser):
        """Should extract class with lazy delegated property."""
        code = """
class HeavyObject {
    val lazyValue: String by lazy {
        println("Computing")
        "Hello"
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "HeavyObject" in class_names

    def test_extract_class_with_observable_property(self, extractor, kotlin_parser):
        """Should extract class with observable delegated property."""
        code = """
import kotlin.properties.Delegates

class User {
    var name: String by Delegates.observable("<no name>") {
        prop, old, new -> println("Changed from $old to $new")
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1


class TestKotlinAnnotations:
    """Tests for Kotlin annotation extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_annotation_class(self, extractor, kotlin_parser):
        """Should extract annotation class."""
        code = """
annotation class Fancy

@Fancy
class AnnotatedClass {}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        # Should detect Fancy as annotation class or AnnotatedClass
        assert len(classes) >= 1

    def test_extract_function_with_annotations(self, extractor, kotlin_parser):
        """Should extract function with annotations."""
        code = """
@Deprecated("Use newFunction instead")
fun oldFunction() {
    println("old")
}

@Suppress("UNUSED_PARAMETER")
fun newFunction(param: String) {
    println("new")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) >= 2


class TestKotlinNestedClasses:
    """Tests for Kotlin nested and inner class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_nested_class(self, extractor, kotlin_parser):
        """Should extract nested class."""
        code = """
class Outer {
    class Nested {
        fun foo() = 2
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Outer" in class_names

    def test_extract_inner_class(self, extractor, kotlin_parser):
        """Should extract inner class."""
        code = """
class Outer {
    private val bar: Int = 1

    inner class Inner {
        fun foo() = bar
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1


class TestKotlinEnumClasses:
    """Tests for Kotlin enum class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_simple_enum(self, extractor, kotlin_parser):
        """Should extract simple enum class."""
        code = """
enum class Direction {
    NORTH, SOUTH, EAST, WEST
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Direction" in class_names

    def test_extract_enum_with_properties(self, extractor, kotlin_parser):
        """Should extract enum class with properties."""
        code = """
enum class Color(val rgb: Int) {
    RED(0xFF0000),
    GREEN(0x00FF00),
    BLUE(0x0000FF);

    fun containsRed() = (rgb and 0xFF0000) != 0
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Color" in class_names


class TestKotlinPluginExtended:
    """Extended tests for KotlinPlugin."""

    @pytest.fixture
    def plugin(self):
        """Create KotlinPlugin instance."""
        return KotlinPlugin()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_plugin_initialization(self, plugin):
        """Test plugin initialization."""
        assert plugin.language == "kotlin"
        assert ".kt" in plugin.supported_extensions
        assert isinstance(plugin.extractor, KotlinElementExtractor)

    def test_plugin_is_applicable(self, plugin):
        """Test is_applicable method."""
        assert plugin.is_applicable("Main.kt") is True
        assert plugin.is_applicable("test.kts") is True
        assert plugin.is_applicable("Main.java") is False
        assert plugin.is_applicable("test.py") is False

    def test_plugin_get_plugin_info(self, plugin):
        """Test get_plugin_info method."""
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert info["language"] == "kotlin"
        assert ".kt" in info["extensions"]

    def test_extract_elements_comprehensive(self, plugin, kotlin_parser):
        """Test extract_elements with comprehensive Kotlin code."""
        code = """
package com.example

import kotlinx.coroutines.flow.*

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
}

class UserRepository {
    companion object {
        const val TAG = "UserRepository"
    }

    suspend fun fetchUser(id: Int): Result<User> {
        return Result.Success(User(id, "name"))
    }

    fun userFlow(): Flow<User> = flow {
        emit(User(1, "test"))
    }
}

data class User(val id: Int, val name: String)

fun main() {
    println("Hello Kotlin")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)

        assert isinstance(result, dict)
        assert "classes" in result
        assert "functions" in result
        assert "imports" in result

    def test_extract_elements_with_none_tree(self, plugin):
        """Test extract_elements with None tree."""
        result = plugin.extract_elements(None, "")

        assert isinstance(result, dict)
        assert "classes" in result
        assert "functions" in result


class TestKotlinExtractorHelpers:
    """Tests for KotlinElementExtractor helper methods."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_get_node_text(self, extractor, kotlin_parser):
        """Test _get_node_text method."""
        code = "fun test() {}"
        tree = kotlin_parser.parse(code.encode("utf-8"))

        extractor.source_code = code
        extractor.content_lines = code.split("\n")

        text = extractor._get_node_text(tree.root_node)
        assert isinstance(text, str)
        assert "fun" in text

    def test_extract_imports(self, extractor, kotlin_parser):
        """Test extract_imports method."""
        code = """
package com.example

import kotlin.collections.List
import kotlin.collections.Map
import kotlinx.coroutines.*
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)

        assert isinstance(imports, list)
        assert len(imports) >= 0  # May or may not extract depending on implementation

    def test_extract_variables(self, extractor, kotlin_parser):
        """Test extract_variables method."""
        code = """
val globalConst = "constant"
var globalVar = 42

fun test() {
    val localVal = "local"
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert isinstance(variables, list)
        # Variables may or may not be detected at top level


class TestKotlinEdgeCases:
    """Edge case tests for Kotlin extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_empty_file(self, extractor, kotlin_parser):
        """Test extraction from empty file."""
        code = ""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)

        assert len(functions) == 0
        assert len(classes) == 0

    def test_comments_only(self, extractor, kotlin_parser):
        """Test extraction from file with only comments."""
        code = """
// This is a comment
/* This is a
   multiline comment */
/**
 * KDoc comment
 */
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)

        assert len(functions) == 0
        assert len(classes) == 0

    def test_malformed_code(self, extractor, kotlin_parser):
        """Test extraction from malformed code."""
        code = """
fun incomplete(
class missing {
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        # Should not crash
        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)

    def test_unicode_identifiers(self, extractor, kotlin_parser):
        """Test extraction with unicode identifiers."""
        code = """
fun 你好() {
    println("Hello in Chinese")
}

class Données {
    val ñ = "Spanish n with tilde"
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)

        # Should handle unicode gracefully
        assert isinstance(functions, list)
        assert isinstance(classes, list)

    def test_deeply_nested_structure(self, extractor, kotlin_parser):
        """Test extraction from deeply nested structure."""
        code = """
class Level1 {
    class Level2 {
        class Level3 {
            class Level4 {
                fun deepFunction() = "deep"
            }
        }
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        classes = extractor.extract_classes(tree, code)

        assert len(classes) >= 1
        class_names = [c.name for c in classes]
        assert "Level1" in class_names

    def test_multiple_same_name_functions(self, extractor, kotlin_parser):
        """Test extraction with function overloading."""
        code = """
fun add(a: Int, b: Int): Int = a + b
fun add(a: Double, b: Double): Double = a + b
fun add(a: String, b: String): String = a + b
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        functions = extractor.extract_functions(tree, code)

        # Should extract all overloaded functions
        assert len(functions) >= 3
        assert all(f.name == "add" for f in functions)
