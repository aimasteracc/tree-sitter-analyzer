#!/usr/bin/env python3
"""Tests for Scala extraction bugs #762 and #764.

#762: Scala enum case values dropped — `enum Color { case Red, Green, Blue }`
      must extract Red, Green, Blue as enum members.

#764: Scala `given`, `extension`, and `type` aliases inside an object/trait
      must carry parent_class="<owner>".
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_scala

from tree_sitter_analyzer.languages.scala_plugin import ScalaElementExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(source: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(tree_sitter_scala.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(source.encode("utf-8"))


def _classes(source: str) -> dict[str, object]:
    extractor = ScalaElementExtractor()
    return {c.name: c for c in extractor.extract_classes(_parse(source), source)}


def _functions(source: str) -> dict[str, object]:
    extractor = ScalaElementExtractor()
    return {f.name: f for f in extractor.extract_functions(_parse(source), source)}


def _variables(source: str) -> dict[str, object]:
    extractor = ScalaElementExtractor()
    return {v.name: v for v in extractor.extract_variables(_parse(source), source)}


# ---------------------------------------------------------------------------
# Bug #762: Scala enum case values must be extracted as enum members
# ---------------------------------------------------------------------------


_ENUM_SIMPLE = """\
enum Color:
  case Red
  case Green
  case Blue
"""

_ENUM_MULTI = """\
enum Direction:
  case North, South, East, West
"""

_ENUM_WITH_PARAMS = """\
enum Planet(mass: Double, radius: Double):
  case Mercury extends Planet(3.303e+23, 2.4397e6)
  case Venus extends Planet(4.869e+24, 6.0518e6)
