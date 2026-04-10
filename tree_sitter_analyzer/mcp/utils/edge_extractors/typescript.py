"""TypeScript/JavaScript edge extractor — relative imports only."""

from __future__ import annotations

import re

from .base import EdgeExtractor


class TypeScriptEdgeExtractor(EdgeExtractor):
    """TypeScript/JS: only relative imports (./ ../) are first-party."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []

        # import { ClassName } from './...' or '../...'
        for m in re.finditer(
            r"import\s+(?:type\s+)?[{]([^}]+)[}]\s+from\s+['\"]"
            r"(\.\.?/[^'\"]+)['\"]",
            source,
        ):
            # Only relative imports (start with ./ or ../)
            for cls in re.split(r"[,\s]+", m.group(1)):
                cls = cls.strip()
                if cls and re.match(r"^[A-Z]\w*$", cls):
                    edges.append((src_name, cls))

        return edges
