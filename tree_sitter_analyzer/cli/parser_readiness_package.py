"""Installed parser package metadata helpers for readiness advice."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from typing import Any

try:
    from packaging.requirements import Requirement
except ImportError:
    # Fallback for environments where packaging is not available
    # (though it should be a transitive dependency)
    Requirement = None  # type: ignore


def parser_distribution_signals(
    package_name: str,
    requirement_spec: str | None = None,
) -> dict[str, Any]:
    """Return local distribution metadata for an installed parser package.

    If the package is installed, returns the actual distribution version.
    If not installed but requirement_spec is provided, attempts to extract
    the version constraint from the spec (e.g., "tree-sitter-swift>=0.7.2").

    Args:
        package_name: The Python package name (e.g., "tree-sitter-swift")
        requirement_spec: Optional requirement string with version constraints
                         (e.g., "tree-sitter-swift>=0.7.2")
    """
    if not package_name:
        return _empty_distribution_signals()
    try:
        distribution = importlib_metadata.distribution(package_name)
    except importlib_metadata.PackageNotFoundError:
        # Package not installed; try to extract version from requirement spec
        if requirement_spec:
            version = _extract_version_from_requirement(requirement_spec)
            if version:
                return {
                    "parser_package_version": version,
                    "parser_project_urls": {},
                    "parser_maintenance_urls": {},
                }
        return _empty_distribution_signals()
    project_urls = _distribution_project_urls(distribution)
    return {
        "parser_package_version": distribution.version,
        "parser_project_urls": project_urls,
        "parser_maintenance_urls": _maintenance_urls(project_urls),
    }


def _extract_version_from_requirement(requirement_spec: str) -> str:
    """Extract version from a requirement spec like 'tree-sitter-swift>=0.7.2'."""
    if not Requirement:
        # packaging not available; fallback regex extraction
        return _extract_version_regex(requirement_spec)
    try:
        req = Requirement(requirement_spec)
        # Try to get the minimum version from '>=' constraint
        for spec in req.specifier:
            if spec.operator == ">=":
                return spec.version
        # Fallback: if there are any constraints, use the first version mentioned
        for spec in req.specifier:
            if spec.version:
                return spec.version
        return ""
    except Exception:
        # If parsing fails, return empty string
        return ""


def _extract_version_regex(requirement_spec: str) -> str:
    """Fallback regex-based version extraction."""
    import re

    # Match patterns like >=0.7.2, ==0.7.2, etc.
    match = re.search(r"[><=!]+([0-9.]+)", requirement_spec)
    if match:
        return match.group(1)
    return ""


def _empty_distribution_signals() -> dict[str, Any]:
    return {
        "parser_package_version": "",
        "parser_project_urls": {},
        "parser_maintenance_urls": {},
    }


def _distribution_project_urls(
    distribution: importlib_metadata.Distribution,
) -> dict[str, str]:
    metadata = distribution.metadata
    urls: dict[str, str] = {}
    homepage = metadata.get("Home-page")
    if homepage:
        urls["Homepage"] = homepage
    for item in metadata.get_all("Project-URL") or []:
        label, separator, url = item.partition(",")
        if separator and url.strip():
            urls[label.strip() or "Project"] = url.strip()
    return urls


def _maintenance_urls(project_urls: dict[str, str]) -> dict[str, str]:
    repository = _first_project_url(project_urls)
    if not repository:
        return {}
    normalized = repository.rstrip("/")
    if not normalized.startswith("https://github.com/"):
        return {"repository": normalized}
    return {
        "repository": normalized,
        "commits": f"{normalized}/commits",
        "releases": f"{normalized}/releases",
        "actions": f"{normalized}/actions",
        "issues": f"{normalized}/issues",
    }


def _first_project_url(project_urls: dict[str, str]) -> str:
    if not project_urls:
        return ""
    return next(iter(project_urls.values()))
