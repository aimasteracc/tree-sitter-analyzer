"""Installed parser package metadata helpers for readiness advice."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from typing import Any


def parser_distribution_signals(package_name: str) -> dict[str, Any]:
    """Return local distribution metadata for an installed parser package."""
    if not package_name:
        return _empty_distribution_signals()
    try:
        distribution = importlib_metadata.distribution(package_name)
    except importlib_metadata.PackageNotFoundError:
        return _empty_distribution_signals()
    project_urls = _distribution_project_urls(distribution)
    return {
        "parser_package_version": distribution.version,
        "parser_project_urls": project_urls,
        "parser_maintenance_urls": _maintenance_urls(project_urls),
    }


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
