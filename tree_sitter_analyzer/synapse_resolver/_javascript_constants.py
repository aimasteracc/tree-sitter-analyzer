"""Conservative builtin / stdlib name tiers for the JavaScript resolver.

RFC-0010 first wave. These literal sets are kept out of the resolver logic so
the resolver module stays small and the tables are auditable in isolation.

CURATION RULE — PRECISION over recall (the RFC-0008 Java lesson, applied to JS).
JavaScript has no receiver-type evidence at this tier and no import-graph step
in the first-wave resolver, so a bare callee name (``log``, ``map``, ``get``…)
carries no proof that it is the global/builtin API rather than a user method.
The project-ownership gate only separates *project* from *not-project* — it does
NOT separate *builtin* from *user-defined-with-the-same-name*. Therefore a name
is KEPT here ONLY if it is a **dotted, namespaced global** call whose receiver is
itself a JS built-in object (``JSON.parse``, ``Object.keys``, ``Math.max``) —
i.e. the FULL call name (receiver + method) is near-exclusively the JS builtin
API and extremely unlikely to be a user-defined object of the same name.

Bare method names (``map``/``filter``/``forEach``/``then``/``get``/``set``/
``push``/``log`` without a namespace) are DELIBERATELY EXCLUDED: every array,
promise, collection wrapper, logger, and domain object defines them, and the
tier cannot tell ``users.map(...)`` (a domain array) from a builtin. Even
``console.log`` is excluded — ``console`` is routinely shadowed by a domain
logger/façade named ``console`` and ``log`` is a ubiquitous user method.

An EMPTY result for a given call is correct and acceptable: everything that is
not a recognised namespaced builtin stays ``local`` (same-file) or ``unknown``,
never mis-classified into another language's file. Matching is on the FULL
dotted call name (``<receiver>.<method>``), never on the bare method name.
"""

from __future__ import annotations

# Namespaced JS global/builtin calls. The KEY is the exact dotted call name
# (receiver + "." + method) as it appears in a call edge's full name; only an
# exact full-name match classifies as ``builtin``. Receivers chosen are global
# singletons that a user object almost never re-creates with the SAME method:
#   * ``JSON`` — the global JSON object (parse/stringify).
#   * ``Math`` — the global Math object (pure numeric helpers).
#   * ``Object`` / ``Array`` / ``Number`` — global constructors used as
#     namespaces for static helpers (``Object.keys``, ``Array.isArray``,
#     ``Number.isNaN``); the STATIC forms are distinctively builtin, unlike the
#     instance methods that share their bare names.
#   * ``Promise`` — static combinators (``Promise.all``/``race``/``resolve``).
#
# Bare-name instance methods (``push``/``map``/``keys`` on an arbitrary object)
# are NOT here — only the namespaced static forms above. ``console.*`` is
# excluded on purpose (``console`` is a commonly shadowed domain logger name).
JS_BUILTIN_CALLS: frozenset[str] = frozenset(
    {
        "JSON.parse",
        "JSON.stringify",
        "Math.max",
        "Math.min",
        "Math.abs",
        "Math.floor",
        "Math.ceil",
        "Math.round",
        "Math.random",
        "Math.sqrt",
        "Math.pow",
        "Object.keys",
        "Object.values",
        "Object.entries",
        "Object.assign",
        "Object.freeze",
        "Object.create",
        "Object.getPrototypeOf",
        "Object.defineProperty",
        "Array.isArray",
        "Array.from",
        "Array.of",
        "Number.isNaN",
        "Number.isInteger",
        "Number.isFinite",
        "Number.parseInt",
        "Number.parseFloat",
        "Promise.all",
        "Promise.allSettled",
        "Promise.race",
        "Promise.any",
        "Promise.resolve",
        "Promise.reject",
    }
)


__all__ = ["JS_BUILTIN_CALLS"]
