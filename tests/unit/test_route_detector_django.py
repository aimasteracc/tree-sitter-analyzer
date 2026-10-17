"""Django ``urls.py`` route detection (#1650).

``scan_django_urls`` used to read the call field ``func``; tree-sitter-python
names it ``function``, so Django routes were never reported. These tests go
through the public ``RouteDetector`` / ``detect_routes`` surface.

``include(...)`` decision: ``path("api/", include("api.urls"))`` mounts a URL
prefix, it is not an endpoint. It is reported as ONE record with
``http_method="INCLUDE"``, the prefix as ``url_pattern`` and the included
target as ``handler_name`` (mirrors Express/Fiber ``USE`` mounts). Prefixes are
not composed into the included module's patterns; those keep the pattern as
declared.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool
from tree_sitter_analyzer.route_detector import RouteDetector
from tree_sitter_analyzer.route_detector.scanners import (
    python_source_may_declare_routes,
)

_ALL_VERBS = ["DELETE", "GET", "PATCH", "POST", "PUT"]

_URLS_PY = """\
from django.urls import include, path, re_path

from . import views

urlpatterns = [
    path("items/", views.items, name="items"),
    re_path(r"^x/$", view),
    path("api/", include("api.urls")),
]
"""


def _write(tmp_path: Path, source: str, name: str = "urls.py") -> Path:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target


def _detect(tmp_path: Path) -> list[tuple[str, str, str, str, int]]:
    detector = RouteDetector(str(tmp_path), cache_enabled=False)
    try:
        return sorted(
            (r.framework, r.http_method, r.url_pattern, r.handler_name, r.line_number)
            for r in detector.detect_all()
        )
    finally:
        detector.close()


def _by_pattern(routes, pattern: str):
    return [r for r in routes if r[2] == pattern]


def test_django_path_yields_one_route_per_verb(tmp_path):
    _write(tmp_path, _URLS_PY)
    routes = _by_pattern(_detect(tmp_path), "items/")
    assert routes == [("django", verb, "items/", "items", 6) for verb in _ALL_VERBS]


def test_django_re_path_strips_raw_string_prefix(tmp_path):
    _write(tmp_path, _URLS_PY)
    routes = _by_pattern(_detect(tmp_path), "^x/$")
    assert routes == [("django", verb, "^x/$", "view", 7) for verb in _ALL_VERBS]


def test_django_include_is_reported_as_one_prefix_record(tmp_path):
    _write(tmp_path, _URLS_PY)
    routes = _by_pattern(_detect(tmp_path), "api/")
    assert routes == [("django", "INCLUDE", "api/", "api.urls", 8)]


def test_django_fixture_total_route_count(tmp_path):
    _write(tmp_path, _URLS_PY)
    # 5 verbs for path(), 5 for re_path(), 1 INCLUDE prefix record.
    assert len(_detect(tmp_path)) == 11


def test_inline_include_list_reports_inner_routes_unprefixed(tmp_path):
    source = (
        "from django.urls import include, path\n"
        "urlpatterns = [\n"
        "    path('v1/', include([path('ping/', views.ping)])),\n"
        "]\n"
    )
    _write(tmp_path, source)
    routes = _detect(tmp_path)
    assert _by_pattern(routes, "v1/") == [("django", "INCLUDE", "v1/", "<inline>", 3)]
    assert _by_pattern(routes, "ping/") == [
        ("django", verb, "ping/", "ping", 3) for verb in _ALL_VERBS
    ]


def test_bare_path_call_without_django_import_is_not_a_route(tmp_path):
    # Once the field is fixed, a helper named ``path`` in any Python file must
    # not turn into a Django route; the scanner is gated on a django import,
    # like the Flask/FastAPI and Go scanners are gated on theirs.
    source = "def path(a, b):\n    return a\n\nresult = path('items/', handler)\n"
    _write(tmp_path, source, name="helpers.py")
    assert _detect(tmp_path) == []


def test_django_urls_file_passes_the_1638_prefilter(tmp_path):
    assert python_source_may_declare_routes(_URLS_PY)
    _write(tmp_path, _URLS_PY)
    assert {r[0] for r in _detect(tmp_path)} == {"django"}


def test_warm_cache_from_the_broken_scanner_is_not_served(tmp_path, monkeypatch):
    # A routes.db written before the fix holds an empty list for urls.py with
    # an unchanged content hash; the scanner-version bump must evict it.
    import tree_sitter_analyzer.route_detector as route_detector
    from tree_sitter_analyzer.registry import route_cache

    _write(tmp_path, _URLS_PY)
    db_path = tmp_path / "routes.db"
    with monkeypatch.context() as patch:
        patch.setattr(route_cache, "_SCANNER_VERSION", route_cache._SCANNER_VERSION - 1)
        patch.setattr(route_detector, "scan_django_urls", lambda *_args: [])
        stale = RouteDetector(str(tmp_path), cache_db_path=db_path)
        assert stale.detect_all() == []
        stale.close()
    fresh = RouteDetector(str(tmp_path), cache_db_path=db_path)
    try:
        assert len(fresh.detect_all()) == 11
        assert fresh.cache_stats()["misses"] == 1
    finally:
        fresh.close()


def test_detect_routes_tool_filters_django(tmp_path):
    _write(tmp_path, _URLS_PY)
    tool = RouteDetectorTool(str(tmp_path))
    result = asyncio.run(
        tool.execute({"mode": "all", "framework": "django", "output_format": "json"})
    )
    assert result["total_routes"] == 11
    assert result["by_framework"] == {"django": 11}
    assert result["by_method"]["INCLUDE"] == 1
    lookup = asyncio.run(
        tool.execute(
            {"mode": "lookup", "url_pattern": "items/", "output_format": "json"}
        )
    )
    assert {r["handler_name"] for r in lookup["routes"]} == {"items"}
    assert lookup["match_count"] == 5
