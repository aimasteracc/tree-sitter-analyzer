"""Order-total arithmetic with two pre-registered seams (NO1-010B).

Defect for task ``0005-bugfix-discount-ignored``: ``total`` drops the
``discount`` argument, so a discounted order is billed at full price.

Seam for task ``0007-migration-drop-legacy-total``: ``legacy_total`` is the
deprecated entry point that the migration task must retire in favour of
``total``.
"""

from __future__ import annotations


def total(quantity: int, unit_price: int, discount: int = 0) -> int:
    """Return the billable amount for one order line, in minor units."""
    return quantity * unit_price


def legacy_total(quantity: int, unit_price: int) -> int:
    """Deprecated: pre-discount total kept only for the migration task."""
    return quantity * unit_price
