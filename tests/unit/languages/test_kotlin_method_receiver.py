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
    from tree_sitter_analyzer._api_result_helpers import element_to_dict

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
