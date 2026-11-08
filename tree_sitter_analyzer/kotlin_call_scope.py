"""#1926: which implicit receivers a Kotlin bare call (``m()`` / ``this.m()``) may use.

In Kotlin a bare call inside a class means ``this.m()``, so a subclass override is a
possible target. That reading is only safe when nothing else supplies an implicit
receiver. The extractor writes one ``kotlin_scope`` string per bare / ``this``
call, and the call graph (:mod:`.call_graph_kotlin_bare`) reads it:

* ``receiver``: an enclosing lambda, anonymous function, extension function or
  extension property may bring its own receiver (``x.apply {}``, ``with(x) {}``,
  ``x.run {}``, DSL builders, ``fun Box.ext()``); a parse error also lands here.
  ``m()`` may be any type's method: the site stays open.
* ``member``: inside a class / object / interface body and no such receiver.
* ``top``: neither (a top-level function: no implicit receiver).

A lambda passed to a standard-library function whose lambda has no receiver
(``let``, ``also``, ``map``, ``forEach``, ...) does not change the scope, nor does
``apply { }`` / ``run { }`` called on the implicit ``this`` (its receiver is that
same ``this``: ``fun f(): Builder = apply { g() }``); the host's name
follows a colon (``member:let,map``) so the graph can still open the site when the
project itself defines a function of that name (which may take ``T.() -> R``).
"""

from __future__ import annotations

from typing import Any

#: Metadata / edge key of the scope string.
KOTLIN_SCOPE_KEY = "kotlin_scope"
RECEIVER = "receiver"
MEMBER = "member"
TOP = "top"

#: Standard-library functions whose lambda parameter has no receiver (``it`` /
#: named parameters only). ``run``, ``apply``, ``with``, ``runCatching``,
#: ``buildString`` / ``buildList``, ``sequence`` and friends have one and are not here.
NO_RECEIVER_HOSTS = frozenset(
    {
        "let",
        "also",
        "takeIf",
        "takeUnless",
        "repeat",
        "forEach",
        "forEachIndexed",
        "onEach",
        "onEachIndexed",
        "map",
        "mapIndexed",
        "mapNotNull",
        "mapIndexedNotNull",
        "mapKeys",
        "mapValues",
        "flatMap",
        "filter",
        "filterNot",
        "filterIndexed",
        "filterKeys",
        "filterValues",
        "any",
        "all",
        "none",
        "count",
        "first",
        "firstOrNull",
        "last",
        "lastOrNull",
        "find",
        "findLast",
        "single",
        "singleOrNull",
        "indexOfFirst",
        "indexOfLast",
        "sortedBy",
        "sortedByDescending",
        "sortBy",
        "sortByDescending",
        "compareBy",
        "thenBy",
        "groupBy",
        "associate",
        "associateBy",
        "associateWith",
        "partition",
        "sumOf",
        "maxOf",
        "minOf",
        "maxByOrNull",
        "minByOrNull",
        "fold",
        "reduce",
        "zip",
        "distinctBy",
        "takeWhile",
        "dropWhile",
        "joinToString",
        "getOrElse",
        "getOrPut",
        "ifEmpty",
        "ifBlank",
        "removeAll",
        "retainAll",
        "removeIf",
        "lazy",
        "require",
        "check",
        "requireNotNull",
        "checkNotNull",
        "synchronized",
    }
)

#: Standard-library scope functions whose lambda receiver is the object they are
#: called on: called on the implicit ``this`` (``apply { }``, ``this.run { }``),
#: the lambda's receiver is that same ``this`` and the scope does not change.
THIS_RECEIVER_HOSTS = frozenset({"apply", "run"})
#: Prefix of such a host in the scope string (``member:this.apply``): only a member
#: of the caller's own class (or a supertype) could replace the standard function.
THIS_HOST_PREFIX = "this."

#: Nodes that hold class members.
_CLASS_BODIES = frozenset({"class_body", "enum_class_body"})


def kotlin_call_scope(call_node: Any, source: str) -> str:
    """The ``kotlin_scope`` of the call ``call_node`` (see the module doc)."""
    hosts: list[str] = []
    member = False
    node = call_node.parent
    while node is not None:
        kind = node.type
        if kind == "ERROR" or _brings_receiver(node, source, hosts):
            return RECEIVER
        if kind in _CLASS_BODIES:
            member = True
        node = node.parent
    scope = MEMBER if member else TOP
    return f"{scope}:{','.join(hosts)}" if hosts else scope


def _brings_receiver(node: Any, source: str, hosts: list[str]) -> bool:
    """``node`` may supply an implicit receiver; records allowed lambda hosts."""
    kind = node.type
    if kind == "lambda_literal":
        host, on_this = _lambda_host(node, source)
        if host in NO_RECEIVER_HOSTS:
            hosts.append(str(host))
            return False
        if on_this and host in THIS_RECEIVER_HOSTS:
            hosts.append(f"{THIS_HOST_PREFIX}{host}")
            return False
        return True
    if kind in {"function_declaration", "anonymous_function"}:
        return _has_receiver_type(node, "function_value_parameters")
    if kind == "property_declaration":
        return _has_receiver_type(node, "variable_declaration")
    return False


def _has_receiver_type(node: Any, before: str) -> bool:
    """A type written before ``before`` (``fun Box.f()`` / ``val Box.p``)."""
    for child in node.named_children:
        if child.type == before or child.type == "identifier":
            return False
        if child.type in {"user_type", "nullable_type", "parenthesized_type"}:
            return True
    return False


def _lambda_host(lambda_node: Any, source: str) -> tuple[str | None, bool]:
    """The name of the function a lambda is passed to (or None), and whether it
    is called on the implicit ``this`` (``apply { }`` / ``this.apply { }``)."""
    parent = lambda_node.parent
    if parent is not None and parent.type == "annotated_lambda":
        call = parent.parent
    elif parent is not None and parent.type == "value_argument":
        arguments = parent.parent
        call = arguments.parent if arguments is not None else None
    else:
        return None, False
    if call is None or call.type != "call_expression" or not call.named_children:
        return None, False
    callee = call.named_children[0]
    return _callee_name(callee, source), _on_this(callee)


def _on_this(callee: Any) -> bool:
    """``f`` or ``this.f`` (not ``this@Label.f``, not ``x.f``)."""
    if callee.type == "identifier":
        return True
    if callee.type != "navigation_expression" or len(callee.named_children) != 2:
        return False
    target = callee.named_children[0]
    return target.type == "this_expression" and not target.named_children


def _callee_name(node: Any, source: str) -> str | None:
    if node.type == "call_expression" and node.named_children:
        # ``with(x) { ... }``: the lambda follows the inner call ``with(x)``.
        return _callee_name(node.named_children[0], source)
    if node.type == "navigation_expression" and node.named_children:
        node = node.named_children[-1]
    if node.type != "identifier":
        return None
    text = getattr(node, "text", None)
    if isinstance(text, bytes):
        return text.decode("utf-8", "replace")
    return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
        "utf-8", "replace"
    )


__all__ = [
    "KOTLIN_SCOPE_KEY",
    "MEMBER",
    "NO_RECEIVER_HOSTS",
    "RECEIVER",
    "THIS_HOST_PREFIX",
    "THIS_RECEIVER_HOSTS",
    "TOP",
    "kotlin_call_scope",
]
