"""RED-first tests for three extraction gaps fixed in one PR:

  1. Kotlin inheritance: delegation_specifiers → superclass / interfaces
  2. Scala inheritance: extends_clause → superclass / interfaces
  3. Kotlin primary constructors: primary_constructor node → Function(is_constructor=True)

All inline fixtures; live-parse via tree_sitter_{kotlin,scala}.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_kotlin")
pytest.importorskip("tree_sitter_scala")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin  # noqa: E402
import tree_sitter_scala  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (  # noqa: E402
    KotlinElementExtractor,
)
from tree_sitter_analyzer.languages.scala_plugin import (  # noqa: E402
    ScalaElementExtractor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kotlin_parser() -> tree_sitter.Parser:
    lang = tree_sitter_kotlin.language()
    if "Language" not in str(type(lang)):
        lang = tree_sitter.Language(lang)
    return tree_sitter.Parser(lang)


def _scala_parser() -> tree_sitter.Parser:
    lang = tree_sitter_scala.language()
    if "Language" not in str(type(lang)):
        lang = tree_sitter.Language(lang)
    return tree_sitter.Parser(lang)


# ---------------------------------------------------------------------------
# Gap 1 — Kotlin inheritance via delegation_specifiers
# ---------------------------------------------------------------------------


KOTLIN_INHERITANCE_SRC = """\
package demo

interface Displayable {
    fun display(): String
}

interface Serializable

open class Result(val value: Int)

class Success(value: Int) : Result(value)

class UserManager(private val db: Any?) : Displayable, Serializable {
    override fun display(): String = "ok"
}
"""


class TestKotlinInheritance:
    """delegation_specifiers → superclass / interfaces populated."""

    @pytest.fixture
    def classes(self) -> dict[str, object]:
        parser = _kotlin_parser()
        tree = parser.parse(KOTLIN_INHERITANCE_SRC.encode())
        ext = KotlinElementExtractor()
        return {c.name: c for c in ext.extract_classes(tree, KOTLIN_INHERITANCE_SRC)}

    def test_success_extends_result(self, classes: dict) -> None:
        """constructor_invocation child → superclass."""
        cls = classes["Success"]
        assert cls.superclass == "Result"

    def test_success_no_interfaces(self, classes: dict) -> None:
        cls = classes["Success"]
        assert cls.interfaces == []

    def test_user_manager_no_superclass(self, classes: dict) -> None:
        """When only user_type children present (no constructor_invocation) all
        are treated as interfaces; superclass stays None."""
        cls = classes["UserManager"]
        assert cls.superclass is None

    def test_user_manager_interfaces(self, classes: dict) -> None:
        """Two user_type delegation_specifiers → interfaces list."""
        cls = classes["UserManager"]
        assert cls.interfaces == ["Displayable", "Serializable"]

    def test_plain_class_no_delegation(self, classes: dict) -> None:
        """Result has no delegation_specifiers — fields stay default."""
        cls = classes["Result"]
        assert cls.superclass is None
        assert cls.interfaces == []

    def test_class_count_unchanged(self, classes: dict) -> None:
        """No extra classes emitted by reading delegation_specifiers."""
        # Displayable, Serializable, Result, Success, UserManager
        assert len(classes) == 5


# ---------------------------------------------------------------------------
# Gap 2 — Scala inheritance via extends_clause
# ---------------------------------------------------------------------------


SCALA_INHERITANCE_SRC = """\
package demo

abstract class Shape(val color: String)

class Circle(radius: Double, color: String) extends Shape(color) with Drawable with Serializable {
  def area(): Double = 3.14
}

class Rectangle extends Shape("red") with Drawable

trait Drawable {
  def draw(): Unit
}

