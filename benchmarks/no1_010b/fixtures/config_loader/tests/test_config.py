"""Suite pinning the currently-correct settings loading."""

import pytest
from src.config import coerce, load


def test_load_returns_every_supplied_setting() -> None:
    assert load({"host": "db", "retries": "3"}) == {"host": "db", "retries": "3"}


def test_load_rejects_a_missing_required_setting() -> None:
    with pytest.raises(ValueError):
        load({"host": "db"})


def test_coerce_converts_retries_to_an_int() -> None:
    assert coerce("retries", "3") == 3
