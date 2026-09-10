"""Suite pinning the currently-correct order bookkeeping."""

from src.orders import cancel, place


def test_place_returns_the_billed_amount() -> None:
    assert place("a-1", 2, 250) == 500


def test_cancel_reports_true_for_a_placed_order() -> None:
    place("a-2", 1, 100)
    assert cancel("a-2") is True
