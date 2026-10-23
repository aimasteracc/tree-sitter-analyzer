"""Python route prefilter (#1638): skip parsing only files no scanner can match."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.route_detector import RouteDetector
from tree_sitter_analyzer.route_detector.scanners import (
    python_source_may_declare_routes,
)


def _routes(tmp_path: Path, source: str) -> list[tuple[str, str, str]]:
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    detector = RouteDetector(str(tmp_path), cache_enabled=False)
    try:
        return sorted(
            (r.framework, r.http_method, r.url_pattern) for r in detector.detect_all()
        )
    finally:
        detector.close()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/a', methods=['POST'])\ndef a():\n    return 1\n",
            [("flask", "POST", "/a")],
        ),
        (
            "@bp.route('/b')\ndef b():\n    return 1\n",
            [("flask", "GET", "/b")],
        ),
        (
            "import flask\napp = flask.Flask(__name__)\n"
            "@app.get('/c')\ndef c():\n    return 1\n",
            [("flask", "GET", "/c")],
        ),
        (
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.delete('/d')\ndef d():\n    return 1\n",
            [("fastapi", "DELETE", "/d")],
        ),
    ],
)
def test_prefilter_keeps_every_route_form(tmp_path, source, expected):
    assert python_source_may_declare_routes(source)
    assert _routes(tmp_path, source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "urlpatterns = [path('e/', views.e)]\n",
        "urlpatterns = [re_path(r'^f/$', views.f)]\n",
        # Comment and line break between the callee and its arguments.
        "urlpatterns = [\n    path  # the g view\n    ('g/', views.g),\n]\n",
        "urlpatterns = [path \\\n ('h/', views.h)]\n",
        "urlpatterns = [path # c\r('i/', views.i)]\r",
    ],
)
def test_prefilter_keeps_django_call_forms(source):
    # Prefilter only: these snippets have no django import, so the scanner
    # itself skips them (#1650). The prefilter must not be the reason a
    # Django call form is dropped; the end-to-end Django cases live in
    # test_route_detector_django.py.
    assert python_source_may_declare_routes(source)


@pytest.mark.parametrize(
    "source",
    [
        "import os\n\ndef f(path):\n    return os.path.join(path, 'x')\n",
        "class Router:\n    def get(self, key):\n        return key\n",
        "@functools.cache\ndef routes():\n    return []\n",
        "",
    ],
)
def test_route_free_python_file_is_not_parsed(tmp_path, monkeypatch, source):
    assert not python_source_may_declare_routes(source)

    def forbidden_parse(self, file_path, language):
        pytest.fail(f"route-free file was parsed: {file_path}")

    monkeypatch.setattr(RouteDetector, "_parse_tree", forbidden_parse)
    assert _routes(tmp_path, source) == []


def test_prefilter_is_linear_on_hash_banners():
    source = "path " + "#" * 200_000 + "\n" + ("# " + "#" * 80 + "\n") * 2_000
    started = time.perf_counter()
    assert not python_source_may_declare_routes(source + "x = 1\n")
    assert time.perf_counter() - started < 1.0


def test_unreadable_file_falls_through_to_parser(tmp_path, monkeypatch):
    import tree_sitter_analyzer.route_detector as route_detector

    def unreadable(file_path):
        raise OSError("denied")

    monkeypatch.setattr(route_detector, "read_file_safe", unreadable)
    source = "@app.route('/z')\ndef z():\n    return 1\n"
    assert _routes(tmp_path, source) == [("flask", "GET", "/z")]
