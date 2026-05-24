# Fixture: cross-file callee resolution via `from X import Y`.
# `caller` calls `baz`, which is imported from sibling module `b`.
# Expected resolution: callee_resolution='project',
# callee_resolved_file ends with 'b.py', callee_symbol_id non-NULL.
from .b import baz


def caller():
    baz()
