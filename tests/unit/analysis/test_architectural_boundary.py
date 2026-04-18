"""Unit tests for ArchitecturalBoundaryAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.architectural_boundary import (
    LAYER_REPOSITORY,
    LAYER_SERVICE,
    LAYER_UI,
    VIOLATION_CIRCULAR,
    VIOLATION_SKIP_LAYER,
    VIOLATION_WRONG_DIRECTION,
    ArchitecturalBoundaryAnalyzer,
    BoundaryResult,
    BoundaryViolation,
    LayerSummary,
    _classify_layer,
    _describe_violation,
)


@pytest.fixture
def analyzer() -> ArchitecturalBoundaryAnalyzer:
    return ArchitecturalBoundaryAnalyzer()


def _write_tmp(project_dir: str, rel_path: str, content: str) -> str:
    full = Path(project_dir) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return str(full)


class TestClassifyLayer:
    def test_controller_layer(self) -> None:
        assert _classify_layer("src/controllers/user_controller.py") == LAYER_UI

    def test_handler_layer(self) -> None:
        assert _classify_layer("app/handlers/request_handler.java") == LAYER_UI

    def test_route_layer(self) -> None:
        assert _classify_layer("routes/api.ts") == LAYER_UI

    def test_view_layer(self) -> None:
        assert _classify_layer("views/dashboard.py") == LAYER_UI

    def test_endpoint_layer(self) -> None:
        assert _classify_layer("endpoints/user_endpoint.py") == LAYER_UI

    def test_api_layer(self) -> None:
        assert _classify_layer("api/routes.py") == LAYER_UI

    def test_service_layer(self) -> None:
        assert _classify_layer("services/user_service.py") == LAYER_SERVICE

    def test_business_layer(self) -> None:
        assert _classify_layer("business/order_logic.java") == LAYER_SERVICE

    def test_application_layer(self) -> None:
        assert _classify_layer("application/usecase.py") == LAYER_SERVICE

    def test_domain_layer(self) -> None:
        assert _classify_layer("domain/user_domain.py") == LAYER_SERVICE

    def test_repository_layer(self) -> None:
        assert _classify_layer("repositories/user_repo.py") == LAYER_REPOSITORY

    def test_dao_layer(self) -> None:
        assert _classify_layer("daos/user_dao.java") == LAYER_REPOSITORY

    def test_data_layer(self) -> None:
        assert _classify_layer("data/access.py") == LAYER_REPOSITORY

    def test_model_layer(self) -> None:
        assert _classify_layer("models/user.py") == LAYER_REPOSITORY

    def test_entity_layer(self) -> None:
        assert _classify_layer("entities/order.java") == LAYER_REPOSITORY

    def test_persistence_layer(self) -> None:
        assert _classify_layer("persistence/db.py") == LAYER_REPOSITORY

    def test_infrastructure_layer(self) -> None:
        assert _classify_layer("infrastructure/database.py") == LAYER_REPOSITORY

    def test_unknown_layer(self) -> None:
        assert _classify_layer("utils/helpers.py") is None

    def test_config_layer(self) -> None:
        assert _classify_layer("config/settings.py") is None

    def test_windows_path(self) -> None:
        assert _classify_layer("src\\controllers\\user.py") == LAYER_UI

    def test_case_insensitive(self) -> None:
        assert _classify_layer("src/Controllers/UserController.cs") == LAYER_UI
        assert _classify_layer("src/Services/UserService.cs") == LAYER_SERVICE
        assert _classify_layer("src/Repositories/UserRepository.cs") == LAYER_REPOSITORY


class TestBoundaryViolation:
    def test_to_dict(self) -> None:
        v = BoundaryViolation(
            source_file="controllers/user.py",
            target_file="repositories/user_repo.py",
            source_layer=LAYER_UI,
            target_layer=LAYER_REPOSITORY,
            violation_type=VIOLATION_SKIP_LAYER,
        )
        d = v.to_dict()
        assert d["source_file"] == "controllers/user.py"
        assert d["target_file"] == "repositories/user_repo.py"
        assert d["source_layer"] == "UI/Controller"
        assert d["target_layer"] == "Repository/DAO"
        assert d["violation_type"] == VIOLATION_SKIP_LAYER
        assert "skips middle" in d["description"]

    def test_wrong_direction_description(self) -> None:
        v = BoundaryViolation(
            source_file="repositories/user_repo.py",
            target_file="controllers/user.py",
            source_layer=LAYER_REPOSITORY,
            target_layer=LAYER_UI,
            violation_type=VIOLATION_WRONG_DIRECTION,
        )
        assert "wrong direction" in v.to_dict()["description"]

    def test_circular_description(self) -> None:
        v = BoundaryViolation(
            source_file="controllers/user.py",
            target_file="services/user_service.py",
            source_layer=LAYER_UI,
            target_layer=LAYER_SERVICE,
            violation_type=VIOLATION_CIRCULAR,
        )
        assert "Circular" in v.to_dict()["description"]

    def test_frozen(self) -> None:
        v = BoundaryViolation(
            source_file="a.py", target_file="b.py",
            source_layer=0, target_layer=2,
            violation_type=VIOLATION_SKIP_LAYER,
        )
        with pytest.raises(AttributeError):
            v.source_file = "x.py"  # type: ignore[misc]


class TestLayerSummary:
    def test_to_dict(self) -> None:
        ls = LayerSummary(
            layer=LAYER_UI,
            layer_name="UI/Controller",
            file_count=5,
            violation_count=2,
        )
        d = ls.to_dict()
        assert d["layer"] == LAYER_UI
        assert d["layer_name"] == "UI/Controller"
        assert d["file_count"] == 5
        assert d["violation_count"] == 2


class TestBoundaryResult:
    def test_to_dict(self) -> None:
        v = BoundaryViolation(
            source_file="a.py", target_file="b.py",
            source_layer=LAYER_UI, target_layer=LAYER_REPOSITORY,
            violation_type=VIOLATION_SKIP_LAYER,
        )
        ls = LayerSummary(
            layer=LAYER_UI, layer_name="UI/Controller",
            file_count=3, violation_count=1,
        )
        r = BoundaryResult(
            project_root="/tmp",
            total_files=10,
            classified_files=8,
            violations=(v,),
            circular_dependencies=(),
            compliance_score=0.85,
            layer_summary=(ls,),
        )
        d = r.to_dict()
        assert d["total_files"] == 10
        assert d["classified_files"] == 8
        assert d["compliance_score"] == 0.85
        assert d["violation_count"] == 1
        assert d["circular_count"] == 0
        assert len(d["violations"]) == 1
        assert len(d["layer_summary"]) == 1

    def test_frozen(self) -> None:
        r = BoundaryResult(
            project_root="/tmp", total_files=0, classified_files=0,
            violations=(), circular_dependencies=(),
            compliance_score=1.0, layer_summary=(),
        )
        with pytest.raises(AttributeError):
            r.total_files = 99  # type: ignore[misc]


class TestAnalyzerEmptyProject:
    def test_nonexistent_path(self, analyzer: ArchitecturalBoundaryAnalyzer) -> None:
        result = analyzer.analyze_project("/nonexistent/path")
        assert result.total_files == 0
        assert result.classified_files == 0
        assert result.compliance_score == 1.0
        assert len(result.violations) == 0

    def test_empty_directory(self, analyzer: ArchitecturalBoundaryAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 0
            assert result.compliance_score == 1.0


class TestAnalyzerCleanArchitecture:
    def test_no_violations_proper_layering(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user_controller.py",
                       "from services.user_service import UserService\n")
            _write_tmp(tmp, "services/user_service.py",
                       "from repositories.user_repo import UserRepo\n")
            _write_tmp(tmp, "repositories/user_repo.py",
                       "import sqlite3\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 0
            assert result.compliance_score == 1.0

    def test_skip_layer_violation(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user_controller.py",
                       "from repositories.user_repo import UserRepo\n")
            _write_tmp(tmp, "services/user_service.py",
                       "from repositories.user_repo import UserRepo\n")
            _write_tmp(tmp, "repositories/user_repo.py",
                       "import sqlite3\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 1
            v = result.violations[0]
            assert v.violation_type == VIOLATION_SKIP_LAYER
            assert v.source_layer == LAYER_UI
            assert v.target_layer == LAYER_REPOSITORY

    def test_wrong_direction_violation(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user_controller.py", "# controller\n")
            _write_tmp(tmp, "services/user_service.py", "# service\n")
            _write_tmp(tmp, "repositories/user_repo.py",
                       "from controllers.user_controller import UserController\n")

            result = analyzer.analyze_project(tmp)
            assert len(result.violations) == 1
            v = result.violations[0]
            assert v.violation_type == VIOLATION_WRONG_DIRECTION
            assert v.source_layer == LAYER_REPOSITORY
            assert v.target_layer == LAYER_UI

    def test_circular_dependency(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user.py",
                       "from services.user_service import UserService\n")
            _write_tmp(tmp, "services/user_service.py",
                       "from controllers.user import UserController\n")

            result = analyzer.analyze_project(tmp)
            assert len(result.circular_dependencies) == 1
            assert result.circular_dependencies[0].violation_type == VIOLATION_CIRCULAR


class TestAnalyzerMixedFiles:
    def test_unclassified_files_ignored(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user.py",
                       "from services.user_service import UserService\n")
            _write_tmp(tmp, "services/user_service.py",
                       "from repositories.user_repo import UserRepo\n")
            _write_tmp(tmp, "repositories/user_repo.py", "import sqlite3\n")
            _write_tmp(tmp, "utils/helpers.py", "# no layer\n")
            _write_tmp(tmp, "config/settings.py", "# no layer\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 0
            assert result.compliance_score == 1.0

    def test_compliance_score_calculation(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user.py",
                       "from services.svc import Svc\n"
                       "from repositories.repo import Repo\n")
            _write_tmp(tmp, "services/svc.py",
                       "from repositories.repo import Repo\n")
            _write_tmp(tmp, "repositories/repo.py", "pass\n")

            result = analyzer.analyze_project(tmp)
            skip_violations = [
                v for v in result.violations if v.violation_type == VIOLATION_SKIP_LAYER
            ]
            assert len(skip_violations) == 1
            assert result.compliance_score < 1.0
            assert result.compliance_score > 0.0


class TestAnalyzerJavaProject:
    def test_java_layer_detection(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "src/main/java/com/example/controller/UserController.java",
                       "import com.example.service.UserService;\n")
            _write_tmp(tmp, "src/main/java/com/example/service/UserService.java",
                       "import com.example.repository.UserRepository;\n")
            _write_tmp(tmp, "src/main/java/com/example/repository/UserRepository.java",
                       "import javax.persistence.*;\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 0


class TestAnalyzerTypeScriptProject:
    def test_typescript_layer_detection(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "routes/userRoutes.ts",
                       "import { UserService } from '../services/userService';\n")
            _write_tmp(tmp, "services/userService.ts",
                       "import { UserRepo } from '../data/userRepo';\n")
            _write_tmp(tmp, "data/userRepo.ts", "export class UserRepo {}\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 0


class TestAnalyzerCSharpProject:
    def test_csharp_layer_detection(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "Controllers/UserController.cs",
                       "using Services.UserService;\n")
            _write_tmp(tmp, "Services/UserService.cs",
                       "using Data.UserRepository;\n")
            _write_tmp(tmp, "Data/UserRepository.cs", "using System;\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 3
            assert len(result.violations) == 0


class TestAnalyzerAnalyzeGraph:
    def test_analyze_graph_directly(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        from tree_sitter_analyzer.analysis.dependency_graph import DependencyGraph

        graph = DependencyGraph(
            nodes={
                "controllers/user.py": {"path": "controllers/user.py", "lines": 10},
                "services/svc.py": {"path": "services/svc.py", "lines": 20},
                "repositories/repo.py": {"path": "repositories/repo.py", "lines": 30},
            },
            edges=[
                ("controllers/user.py", "repositories/repo.py"),
            ],
        )
        result = analyzer.analyze_graph(graph, "/test")
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == VIOLATION_SKIP_LAYER


class TestAnalyzerLayerSummary:
    def test_layer_summary_populated(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/a.py", "pass\n")
            _write_tmp(tmp, "controllers/b.py", "pass\n")
            _write_tmp(tmp, "services/c.py", "pass\n")
            _write_tmp(tmp, "repositories/d.py", "pass\n")

            result = analyzer.analyze_project(tmp)
            assert len(result.layer_summary) == 3
            ui_layer = next(
                ls for ls in result.layer_summary if ls.layer == LAYER_UI
            )
            assert ui_layer.file_count == 2

    def test_no_layers_detected(
        self, analyzer: ArchitecturalBoundaryAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "helpers/math.py", "pass\n")
            _write_tmp(tmp, "utils/text.py", "pass\n")

            result = analyzer.analyze_project(tmp)
            assert result.classified_files == 0
            assert len(result.layer_summary) == 0
            assert result.compliance_score == 1.0


class TestDescribeViolation:
    def test_unknown_violation_type(self) -> None:
        v = BoundaryViolation(
            source_file="a.py", target_file="b.py",
            source_layer=LAYER_UI, target_layer=LAYER_SERVICE,
            violation_type="unknown_type",
        )
        desc = _describe_violation(v)
        assert "Unknown violation" in desc
