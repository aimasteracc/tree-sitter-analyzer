# Fixture: star-import edge case.
# `from .b import *` pulls everything (including `baz`) into the local
# namespace. The resolver is allowed to either:
#   - resolve `baz()` to b.py (callee_resolution='project'), OR
#   - fall back to 'unknown' if star imports are not statically resolvable.
# The test only asserts that ast_imports tracks the star import with
# is_star=1; it does NOT pin the resolution of the call itself.
from .b import *  # noqa: F401,F403


def use():
    baz()  # noqa: F405  -- comes in via star import
