"""Suite pinning the registry seam that the refactor task moves the table to."""

from src.registry import resolve


def test_resolve_is_unknown_for_an_unregistered_path() -> None:
    assert resolve("/nope") is None
