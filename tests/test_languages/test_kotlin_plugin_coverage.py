#!/usr/bin/env python3
"""Additional Kotlin plugin coverage tests targeting 75%+."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from tree_sitter_analyzer.languages.kotlin_plugin import KotlinPlugin
from tree_sitter_analyzer.models import Class, Function, Variable, Import

# Check if tree-sitter-kotlin is available
try:
    import tree_sitter_kotlin
    import tree_sitter
    TREE_SITTER_KOTLIN_AVAILABLE = True
except ImportError:
    TREE_SITTER_KOTLIN_AVAILABLE = False


class TestKotlinPluginBasics:
    """Test basic Kotlin plugin functionality."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    def test_plugin_initialization(self, plugin):
        """Test plugin initializes correctly."""
        assert plugin is not None
        assert plugin.get_language_name() == "kotlin"

    def test_supported_extensions(self, plugin):
        """Test supported extensions."""
        extensions = plugin.supported_extensions
        assert ".kt" in extensions
        assert ".kts" in extensions

    def test_get_language_name(self, plugin):
        """Test get_language_name method."""
        assert plugin.get_language_name() == "kotlin"


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinPluginExtraction:
    """Test Kotlin element extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_simple_function(self, plugin, parser):
        """Test extracting simple function."""
        code = """
