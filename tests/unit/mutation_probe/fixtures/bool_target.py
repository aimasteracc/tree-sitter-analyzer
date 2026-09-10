"""Boolean-logic target (RFC-0029 test-plan items 3 & 10).

is_positive() and divide() are small, observable functions used as positive
controls and as false-negative profile examples.
"""


def is_positive(x: int) -> bool:
    if x > 0:
        return True
    return False


def divide(a: float, b: float) -> float | None:
    if b == 0:
        return None
    return a / b
