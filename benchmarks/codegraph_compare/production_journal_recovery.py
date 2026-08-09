"""Legacy local-journal inspection (E0 diagnostics only)."""

from __future__ import annotations

from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchRequestV1,
)


def recover_hanging_journal(request: ProductionDispatchRequestV1) -> bool:
    """Never terminalize a production run from mutable local path state.

    A local journal can be renamed, unlinked, or replayed.  Only an external
    immutable evidence-authority receipt can establish a durable terminal, so
    recovery deliberately performs no authorization-bearing write.
    """
    return False
