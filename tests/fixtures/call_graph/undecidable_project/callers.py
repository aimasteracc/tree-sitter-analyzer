"""Call sites for the undecidable corpus.

The names reached here never appear next to a call. A text search for a call to
any target finds its definition and nothing else, which is what makes a bare
"0 callers" answer wrong rather than merely imprecise.

As in ``plugins.py``, this docstring avoids writing a target name immediately
followed by an opening parenthesis, so the corpus genuinely defeats a text
search.
"""

from __future__ import annotations

from dynamic import Service, call_through_globals, call_through_import
from plugins import dispatch_by_name

NAMES = ("alpha", "beta")
METHODS = ("method_one", "method_two")


def run_all() -> list[int]:
    results = [dispatch_by_name(name) for name in NAMES]
    service = Service()
    results.extend(service.run_named(method) for method in METHODS)
    results.append(call_through_globals("module_level_target"))
    results.append(call_through_import("dynamic", "module_level_target"))
    return results