class Standalone {
  def foo(): Unit = ()
}
"""


class TestScalaInheritance:
    """extends_clause → superclass / interfaces populated."""

    @pytest.fixture
    def classes(self) -> dict[str, object]:
        parser = _scala_parser()
        tree = parser.parse(SCALA_INHERITANCE_SRC.encode())
        ext = ScalaElementExtractor()
        return {c.name: c for c in ext.extract_classes(tree, SCALA_INHERITANCE_SRC)}

    def test_circle_superclass(self, classes: dict) -> None:
        """First type_identifier after 'extends' = superclass."""
        assert classes["Circle"].superclass == "Shape"

    def test_circle_interfaces(self, classes: dict) -> None:
        """type_identifier after 'with' keywords = interfaces."""
        assert classes["Circle"].interfaces == ["Drawable", "Serializable"]

    def test_rectangle_superclass(self, classes: dict) -> None:
        assert classes["Rectangle"].superclass == "Shape"

    def test_rectangle_interfaces(self, classes: dict) -> None:
        assert classes["Rectangle"].interfaces == ["Drawable"]

    def test_shape_no_extends(self, classes: dict) -> None:
        """Abstract base class — no extends_clause."""
        assert classes["Shape"].superclass is None
        assert classes["Shape"].interfaces == []

    def test_standalone_no_extends(self, classes: dict) -> None:
        assert classes["Standalone"].superclass is None
        assert classes["Standalone"].interfaces == []

    def test_class_count_unchanged(self, classes: dict) -> None:
        """No extra classes emitted by reading extends_clause."""
        # Shape, Circle, Rectangle, Drawable (as trait), Standalone
        assert len(classes) == 5


# ---------------------------------------------------------------------------
# Gap 3 — Kotlin primary constructors emitted as Functions
# ---------------------------------------------------------------------------


KOTLIN_PRIMARY_CTOR_SRC = """\
package demo

data class Point(val x: Int, val y: Int)

class Named(val name: String, val age: Int) {
    fun greet(): String = "Hello ${'$'}name"
}

class NoArgs {
    fun doWork() {}
}
"""


class TestKotlinPrimaryConstructors:
    """primary_constructor nodes emitted as Function(is_constructor=True)."""

    @pytest.fixture
    def functions(self) -> list:
        parser = _kotlin_parser()
        tree = parser.parse(KOTLIN_PRIMARY_CTOR_SRC.encode())
        ext = KotlinElementExtractor()
        return ext.extract_functions(tree, KOTLIN_PRIMARY_CTOR_SRC)

    def test_point_ctor_emitted(self, functions: list) -> None:
        ctors = [f for f in functions if f.name == "Point"]
        assert len(ctors) == 1

    def test_point_ctor_is_constructor_true(self, functions: list) -> None:
        ctor = next(f for f in functions if f.name == "Point")
        assert ctor.is_constructor is True

    def test_point_ctor_parameters(self, functions: list) -> None:
        """Primary constructor parameters extracted."""
        ctor = next(f for f in functions if f.name == "Point")
        assert len(ctor.parameters) == 2

    def test_named_ctor_emitted(self, functions: list) -> None:
        ctors = [f for f in functions if f.name == "Named"]
        assert len(ctors) == 1

    def test_named_ctor_params(self, functions: list) -> None:
        ctor = next(f for f in functions if f.name == "Named")
        assert len(ctor.parameters) == 2

    def test_noargs_class_no_ctor(self, functions: list) -> None:
        """class NoArgs {} has no primary_constructor node — not emitted."""
        ctors = [f for f in functions if f.name == "NoArgs"]
        assert len(ctors) == 0

    def test_regular_methods_still_present(self, functions: list) -> None:
        """greet and doWork still extracted."""
        names = {f.name for f in functions}
        assert "greet" in names
        assert "doWork" in names

    def test_total_function_count(self, functions: list) -> None:
        """Point ctor + Named ctor + greet + doWork = 4."""
        assert len(functions) == 4

    def test_ctor_language_kotlin(self, functions: list) -> None:
        ctor = next(f for f in functions if f.name == "Point")
        assert ctor.language == "kotlin"
