"""Location-sensitive dispatch target (RFC-0029 test-plan item 2).

_private() is the low-level implementation; public_dispatch() delegates to it.
A test that calls _private() directly constrains _private's condition (line 2)
but does NOT constrain public_dispatch's condition (line 8), because the
latter is never exercised by the test.
"""


def _private(x: int) -> int:
    if x == 0:
        return 0
    return x * 2


def public_dispatch(x: int) -> int:
    if x > 0:
        return _private(x)
    return 0
