"""Route-registry seam for task ``0003-refactor-extract-route-registry``.

The route table currently lives inline in :mod:`src.dispatch`. The registered
refactor moves it behind ``resolve`` without changing any response.
"""

from __future__ import annotations


def resolve(path: str) -> str | None:
    """Return the body registered for ``path``, or ``None`` when unknown."""
    return None
