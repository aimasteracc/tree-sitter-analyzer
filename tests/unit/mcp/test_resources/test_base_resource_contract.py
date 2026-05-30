"""Contract tests for MCP resource classes.

These tests verify invariants that every concrete resource must satisfy:
  1. test_initialization     — instance is not None, _uri_pattern is set.
  2. test_resource_info_structure — get_resource_info() returns dict with
                               required keys: name, description, uri_template,
                               mime_type; all values are non-empty strings.
  3. test_uri_pattern_validation — _uri_pattern is a compiled regex.
  4. test_matches_valid_uri  — matches_uri() returns True for known-valid URIs.
  5. test_malformed_uri_handling — matches_uri() returns False for URIs that
                               lack a path segment after the authority.
  6. test_rejects_invalid_scheme — matches_uri() returns False for wrong schemes.
  7. test_get_resource_info  — get_resource_info() does not raise and returns a dict.

Specific values (name, uri_template, etc.) stay in per-resource test files.
Any new resource class should be added to _RESOURCE_CASES below.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.resources.code_file_resource import CodeFileResource
from tree_sitter_analyzer.mcp.resources.project_stats_resource import (
    ProjectStatsResource,
)

# ---------------------------------------------------------------------------
# Per-resource parametrize data
# ---------------------------------------------------------------------------

_RESOURCE_CASES: list[tuple[Any, list[str]]] = [
    (
        CodeFileResource,
        [
            "code://file/src/main.py",
            "code://file/test.js",
            "code://file/scripts/helper.sh",
        ],
    ),
    (
        ProjectStatsResource,
        [
            "code://stats/overview",
            "code://stats/languages",
            "code://stats/complexity",
            "code://stats/files",
        ],
    ),
]


def _resource_id(param: tuple) -> str:
    cls, _ = param
    return cls.__name__


@pytest.fixture(params=_RESOURCE_CASES, ids=_resource_id)
def resource_and_valid_uris(request):
    cls, valid_uris = request.param
    return cls(), valid_uris


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestBaseResourceContract:
    """Invariants shared by every concrete resource class."""

    def test_initialization(self, resource_and_valid_uris):
        resource, _ = resource_and_valid_uris
        assert resource is not None
        assert resource._uri_pattern is not None

    def test_uri_pattern_validation(self, resource_and_valid_uris):
        resource, _ = resource_and_valid_uris
        assert isinstance(resource._uri_pattern, re.Pattern)

    def test_get_resource_info(self, resource_and_valid_uris):
        resource, _ = resource_and_valid_uris
        info = resource.get_resource_info()
        assert isinstance(info, dict)

    def test_resource_info_structure(self, resource_and_valid_uris):
        resource, _ = resource_and_valid_uris
        info = resource.get_resource_info()
        for key in ("name", "description", "uri_template", "mime_type"):
            assert key in info, f"get_resource_info() missing key: {key!r}"
            assert isinstance(info[key], str) and info[key], (
                f"get_resource_info()[{key!r}] must be a non-empty string"
            )

    def test_matches_valid_uri(self, resource_and_valid_uris):
        resource, valid_uris = resource_and_valid_uris
        for uri in valid_uris:
            assert resource.matches_uri(uri), (
                f"{type(resource).__name__}.matches_uri({uri!r}) returned False"
            )

    def test_malformed_uri_handling(self, resource_and_valid_uris):
        """URIs without a path segment after the authority must be rejected."""
        resource, _ = resource_and_valid_uris
        malformed = [
            "code://",
            "invalid",
            "http://example.com",
        ]
        for uri in malformed:
            assert not resource.matches_uri(uri), (
                f"{type(resource).__name__}.matches_uri({uri!r}) should return False"
            )

    def test_rejects_invalid_scheme(self, resource_and_valid_uris):
        resource, _ = resource_and_valid_uris
        wrong_scheme_uris = [
            "http://example.com/file.py",
            "data://file/test.py",
            "ftp://file/test.py",
        ]
        for uri in wrong_scheme_uris:
            assert not resource.matches_uri(uri), (
                f"{type(resource).__name__}.matches_uri({uri!r}) should return False"
            )
