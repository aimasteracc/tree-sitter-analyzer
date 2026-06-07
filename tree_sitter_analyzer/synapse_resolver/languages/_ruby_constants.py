"""Conservative builtin name tier for the Ruby resolver (RFC-0010 second wave).

These literal sets live outside the resolver logic so the resolver module stays
small and the tables are auditable in isolation.

CURATION RULE — PRECISION over recall (the RFC-0008 Java lesson, applied to
Ruby). Ruby method names are *extremely* overloaded: ``puts``, ``require``,
``raise``, ``new``, ``call``, ``each``, ``map``, ``to_s`` and friends are
defined or re-opened by every gem, DSL, and domain object. Ruby's open classes
and ubiquitous monkey-patching mean even a "core" bare name carries NO proof
that a given call hits the core API rather than a user redefinition. The Ruby
resolver has no receiver-type evidence and no symbol-level import graph
(``require`` loads *files*, not named symbols), so the only thing it can prove
is the FULL dotted call name.

Therefore a call is KEPT in the ``builtin`` tier ONLY if it is a **dotted,
namespaced call whose receiver is a Ruby core module that user code almost never
re-creates with the SAME method** — currently the ``Math`` module's pure
numeric helpers (``Math.sqrt``, ``Math.sin`` …). ``Math`` is a frozen core
module; a domain object literally named ``Math`` carrying ``sqrt``/``sin`` is
vanishingly rare, and these calls are near-exclusively the core API.

DELIBERATELY EXCLUDED (an EMPTY tier for these is correct):
  * Bare ``puts`` / ``print`` / ``p`` / ``require`` / ``require_relative`` /
    ``raise`` / ``loop`` / ``freeze`` / ``new`` / ``call`` — bare ``Kernel``/
    core names with no namespace; every object can define them, and a bare name
    carries no proof it is the core method (it may be a same-file private
    method, which the ``local`` tier handles, or a user override).
  * ``File.*`` / ``JSON.*`` / ``Time.*`` / ``Hash.*`` / ``Array.*`` — ``File``,
    ``JSON``, ``Time`` etc. are commonly shadowed by domain constants, gems
    (``require 'json'`` swaps implementations), and Rails/ActiveSupport
    re-openings, so the FULL name is not near-exclusively the core API.

Matching is on the FULL dotted call name (``<receiver>.<method>``), never on the
bare method name. An empty match is acceptable: everything that is not a
recognised namespaced core call stays ``local`` (same-file) or ``unknown`` —
never mis-classified into another language's file.
"""

from __future__ import annotations

# Namespaced Ruby core calls. The KEY is the exact dotted call name
# (receiver + "." + method) as it appears in a call edge's full name; only an
# exact full-name match classifies as ``builtin``. Restricted to the ``Math``
# core module: a frozen module of pure numeric helpers that user code almost
# never re-creates with the same method name. The instance/bare forms of any of
# these names (``round`` on a Float, a bare ``sqrt``) are NOT here — only the
# ``Math.``-namespaced static forms.
RUBY_BUILTIN_CALLS: frozenset[str] = frozenset(
    {
        "Math.sqrt",
        "Math.cbrt",
        "Math.sin",
        "Math.cos",
        "Math.tan",
        "Math.asin",
        "Math.acos",
        "Math.atan",
        "Math.atan2",
        "Math.exp",
        "Math.log",
        "Math.log2",
        "Math.log10",
        "Math.hypot",
        "Math.pow",
    }
)


__all__ = ["RUBY_BUILTIN_CALLS"]
