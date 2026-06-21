"""Tests for web framework route detection: Express and Spring Boot."""

from __future__ import annotations

from pathlib import Path

from tests.unit.conftest import _write
from tree_sitter_analyzer.route_detector import RouteDetector

# ---------------------------------------------------------------------------
# Express
# ---------------------------------------------------------------------------


class TestExpressDetection:
    def test_detect_express_routes(self, express_project: Path):
        routes = RouteDetector(str(express_project)).detect_all()
        assert len(routes) == 3
        methods = sorted(r.http_method for r in routes)
        assert methods == ["DELETE", "GET", "POST"]

    def test_express_framework_label(self, express_project: Path):
        routes = RouteDetector(str(express_project)).detect_all()
        assert all(r.framework == "express" for r in routes)
        assert all(r.language == "javascript" for r in routes)


# ---------------------------------------------------------------------------
# Finding 3: Express receiver-name filter (round-16b dogfood)
# ---------------------------------------------------------------------------


class TestExpressReceiverFilter:
    """``X.post('/x', ...)`` must not match unless X is an Express receiver."""

    def test_client_http_call_is_not_a_route(self, tmp_path: Path):
        """Custom apiClient.post('/save', ...) is a client call, not a route.

        Reproduces round-16b finding 3: round-15 RouteDetector reported
        2 Express routes from a file that doesn't even import express and
        whose ``.post(...)`` calls were against a custom ``apiClient``
        object — a common pattern in vanilla JS.
        """
        _write(
            tmp_path,
            "client.js",
            """\
const API_BASE = 'https://api.example.com';
const apiClient = {
    async post(endpoint, data) {
        return fetch(API_BASE + endpoint, {method: 'POST', body: JSON.stringify(data)});
    },
    async get(endpoint) {
        return fetch(API_BASE + endpoint);
    },
};

async function handleAction(action, element) {
    switch (action) {
        case 'save':
            await apiClient.post('/save', {data: 'example'});
            break;
        case 'delete':
            await apiClient.post('/delete', {id: element.dataset.id});
            break;
    }
}
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes == [], (
            f"Finding 3: apiClient.post('/...') falsely matched as route — got {len(routes)}"
        )

    def test_express_routes_still_match_with_router_receiver(self, tmp_path: Path):
        """userRouter.post(...) with require('express') still detected."""
        _write(
            tmp_path,
            "routes.js",
            """\
const express = require('express');
const userRouter = express.Router();
userRouter.get('/users', listUsers);
userRouter.post('/users', createUser);
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 2, (
            "Custom <name>Router receivers must still match when file "
            f"imports express. Got {len(routes)} routes."
        )

    def test_app_post_without_express_import_is_skipped(self, tmp_path: Path):
        """app.post(...) is ignored unless the file imports express.

        Defends against random ``app`` namespaces in non-Express code
        (e.g. Electron's ``app``) producing false positives.
        """
        _write(
            tmp_path,
            "electron-main.js",
            """\
const { app } = require('electron');
app.post('/some-channel', () => {});
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes == [], (
            f"Finding 3: non-express `app.post()` matched anyway — got {len(routes)}"
        )

    def test_es_module_express_import_still_detected(self, tmp_path: Path):
        """from 'express' should also count as an express import."""
        _write(
            tmp_path,
            "app.js",
            """\
import express from 'express';
const app = express();
app.get('/health', (req, res) => res.send('ok'));
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 1
        assert routes[0].url_pattern == "/health"


# ---------------------------------------------------------------------------
# Spring Boot
# ---------------------------------------------------------------------------


class TestSpringDetection:
    def test_detect_spring_routes(self, spring_project: Path):
        routes = RouteDetector(str(spring_project)).detect_all()
        assert len(routes) >= 2  # GetMapping + PostMapping  # ratchet: nondeterministic
        methods = {r.http_method for r in routes}
        assert "GET" in methods
        assert "POST" in methods

    def test_spring_framework_label(self, spring_project: Path):
        routes = RouteDetector(str(spring_project)).detect_all()
        assert all(r.framework == "spring" for r in routes)
        assert all(r.language == "java" for r in routes)
