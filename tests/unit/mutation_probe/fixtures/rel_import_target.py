"""Relative-import target (RFC-0029 test-plan item 8).

Uses a package-relative import so we can verify that ast.unparse() preserves
relative import semantics after mutation.
"""

from . import rel_import_helper


def compute(x: int) -> int:
    if x > 0:
        return rel_import_helper.VALUE * x
    return 0
