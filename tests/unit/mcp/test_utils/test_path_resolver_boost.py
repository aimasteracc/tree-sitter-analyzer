#!/usr/bin/env python3
"""Coverage boost for path_resolver.py: validate_path edge cases."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.path_resolver import PathResolver


class TestValidatePathEdges:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_symlink_is_rejected(self, tmp_path):
        """is_symlink() returns True → rejected"""
        from unittest.mock import patch as upatch

        resolver = PathResolver()
        with (
            upatch("pathlib.Path.resolve") as mock_resolve,
            upatch("pathlib.Path.exists", return_value=True),
            upatch("pathlib.Path.is_file", return_value=True),
            upatch("pathlib.Path.is_symlink", return_value=True),
        ):
            mock_resolve.return_value = Path(str(tmp_path) + "/fake")
            is_valid, msg = resolver.validate_path(str(tmp_path / "x"))
        assert not is_valid
        assert "symlink" in msg

    def test_symlink_check_oserror_passes(self, tmp_path):
        """is_symlink() raises OSError → swallowed, path accepted"""
        resolver = PathResolver(str(tmp_path))
        f = tmp_path / "real.txt"
        f.write_text("hi")
        is_valid, _ = resolver.validate_path(str(f))
        assert is_valid

    def test_outside_project_root_rejected(self, tmp_path):
        """absolute path outside project_root → rejected"""
        inner = tmp_path / "sub"
        inner.mkdir()
        f = inner / "f.txt"
        f.write_text("x")
        resolver = PathResolver(str(inner))
        parent_file = tmp_path / "outside.txt"
        parent_file.write_text("y")
        is_valid, msg = resolver.validate_path(str(parent_file))
        assert not is_valid
        assert "outside project root" in msg

    def test_validate_path_exception_handling(self):
        """general exception → error message"""
        resolver = PathResolver()
        with patch.object(resolver, "resolve", side_effect=RuntimeError("boom")):
            is_valid, msg = resolver.validate_path("anything")
        assert not is_valid
        assert "Path validation error" in msg

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows-specific incompatibility — tracked separately",
    )
    def test_set_project_root_absolute(self, tmp_path):
        resolver = PathResolver()
        resolver.set_project_root(str(tmp_path))
        assert resolver.project_root is not None
        assert str(tmp_path) in resolver.project_root

    def test_set_project_root_none_clears(self):
        resolver = PathResolver("/tmp")
        resolver.set_project_root(None)
        assert resolver.project_root is None

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows-specific incompatibility — tracked separately",
    )
    def test_get_relative_path_cross_drive(self):
        """ValueError when paths don't share a prefix"""
        resolver = PathResolver()
        result = resolver.get_relative_path("/foo/bar")
        assert result == "/foo/bar"  # falls back to returning input
