"""Theme-A (Kotlin) regression: class/object method ownership.

2026-06-11 quality-audit finding DF-18: Kotlin functions inside classes were
extracted with ``is_method=False`` and ``receiver_type=None`` — an agent
could not tell ``feed`` belongs to ``Dog``.

Semantics pinned here:
- any fun inside a ``class_declaration`` or ``object_declaration`` gets
  ``receiver_type`` = the owning type name, ``is_method=True``
  (Kotlin instance methods always have an implicit ``this``);
- fun inside ``companion object`` gets ``receiver_type`` = the enclosing
  class name, ``is_method=False`` (companion funs are effectively static);
- top-level fun: ``receiver_type=None``, ``is_method=False``;
- extension fun (``fun String.shout()``): ``receiver_type='String'``,
  ``is_method=True`` (documented choice — extension funs behave like
  methods on the receiver type from the call-site's perspective).

Node types confirmed by live parse (2026-06-11):
  class member: function_declaration → class_body → class_declaration
  companion member: function_declaration → class_body → companion_object
                     → class_body → class_declaration
  object member: function_declaration → class_body → object_declaration
  extension: user_type + '.' + identifier siblings in function_declaration
"""

from __future__ import annotations

from unittest.mock import MagicMock

import tree_sitter
import tree_sitter_kotlin

from tree_sitter_analyzer.languages.kotlin_helpers import extract_kotlin_function

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_language() -> tree_sitter.Language:
    caps_or_lang = tree_sitter_kotlin.language()
    if hasattr(caps_or_lang, "__class__") and "Language" in str(type(caps_or_lang)):
        return caps_or_lang
    return tree_sitter.Language(caps_or_lang)


def _parse(source: str) -> tree_sitter.Tree:
    lang = _build_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(lang)
    else:
        parser = tree_sitter.Parser(lang)
    return parser.parse(source.encode("utf-8"))


