"""Tests for Kotlin extraction bugs #759, #760, #761.

#759: Local val/var inside method bodies must NOT be extracted as properties.
#760: Property modifiers (private, protected, internal, override, lateinit, const)
      must be captured and reflected in visibility + modifiers fields.
#761: Kotlin constructor return_type must be None, not "void".
"""

import pytest

pytest.importorskip("tree_sitter_kotlin")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (
    KotlinElementExtractor,  # noqa: E402
)


@pytest.fixture(scope="module")
def kotlin_parser():
    language = tree_sitter.Language(tree_sitter_kotlin.language())
    return tree_sitter.Parser(language)


@pytest.fixture
def extractor():
    return KotlinElementExtractor()


# ---------------------------------------------------------------------------
# Bug #759 – local val/var inside method bodies extracted as class fields
# ---------------------------------------------------------------------------


class TestBug759LocalVarNotExtractedAsField:
    """Local val/var inside function bodies must not appear in extract_variables."""

    def test_local_val_inside_method_excluded(self, extractor, kotlin_parser):
        code = """\
class Dog {
    val breed: String = "Lab"

    fun bark() {
        val sound = "Woof"
    }
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        # Only the class field "breed" should be extracted; "sound" is local
        assert "sound" not in names
        assert "breed" in names
        assert len(variables) == 1

    def test_local_var_inside_method_excluded(self, extractor, kotlin_parser):
        code = """\
class Cat {
    var lives: Int = 9

    fun hiss() {
        var volume = 5
        var pitch = 10
    }
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "volume" not in names
        assert "pitch" not in names
        assert "lives" in names
        assert len(variables) == 1

    def test_local_val_in_nested_block_excluded(self, extractor, kotlin_parser):
        """val inside an if-block or for-loop is also local."""
        code = """\
class Example {
    val id: Int = 1

    fun compute(): Int {
        val result = if (id > 0) {
            val tmp = id * 2
            tmp
        } else 0
        return result
    }
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "result" not in names
        assert "tmp" not in names
        assert "id" in names
        assert len(variables) == 1

    def test_top_level_val_still_extracted(self, extractor, kotlin_parser):
        """Top-level (file-scope) val must still be extracted."""
        code = """\
val topLevel: String = "hello"
var mutable: Int = 42
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "topLevel" in names
        assert "mutable" in names
        assert len(variables) == 2

    def test_class_field_and_local_mixed(self, extractor, kotlin_parser):
        """Class field extracted, local variable skipped, in the same class."""
        code = """\
class Manager {
    private val maxRetries: Int = 3
    internal var timeout: Long = 5000

    fun retry() {
        val attempt = 0
        var lastError: String = ""
    }
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "maxRetries" in names
        assert "timeout" in names
        assert "attempt" not in names
        assert "lastError" not in names
        assert len(variables) == 2


# ---------------------------------------------------------------------------
# Bug #760 – property modifiers not captured
# ---------------------------------------------------------------------------


class TestBug760PropertyModifiers:
    """Modifier keywords must be captured and visibility must be set correctly."""

    def test_private_val_visibility(self, extractor, kotlin_parser):
        code = """\
class Foo {
    private val secret: String = "x"
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        v = variables[0]
        assert v.name == "secret"
        assert v.visibility == "private"

    def test_protected_var_visibility(self, extractor, kotlin_parser):
        code = """\
open class Animal {
    protected var age: Int = 0
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        assert variables[0].visibility == "protected"

    def test_internal_visibility(self, extractor, kotlin_parser):
        code = """\
class Service {
    internal var config: String = ""
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        assert variables[0].visibility == "internal"

    def test_public_val_is_val(self, extractor, kotlin_parser):
        """val without modifiers: is_val=True, is_var=False."""
        code = """\
class Box {
    val width: Int = 10
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        v = variables[0]
        assert v.is_val == True  # noqa: E712
        assert v.is_var == False  # noqa: E712

    def test_private_val_is_val(self, extractor, kotlin_parser):
        """private val: is_val=True despite modifier prefix."""
        code = """\
class Box {
    private val width: Int = 10
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        v = variables[0]
        assert v.name == "width"
        assert v.is_val == True  # noqa: E712
        assert v.is_var == False  # noqa: E712

