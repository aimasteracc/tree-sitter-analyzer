"""Python edge extractor — first-party filtering via stdlib_module_names."""

from __future__ import annotations

import re
import sys

from .base import EdgeExtractor

_STDLIB: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())

# Cache third-party packages (computed once per process)
_third_party_cache: set[str] | None = None


def _get_third_party() -> set[str]:
    global _third_party_cache  # noqa: PLW0603
    if _third_party_cache is not None:
        return _third_party_cache
    try:
        from importlib.metadata import packages_distributions

        _third_party_cache = set(packages_distributions().keys())
    except ImportError:
        _third_party_cache = set()
    return _third_party_cache


def _is_first_party(module: str) -> bool:
    """Check if a Python module is first-party (not stdlib, not third-party)."""
    top = module.split(".")[0]
    if top in _STDLIB:
        return False
    if top in _get_third_party():
        return False
    return True


class PythonEdgeExtractor(EdgeExtractor):
    """Python: filter stdlib and third-party imports using built-in APIs."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []

        # from module import ClassName
        for m in re.finditer(
            r"from\s+([\w.]+)\s+import\s+([\w,\s]+)", source
        ):
            module = m.group(1)
            if not _is_first_party(module):
                continue
            for cls in re.split(r"[,\s]+", m.group(2)):
                cls = cls.strip()
                if cls and re.match(r"^[A-Z]\w*$", cls):
                    edges.append((src_name, cls))

        # import module.ClassName
        for m in re.finditer(
            r"^import\s+([\w.]+\.(\w+))", source, re.M
        ):
            module = m.group(1)
            if _is_first_party(module):
                edges.append((src_name, m.group(2)))

        return edges
