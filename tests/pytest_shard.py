"""Deterministic ``--shard=I/N`` test selection (#1910).

``macos-latest`` hands out 3- and 5-vCPU machines of one image; on the 3-vCPU
ones a whole-suite session ran 690-980 s against a 1080 s budget. Splitting the
suite across N independent CI jobs halves the wall clock without dropping a test.

The split is a pure function of each node id (``zlib.crc32``), so:

* every shard computes the same partition on its own machine - no stored
  durations, no extra dependency, nothing to keep in sync with the test tree;
* adding or removing a test never moves any other test between shards;
* the shards are disjoint and their union is exactly the unsharded selection
  (pinned by ``tests/governance/test_ci_shard_contract.py``).

Hashing individual node ids (not files) spreads the heavy parametrised files
over every shard, so shard durations stay close without measuring them.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from typing import Any

import pytest

SHARD_OPTION = "--shard"


def parse_shard(value: str) -> tuple[int, int]:
    """Parse ``I/N`` (1-based) into ``(index, count)``; raise ValueError if bad."""
    index_text, sep, count_text = value.partition("/")
    if not sep:
        raise ValueError(f"expected I/N, got {value!r}")
    try:
        index, count = int(index_text), int(count_text)
    except ValueError:
        raise ValueError(f"expected integers in I/N, got {value!r}") from None
    if count < 1 or not 1 <= index <= count:
        raise ValueError(f"shard index must satisfy 1 <= I <= N, got {value!r}")
    return index, count


def shard_of(nodeid: str, count: int) -> int:
    """Return the 1-based shard that owns ``nodeid``."""
    return zlib.crc32(nodeid.encode("utf-8")) % count + 1


def select_shard(items: Sequence[Any], index: int, count: int) -> tuple[list, list]:
    """Split ``items`` into ``(selected, deselected)`` for shard ``index``/``count``."""
    selected: list[Any] = []
    deselected: list[Any] = []
    for item in items:
        target = selected if shard_of(item.nodeid, count) == index else deselected
        target.append(item)
    return selected, deselected


def add_options(parser: pytest.Parser) -> None:
    parser.addoption(
        SHARD_OPTION,
        default=None,
        metavar="I/N",
        help=(
            "Run only shard I of N (1-based) of the selected tests, split "
            "deterministically by node id (#1910)."
        ),
    )


def validate(config: pytest.Config) -> None:
    """Fail fast on a malformed ``--shard`` value."""
    value = config.getoption("shard", default=None)
    if value is None:
        return
    try:
        parse_shard(value)
    except ValueError as exc:
        raise pytest.UsageError(f"--shard: {exc}") from None


def apply(config: pytest.Config, items: list[Any]) -> None:
    """Keep only this shard's items (call from ``pytest_collection_modifyitems``)."""
    value = config.getoption("shard", default=None)
    if value is None:
        return
    index, count = parse_shard(value)
    selected, deselected = select_shard(items, index, count)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
