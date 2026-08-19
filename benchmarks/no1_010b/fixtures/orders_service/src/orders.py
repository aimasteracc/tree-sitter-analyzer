"""Order bookkeeping with one pre-registered defect (NO1-010B).

Defect for task ``0006-bugfix-cancel-unknown-order``: cancelling an order that
was never placed raises ``KeyError`` instead of reporting ``False``. This is
the task whose registered reference patch is deliberately wrong.
"""

from __future__ import annotations

from .totals import legacy_total

_ORDERS: dict[str, int] = {}


def place(order_id: str, quantity: int, unit_price: int) -> int:
    """Record an order and return its billed amount."""
    amount = legacy_total(quantity, unit_price)
    _ORDERS[order_id] = amount
    return amount


def cancel(order_id: str) -> bool:
    """Cancel ``order_id`` and report whether anything was cancelled."""
    del _ORDERS[order_id]
    return True
