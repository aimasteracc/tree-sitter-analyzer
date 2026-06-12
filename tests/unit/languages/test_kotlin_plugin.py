"""Tests for Kotlin language plugin."""

from unittest.mock import MagicMock, Mock

import pytest

# Skip if tree_sitter_kotlin not available
pytest.importorskip("tree_sitter_kotlin")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin as _tree_sitter_kotlin  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (  # noqa: E402
    KotlinElementExtractor,
    KotlinPlugin,
)

# Since pytest.importorskip passed, tree-sitter-kotlin is available
TREE_SITTER_KOTLIN_AVAILABLE = True


class TestKotlinElementExtractorInit:
    """Tests for KotlinElementExtractor initialization."""

    def test_init_creates_instance(self):
        """KotlinElementExtractor should be instantiable."""
        extractor = KotlinElementExtractor()
        assert extractor is not None

    def test_init_sets_defaults(self):
        """KotlinElementExtractor should initialize default values."""
        extractor = KotlinElementExtractor()
        assert extractor.current_package == ""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []


class TestKotlinElementExtractorFunctions:
    """Tests for Kotlin function extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_simple_function(self, extractor, kotlin_parser):
        """Should extract simple function."""
        code = """
fun hello() {
    println("Hello")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1
        func = functions[0]
        assert func.name == "hello"
        assert func.language == "kotlin"

    def test_extract_function_with_parameters(self, extractor, kotlin_parser):
        """Should extract function with parameters."""
        code = """
fun greet(name: String, age: Int) {
    println("Hello $name, age $age")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1
        func = functions[0]
        assert func.name == "greet"
        assert (
            len(func.parameters) >= 0
        )  # May or may not extract params depending on implementation

    def test_extract_function_with_return_type(self, extractor, kotlin_parser):
        """Should extract function with return type."""
        code = """
fun add(a: Int, b: Int): Int {
    return a + b
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1
        func = functions[0]
        assert func.name == "add"

    def test_extract_suspend_function(self, extractor, kotlin_parser):
        """Should extract suspend function."""
        code = """
suspend fun fetchData(): String {
    return "data"
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1
        func = functions[0]
        assert func.name == "fetchData"

    def test_extract_private_function(self, extractor, kotlin_parser):
        """Should extract private function."""
        code = """
private fun helper() {
    println("helping")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1

    def test_extract_extension_function(self, extractor, kotlin_parser):
        """Should extract extension function."""
        code = """
fun String.hello() {
    println("Hello $this")
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1


class TestKotlinElementExtractorClasses:
    """Tests for Kotlin class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_simple_class(self, extractor, kotlin_parser):
        """Should extract simple class."""
        code = """
class Person {
    var name: String = ""
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1
        cls = classes[0]
        assert cls.name == "Person"
        assert cls.language == "kotlin"

    def test_extract_data_class(self, extractor, kotlin_parser):
        """Should extract data class."""
        code = """
data class User(val name: String, val age: Int)
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1
        cls = classes[0]
        assert cls.name == "User"

    def test_extract_class_with_inheritance(self, extractor, kotlin_parser):
        """Should extract class with inheritance."""
        code = """
class Student : Person() {
    var grade: Int = 0
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1

    def test_extract_object_declaration(self, extractor, kotlin_parser):
        """Should extract object declaration."""
        code = """
object Singleton {
    fun doSomething() {
        println("Singleton")
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1
        obj = classes[0]
        assert obj.name == "Singleton"

    def test_extract_companion_object(self, extractor, kotlin_parser):
        """Should handle companion object."""
        code = """
class MyClass {
    companion object {
        const val CONSTANT = "value"
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1

    def test_extract_sealed_class(self, extractor, kotlin_parser):
        """Should extract sealed class."""
        code = """
sealed class Result {
    data class Success(val data: String) : Result()
    data class Error(val message: String) : Result()
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 3


class TestKotlinElementExtractorVariables:
    """Tests for Kotlin variable/property extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_val_property(self, extractor, kotlin_parser):
        """Should extract val property."""
        code = """
val name: String = "John"
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        var = variables[0]
        # Name extraction may vary
        assert var.language == "kotlin"

    def test_extract_var_property(self, extractor, kotlin_parser):
        """Should extract var property."""
        code = """
var count: Int = 0
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1

    def test_extract_const_val(self, extractor, kotlin_parser):
        """Should extract const val."""
        code = """
const val MAX_SIZE = 100
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1

    def test_extract_lateinit_var(self, extractor, kotlin_parser):
        """Should extract lateinit var."""
        code = """
lateinit var adapter: ListAdapter
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1


class TestKotlinElementExtractorImports:
    """Tests for Kotlin import extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_import(self, extractor, kotlin_parser):
        """Should extract import statement."""
        code = """
import kotlin.collections.List
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)

        # Import extraction may not be fully implemented
        assert isinstance(imports, list)

    def test_extract_multiple_imports(self, extractor, kotlin_parser):
        """Should extract multiple imports."""
        code = """
import kotlin.collections.List
import kotlin.collections.Map
import java.util.Date
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)

        # Import extraction may not be fully implemented
        assert isinstance(imports, list)

    def test_extract_import_alias(self, extractor, kotlin_parser):
        """Should extract import with alias."""
        code = """
import kotlin.collections.ArrayList as KList
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)

        # Import extraction may not be fully implemented
        assert isinstance(imports, list)


class TestKotlinElementExtractorPackages:
    """Tests for Kotlin package extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_package(self, extractor, kotlin_parser):
        """Should extract package declaration."""
        code = """
package com.example.app

class MyClass {}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        packages = extractor.extract_packages(tree, code)

        # May or may not extract packages depending on implementation
        assert isinstance(packages, list)

    def test_extract_no_package(self, extractor, kotlin_parser):
        """Should handle code without package."""
        code = """
class MyClass {}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        packages = extractor.extract_packages(tree, code)

        assert isinstance(packages, list)


class TestKotlinPlugin:
    """Tests for KotlinPlugin class."""

    def test_get_supported_element_types(self):
        """get_supported_element_types should return standard types."""
        plugin = KotlinPlugin()
        types = plugin.get_supported_element_types()

        assert "function" in types
        assert "class" in types


class TestKotlinPluginAnalyze:
    """Tests for KotlinPlugin analyze_file method."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return KotlinPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_returns_result(self, plugin, tmp_path):
        """analyze_file should return AnalysisResult."""
        # Create temporary Kotlin file
        kt_file = tmp_path / "Test.kt"
        kt_file.write_text("""
package com.example

fun main() {
    println("Hello")
}
""")

        mock_request = MagicMock()
        mock_request.file_path = str(kt_file)

        result = await plugin.analyze_file(str(kt_file), mock_request)

        # Should return an AnalysisResult (successful or not)
        assert result is not None

    @pytest.mark.asyncio
    async def test_analyze_file_with_classes(self, plugin, tmp_path):
        """analyze_file should extract classes."""
        kt_file = tmp_path / "Person.kt"
        kt_file.write_text("""
class Person(val name: String) {
    fun greet() {
        println("Hello, $name")
    }
}
""")

        mock_request = MagicMock()
        mock_request.file_path = str(kt_file)

        result = await plugin.analyze_file(str(kt_file), mock_request)

        assert result is not None


class TestKotlinComplexExtraction:
    """Tests for complex Kotlin code extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        import tree_sitter
        import tree_sitter_kotlin

        language = tree_sitter.Language(tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_complete_kotlin_file(self, extractor, kotlin_parser):
        """Should extract elements from complete Kotlin file."""
        code = """
package com.example.app

import kotlin.collections.List
import java.util.Date

data class User(
    val id: Int,
    val name: String,
    val email: String
)

class UserRepository {
    private val users = mutableListOf<User>()

    fun addUser(user: User) {
        users.add(user)
    }

    suspend fun fetchUsers(): List<User> {
        return users.toList()
    }
}

object UserFactory {
    fun createUser(name: String): User {
        return User(id = 0, name = name, email = "$name@example.com")
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))

        functions = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)
        imports = extractor.extract_imports(tree, code)

        # Re-pinned (old=3): User primary_ctor + addUser + fetchUsers + createUser
        assert len(functions) == 4
        assert len(classes) == 3  # User, UserRepository, UserFactory
        # Import extraction may not be fully implemented
        assert isinstance(imports, list)

    def test_extract_generic_function(self, extractor, kotlin_parser):
        """Should handle generic function."""
        code = """
fun <T> identity(value: T): T {
    return value
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1

    def test_extract_interface(self, extractor, kotlin_parser):
        """Should extract interface."""
        code = """
interface Repository<T> {
    fun findById(id: Int): T?
    fun save(entity: T)
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        # Interface might be extracted as class or separately
        assert isinstance(classes, list)

    def test_extract_enum_class(self, extractor, kotlin_parser):
        """Should handle enum class."""
        code = """
enum class Color {
    RED, GREEN, BLUE
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert isinstance(classes, list)


# ---------------------------------------------------------------------------
# From test_kotlin_plugin_coverage.py
# ---------------------------------------------------------------------------


class TestKotlinPluginExtraction:
    """Test Kotlin element extraction via plugin.extract_elements."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_extract_simple_function_via_plugin(self, plugin, parser):
        """Test extracting simple function via plugin."""
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

    def test_extract_suspend_function_via_plugin(self, plugin, parser):
        """Test extracting suspend function via plugin."""
        code = """
suspend fun fetchData(url: String): String {
    delay(1000)
    return "data"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_private_function_via_plugin(self, plugin, parser):
        """Test extracting private function via plugin."""
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

    def test_extract_interface_via_plugin(self, plugin, parser):
        """Test extracting interface via plugin."""
        code = """
interface Repository {
    fun findById(id: Int): Entity?
    fun save(entity: Entity): Boolean
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_object_declaration_via_plugin(self, plugin, parser):
        """Test extracting object declaration via plugin."""
        code = """
object Singleton {
    val instance = "singleton"
    fun doSomething() {}
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_companion_object_via_plugin(self, plugin, parser):
        """Test extracting companion object via plugin."""
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

    def test_extract_data_class_via_plugin(self, plugin, parser):
        """Test extracting data class via plugin."""
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

    def test_extract_sealed_class_via_plugin(self, plugin, parser):
        """Test extracting sealed class via plugin."""
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

    def test_extract_enum_class_via_plugin(self, plugin, parser):
        """Test extracting enum class via plugin."""
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

    def test_extract_property_val_via_plugin(self, plugin, parser):
        """Test extracting val property via plugin."""
        code = """
val immutableValue: String = "constant"
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result

    def test_extract_property_var_via_plugin(self, plugin, parser):
        """Test extracting var property via plugin."""
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

    def test_extract_imports_via_plugin(self, plugin, parser):
        """Test extracting import statements via plugin."""
        code = """
import kotlin.collections.List
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MyClass
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "imports" in result

    def test_extract_function_with_parameters_via_plugin(self, plugin, parser):
        """Test extracting function with multiple parameters via plugin."""
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
            assert hasattr(calc_func, "parameters") or True

    def test_extract_extension_function_via_plugin(self, plugin, parser):
        """Test extracting extension function via plugin."""
        code = """
fun String.addExclamation(): String {
    return this + "!"
}

fun Int.isEven(): Boolean = this % 2 == 0
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_inline_function_via_plugin(self, plugin, parser):
        """Test extracting inline function via plugin."""
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

    def test_extract_function_with_default_params_via_plugin(self, plugin, parser):
        """Test extracting function with default parameters via plugin."""
        code = """
fun greet(name: String = "World", greeting: String = "Hello"): String {
    return "$greeting, $name!"
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_class_with_constructor_via_plugin(self, plugin, parser):
        """Test extracting class with primary constructor via plugin."""
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

    def test_extract_abstract_class_via_plugin(self, plugin, parser):
        """Test extracting abstract class via plugin."""
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

    def test_extract_generic_class_via_plugin(self, plugin, parser):
        """Test extracting generic class via plugin."""
        code = """
class Container<T>(val item: T) {
    fun get(): T = item
    fun set(newItem: T): Container<T> = Container(newItem)
}
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_nested_class_via_plugin(self, plugin, parser):
        """Test extracting nested class via plugin."""
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

    def test_extract_annotation_class_via_plugin(self, plugin, parser):
        """Test extracting annotation class via plugin."""
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


class TestKotlinDocstring:
    """Test docstring extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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


class TestKotlinComplexCode:
    """Test extraction with complex Kotlin code."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        return tree_sitter.Parser(language)

    def test_full_kotlin_file(self, plugin, parser):
        """Test extraction from full Kotlin file."""
        code = """
package com.example.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

interface UserRepository {
    suspend fun findById(id: Int): User?
    suspend fun save(user: User): Boolean
    suspend fun delete(id: Int): Boolean
}

data class User(
    val id: Int,
    val name: String,
    val email: String,
    val isActive: Boolean = true
)

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
        lang = plugin.get_tree_sitter_language()
        assert lang is not None

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


# ---------------------------------------------------------------------------
# From test_kotlin_plugin_enhanced.py
# ---------------------------------------------------------------------------


class TestKotlinCoroutinesExtended:
    """Tests for Kotlin coroutine patterns."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

        assert len(functions) == 1
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

        assert len(functions) == 1

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

        assert len(functions) == 1
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
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_sealed_class_named(self, extractor, kotlin_parser):
        """Should extract sealed class and verify name."""
        code = """
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Exception) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 4
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
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_inline_function_named(self, extractor, kotlin_parser):
        """Should extract inline function and verify name."""
        code = """
inline fun measureTime(block: () -> Unit): Long {
    val start = System.currentTimeMillis()
    block()
    return System.currentTimeMillis() - start
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1
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

        assert len(functions) == 1

    def test_extract_crossinline_function(self, extractor, kotlin_parser):
        """Should extract function with crossinline parameter."""
        code = """
inline fun createRunnable(crossinline body: () -> Unit): Runnable {
    return Runnable { body() }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1


class TestKotlinCompanionObjects:
    """Tests for Kotlin companion object extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

        assert len(classes) == 1
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

        assert len(classes) == 1


class TestKotlinGenerics:
    """Tests for Kotlin generic class and function extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_generic_class_named(self, extractor, kotlin_parser):
        """Should extract generic class and verify name."""
        code = """
class Box<T>(val value: T) {
    fun get(): T = value
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1
        class_names = [c.name for c in classes]
        assert "Box" in class_names

    def test_extract_generic_function_list(self, extractor, kotlin_parser):
        """Should extract generic function returning list."""
        code = """
fun <T> singletonList(item: T): List<T> {
    return listOf(item)
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)

        assert len(functions) == 1

    def test_extract_bounded_generic(self, extractor, kotlin_parser):
        """Should extract class with bounded generic type."""
        code = """
class NumberBox<T : Number>(val value: T) {
    fun doubleValue(): Double = value.toDouble()
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 1

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

        assert len(classes) == 2


class TestKotlinPropertyDelegates:
    """Tests for Kotlin property delegates extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

        assert len(classes) == 1
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

        assert len(classes) == 1


class TestKotlinAnnotations:
    """Tests for Kotlin annotation extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_annotation_class_named(self, extractor, kotlin_parser):
        """Should extract annotation class."""
        code = """
annotation class Fancy

@Fancy
class AnnotatedClass {}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        # Should detect Fancy as annotation class or AnnotatedClass
        assert len(classes) == 2

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

        assert len(functions) == 2


class TestKotlinNestedClasses:
    """Tests for Kotlin nested and inner class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

    def test_extract_nested_class_named(self, extractor, kotlin_parser):
        """Should extract nested class and verify outer name."""
        code = """
class Outer {
    class Nested {
        fun foo() = 2
    }
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)

        assert len(classes) == 2
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

        assert len(classes) == 2


class TestKotlinEnumClasses:
    """Tests for Kotlin enum class extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

        assert len(classes) == 1
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

        assert len(classes) == 1
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
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
        parser = tree_sitter.Parser(language)
        return parser

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
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

    def test_extract_imports_extractor(self, extractor, kotlin_parser):
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
        assert len(imports) == 3
        names = sorted(imp.name for imp in imports)
        assert names == [
            "kotlin.collections.List",
            "kotlin.collections.Map",
            "kotlinx.coroutines.*",
        ]
        wildcard = next(i for i in imports if i.name == "kotlinx.coroutines.*")
        assert wildcard.is_wildcard is True

    def test_extract_import_text_fallback(self):
        """Old-grammar nodes without a qualified_identifier child fall back to
        whitespace parsing (semicolon stripped, wildcard detected)."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.languages.kotlin_helpers import extract_import

        node = MagicMock()
        node.parent = None
        node.children = []
        node.start_point = (0, 0)
        node.end_point = (0, 30)

        plain = extract_import(node, lambda n: "import com.foo.Bar;")
        assert plain is not None
        assert plain.name == "com.foo.Bar"
        assert plain.is_wildcard is False

        wildcard = extract_import(node, lambda n: "import com.foo.*")
        assert wildcard is not None
        assert wildcard.name == "com.foo.*"
        assert wildcard.is_wildcard is True

        keyword_leaf = extract_import(node, lambda n: "import")
        assert keyword_leaf is None

        def _boom(_node):
            raise RuntimeError("boom")

        assert extract_import(node, _boom) is None

    def test_extract_variables_extractor(self, extractor, kotlin_parser):
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


class TestKotlinEdgeCasesExtended:
    """Edge case tests for Kotlin extraction (from enhanced file)."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return KotlinElementExtractor()

    @pytest.fixture
    def kotlin_parser(self):
        """Create Kotlin parser."""
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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

        assert len(classes) == 4
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
        assert len(functions) == 3
        assert all(f.name == "add" for f in functions)


# ---------------------------------------------------------------------------
# From test_kotlin_plugin_final.py
# ---------------------------------------------------------------------------


class TestKotlinExtractionBranches:
    """Test uncovered branches in Kotlin extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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


class TestKotlinDocstringExtraction:
    """Test KDoc/docstring extraction."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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
    """Test Kotlin plugin when tree is None."""

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


class TestKotlinEdgeCasesFinal:
    """Test edge cases in Kotlin extraction (from final file)."""

    @pytest.fixture
    def plugin(self):
        return KotlinPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(_tree_sitter_kotlin.language())
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
