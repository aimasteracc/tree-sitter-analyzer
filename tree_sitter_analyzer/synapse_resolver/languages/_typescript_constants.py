"""Conservative classification tiers for the TypeScript resolver (RFC-0010).

The TypeScript resolver carries NO receiver-type inference, so — per the
RFC-0008 Java lesson — classification keys on the SAFEST available signal and
nothing more. For JS/TS that signal is a **distinctive global-object receiver
head**: a call whose receiver's first segment is a built-in global namespace
object (``console.log``, ``JSON.stringify``, ``Math.max``) is overwhelmingly the
JS runtime, because user code essentially never names a variable ``console`` /
``JSON`` / ``Math``. Such names resolve ``builtin``.

PRECISION over recall (the mandate). Two things are DELIBERATELY excluded:

* **Bare method-name tiers are EMPTY.** Generic JS method names — ``map`` /
  ``filter`` / ``forEach`` / ``push`` / ``substring`` / ``then`` / ``get`` —
  are routinely defined by domain objects, third-party collections, promises,
  and value objects. With no receiver-type evidence, classifying them ``stdlib``
  / ``external`` would mis-wire domain calls (the exact CodeGraph failure this
  project beats). They stay ``unknown`` — which is correct.
* **Ambiguous global names are excluded from the receiver set.** Only global
  objects that are essentially never shadowed by a user variable are listed.
  ``window`` / ``document`` / ``global`` / ``process`` are common DOM/Node
  globals BUT are also frequently re-bound (mock ``window``, a ``process``
  domain entity), so they are omitted to stay conservative.

An EMPTY-er tier is always safe: everything just stays ``local`` / ``project`` /
``unknown``, never cross-wired.
"""

from __future__ import annotations

# Distinctive built-in global NAMESPACE objects. A call ``X.method(...)`` whose
# receiver head ``X`` is one of these is the JS/TS runtime built-in, classified
# ``builtin`` — but only when the project owns no compatible-language (TS/JS)
# symbol of that name (shadowing gate). These names are intentionally limited to
# global objects that a user variable almost never collides with; common-but-
# shadowable globals (``window``/``document``/``process``/``global``) are
# excluded on purpose to keep precision high.
TYPESCRIPT_GLOBAL_OBJECTS: frozenset[str] = frozenset(
    {
        "console",
        "JSON",
        "Math",
        "Object",
        "Array",
        "Number",
        "String",
        "Boolean",
        "Symbol",
        "Reflect",
        "Promise",
        "Proxy",
        "BigInt",
        "Date",
        "RegExp",
        "Map",
        "Set",
        "WeakMap",
        "WeakSet",
        "Intl",
        "Atomics",
        "ArrayBuffer",
        "DataView",
        "Int8Array",
        "Uint8Array",
        "Uint8ClampedArray",
        "Int16Array",
        "Uint16Array",
        "Int32Array",
        "Uint32Array",
        "Float32Array",
        "Float64Array",
        "BigInt64Array",
        "BigUint64Array",
    }
)


__all__ = ["TYPESCRIPT_GLOBAL_OBJECTS"]
