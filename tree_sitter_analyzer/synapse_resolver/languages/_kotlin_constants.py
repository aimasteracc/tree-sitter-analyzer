"""Conservative stdlib name tiers for the Kotlin resolver (RFC-0010).

The RFC-0008 lesson is MANDATORY here: classification without receiver-type
inference has a low precision ceiling, so a name lands in a classified tier ONLY
when it is (near-)exclusively that stdlib API and very unlikely to be a
user-defined function. Two facts shape the Kotlin curation:

* Kotlin auto-imports the ``kotlin`` / ``kotlin.collections`` / ``kotlin.io``
  packages, so a small set of stdlib TOP-LEVEL functions are callable *bare*
  (no ``import`` line, no receiver) — ``listOf()``, ``println()``,
  ``require()``. These appear as receiver-less call edges, exactly the shape a
  same-file project function would, so the tier is gated on the project NOT
  owning the name (``_project_owns`` in ``kotlin.py``): a project ``fun
  println(...)`` shadows the stdlib claim and the call stays ``local``/unknown.

* A bare-method-name tier (``map`` / ``filter`` / ``forEach`` / ``first`` …) is
  **intentionally EMPTY**. Those are receiver-style extension/member calls whose
  receiver type the call edge does not carry, and every one of them collides
  with user methods and domain DSLs (Kotlin's builder/DSL idiom defines exactly
  such names). Without receiver-type evidence they would be mis-classified, so
  they stay ``unknown`` — an unknown edge is never a mis-wire.

Kotlin/Java interop is real, but per the conservative mandate it is NOT modelled
here: Kotlin and Java are not one ``languages_compatible`` family, so a Kotlin
caller never binds a Java symbol (and vice-versa). That keeps the moat absolute;
adding cross-JVM resolution would need import/type evidence this tier lacks.

Kept in a dedicated module so the literal sets stay out of the resolver logic
and the file-size rule is honoured.
"""

from __future__ import annotations

# Stdlib TOP-LEVEL functions that Kotlin AUTO-IMPORTS (the ``kotlin``,
# ``kotlin.collections``, ``kotlin.io``, ``kotlin.text`` default-import set), so
# they are routinely called BARE — no ``import`` line and no receiver. Each name
# here is (near-)exclusively the Kotlin stdlib builder/intrinsic and is very
# unlikely to be re-defined as a user TOP-LEVEL function; if a project DOES
# define one, the ``_project_owns`` gate in ``kotlin.py`` suppresses the stdlib
# claim (shadowing preserved → precision over recall).
#
# CURATION RULE — only collection/array builders, the standard I/O intrinsics,
# and the contract intrinsics whose names projects essentially never reuse as a
# free function. Deliberately EXCLUDED: ``run`` / ``let`` / ``apply`` / ``also``
# / ``with`` / ``use`` (scope functions — extension calls on a receiver, not bare
# builders, and ``run``/``with`` are common project verbs), ``to`` (the Pair
# infix — collides with the English word), ``lazy`` / ``repeat`` (common domain
# names). An empty-leaning set beats a false positive.
STDLIB_BARE_FUNCTIONS_KOTLIN: frozenset[str] = frozenset(
    {
        # collection builders (kotlin.collections, auto-imported)
        "listOf",
        "mutableListOf",
        "emptyList",
        "setOf",
        "mutableSetOf",
        "emptySet",
        "mapOf",
        "mutableMapOf",
        "emptyMap",
        "arrayListOf",
        "hashMapOf",
        "hashSetOf",
        "linkedMapOf",
        "linkedSetOf",
        "sortedMapOf",
        "sortedSetOf",
        # array builders (kotlin, auto-imported)
        "arrayOf",
        "arrayOfNulls",
        "emptyArray",
        "booleanArrayOf",
        "byteArrayOf",
        "charArrayOf",
        "shortArrayOf",
        "intArrayOf",
        "longArrayOf",
        "floatArrayOf",
        "doubleArrayOf",
        # I/O intrinsics (kotlin.io, auto-imported)
        "println",
        "print",
        "readLine",
        # contract intrinsics (kotlin, auto-imported) — distinctive stdlib names
        "require",
        "requireNotNull",
        "check",
        "checkNotNull",
        "error",
        # number/range helpers projects essentially never re-define bare
        "TODO",
    }
)

# Bare *method* names classified ``stdlib`` on an UNRESOLVED receiver.
# INTENTIONALLY EMPTY (see module docstring): without receiver-type evidence,
# every candidate (``map`` / ``filter`` / ``forEach`` / ``first`` / ``isEmpty``
# …) collides with user members and Kotlin DSL builders. Precision over recall —
# an unknown edge is correct; a mis-classified one is a moat breach.
STDLIB_METHODS_KOTLIN: frozenset[str] = frozenset()

# Bare names classified ``external`` (third-party). INTENTIONALLY EMPTY: Kotlin
# has no single dominant third-party library whose bare call names are safe to
# hardcode, and many candidates (``test`` from kotlin.test, ``shouldBe`` from
# Kotest) are receiver-style or collide with user code. Stays empty until a safe
# set is proven.
EXTERNAL_METHODS_KOTLIN: frozenset[str] = frozenset()


__all__ = [
    "EXTERNAL_METHODS_KOTLIN",
    "STDLIB_BARE_FUNCTIONS_KOTLIN",
    "STDLIB_METHODS_KOTLIN",
]
