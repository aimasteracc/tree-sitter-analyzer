"""Request router fixture with two pre-registered defects (NO1-010B).

Defect for task ``0001-bugfix-dispatch-unknown-route``: an unknown path falls
through and returns ``None`` instead of a 404 response.

Defect for task ``0002-bugfix-dispatch-trailing-slash``: a trailing slash is
not normalised, so ``/health/`` misses the route table.
"""

from __future__ import annotations

from dataclasses import dataclass

ROUTES = {
    "/": "home",
    "/health": "ok",
}


@dataclass(frozen=True)
class Response:
    """One router response."""

    status: int
    body: str


def dispatch(path: str) -> Response | None:
    """Return the response registered for ``path``."""
    if path in ROUTES:
        return Response(200, ROUTES[path])
    return None
