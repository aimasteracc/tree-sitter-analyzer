#!/usr/bin/env python3
"""Tests for PythonImportResolver (Code Intelligence Graph)."""

import pytest
from pathlib import Path
from tree_sitter_analyzer.intelligence.import_resolver import PythonImportResolver


@pytest.fixture
def project_dir(tmp_path):
    """Create a mock Python project structure."""
    # Create directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "src" / "models").mkdir()
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "tests").mkdir()

    # Create files
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "auth" / "__init__.py").write_text("")
    (tmp_path / "src" / "auth" / "service.py").write_text("class AuthService: pass")
    (tmp_path / "src" / "auth" / "token.py").write_text("class TokenManager: pass")
    (tmp_path / "src" / "models" / "__init__.py").write_text("")
    (tmp_path / "src" / "models" / "user.py").write_text("class User: pass")
    (tmp_path / "src" / "utils" / "__init__.py").write_text("")
    (tmp_path / "src" / "utils" / "logger.py").write_text("def get_logger(): pass")
    (tmp_path / "main.py").write_text("from src.auth.service import AuthService")
    (tmp_path / "tests" / "test_auth.py").write_text("from src.auth.service import AuthService")

    return tmp_path


@pytest.fixture
def resolver():
    return PythonImportResolver()


class TestPythonImportResolverAbsolute:
    """Test absolute import resolution."""

    def test_resolve_absolute_import_module(self, resolver, project_dir):
        """Resolve 'from src.auth.service import AuthService'."""
        result = resolver.resolve_import(
            module_name="src.auth.service",
            imported_names=["AuthService"],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_resolved
        assert not result.is_external
        assert result.resolved_path.endswith("service.py")
        assert "AuthService" in result.imported_names

    def test_resolve_absolute_import_package(self, resolver, project_dir):
        """Resolve 'from src.auth import service'."""
        result = resolver.resolve_import(
            module_name="src.auth",
            imported_names=["service"],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_resolved
        assert not result.is_external

    def test_resolve_absolute_import_deep_module(self, resolver, project_dir):
        """Resolve 'from src.models.user import User'."""
        result = resolver.resolve_import(
            module_name="src.models.user",
            imported_names=["User"],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_resolved
        assert "User" in result.imported_names


class TestPythonImportResolverRelative:
    """Test relative import resolution."""

    def test_resolve_relative_import_same_package(self, resolver, project_dir):
        """Resolve 'from .token import TokenManager' inside auth/service.py."""
        result = resolver.resolve_import(
            module_name=".token",
            imported_names=["TokenManager"],
            source_file=str(project_dir / "src" / "auth" / "service.py"),
            project_root=str(project_dir),
            is_relative=True,
        )
        assert result.is_resolved
        assert not result.is_external
        assert "token.py" in result.resolved_path

    def test_resolve_relative_import_parent_package(self, resolver, project_dir):
        """Resolve 'from ..models.user import User' inside auth/service.py."""
        result = resolver.resolve_import(
            module_name="..models.user",
            imported_names=["User"],
            source_file=str(project_dir / "src" / "auth" / "service.py"),
            project_root=str(project_dir),
            is_relative=True,
        )
        assert result.is_resolved
        assert "user.py" in result.resolved_path

    def test_resolve_relative_import_current_package(self, resolver, project_dir):
        """Resolve 'from . import token' inside auth/service.py."""
        result = resolver.resolve_import(
            module_name=".",
            imported_names=["token"],
            source_file=str(project_dir / "src" / "auth" / "service.py"),
            project_root=str(project_dir),
            is_relative=True,
        )
        assert result.is_resolved


class TestPythonImportResolverExternal:
    """Test external import detection."""

    def test_resolve_stdlib_import(self, resolver, project_dir):
        """'import os' should be external."""
        result = resolver.resolve_import(
            module_name="os",
            imported_names=[],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_external

    def test_resolve_third_party_import(self, resolver, project_dir):
        """'import fastapi' should be external."""
        result = resolver.resolve_import(
            module_name="fastapi",
            imported_names=["FastAPI"],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_external

    def test_resolve_stdlib_submodule(self, resolver, project_dir):
        """'from pathlib import Path' should be external."""
        result = resolver.resolve_import(
            module_name="pathlib",
            imported_names=["Path"],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_external


class TestPythonImportResolverEdgeCases:
    """Test edge cases."""

    def test_resolve_nonexistent_module(self, resolver, project_dir):
        """Non-existent module should be marked as external."""
        result = resolver.resolve_import(
            module_name="nonexistent.module",
            imported_names=[],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        # If not found in project, treat as external
        assert result.is_external or not result.is_resolved

    def test_resolve_init_package(self, resolver, project_dir):
        """Import of a package should resolve to __init__.py."""
        result = resolver.resolve_import(
            module_name="src.auth",
            imported_names=[],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_resolved
        assert "__init__.py" in result.resolved_path or "auth" in result.resolved_path

    def test_resolve_empty_module_name(self, resolver, project_dir):
        """Empty module name should not crash."""
        result = resolver.resolve_import(
            module_name="",
            imported_names=[],
            source_file=str(project_dir / "main.py"),
            project_root=str(project_dir),
        )
        assert result.is_external or not result.is_resolved
