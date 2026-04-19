"""Tests for ArchitecturalBoundaryAnalyzer."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.architectural_boundary import (
    VIOLATION_SKIP_LAYER,
    VIOLATION_WRONG_DIRECTION,
    _classify_layer,
)


class TestLayerClassification:
    def test_controller_is_ui_layer(self) -> None:
        assert _classify_layer("src/controllers/user_controller.py") == 0

    def test_service_is_business_layer(self) -> None:
        assert _classify_layer("src/services/user_service.py") == 1

    def test_repository_is_data_layer(self) -> None:
        assert _classify_layer("src/repositories/user_repo.py") == 2

    def test_unknown_path_returns_none(self) -> None:
        assert _classify_layer("src/utils/helpers.py") is None

    def test_handler_is_ui_layer(self) -> None:
        assert _classify_layer("src/handlers/request.go") == 0

    def test_dao_is_repository_layer(self) -> None:
        assert _classify_layer("src/dao/user_dao.java") == 2


class TestViolationConstants:
    def test_violation_types_are_distinct(self) -> None:
        types = {VIOLATION_SKIP_LAYER, VIOLATION_WRONG_DIRECTION}
        assert len(types) == 2
