from __future__ import annotations

from typing import Any


class SharedCache:
    """
    Shared cache for MCP tools to reduce redundant operations.
    Implements singleton pattern to ensure sharing across tool instances.
    """

    _instance = None

    def __new__(cls) -> SharedCache:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._language_cache: dict[str, str] = {}
        self._language_meta_cache: dict[str, dict[str, Any]] = {}
        self._security_cache: dict[str, tuple[bool, str]] = {}
        self._metrics_cache: dict[str, dict[str, Any]] = {}
        self._resolved_paths: dict[str, str] = {}

    def _make_key(self, kind: str, path: str, project_root: str | None) -> str:
        """
        Build a stable scoped cache key.

        Notes:
        - project_root is included to avoid cross-project cache pollution.
        - kind differentiates different caches sharing the same underlying dict key space.
        """
        pr = project_root or ""
        return f"{pr}::{kind}::{path}"

    def get_language(
        self, file_path: str, project_root: str | None = None
    ) -> str | None:
        return self._language_cache.get(
            self._make_key("language", file_path, project_root)
        )

    def set_language(
        self, file_path: str, language: str, project_root: str | None = None
    ) -> None:
        self._language_cache[self._make_key("language", file_path, project_root)] = (
            language
        )

    def get_language_meta(
        self, abs_path: str, project_root: str | None = None
    ) -> dict[str, Any] | None:
        return self._language_meta_cache.get(
            self._make_key("language_meta", abs_path, project_root)
        )

    def set_language_meta(
        self, abs_path: str, meta: dict[str, Any], project_root: str | None = None
    ) -> None:
        self._language_meta_cache[
            self._make_key("language_meta", abs_path, project_root)
        ] = meta

    def get_security_validation(
        self, file_path: str, project_root: str | None = None
    ) -> tuple[bool, str] | None:
        return self._security_cache.get(
            self._make_key("security", file_path, project_root)
        )

    def set_security_validation(
        self, file_path: str, result: tuple[bool, str], project_root: str | None = None
    ) -> None:
        self._security_cache[self._make_key("security", file_path, project_root)] = (
            result
        )

    def get_metrics(
        self, file_path: str, project_root: str | None = None
    ) -> dict[str, Any] | None:
        return self._metrics_cache.get(
            self._make_key("metrics", file_path, project_root)
        )

    def set_metrics(
        self, file_path: str, metrics: dict[str, Any], project_root: str | None = None
    ) -> None:
        self._metrics_cache[self._make_key("metrics", file_path, project_root)] = (
            metrics
        )

    def get_resolved_path(
        self, original_path: str, project_root: str | None = None
    ) -> str | None:
        return self._resolved_paths.get(
            self._make_key("resolved_path", original_path, project_root)
        )

    def set_resolved_path(
        self, original_path: str, resolved_path: str, project_root: str | None = None
    ) -> None:
        self._resolved_paths[
            self._make_key("resolved_path", original_path, project_root)
        ] = resolved_path

    def clear(self) -> None:
        """Clear all caches"""
        self._initialize()


# Global instance access
def get_shared_cache() -> SharedCache:
    return SharedCache()
