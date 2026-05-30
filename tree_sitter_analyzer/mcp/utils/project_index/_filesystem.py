"""
File-system scanning helpers for project_index.

Provides file enumeration (fd / os.walk fallback), entry-point detection,
top-level structure building, language distribution, and module description
extraction.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec
from pathlib import Path
from typing import Any

from ._models import (
    _DIR_CONVENTIONS,
    _ENTRY_POINT_NAMES,
    _EXT_TO_LANGUAGE,
    _KEY_FILE_NAMES,
)
from ._readme import (
    _excerpt_from_blockquotes,
    _excerpt_from_paragraphs,
    _is_language_count_excluded,
    _read_directory_readme_title,
)

# Directories that are build/cache artifacts — exclude from structure output
_ARTIFACT_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".tree-sitter-cache",
        "node_modules",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        "target",
        "htmlcov",
        "coverage",
        ".coverage",
        "comprehensive_test_results",
        ".tox",
        ".eggs",
        "*.egg-info",
    }
)


def list_files(roots: list[str]) -> list[str]:
    """Return absolute paths of all regular files under *roots*.

    Tries ``fd`` first for speed; falls back to ``os.walk``.
    """
    abs_roots = [str(Path(r).resolve()) for r in roots]

    try:
        result = subprocess.run(  # nosec
            ["fd", "--type", "f", "--color", "never", "--absolute-path", "."]
            + abs_roots,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: os.walk
    files: list[str] = []
    skip_dirs = {
        ".git",
        ".tree-sitter-cache",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
    }
    for root_str in abs_roots:
        for dirpath, dirnames, filenames in os.walk(root_str):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                files.append(os.path.join(dirpath, fname))
    return files


def compute_language_distribution(all_files: list[str]) -> dict[str, int]:
    """Derive ``{language: count}`` from file extensions.

    Excludes fixture/golden/internal-doc paths so the language mix
    reflects the project's *real* source mix.
    """
    lang_dist: dict[str, int] = {}
    for filepath in all_files:
        if _is_language_count_excluded(filepath):
            continue
        ext = Path(filepath).suffix.lower()
        lang = _EXT_TO_LANGUAGE.get(ext)
        if lang:
            lang_dist[lang] = lang_dist.get(lang, 0) + 1
        else:
            lang_dist["other"] = lang_dist.get("other", 0) + 1
    return lang_dist


def collect_root_key_files(root_path: Path) -> list[str]:
    """Return key files (LICENSE/README/etc.) living at project root."""
    root_entries = {e.name.lower(): e.name for e in root_path.iterdir() if e.is_file()}
    return [
        root_entries[name] for name in sorted(root_entries) if name in _KEY_FILE_NAMES
    ]


def find_entry_points(root_path: Path) -> list[str]:
    """Scan the project root (up to 3 levels) for known entry-point files."""
    found: list[str] = []
    for entry_name in _ENTRY_POINT_NAMES:
        candidate = root_path / entry_name
        if candidate.is_file():
            found.append(entry_name)

    try:
        for subdir in root_path.iterdir():
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            found.extend(_scan_subdir_entry_points(root_path, subdir))
    except OSError:
        pass

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for ep in found:
        if ep not in seen:
            seen.add(ep)
            result.append(ep)
    return result


def _scan_subdir_entry_points(root_path: Path, subdir: Path) -> list[str]:
    """Return relative paths of entry-point files in ``subdir``."""
    results: list[str] = []
    for entry_name_raw in _ENTRY_POINT_NAMES:
        if "/" in entry_name_raw:
            continue
        candidate = subdir / entry_name_raw
        if not candidate.is_file():
            continue
        results.append(str(candidate.relative_to(root_path)))
    return results


def build_top_level_structure(
    root_path: Path, all_files: list[str]
) -> list[dict[str, Any]]:
    """Return depth-1 directory entries with file counts and depth-2 breakdown."""
    dir_counts: dict[str, int] = {}
    sub_counts: dict[str, dict[str, int]] = {}
    abs_root = root_path.resolve()

    for filepath in all_files:
        fp = Path(filepath)
        abs_fp = fp.resolve() if not fp.is_absolute() else fp
        try:
            rel_path = abs_fp.relative_to(abs_root)
        except ValueError:
            continue
        parts = rel_path.parts
        if len(parts) < 2:
            continue
        top_dir = parts[0]
        if top_dir in _ARTIFACT_DIRS or top_dir.startswith("."):
            continue
        dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
        if len(parts) < 3:
            continue
        sub_dir = parts[1]
        if sub_dir in _ARTIFACT_DIRS or sub_dir.startswith("."):
            continue
        sub_counts.setdefault(top_dir, {})
        sub_counts[top_dir][sub_dir] = sub_counts[top_dir].get(sub_dir, 0) + 1

    structure: list[dict[str, Any]] = []
    for name, count in sorted(dir_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        structure.append(_build_dir_entry(name, count, sub_counts))
    return structure


def _build_dir_entry(
    name: str,
    count: int,
    sub_counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Build a single ``top_level_structure[i]`` dict for ``name``."""
    entry: dict[str, Any] = {
        "name": name,
        "type": "directory",
        "file_count": count,
    }
    if name in sub_counts:
        entry["subdirectories"] = [
            {"name": sname, "file_count": scount}
            for sname, scount in sorted(
                sub_counts[name].items(), key=lambda kv: (-kv[1], kv[0])
            )
        ]
    return entry


