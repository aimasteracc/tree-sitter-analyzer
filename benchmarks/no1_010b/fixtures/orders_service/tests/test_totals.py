"""Suite pinning the currently-correct total arithmetic."""

from src.totals import legacy_total, total


def test_total_without_discount_multiplies_quantity_by_price() -> None:
    assert total(3, 500) == 1500


def test_legacy_total_multiplies_quantity_by_price() -> None:
    assert legacy_total(3, 500) == 1500
