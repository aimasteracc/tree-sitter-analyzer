"""Installed parser package metadata helpers for readiness advice."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from typing import Any


def parser_distribution_signals(
    package_name: str,
    requirement_spec: str | None = None,
) -> dict[str, Any]:
    """Return local distribution metadata for an installed parser package.

    ``parser_package_version`` is the *installed* distribution version and is
    ALWAYS ``""`` when the package is not installed.  Callers can trust that a
    non-empty value means the package is actually installed.

    ``parser_required_spec`` is the raw requirement string from pyproject
    (e.g. ``"tree-sitter-swift>=0.7.2"``).  It is populated whenever
    ``requirement_spec`` is provided, regardless of install state, so agents
    can distinguish "no spec declared" from "declared but not installed".

    Args:
        package_name: The Python package name (e.g., "tree-sitter-swift")
        requirement_spec: Optional raw requirement string from pyproject
                         (e.g., "tree-sitter-swift>=0.7.2")
    """
    required_spec = requirement_spec or ""
    if not package_name:
        return _empty_distribution_signals(required_spec)
    try:
        distribution = importlib_metadata.distribution(package_name)
    except importlib_metadata.PackageNotFoundError:
        return _empty_distribution_signals(required_spec)
    project_urls = _distribution_project_urls(distribution)
    return {
        "parser_package_version": distribution.version,
        "parser_required_spec": required_spec,
        "parser_project_urls": project_urls,
        "parser_maintenance_urls": _maintenance_urls(project_urls),
    }


def _empty_distribution_signals(required_spec: str = "") -> dict[str, Any]:
    return {
        "parser_package_version": "",
        "parser_required_spec": required_spec,
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