def extract_readme_excerpt(root_path: Path) -> str:
    """Extract the first meaningful paragraph from README.md (max 200 chars)."""
    for candidate in ("README.md", "README.rst", "README.txt", "README"):
        readme = root_path / candidate
        if not readme.is_file():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = _excerpt_from_blockquotes(text)
        if excerpt:
            return excerpt
        excerpt = _excerpt_from_paragraphs(text)
        if excerpt:
            return excerpt
    return ""


def read_module_docstring(init_path: Path) -> str:
    """Extract the module-level docstring from a Python __init__.py file."""
    if not init_path.is_file():
        return ""
    try:
        source = init_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    pattern = re.compile(
        r'^(?:#[^\n]*\n)*\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')',
        re.DOTALL,
    )
    m = pattern.match(source)
    if not m:
        return ""
    raw = m.group(1) if m.group(1) is not None else m.group(2)
    for line in raw.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:80]
    return ""


def describe_dir(dir_path: Path, dir_name: str) -> str:
    """Return a short description for a directory.

    Priority:
    1. __init__.py module docstring (Python convention)
    2. README.md first meaningful line (Java / JS / any project)
    3. _DIR_CONVENTIONS lookup (well-known directory names)
    4. Empty string
    """
    doc = read_module_docstring(dir_path / "__init__.py")
    if doc:
        return doc[:80]
    readme_excerpt = _read_directory_readme_title(dir_path / "README.md")
    if readme_excerpt:
        return readme_excerpt
    return _DIR_CONVENTIONS.get(dir_name.lower(), "")


def scan_subdir_descriptions(
    top_name: str,
    top_path: Path,
    descriptions: dict[str, str],
) -> None:
    """Populate ``descriptions`` with ``top/sub`` → ``desc`` mappings.

    Mutates ``descriptions`` in place.
    """
    for sub in sorted(top_path.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in _ARTIFACT_DIRS or sub.name.startswith("."):
            continue
        sub_desc = describe_dir(sub, sub.name)
        if sub_desc:
            descriptions[f"{top_name}/{sub.name}"] = sub_desc


def extract_module_descriptions(root_path: Path, top_dirs: list[str]) -> dict[str, str]:
    """Return a mapping of relative directory path → short description."""
    descriptions: dict[str, str] = {}
    for top_name in top_dirs:
        top_path = root_path / top_name
        if not top_path.is_dir():
            continue
        desc = describe_dir(top_path, top_name)
        if desc:
            descriptions[top_name] = desc
        try:
            scan_subdir_descriptions(top_name, top_path, descriptions)
        except OSError:
            pass
    return descriptions
