"""Conservative classification tiers for the PHP resolver (RFC-0010, 2nd wave).

The RFC-0008 lesson is MANDATORY here: a name belongs in a classified tier ONLY
when it is (near-)exclusively that API and is unlikely to be a project symbol.
The PHP resolver carries NO receiver-type inference, so it classifies on the
SAFEST available signal and nothing more.

For PHP that signal is a **bare, unqualified, global free-function call**.
PHP's standard library is exposed as thousands of *global* functions
(``strlen``, ``count``, ``array_map``, ``json_encode``, ``preg_match`` …) that
live in the root namespace and are called WITHOUT a receiver. This is the one
PHP call shape where a name match is a relatively safe classification signal:

* A ``Foo::bar()`` static call or a ``$obj->bar()`` instance call has a receiver
  whose class type the edge does not carry — classifying those by bare method
  name would mis-wire domain calls (the exact CodeGraph failure this project
  beats). They stay ``unknown``.
* A bare ``foo()`` call is either a project free function (resolved ``local`` by
  the caller-file symbol table FIRST) or a global built-in. Only a curated,
  unambiguous set of built-ins is classified ``builtin``.

PRECISION over recall (the mandate):

* ``PHP_BUILTIN_FUNCTIONS`` is a HAND-AUDITED subset of PHP's global functions,
  deliberately limited to names a project almost never shadows with its own
  free function. Generic-looking names that a domain layer legitimately defines
  as a helper (``get`` / ``set`` / ``add`` / ``filter`` / ``map`` / ``find`` /
  ``log`` / ``format`` / ``validate``) are EXCLUDED — they would mis-classify a
  project helper as a built-in.
* The ``local`` tier always wins first: a project free function named ``count``
  shadows the built-in (checked before this set is consulted), so even a listed
  name stays ``local``/``unknown`` when the project owns it.
* ``EXTERNAL_FUNCTIONS_PHP`` is intentionally EMPTY: PHP third-party libraries
  expose their API through *namespaced classes and methods*, not distinctive
  global free functions, so there is no bare name that is (near-)exclusively one
  third-party library. Everything non-local, non-builtin stays ``unknown``.

An EMPTY-er tier is always safe: names just stay ``local`` / ``unknown``, never
cross-wired.
"""

from __future__ import annotations

#: Hand-audited PHP global built-in free functions. A BARE (unqualified, no
#: receiver) call to one of these classifies as ``builtin`` — but ONLY when the
#: project does not itself define a free function of that name (the ``local`` /
#: ownership gate runs first, so a domain helper shadowing a built-in stays
#: project-owned). These are core-language functions whose names a project very
#: rarely reuses as a free function. When in doubt a name is LEFT OUT (it then
#: stays ``unknown`` — never guessed in).
PHP_BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {
        # strings
        "strlen",
        "strpos",
        "stripos",
        "strrpos",
        "substr",
        "str_replace",
        "str_repeat",
        "str_pad",
        "str_split",
        "str_contains",
        "str_starts_with",
        "str_ends_with",
        "strtolower",
        "strtoupper",
        "ucfirst",
        "ucwords",
        "trim",
        "ltrim",
        "rtrim",
        "sprintf",
        "vsprintf",
        "number_format",
        "nl2br",
        "htmlspecialchars",
        "htmlentities",
        "strip_tags",
        "wordwrap",
        "mb_strlen",
        "mb_substr",
        "mb_strtolower",
        "mb_strtoupper",
        # arrays
        "array_map",
        "array_filter",
        "array_reduce",
        "array_merge",
        "array_keys",
        "array_values",
        "array_search",
        "array_key_exists",
        "array_combine",
        "array_flip",
        "array_slice",
        "array_splice",
        "array_diff",
        "array_intersect",
        "array_unique",
        "array_reverse",
        "array_column",
        "array_fill",
        "array_pad",
        "array_chunk",
        "array_push",
        "array_pop",
        "array_shift",
        "array_unshift",
        "in_array",
        "implode",
        "explode",
        "compact",
        "extract",
        "ksort",
        "krsort",
        "asort",
        "arsort",
        "usort",
        "uasort",
        "uksort",
        # JSON / serialization
        "json_encode",
        "json_decode",
        "serialize",
        "unserialize",
        "base64_encode",
        "base64_decode",
        # regex
        "preg_match",
        "preg_match_all",
        "preg_replace",
        "preg_replace_callback",
        "preg_split",
        "preg_quote",
        # math
        "abs",
        "ceil",
        "floor",
        "round",
        "intdiv",
        "fmod",
        "pow",
        "sqrt",
        "intval",
        "floatval",
        # type / variable
        "is_array",
        "is_string",
        "is_int",
        "is_integer",
        "is_float",
        "is_bool",
        "is_null",
        "is_numeric",
        "is_callable",
        "is_object",
        "is_iterable",
        "gettype",
        "settype",
        "isset",
        "empty",
        "var_dump",
        "var_export",
        "print_r",
        # functional / misc core
        "call_user_func",
        "call_user_func_array",
        "func_get_args",
        "func_num_args",
        "function_exists",
        "class_exists",
        "method_exists",
        "property_exists",
        "interface_exists",
        "get_class",
        "get_parent_class",
        "instanceof",
        "spl_autoload_register",
        # array count / iteration (count is core, very rarely shadowed)
        "count",
        "sizeof",
        "iterator_to_array",
    }
)

#: Intentionally EMPTY (RFC-0008 / RFC-0010): no PHP bare free-function name is
#: (near-)exclusively one third-party library — PHP libraries expose their API
#: through namespaced classes/methods, not distinctive global functions. So
#: everything that is neither a same-file local nor a curated built-in stays
#: ``unknown`` rather than risk a mis-classification. An empty tier is correct.
EXTERNAL_FUNCTIONS_PHP: frozenset[str] = frozenset()


__all__ = ["EXTERNAL_FUNCTIONS_PHP", "PHP_BUILTIN_FUNCTIONS"]