"""


class TestEnumCaseExtraction:
    """#762: enum case values must appear in the extracted elements."""

    def test_enum_itself_extracted(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert "Color" in classes

    def test_enum_class_type(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert classes["Color"].class_type == "enum"

    def test_simple_enum_cases_count(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        # Color + Red + Green + Blue = 4
        assert len(classes) == 4

    def test_red_extracted(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert "Red" in classes

    def test_green_extracted(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert "Green" in classes

    def test_blue_extracted(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert "Blue" in classes

    def test_enum_case_class_type(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert classes["Red"].class_type == "enum_member"

    def test_enum_case_parent_class(self) -> None:
        classes = _classes(_ENUM_SIMPLE)
        assert classes["Red"].parent_class == "Color"
        assert classes["Green"].parent_class == "Color"
        assert classes["Blue"].parent_class == "Color"

    def test_multi_case_on_one_line_count(self) -> None:
        classes = _classes(_ENUM_MULTI)
        # Direction + North + South + East + West = 5
        assert len(classes) == 5

    def test_multi_case_names_extracted(self) -> None:
        classes = _classes(_ENUM_MULTI)
        assert "North" in classes
        assert "South" in classes
        assert "East" in classes
        assert "West" in classes

    def test_multi_case_parent_class(self) -> None:
        classes = _classes(_ENUM_MULTI)
        assert classes["North"].parent_class == "Direction"

    def test_enum_with_params_cases_count(self) -> None:
        classes = _classes(_ENUM_WITH_PARAMS)
        # Planet + Mercury + Venus = 3
        assert len(classes) == 3

    def test_enum_with_params_case_names(self) -> None:
        classes = _classes(_ENUM_WITH_PARAMS)
        assert "Mercury" in classes
        assert "Venus" in classes

    def test_enum_with_params_case_parent(self) -> None:
        classes = _classes(_ENUM_WITH_PARAMS)
        assert classes["Mercury"].parent_class == "Planet"

    def test_full_enum_cases_with_constructor_params_are_extracted(self) -> None:
        code = """\
enum Command:
  case Quit
  case Move(dx: Int, dy: Int)
  case Error(code: Int) extends Command
"""
        classes = _classes(code)
        assert classes["Move"].class_type == "enum_member"
        assert classes["Move"].parent_class == "Command"
        assert "dx: Int" in classes["Move"].raw_text
        assert classes["Error"].superclass == "Command"

    def test_enum_modifiers_are_preserved(self) -> None:
        classes = _classes(
            """\
private enum Secret:
  case Token
"""
        )
        assert classes["Secret"].visibility == "private"
        assert "private" in classes["Secret"].modifiers


# ---------------------------------------------------------------------------
# Bug #764: given/type/extension inside object/trait must carry parent_class
# ---------------------------------------------------------------------------


_GIVEN_IN_OBJECT = """\
object Instances {
  given intOrdering: Ordering[Int] = Ordering.Int
  given stringOrdering: Ordering[String] = Ordering.String
}
"""

_TYPE_IN_OBJECT = """\
object Types {
  type MyInt = Int
  type MyString = String
}
"""

_GIVEN_IN_TRAIT = """\
trait Defaults {
  given defaultString: String = "hello"
}
"""

_NESTED_MIX = """\
object Outer {
  given outerGiven: Int = 42
  type AliasT = Long

  object Inner {
    given innerGiven: Boolean = true
  }
}
"""


class TestGivenTypeParentClass:
    """#764: given/type constructs must carry parent_class of their enclosing scope."""

    # --- given_definition inside object ---

    def test_given_in_object_classes_extracted(self) -> None:
        classes = _classes(_GIVEN_IN_OBJECT)
        # Instances + intOrdering + stringOrdering = 3
        assert len(classes) == 3

    def test_given_intOrdering_extracted(self) -> None:
        classes = _classes(_GIVEN_IN_OBJECT)
        assert "intOrdering" in classes

    def test_given_stringOrdering_extracted(self) -> None:
        classes = _classes(_GIVEN_IN_OBJECT)
        assert "stringOrdering" in classes

    def test_given_parent_class_is_object(self) -> None:
        classes = _classes(_GIVEN_IN_OBJECT)
        assert classes["intOrdering"].parent_class == "Instances"
        assert classes["stringOrdering"].parent_class == "Instances"

    def test_given_class_type(self) -> None:
        classes = _classes(_GIVEN_IN_OBJECT)
        assert classes["intOrdering"].class_type == "given"

    # --- type_definition inside object ---

    def test_type_alias_in_object_count(self) -> None:
        classes = _classes(_TYPE_IN_OBJECT)
        # Types + MyInt + MyString = 3
        assert len(classes) == 3

    def test_type_alias_extracted(self) -> None:
        classes = _classes(_TYPE_IN_OBJECT)
        assert "MyInt" in classes
        assert "MyString" in classes

    def test_type_alias_parent_class(self) -> None:
        classes = _classes(_TYPE_IN_OBJECT)
        assert classes["MyInt"].parent_class == "Types"
        assert classes["MyString"].parent_class == "Types"

    def test_type_alias_class_type(self) -> None:
        classes = _classes(_TYPE_IN_OBJECT)
        assert classes["MyInt"].class_type == "type_alias"

    # --- given inside trait ---

    def test_given_in_trait_parent_class(self) -> None:
        classes = _classes(_GIVEN_IN_TRAIT)
        assert "defaultString" in classes
        assert classes["defaultString"].parent_class == "Defaults"

    # --- nested objects: inner given must reference Inner, not Outer ---

    def test_nested_inner_given_parent_class(self) -> None:
        classes = _classes(_NESTED_MIX)
        assert classes["innerGiven"].parent_class == "Inner"

    def test_nested_outer_given_parent_class(self) -> None:
        classes = _classes(_NESTED_MIX)
        assert classes["outerGiven"].parent_class == "Outer"

    def test_nested_type_alias_parent_class(self) -> None:
        classes = _classes(_NESTED_MIX)
        assert classes["AliasT"].parent_class == "Outer"

    def test_local_given_and_type_inside_method_are_not_members(self) -> None:
        classes = _classes(
            """\
object Ops:
  def configure(): Unit =
    given localOrdering: Ordering[Int] = Ordering.Int
    type LocalAlias = String
"""
        )
        assert "localOrdering" not in classes
        assert "LocalAlias" not in classes

    def test_given_and_type_modifiers_are_preserved(self) -> None:
        classes = _classes(
            """\
object Api:
  private given secret: String = "s"
  protected type Hidden = Int
"""
        )
        assert classes["secret"].visibility == "private"
        assert "private" in classes["secret"].modifiers
        assert classes["Hidden"].visibility == "protected"
        assert "protected" in classes["Hidden"].modifiers

    def test_qualified_access_class_visibility_is_private(self) -> None:
        # #961 regression: ``_scala_modifiers`` yields the literal token
        # ``private[pkg]`` (not bare ``private``), so the exact-membership
        # check reported ``public``. Match the keyword as a prefix instead.
        classes = _classes("private[pkg] class Secret(x: Int)\n")
        assert classes["Secret"].visibility == "private"

    def test_qualified_access_protected_def_visibility(self) -> None:
        functions = _functions(
            """\
object O:
  protected[this] def f(): Int = 1
"""
        )
        assert functions["f"].visibility == "protected"

    def test_anonymous_givens_use_distinct_type_based_names(self) -> None:
        classes = _classes(
            """\
object Instances:
  given Ordering[Int] = Ordering.Int
  given Ordering[String] = Ordering.String
"""
        )
        assert "given Ordering[Int]" in classes
        assert "given Ordering[String]" in classes

    def test_abstract_type_members_are_not_reported_as_aliases(self) -> None:
        classes = _classes(
            """\
trait Api:
  type Out
  type In <: String
  type Alias = Int
"""
        )
        assert classes["Out"].class_type == "type_member"
        assert classes["In"].class_type == "type_member"
        assert classes["Alias"].class_type == "type_alias"

    def test_extension_symbol_and_method_keep_owner_context(self) -> None:
        code = """\
object Ops:
  extension (s: String)
    def shout: String = s.toUpperCase
"""
        classes = _classes(code)
        functions = _functions(code)
        assert classes["extension[String]"].class_type == "extension"
        assert classes["extension[String]"].parent_class == "Ops"
        assert functions["shout"].parent_class == "Ops"
        assert functions["shout"].receiver_type == "String"


class TestScalaVisibilityBranches:
    """#972: cover every prefix branch of ``_scala_visibility`` / ``_scala_modifiers``."""

    def test_private_qualified_class_is_private(self) -> None:
        classes = _classes("private[pkg] class Secret(x: Int)\n")
        assert classes["Secret"].visibility == "private"
        assert classes["Secret"].modifiers == ["private[pkg]"]

    def test_protected_qualified_def_is_protected(self) -> None:
        functions = _functions(
            """\
object O:
  protected[this] def f(): Int = 1
"""
        )
        assert functions["f"].visibility == "protected"
        assert functions["f"].modifiers == ["protected[this]"]

    def test_bare_private_class_is_private(self) -> None:
        classes = _classes("private class Hidden(x: Int)\n")
        assert classes["Hidden"].visibility == "private"

    def test_bare_protected_class_is_protected(self) -> None:
        classes = _classes("protected class Guarded(x: Int)\n")
        assert classes["Guarded"].visibility == "protected"

    def test_no_modifier_class_defaults_public(self) -> None:
        classes = _classes("class Plain(x: Int)\n")
        assert classes["Plain"].visibility == "public"
        assert classes["Plain"].modifiers == []

    def test_non_visibility_modifier_stays_public(self) -> None:
        # ``final`` is a modifier but not a visibility keyword: visibility stays
        # public while the modifier is still captured.
        classes = _classes("final class Sealed(x: Int)\n")
        assert classes["Sealed"].visibility == "public"
        assert classes["Sealed"].modifiers == ["final"]


class TestScalaGivenNameBranches:
    """#972: cover the named / typed / anonymous arms of ``_scala_given_name``."""

    def test_named_given_uses_identifier(self) -> None:
        classes = _classes("object O:\n  given namedGiven: Int = 1\n")
        assert "namedGiven" in classes

    def test_anonymous_given_uses_generic_type(self) -> None:
        classes = _classes("object O:\n  given Ordering[Int] = ???\n")
        assert classes["given Ordering[Int]"].class_type == "given"

    def test_anonymous_given_uses_tuple_type(self) -> None:
        classes = _classes("object O:\n  given (Int, String) = ???\n")
        assert "given (Int, String)" in classes

    def test_anonymous_given_uses_function_type(self) -> None:
        classes = _classes("object O:\n  given (Int => String) = ???\n")
        assert "given (Int => String)" in classes

    def test_anonymous_given_uses_stable_type_identifier(self) -> None:
        classes = _classes("object O:\n  given Foo.Bar = ???\n")
        assert "given Foo.Bar" in classes

    def test_degenerate_given_falls_back_to_line_based_name(self) -> None:
        # ``given = 1`` has neither a name identifier nor a recognizable type
        # child, so ``_scala_given_name`` falls back to ``anonymous_given_<line>``
        # (and ``_scala_given_type_name`` returns None).
        classes = _classes("object O:\n  given = 1\n")
        assert "anonymous_given_2" in classes


class TestScalaExtensionReceiver:
    """#972: cover ``_scala_extension_receiver_type`` typed / no-param arms."""

    def test_typed_receiver_is_split_after_colon(self) -> None:
        classes = _classes(
            """\
object Ops:
  extension (xs: List[Int])
    def f: Int = 1
"""
        )
        assert classes["extension[List[Int]]"].class_type == "extension"
        assert classes["extension[List[Int]]"].parent_class == "Ops"

    def test_no_valid_params_falls_back_to_line_suffix(self) -> None:
        # ``extension (s)`` (no type) parses with an ERROR node, so
        # ``_extract_parameters`` yields nothing and the receiver type is None,
        # forcing the line-number suffix.
        classes = _classes("extension (s)\n  def f: Int = 1\n")
        assert "extension[1]" in classes
        assert classes["extension[1]"].class_type == "extension"

    def test_no_parameters_child_falls_back_to_line_suffix(self) -> None:
        # ``extension EmptyExt`` has no ``parameters`` child at all, so
        # ``_scala_extension_receiver_type`` returns None via its final
        # ``return None`` and the line-number suffix is used.
        classes = _classes(
            """\
object O:
  extension EmptyExt
    def f: Int = 1
"""
        )
        assert "extension[2]" in classes
        assert classes["extension[2]"].class_type == "extension"


class TestScalaTypeMemberVsAlias:
    """#972: ``_scala_type_has_alias_target`` decides type_alias vs type_member."""

    def test_assigned_type_is_alias(self) -> None:
        classes = _classes("trait Api:\n  type Alias = Int\n")
        assert classes["Alias"].class_type == "type_alias"

    def test_abstract_type_is_member(self) -> None:
        classes = _classes("trait Api:\n  type Out\n")
        assert classes["Out"].class_type == "type_member"

    def test_bounded_abstract_type_is_member(self) -> None:
        classes = _classes("trait Api:\n  type In <: String\n")
        assert classes["In"].class_type == "type_member"


class TestScalaFunctionContext:
    """#972: ``_traverse_functions_with_context`` propagates parent_class /
    receiver_type through class-like, given, and extension scopes."""

    def test_method_in_object_has_parent_class(self) -> None:
        functions = _functions(
            """\
object Calc:
  def add(a: Int, b: Int): Int = a + b
"""
        )
        assert functions["add"].parent_class == "Calc"
        assert functions["add"].receiver_type is None

    def test_method_in_trait_has_parent_class(self) -> None:
        functions = _functions(
            """\
trait Shape:
  def area(): Double = 0.0
"""
        )
        assert functions["area"].parent_class == "Shape"

    def test_abstract_method_declaration_has_parent_class(self) -> None:
        # ``function_declaration`` (no body) goes through the declaration arm.
        functions = _functions(
            """\
trait Shape:
  def perimeter(): Double
"""
        )
        assert functions["perimeter"].parent_class == "Shape"

    def test_method_inside_given_with_block_has_given_parent(self) -> None:
        functions = _functions(
            """\
object O:
  given listOrd: Ordering[List[Int]] with
    def compare(a: List[Int], b: List[Int]): Int = 0
"""
        )
        assert functions["compare"].parent_class == "listOrd"
        assert functions["compare"].receiver_type is None

    def test_top_level_function_has_no_parent(self) -> None:
        functions = _functions("def free(x: Int): Int = x\n")
        assert functions["free"].parent_class is None
        assert functions["free"].receiver_type is None


def test_scala_ast_cache_symbol_path_indexes_new_constructs() -> None:
    from tree_sitter_analyzer._ast_extraction import _extract_symbols

    code = """\
object Instances:
  given Ordering[Int] = Ordering.Int
  type Alias = Int

enum Color:
  case Red
"""
    symbols = _extract_symbols(_parse(code), code, "scala")["symbols"]
    by_name = {s["name"]: s for s in symbols}
    assert by_name["Instances"]["kind"] == "class"
    assert by_name["given Ordering[Int]"]["kind"] == "class"
    assert by_name["Alias"]["kind"] == "class"
    assert by_name["Color"]["kind"] == "enum"
