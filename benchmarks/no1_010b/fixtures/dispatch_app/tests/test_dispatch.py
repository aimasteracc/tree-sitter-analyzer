"""Suite pinning the currently-correct dispatch behaviour."""

from src.dispatch import Response, dispatch


def test_root_route_returns_home_response() -> None:
    assert dispatch("/") == Response(200, "home")


def test_health_route_returns_ok_body() -> None:
    assert dispatch("/health") == Response(200, "ok")
