"""Base class for language-specific edge extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EdgeExtractor(ABC):
    """Extract (source_class, target_class) edges from source code.

    Each language implements its own subclass. The registry in __init__.py
    maps file extensions to extractor instances.

    To add a new language:
    1. Create a new file (e.g., kotlin.py)
    2. Subclass EdgeExtractor
    3. Register in __init__.py
    """

    @abstractmethod
    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        """Extract edges from source code.

        Args:
            source: file content as string
            src_name: file stem (e.g. "BeanFactory" from BeanFactory.java)
            project_root: project root path for first-party detection

        Returns:
            list of (source_class, target_class) tuples
        """

    def detect_root_packages(self, project_root: str) -> frozenset[str]:
        """Detect project root packages for first-party filtering.

        Override in subclasses that need build-file-based detection.
        Default: empty (no filtering).
        """
        return frozenset()