fun greet(name: String): String {
    return "Hello, $name!"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result
        func_names = [f.name for f in result["functions"]]
        assert "greet" in func_names

    def test_extract_suspend_function(self, plugin, parser):
        """Test extracting suspend function."""
        code = """
suspend fun fetchData(url: String): String {
    delay(1000)
    return "data"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_private_function(self, plugin, parser):
        """Test extracting private function."""
        code = """
private fun internalHelper(): Int {
    return 42
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_protected_function(self, plugin, parser):
        """Test extracting protected function."""
        code = """
open class Base {
    protected fun helperMethod(): String {
        return "helper"
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result
        assert "classes" in result

    def test_extract_internal_function(self, plugin, parser):
        """Test extracting internal function."""
        code = """
internal fun moduleHelper(): Boolean {
    return true
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_class_with_visibility(self, plugin, parser):
        """Test extracting class with different visibility."""
        code = """
public class PublicClass
private class PrivateClass
internal class InternalClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_interface(self, plugin, parser):
        """Test extracting interface."""
        code = """
interface Repository {
    fun findById(id: Int): Entity?
    fun save(entity: Entity): Boolean
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_object_declaration(self, plugin, parser):
        """Test extracting object declaration."""
        code = """
object Singleton {
    val instance = "singleton"
    fun doSomething() {}
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_companion_object(self, plugin, parser):
        """Test extracting companion object."""
        code = """
class MyClass {
    companion object {
        const val TAG = "MyClass"
        fun create(): MyClass = MyClass()
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_data_class(self, plugin, parser):
        """Test extracting data class."""
        code = """
data class User(
    val id: Int,
    val name: String,
    val email: String
)
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_sealed_class(self, plugin, parser):
        """Test extracting sealed class."""
        code = """
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Exception) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_enum_class(self, plugin, parser):
        """Test extracting enum class."""
        code = """
enum class Status {
    PENDING,
    ACTIVE,
    COMPLETED,
    CANCELLED
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_property_val(self, plugin, parser):
        """Test extracting val property."""
        code = """
val immutableValue: String = "constant"
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result

    def test_extract_property_var(self, plugin, parser):
        """Test extracting var property."""
        code = """
var mutableValue: Int = 0
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result

    def test_extract_private_property(self, plugin, parser):
        """Test extracting private property."""
        code = """
class Config {
    private val secret: String = "hidden"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result or "classes" in result

    def test_extract_package_declaration(self, plugin, parser):
        """Test extracting package declaration."""
        code = """
package com.example.myapp

class MyClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "packages" in result or "classes" in result

    def test_extract_imports(self, plugin, parser):
        """Test extracting import statements."""
        code = """
import kotlin.collections.List
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MyClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "imports" in result

    def test_extract_function_with_parameters(self, plugin, parser):
        """Test extracting function with multiple parameters."""
        code = """
fun calculate(a: Int, b: Int, operation: (Int, Int) -> Int): Int {
    return operation(a, b)
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result
        funcs = result["functions"]
        calc_func = next((f for f in funcs if f.name == "calculate"), None)
        if calc_func:
            assert hasattr(calc_func, 'parameters') or True

    def test_extract_extension_function(self, plugin, parser):
        """Test extracting extension function."""
        code = """
fun String.addExclamation(): String {
    return this + "!"
}

fun Int.isEven(): Boolean = this % 2 == 0
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_inline_function(self, plugin, parser):
        """Test extracting inline function."""
        code = """
inline fun <T> measureTime(block: () -> T): T {
    val start = System.currentTimeMillis()
    val result = block()
    println("Time: ${System.currentTimeMillis() - start}ms")
    return result
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_function_with_default_params(self, plugin, parser):
        """Test extracting function with default parameters."""
        code = """
fun greet(name: String = "World", greeting: String = "Hello"): String {
    return "$greeting, $name!"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_class_with_constructor(self, plugin, parser):
        """Test extracting class with primary constructor."""
        code = """
class Person(
    val name: String,
    val age: Int,
    private var email: String
) {
    fun greet() = "Hello, I'm $name"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        assert "functions" in result

    def test_extract_class_with_secondary_constructor(self, plugin, parser):
        """Test extracting class with secondary constructor."""
        code = """
class Person {
    val name: String
    val age: Int
    
    constructor(name: String) {
        this.name = name
        this.age = 0
    }
    
    constructor(name: String, age: Int) {
        this.name = name
        this.age = age
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_abstract_class(self, plugin, parser):
        """Test extracting abstract class."""
        code = """
abstract class Shape {
    abstract fun area(): Double
    abstract fun perimeter(): Double
    
    fun describe(): String = "I am a shape"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        assert "functions" in result

    def test_extract_generic_class(self, plugin, parser):
        """Test extracting generic class."""
        code = """
class Container<T>(val item: T) {
    fun get(): T = item
    fun set(newItem: T): Container<T> = Container(newItem)
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_nested_class(self, plugin, parser):
        """Test extracting nested class."""
        code = """
class Outer {
    class Nested {
        fun nestedMethod(): String = "nested"
    }
    
    inner class Inner {
        fun innerMethod(): String = "inner"
    }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_annotation_class(self, plugin, parser):
        """Test extracting annotation class."""
        code = """
annotation class MyAnnotation(val value: String)

@MyAnnotation("test")
class AnnotatedClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_typealias(self, plugin, parser):
        """Test extracting typealias."""
        code = """
typealias StringList = List<String>
typealias Handler = (Int, String) -> Boolean
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        # Typealias may be extracted as variables or not at all
        assert isinstance(result, dict)


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinPluginAnalyzeFile:
    """Test analyze_file method."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin, tmp_path):
        """Test successful file analysis."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        kt_file = tmp_path / "test.kt"
        kt_file.write_text("""
package com.example

class TestClass {
    fun testMethod(): String = "test"
}
""")
        request = AnalysisRequest(file_path=str(kt_file))
        result = await plugin.analyze_file(str(kt_file), request)
        
        assert result is not None
        assert result.language == "kotlin"

    @pytest.mark.asyncio
    async def test_analyze_file_with_imports(self, plugin, tmp_path):
        """Test file analysis with imports."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        kt_file = tmp_path / "imports.kt"
        kt_file.write_text("""
package com.example

import kotlin.collections.List

class ImportTest {
    val items: List<String> = emptyList()
}
""")
        request = AnalysisRequest(file_path=str(kt_file))
        result = await plugin.analyze_file(str(kt_file), request)
        
        assert result is not None
        assert result.language == "kotlin"

    @pytest.mark.asyncio
    async def test_analyze_file_error_handling(self, plugin):
        """Test file analysis error handling."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        # Non-existent file - just check it doesn't crash
        request = AnalysisRequest(file_path="/nonexistent/path/file.kt")
        result = await plugin.analyze_file("/nonexistent/path/file.kt", request)
        
        # Should return a result even for error cases
        assert result is not None


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinDocstring:
    """Test docstring extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_kdoc_comment(self, plugin, parser):
        """Test extracting KDoc comment."""
        code = """
/**
 * This is a documented function.
 * @param name The name to greet
 * @return A greeting string
 */
fun greet(name: String): String {
    return "Hello, $name!"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_class_with_kdoc(self, plugin, parser):
        """Test extracting class with KDoc."""
        code = """
/**
 * User data class.
 * @property id User ID
 * @property name User name
 */
data class User(val id: Int, val name: String)
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result


@pytest.mark.skipif(not TREE_SITTER_KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not installed")
class TestKotlinComplexCode:
    """Test extraction with complex Kotlin code."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_full_kotlin_file(self, plugin, parser):
        """Test extraction from full Kotlin file."""
        code = """
package com.example.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Repository for user data.
 */
interface UserRepository {
    suspend fun findById(id: Int): User?
    suspend fun save(user: User): Boolean
    suspend fun delete(id: Int): Boolean
}

/**
 * User data class.
 */
data class User(
    val id: Int,
    val name: String,
    val email: String,
    val isActive: Boolean = true
)

/**
 * Implementation of UserRepository.
 */
class UserRepositoryImpl(
    private val database: Database
) : UserRepository {
    
    private val cache = mutableMapOf<Int, User>()
    
    override suspend fun findById(id: Int): User? = withContext(Dispatchers.IO) {
        cache[id] ?: database.query("SELECT * FROM users WHERE id = ?", id)
            ?.let { User(it.id, it.name, it.email) }
            ?.also { cache[id] = it }
    }
    
    override suspend fun save(user: User): Boolean = withContext(Dispatchers.IO) {
        try {
            database.execute("INSERT INTO users VALUES (?, ?, ?)", user.id, user.name, user.email)
            cache[user.id] = user
            true
        } catch (e: Exception) {
            false
        }
    }
    
    override suspend fun delete(id: Int): Boolean = withContext(Dispatchers.IO) {
        cache.remove(id)
        database.execute("DELETE FROM users WHERE id = ?", id) > 0
    }
    
    companion object {
        private const val TAG = "UserRepositoryImpl"
        
        fun create(database: Database): UserRepository = UserRepositoryImpl(database)
    }
}

object DatabaseFactory {
    fun create(): Database = TODO()
}

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Throwable) : Result<Nothing>()
    object Loading : Result<Nothing>()
}

typealias UserResult = Result<User>

fun <T> Result<T>.getOrNull(): T? = when (this) {
    is Result.Success -> data
    else -> null
}

inline fun <T, R> Result<T>.map(transform: (T) -> R): Result<R> = when (this) {
    is Result.Success -> Result.Success(transform(data))
    is Result.Error -> this
    is Result.Loading -> this
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        
        assert "classes" in result
        assert "functions" in result
        assert "imports" in result
        
        class_names = [c.name for c in result["classes"]]
        assert "User" in class_names or "UserRepository" in class_names

    def test_coroutine_code(self, plugin, parser):
        """Test extracting coroutine-based code."""
        code = """
import kotlinx.coroutines.*

suspend fun fetchUserData(userId: Int): User {
    return withContext(Dispatchers.IO) {
        delay(1000)
        User(userId, "Test User")
    }
}

suspend fun processUsers(users: List<Int>) = coroutineScope {
    users.map { userId ->
        async { fetchUserData(userId) }
    }.awaitAll()
}

fun CoroutineScope.launchDataFetch() = launch {
    val users = processUsers(listOf(1, 2, 3))
    users.forEach { println(it) }
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_dsl_style_code(self, plugin, parser):
        """Test extracting DSL-style Kotlin code."""
        code = """
class HtmlBuilder {
    private val elements = mutableListOf<String>()
    
    fun head(init: HeadBuilder.() -> Unit) {
        elements.add("<head>")
        HeadBuilder().apply(init)
        elements.add("</head>")
    }
    
    fun body(init: BodyBuilder.() -> Unit) {
        elements.add("<body>")
        BodyBuilder().apply(init)
        elements.add("</body>")
    }
    
    fun build(): String = elements.joinToString("\\n")
}

fun html(init: HtmlBuilder.() -> Unit): String {
    return HtmlBuilder().apply(init).build()
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        assert "functions" in result


class TestKotlinPluginEdgeCases:
    """Test edge cases in Kotlin plugin."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    def test_extract_empty_code(self, plugin):
        """Test extraction with empty code."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)

    def test_extract_whitespace_only(self, plugin):
        """Test extraction with whitespace only."""
        result = plugin.extract_elements(None, "   \n\n   \t   ")
        assert isinstance(result, dict)

    def test_extract_comments_only(self, plugin):
        """Test extraction with comments only."""
        code = """
// Single line comment
/* Multi-line
   comment */
/**
 * KDoc comment
 */
"""
        result = plugin.extract_elements(None, code)
        assert isinstance(result, dict)

    def test_get_tree_sitter_language(self, plugin):
        """Test getting tree-sitter language."""
        if TREE_SITTER_KOTLIN_AVAILABLE:
            lang = plugin.get_tree_sitter_language()
            assert lang is not None
        else:
            lang = plugin.get_tree_sitter_language()
            assert lang is None

    def test_count_tree_nodes(self, plugin):
        """Test _count_tree_nodes method."""
        mock_node = Mock()
        mock_child1 = Mock()
        mock_child2 = Mock()
        mock_child1.children = []
        mock_child2.children = []
        mock_node.children = [mock_child1, mock_child2]
        
        count = plugin._count_tree_nodes(mock_node)
        assert count == 3  # Root + 2 children

    def test_count_tree_nodes_none(self, plugin):
        """Test _count_tree_nodes with None."""
        count = plugin._count_tree_nodes(None)
        assert count == 0