    def test_private_var_is_var(self, extractor, kotlin_parser):
        """private var: is_var=True despite modifier prefix."""
        code = """\
class Box {
    private var height: Int = 5
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        v = variables[0]
        assert v.name == "height"
        assert v.is_val == False  # noqa: E712
        assert v.is_var == True  # noqa: E712

    def test_override_val_modifiers(self, extractor, kotlin_parser):
        """override val: modifiers list contains 'override'."""
        code = """\
open class Animal {
    open val sound: String = ""
}
class Dog : Animal() {
    override val sound: String = "Woof"
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        override_vars = [
            v
            for v in variables
            if v.name == "sound" and "override" in getattr(v, "modifiers", [])
        ]
        assert len(override_vars) == 1

    def test_lateinit_var_modifiers(self, extractor, kotlin_parser):
        """lateinit var: modifiers list contains 'lateinit'."""
        code = """\
class Service {
    lateinit var repository: String
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        v = variables[0]
        assert v.name == "repository"
        assert "lateinit" in v.modifiers

    def test_property_name_extracted_with_modifiers(self, extractor, kotlin_parser):
        """Name must be correct even when modifiers precede the val/var keyword."""
        code = """\
class Config {
    private val maxSize: Int = 100
    protected var minSize: Int = 1
    internal lateinit var label: String
}
"""
        tree = kotlin_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = {v.name for v in variables}
        assert names == {"maxSize", "minSize", "label"}


# ---------------------------------------------------------------------------
# Bug #761 – Kotlin constructor return_type should be None, not "void"
# ---------------------------------------------------------------------------


class TestBug761ConstructorReturnType:
    """Primary constructors must have return_type=None."""

    def test_primary_constructor_return_type_none(self, extractor, kotlin_parser):
        code = """\
class Point(val x: Int, val y: Int)
"""
        tree = kotlin_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        ctors = [f for f in functions if getattr(f, "is_constructor", False)]
        assert len(ctors) == 1
        ctor = ctors[0]
        assert ctor.name == "Point"
        assert ctor.return_type is None

    def test_primary_constructor_with_visibility_return_type_none(
        self, extractor, kotlin_parser
    ):
        """Even with explicit `constructor` keyword and visibility, return_type=None."""
        code = """\
class Service private constructor(val name: String)
"""
        tree = kotlin_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        ctors = [f for f in functions if getattr(f, "is_constructor", False)]
        assert len(ctors) == 1
        assert ctors[0].return_type is None

    def test_primary_constructor_data_class_return_type_none(
        self, extractor, kotlin_parser
    ):
        code = """\
data class User(val id: Long, val name: String, var email: String)
"""
        tree = kotlin_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        ctors = [f for f in functions if getattr(f, "is_constructor", False)]
        assert len(ctors) == 1
        assert ctors[0].return_type is None

    def test_primary_constructor_is_constructor_true(self, extractor, kotlin_parser):
        """is_constructor flag must be set."""
        code = """\
class Node(val value: Int)
"""
        tree = kotlin_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        ctors = [f for f in functions if getattr(f, "is_constructor", False)]
        assert len(ctors) == 1
        assert ctors[0].is_constructor == True  # noqa: E712

    def test_regular_functions_not_affected(self, extractor, kotlin_parser):
        """Regular functions should keep their return_type (not None)."""
        code = """\
class Foo {
    fun bar(): String = "x"
    fun baz(): Unit {}
}
"""
        tree = kotlin_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        regular = [f for f in functions if not getattr(f, "is_constructor", False)]
        assert len(regular) == 2
        names = {f.name for f in regular}
        assert names == {"bar", "baz"}
        for f in regular:
            # return_type is not None for regular functions
            assert f.return_type is not None
