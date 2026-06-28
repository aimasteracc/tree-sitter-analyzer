"""Static configuration builders and path helpers for language detection.

This module is intentionally kept unified.  Mycelium flagged it as a "covert hub"
with 8-10 callers, but the actual call graph has exactly **two** consumers:
  - tree_sitter_analyzer/language_detector.py  (production)
  - tests/unit/core/test_language_detector_helpers.py  (test)

Both import all six functions.  Splitting into _language_path_helpers.py and
_language_detector_helpers.py would yield a ~19-line path file with a single
downstream consumer, adding indirection without reducing coupling.

Logical groups within this file:
  GROUP 1 — filesystem/path helpers (low-level OS operations):
      normalize_detection_path, get_path_mtime_ns
  GROUP 2 — language pattern builders (detection heuristics):
      build_extension_confidence_map, build_content_pattern_weights
  GROUP 3 — shared-cache integration:
      get_cached_language, store_cached_language
"""

import logging
import os
from pathlib import Path

from ..registry.shared_cache import get_shared_cache

logger = logging.getLogger("tree_sitter_analyzer.language_detector")


def build_extension_confidence_map() -> dict[str, tuple[str, float]]:
    return {
        ".java": ("java", 0.9),
        ".js": ("javascript", 0.9),
        ".jsx": ("javascript", 0.8),
        ".ts": ("typescript", 0.9),
        ".tsx": ("typescript", 0.8),
        ".mts": ("typescript", 0.9),
        ".cts": ("typescript", 0.9),
        ".py": ("python", 0.9),
        ".pyw": ("python", 0.8),
        ".c": ("c", 0.9),
        ".h": ("c", 0.7),
        ".cpp": ("cpp", 0.9),
        ".cxx": ("cpp", 0.9),
        ".cc": ("cpp", 0.9),
        ".hpp": ("cpp", 0.8),
        ".rs": ("rust", 0.9),
        ".go": ("go", 0.9),
        ".cs": ("csharp", 0.9),
        ".php": ("php", 0.9),
        ".rb": ("ruby", 0.9),
        ".swift": ("swift", 0.9),
        ".swiftinterface": ("swift", 0.9),
        ".kt": ("kotlin", 0.9),
        ".kts": ("kotlin", 0.9),
        ".scala": ("scala", 0.9),
        ".clj": ("clojure", 0.9),
        ".hs": ("haskell", 0.9),
        ".ml": ("ocaml", 0.9),
        ".fs": ("fsharp", 0.9),
        ".elm": ("elm", 0.9),
        ".dart": ("dart", 0.9),
        ".lua": ("lua", 0.9),
        ".r": ("r", 0.9),
        ".m": ("objectivec", 0.7),
        ".mm": ("objectivec", 0.8),
        ".md": ("markdown", 0.9),
        ".markdown": ("markdown", 0.9),
        ".mdown": ("markdown", 0.8),
        ".mkd": ("markdown", 0.8),
        ".mkdn": ("markdown", 0.8),
        ".mdx": ("markdown", 0.7),
        ".html": ("html", 0.9),
        ".htm": ("html", 0.9),
        ".xhtml": ("html", 0.8),
        ".css": ("css", 0.9),
        ".scss": ("css", 0.8),
        ".sass": ("css", 0.8),
        ".less": ("css", 0.8),
        ".json": ("json", 0.9),
        ".jsonc": ("json", 0.8),
        ".json5": ("json", 0.8),
        ".sql": ("sql", 0.9),
        ".yaml": ("yaml", 0.9),
        ".yml": ("yaml", 0.9),
    }