def _functions(source: str) -> dict[str, object]:
    """Return a name→Function dict parsed from *source*."""
    tree = _parse(source)
    results = {}

    def _visit(node: tree_sitter.Node) -> None:
        if node.type == "function_declaration":
            func = extract_kotlin_function(node, _node_text, "")
            if func:
                results[func.name] = func
        for child in node.children:
            _visit(child)

    src_bytes = source.encode("utf-8")

    def _node_text(n: tree_sitter.Node) -> str:
        return src_bytes[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    _visit(tree.root_node)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

_CLASS_SRC = """\
class Dog(val name: String) {
    fun feed(food: String): Unit {
        println(food)
    }

    fun bark(): String = "Woof"

    companion object {
        fun create(): Dog = Dog("Buddy")
    }
}

object Singleton {
    fun doSomething(): Int = 42
}

fun topLevelFun(x: Int): Int = x + 1

fun String.shout(): String = this.uppercase()
"""


def test_class_method_gets_receiver_type() -> None:
    """fun inside a class_declaration → receiver_type = class name, is_method=True."""
    funcs = _functions(_CLASS_SRC)
    assert funcs["feed"].receiver_type == "Dog", f"got {funcs['feed'].receiver_type!r}"
    assert funcs["feed"].is_method is True


def test_class_method_bark_gets_receiver_type() -> None:
    funcs = _functions(_CLASS_SRC)
    assert funcs["bark"].receiver_type == "Dog"
    assert funcs["bark"].is_method is True


def test_companion_object_fun_is_not_instance_method() -> None:
    """companion object funs are static-like — receiver_type = enclosing class,
    is_method=False (no implicit this on a companion fun call)."""
    funcs = _functions(_CLASS_SRC)
    assert funcs["create"].receiver_type == "Dog", (
        f"got {funcs['create'].receiver_type!r}"
    )
    assert funcs["create"].is_method is False


def test_object_declaration_member_gets_receiver_type() -> None:
    """fun inside an object_declaration → receiver_type = object name, is_method=True."""
    funcs = _functions(_CLASS_SRC)
    assert funcs["doSomething"].receiver_type == "Singleton"
    assert funcs["doSomething"].is_method is True


def test_top_level_fun_is_unowned() -> None:
    funcs = _functions(_CLASS_SRC)
    assert funcs["topLevelFun"].receiver_type is None
    assert funcs["topLevelFun"].is_method is False


def test_extension_fun_receiver_type_and_is_method() -> None:
    """``fun String.shout()`` — receiver_type='String', is_method=True.

    Semantic choice: extension funs behave like methods on the receiver
    type from the call-site's perspective, so is_method=True communicates
    that agents should model ``str.shout()`` rather than ``shout(str)``.
    The receiver_type is read from the ``user_type`` node sibling before
    the ``.`` in the function declaration node.
    """
    funcs = _functions(_CLASS_SRC)
    assert funcs["shout"].receiver_type == "String", (
        f"got {funcs['shout'].receiver_type!r}"
    )
    assert funcs["shout"].is_method is True


def test_receiver_survives_api_serialization() -> None:
    """End-to-end Theme-A (Kotlin): the serializer allowlist must carry
    the receiver binding to API consumers."""
    from tree_sitter_analyzer.internal_api.result_helpers import element_to_dict

    funcs = _functions(_CLASS_SRC)
    feed = element_to_dict(funcs["feed"])
    assert feed["receiver_type"] == "Dog"
    assert feed["is_method"] is True


# ---------------------------------------------------------------------------
# P1 — local functions falsely attributed (adversarial review fix)
# ---------------------------------------------------------------------------

_LOCAL_FUN_SRC = """\
class Outer {
    fun outer() {
        fun inner() {}
    }
}
"""

_ANON_OBJECT_SRC = """\
class C {
    fun m() {
        val r = object : Runnable {
            override fun run() {}
        }
    }
}
"""


def test_local_fun_inside_method_is_unowned() -> None:
    """P1: ``inner`` declared inside a method body must NOT be attributed to Outer.

    The walk must stop (return no-owner) when it crosses a
    ``function_declaration`` boundary before finding a class.
    receiver_type=None, is_method=False (exact).
    """
    funcs = _functions(_LOCAL_FUN_SRC)
    assert "inner" in funcs, f"inner not found; found: {list(funcs)}"
    assert funcs["inner"].receiver_type is None, f"got {funcs['inner'].receiver_type!r}"
    assert funcs["inner"].is_method is False


def test_anon_object_override_inside_method_is_unowned() -> None:
    """P1: ``run`` inside an anonymous object literal in a method must NOT be
    attributed to C.  Walk stops at ``object_literal`` boundary.
    receiver_type=None, is_method=False (exact).
    """
    funcs = _functions(_ANON_OBJECT_SRC)
    assert "run" in funcs, f"run not found; found: {list(funcs)}"
    assert funcs["run"].receiver_type is None, f"got {funcs['run'].receiver_type!r}"
    assert funcs["run"].is_method is False


# ---------------------------------------------------------------------------
# P2a — nullable extension receiver (adversarial review fix)
# ---------------------------------------------------------------------------

_NULLABLE_EXT_SRC = """\
fun String?.safe(): String = this ?: ""
"""


def test_nullable_extension_receiver_type() -> None:
    """P2a: ``fun String?.safe()`` -> receiver_type='String?', is_method=True."""
    funcs = _functions(_NULLABLE_EXT_SRC)
    assert "safe" in funcs, f"safe not found; found: {list(funcs)}"
    assert funcs["safe"].receiver_type == "String?", (
        f"got {funcs['safe'].receiver_type!r}"
    )
    assert funcs["safe"].is_method is True


# ---------------------------------------------------------------------------
# P2b — companion is_static (adversarial review fix)
# ---------------------------------------------------------------------------

_COMPANION_STATIC_SRC = """\
class Box {
    companion object {
        fun empty(): Box = Box()
    }
}
"""


def test_companion_fun_is_static() -> None:
    """P2b: companion fun -> is_method=False, is_static=True,
    receiver_type == enclosing class name (exact).
    """
    funcs = _functions(_COMPANION_STATIC_SRC)
    assert "empty" in funcs, f"empty not found; found: {list(funcs)}"
    f = funcs["empty"]
    assert f.receiver_type == "Box", f"got {f.receiver_type!r}"
    assert f.is_method is False
    assert f.is_static is True


# ---------------------------------------------------------------------------
# Coverage: _kotlin_extension_receiver edge cases (real parses)
# ---------------------------------------------------------------------------

_NESTED_CLASS_OWNER_SRC = """\
class Outer {
    class Inner {
        fun method() {}
    }
}
"""

_ENUM_CLASS_WITH_MEMBER_SRC = """\
enum class Color {
    RED, GREEN, BLUE;

    fun describe(): String = name
}
"""

_EXT_REC_NULLABLE_FOLLOWED_BY_DOT = """\
fun String?.ext(): String = this ?: ""
"""

_EXT_REC_USER_TYPE_FOLLOWED_BY_DOT = """\
fun List.first(): Any = this.get(0)
"""


def test_nested_class_member_gets_inner_owner() -> None:
    """fun inside nested Inner class → receiver_type = Inner (the immediate owner,
    not the outer Outer class)."""
    funcs = _functions(_NESTED_CLASS_OWNER_SRC)
    assert "method" in funcs
    assert funcs["method"].receiver_type == "Inner", (
        f"got {funcs['method'].receiver_type!r}"
    )


def test_enum_class_member_gets_enum_owner() -> None:
    """fun inside enum class body → receiver_type = enum name, is_method=True.
    The walk passes through enum_class_body without stopping."""
    funcs = _functions(_ENUM_CLASS_WITH_MEMBER_SRC)
    assert "describe" in funcs
    assert funcs["describe"].receiver_type == "Color", (
        f"got {funcs['describe'].receiver_type!r}"
    )
    assert funcs["describe"].is_method is True


def test_extension_receiver_with_nullable_type_and_dot() -> None:
    """_kotlin_extension_receiver identifies nullable_type followed by '.' as
    extension receiver."""
    funcs = _functions(_EXT_REC_NULLABLE_FOLLOWED_BY_DOT)
    assert "ext" in funcs
    assert funcs["ext"].receiver_type == "String?", (
        f"got {funcs['ext'].receiver_type!r}"
    )


def test_extension_receiver_with_user_type_and_dot() -> None:
    """_kotlin_extension_receiver identifies user_type followed by '.' as
    extension receiver."""
    funcs = _functions(_EXT_REC_USER_TYPE_FOLLOWED_BY_DOT)
    assert "first" in funcs
    assert funcs["first"].receiver_type == "List", (
        f"got {funcs['first'].receiver_type!r}"
    )


# ---------------------------------------------------------------------------
# Coverage: _kotlin_owning_type (unit tests with mocks)
# ---------------------------------------------------------------------------


def test_kotlin_owning_type_parent_none_depth_zero() -> None:
    """_kotlin_owning_type with node.parent = None → (None, False)."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    node.parent = None
    result = _kotlin_owning_type(node)
    assert result == (None, False), f"got {result!r}"


def test_kotlin_owning_type_source_file_boundary() -> None:
    """_kotlin_owning_type stops at source_file → (None, False)."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    source_file = MagicMock()
    source_file.type = "source_file"
    source_file.parent = None
    node.parent = source_file
    result = _kotlin_owning_type(node)
    assert result == (None, False), f"got {result!r}"


def test_kotlin_owning_type_local_function_boundary() -> None:
    """_kotlin_owning_type stops at function_declaration → (None, False).
    Local functions inside a method must not be attributed to the enclosing class."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    func_decl = MagicMock()
    func_decl.type = "function_declaration"
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    node.parent = func_decl
    func_decl.parent = class_decl
    class_decl.parent = None

    result = _kotlin_owning_type(node)
    assert result == (None, False), (
        f"got {result!r} — walk should stop at function_declaration"
    )


def test_kotlin_owning_type_object_literal_boundary() -> None:
    """_kotlin_owning_type stops at object_literal → (None, False).
    Overrides inside anonymous objects must not be attributed to the enclosing class."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    obj_lit = MagicMock()
    obj_lit.type = "object_literal"
    func_decl = MagicMock()
    func_decl.type = "function_declaration"
    node.parent = obj_lit
    obj_lit.parent = func_decl
    func_decl.parent = None

    result = _kotlin_owning_type(node)
    assert result == (None, False), (
        f"got {result!r} — walk should stop at object_literal"
    )


def test_kotlin_owning_type_class_declaration_with_name_field() -> None:
    """_kotlin_owning_type finds class owner via child_by_field_name('name')."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None

    name_node = MagicMock()
    name_node.text = b"MyClass"
    class_decl.child_by_field_name.return_value = name_node

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    assert result == ("MyClass", False), f"got {result!r}"


def test_kotlin_owning_type_class_declaration_name_via_identifier_scan() -> None:
    """_kotlin_owning_type falls back to scanning children for 'identifier'
    when child_by_field_name('name') returns None."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None

    class_decl.child_by_field_name.return_value = None
    name_child = MagicMock()
    name_child.type = "identifier"
    name_child.text = b"ClassViaIdent"
    other_child = MagicMock()
    other_child.type = "other"
    class_decl.children = [other_child, name_child]

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    assert result == ("ClassViaIdent", False), f"got {result!r}"


def test_kotlin_owning_type_class_declaration_no_name_found() -> None:
    """_kotlin_owning_type returns (None, False) when class has no name field
    and no identifier child."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None
    class_decl.child_by_field_name.return_value = None
    class_decl.children = []

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    assert result == (None, False), f"got {result!r}"


def test_kotlin_owning_type_object_declaration_owner() -> None:
    """_kotlin_owning_type finds object owner."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    obj_decl = MagicMock()
    obj_decl.type = "object_declaration"
    obj_decl.parent = None
    name_node = MagicMock()
    name_node.text = b"SingletonObj"
    obj_decl.child_by_field_name.return_value = name_node

    node.parent = obj_decl
    result = _kotlin_owning_type(node)
    assert result == ("SingletonObj", False), f"got {result!r}"


def test_kotlin_owning_type_companion_object_walks_further() -> None:
    """_kotlin_owning_type marks in_companion=True and continues walking
    past companion_object to find the enclosing class."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    companion = MagicMock()
    companion.type = "companion_object"

    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None
    class_name = MagicMock()
    class_name.text = b"Box"
    class_decl.child_by_field_name.return_value = class_name

    node.parent = companion
    companion.parent = class_decl

    result = _kotlin_owning_type(node)
    assert result == ("Box", True), (
        f"got {result!r} — should return enclosing class with is_companion=True"
    )


def test_kotlin_owning_type_depth_cap() -> None:
    """_kotlin_owning_type is capped at 256 iterations to prevent unbounded loops
    on non-conforming node objects (e.g. circular parent chains or MagicMock)."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    current = node
    for i in range(260):
        parent = MagicMock()
        parent.type = f"unknown_{i}"
        parent.parent = None if i == 259 else MagicMock()
        current.parent = parent
        current = parent

    result = _kotlin_owning_type(node)
    assert result == (None, False), (
        f"got {result!r} — depth cap at 256 should terminate the loop and return (None, False)"
    )


def test_kotlin_owning_type_unicode_name_handling() -> None:
    """_kotlin_owning_type safely decodes non-UTF8 bytes in name_node.text."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None
    name_node = MagicMock()
    name_node.text = b"\xff\xfe"
    class_decl.child_by_field_name.return_value = name_node

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    assert result[0] is not None, f"got {result!r}"
    assert result[1] is False


def test_kotlin_owning_type_decode_attribute_error() -> None:
    """_kotlin_owning_type handles AttributeError when name_node.text
    doesn't have a decode method."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None
    name_node = MagicMock()
    # Simulate a text attribute that doesn't have .decode() method
    name_node.text = "StringInsteadOfBytes"  # str, not bytes
    class_decl.child_by_field_name.return_value = name_node

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    # Should fall back to str(name_node.text)
    assert result == ("StringInsteadOfBytes", False), f"got {result!r}"


def test_kotlin_owning_type_decode_unicode_error() -> None:
    """_kotlin_owning_type handles UnicodeDecodeError when name_node.text
    contains invalid UTF-8."""
    from tree_sitter_analyzer.languages.kotlin_helpers import _kotlin_owning_type

    node = MagicMock()
    class_decl = MagicMock()
    class_decl.type = "class_declaration"
    class_decl.parent = None
    name_node = MagicMock()
    # Create a mock that raises UnicodeDecodeError when .decode is called
    name_node.text = MagicMock()
    name_node.text.decode.side_effect = UnicodeDecodeError(
        "utf-8", b"\x80", 0, 1, "invalid start byte"
    )

    class_decl.child_by_field_name.return_value = name_node

    node.parent = class_decl
    result = _kotlin_owning_type(node)
    # Should fall back to str(name_node.text)
    assert result[0] is not None, f"got {result!r}"
    assert result[1] is False