def build_content_pattern_weights() -> dict[str, list[tuple[str, float]]]:
    return {
        "java": [
            (r"package\s+[\w\.]+\s*;", 0.3),
            (r"public\s+class\s+\w+", 0.3),
            (r"import\s+[\w\.]+\s*;", 0.2),
            (r"@\w+\s*\(", 0.2),
        ],
        "python": [
            (r"def\s+\w+\s*\(", 0.3),
            (r"import\s+\w+", 0.2),
            (r"from\s+\w+\s+import", 0.2),
            (r'if\s+__name__\s*==\s*["\']__main__["\']', 0.3),
        ],
        "javascript": [
            (r"function\s+\w+\s*\(", 0.3),
            (r"var\s+\w+\s*=", 0.2),
            (r"let\s+\w+\s*=", 0.2),
            (r"const\s+\w+\s*=", 0.2),
            (r"console\.log\s*\(", 0.1),
        ],
        "typescript": [
            (r"interface\s+\w+", 0.3),
            (r"type\s+\w+\s*=", 0.2),
            (r":\s*\w+\s*=", 0.2),
            (r"export\s+(interface|type|class)", 0.2),
        ],
        "c": [
            (r"#include\s*<[\w\.]+>", 0.3),
            (r"int\s+main\s*\(", 0.3),
            (r"printf\s*\(", 0.2),
            (r"#define\s+\w+", 0.2),
        ],
        "cpp": [
            (r"#include\s*<[\w\.]+>", 0.2),
            (r"using\s+namespace\s+\w+", 0.3),
            (r"std::\w+", 0.2),
            (r"class\s+\w+\s*{", 0.3),
        ],
        "markdown": [
            (r"^#{1,6}\s+", 0.4),
            (r"^\s*[-*+]\s+", 0.3),
            (r"```[\w]*", 0.3),
            (r"\[.*\]\(.*\)", 0.2),
            (r"!\[.*\]\(.*\)", 0.2),
            (r"^\s*>\s+", 0.2),
            (r"^\s*\|.*\|", 0.2),
            (r"^[-=]{3,}$", 0.2),
        ],
        "html": [
            (r"<!DOCTYPE\s+html", 0.4),
            (r"<html[^>]*>", 0.3),
            (r"<head[^>]*>", 0.3),
            (r"<body[^>]*>", 0.3),
            (r"<div[^>]*>", 0.2),
            (r"<p[^>]*>", 0.2),
            (r"<a\s+href=", 0.2),
            (r"<img\s+src=", 0.2),
        ],
        "css": [
            (r"[.#][\w-]+\s*{", 0.4),
            (r"@media\s+", 0.3),
            (r"@import\s+", 0.3),
            (r"@keyframes\s+", 0.3),
            (r":\s*[\w-]+\s*;", 0.2),
            (r"color\s*:", 0.2),
            (r"font-", 0.2),
            (r"margin\s*:", 0.2),
        ],
    }


def normalize_detection_path(file_path: str, project_root: str | None) -> str:
    try:
        path = Path(file_path).expanduser()
        if project_root and not path.is_absolute():
            return str((Path(project_root).expanduser() / path).resolve()).replace(
                "\\", "/"
            )
        return str(path.resolve()).replace("\\", "/")
    except Exception:
        return file_path


def get_path_mtime_ns(abs_path: str) -> int | None:
    try:
        if os.path.exists(abs_path):
            return os.stat(abs_path).st_mtime_ns
    except (PermissionError, OSError):
        return None
    return None


def get_cached_language(
    abs_path: str, mtime_ns: int, project_root: str | None
) -> str | None:
    try:
        cached = get_shared_cache().get_language_meta(
            abs_path, project_root=project_root
        )
        if (
            cached
            and cached.get("mtime_ns") == mtime_ns
            and isinstance(cached.get("language"), str)
        ):
            cached_lang = cached["language"]
            return cached_lang if cached_lang.strip() else "unknown"
    except Exception as e:
        logger.debug("Language cache lookup failed for %s: %s", abs_path, e)
    return None


def store_cached_language(
    abs_path: str, result: str, mtime_ns: int | None, project_root: str | None
) -> None:
    if mtime_ns is None:
        return

    try:
        get_shared_cache().set_language_meta(
            abs_path,
            {"language": result, "mtime_ns": mtime_ns},
            project_root=project_root,
        )
    except Exception as e:
        logger.debug("Language cache store failed for %s: %s", abs_path, e)
