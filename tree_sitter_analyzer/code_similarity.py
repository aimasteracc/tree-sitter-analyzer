#!/usr/bin/env python3
"""
Code Similarity Detector — AST-structural clone detection.

Finds duplicate and near-duplicate code using tree-sitter AST fingerprints.

Two detection modes:
- **structural**: Groups functions by their AST node-type skeleton.
  Two functions with the same structural fingerprint have identical
  control flow and expression structure (only names/literals differ).
- **textual**: Uses normalized text hashing to find exact copy-paste clones
  after stripping whitespace, comments, and identifier names.

Returns groups of similar functions with similarity scores and file locations.
CodeGraph parity: equivalent to CodeGraph's code similarity / clone detection.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .core.parser import Parser
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
}

_FUNC_DEF_TYPES = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "function_item",
        "method_declaration",
        "constructor_declaration",
        "class_method",
        "member_function",
    }
)


@dataclass
class SimilarFunction:
    file: str
    name: str
    line: int
    end_line: int
    language: str
    body_snippet: str = ""

    def to_dict(self, include_snippet: bool = False) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "file": self.file,
            "name": self.name,
            "line": self.line,
            "end_line": self.end_line,
            "language": self.language,
        }
        if include_snippet:
            entry["snippet"] = self.body_snippet[:200]
        return entry


@dataclass
class SimilarityGroup:
    fingerprint: str
    method: str
    similarity: float
    functions: list[SimilarFunction] = field(default_factory=list)

    def to_dict(self, include_bodies: bool = False) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint[:16],
            "method": self.method,
            "similarity": round(self.similarity, 3),
            "function_count": len(self.functions),
            "functions": [
                f.to_dict(include_snippet=include_bodies) for f in self.functions
            ],
        }


@dataclass
class SimilarityResult:
    groups: list[SimilarityGroup] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_bodies: bool = False) -> dict[str, Any]:
        return {
            "group_count": len(self.groups),
            "groups": [g.to_dict(include_bodies=include_bodies) for g in self.groups],
            "stats": self.stats,
        }


def _ast_fingerprint(node: Any, source: str, max_depth: int = 15) -> str:
    """Compute a structural fingerprint from an AST node.

    The fingerprint captures the tree structure (node types + child counts)
    but ignores identifier names and literal values. Two functions with
    the same fingerprint have identical structure.
    """
    parts: list[str] = []

    def _walk(n: Any, depth: int) -> None:
        if depth > max_depth or not hasattr(n, "type"):
            return
        child_count = len(getattr(n, "children", []))
        parts.append(f"{n.type}:{child_count}")
        for child in getattr(n, "children", []):
            _walk(child, depth + 1)

    _walk(node, 0)
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _text_fingerprint(source_text: str) -> str:
    """Compute a normalized text fingerprint.

    Strips:
    - All whitespace (spaces, tabs, newlines)
    - All comments (Python #, JS/TS //, /* */)
    - Normalizes identifier-like sequences to '_'

    Two code blocks with the same text fingerprint are copy-paste clones
    with only identifier name differences.
    """
    text = source_text
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    text = re.sub(r"'''[\s\S]*?'''", "", text)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    text = re.sub(r"#[^\n]*", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[a-zA-Z_][a-zA-Z0-9_]*", "_", text)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _should_visit_dir(d: str) -> bool:
    """Return True if directory should be walked (not excluded, not hidden)."""
    return d not in _EXCLUDE_DIRS and not d.startswith(".")


def _read_file_content(path: str) -> str | None:
    """Read file content as text, returning None on OSError."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _source_hash(source: str) -> str:
    """Return the same content hash format used by the AST cache."""
    return hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()


def _split_path_filter(path_filter: str | None) -> tuple[str, ...]:
    """Return normalized glob patterns from a comma/semicolon separated filter."""
    if not path_filter:
        return ()
    raw_patterns = re.split(r"[;,]", path_filter)
    return tuple(
        pattern.strip().replace("\\", "/")
        for pattern in raw_patterns
        if pattern.strip()
    )


def _matches_path_filter(file_path: str, path_filter: str | None) -> bool:
    """Return True when file_path is allowed by the optional glob filter."""
    patterns = _split_path_filter(path_filter)
    if not patterns:
        return True

    normalized = file_path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if not any(ch in pattern for ch in "*?[]"):
            prefix = pattern.rstrip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
    return False


def _extract_function_bodies(
    project_root: str,
    *,
    min_lines: int = 5,
    max_files: int = 1000,
    path_filter: str | None = None,
) -> list[tuple[str, str, int, int, str, str]]:
    """Extract function bodies from source files.

    Returns list of (file_path, name, start_line, end_line, language, body_text).
    """
    parser = Parser()
    root = os.path.abspath(project_root)
    results: list[tuple[str, str, int, int, str, str]] = []
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if _should_visit_dir(d)]
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            ext = ext.lower()
            fake_name = "dummy" + ext
            lang = _language_from_ext(fake_name)
            if not lang:
                continue

            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root)
            if not _matches_path_filter(rel_path, path_filter):
                continue
            file_count += 1
            if file_count > max_files:
                return results

            source = _read_file_content(abs_path)
            if source is None:
                continue

            try:
                parse_result = parser.parse_code(source, lang)
            except Exception:
                continue
            if not parse_result or not parse_result.tree:
                continue

            _extract_from_tree(
                parse_result.tree.root_node,
                source,
                rel_path,
                lang,
                min_lines,
                results,
            )

    return results


def _extract_from_tree(
    node: Any,
    source: str,
    file_path: str,
    language: str,
    min_lines: int,
    results: list[tuple[str, str, int, int, str, str]],
) -> None:
    """Walk AST and extract function bodies."""
    if not hasattr(node, "type"):
        return

    if node.type in _FUNC_DEF_TYPES:
        name_node = node.child_by_field_name("name")
        name = (
            source[name_node.start_byte : name_node.end_byte]
            if name_node
            else "<anonymous>"
        )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        line_count = end_line - start_line + 1

        if line_count >= min_lines:
            body = source[node.start_byte : node.end_byte]
            results.append((file_path, name, start_line, end_line, language, body))

    for child in getattr(node, "children", []):
        _extract_from_tree(child, source, file_path, language, min_lines, results)


def _body_snippet(body: str, max_len: int = 200) -> str:
    first_line = body.split("\n")[0] if body else ""
    if len(first_line) > max_len:
        return first_line[:max_len] + "..."
    return first_line


def detect_structural_clones(
    project_root: str,
    *,
    min_lines: int = 5,
    min_group_size: int = 2,
    max_files: int = 1000,
    max_groups: int = 30,
    path_filter: str | None = None,
) -> list[SimilarityGroup]:
    """Find functions with identical AST structure.

    Groups functions by their structural fingerprint. Groups of size >= 2
    represent structural clones — functions with the same control flow
    but potentially different identifier names.
    """
    functions = _extract_function_bodies(
        project_root,
        min_lines=min_lines,
        max_files=max_files,
        path_filter=path_filter,
    )
    if not functions:
        return []

    parser = Parser()
    fingerprint_map: dict[str, list[SimilarFunction]] = defaultdict(list)

    for file_path, name, start_line, end_line, language, body in functions:
        try:
            result = parser.parse_code(body, language)
        except Exception:
            continue
        if not result or not result.tree:
            continue

        fp = _ast_fingerprint(result.tree.root_node, body)
        fingerprint_map[fp].append(
            SimilarFunction(
                file=file_path,
                name=name,
                line=start_line,
                end_line=end_line,
                language=language,
                body_snippet=_body_snippet(body),
            )
        )

    groups: list[SimilarityGroup] = []
    for fp, funcs in fingerprint_map.items():
        if len(funcs) < min_group_size:
            continue
        groups.append(
            SimilarityGroup(
                fingerprint=fp,
                method="structural",
                similarity=1.0,
                functions=funcs,
            )
        )

    groups.sort(key=lambda g: -len(g.functions))
    return groups[:max_groups]


def detect_textual_clones(
    project_root: str,
    *,
    min_lines: int = 5,
    min_group_size: int = 2,
    max_files: int = 1000,
    max_groups: int = 30,
    path_filter: str | None = None,
) -> list[SimilarityGroup]:
    """Find functions with nearly identical normalized text.

    Groups functions by their normalized text fingerprint. Catches
    copy-paste duplicates where only identifier names differ.
    """
    functions = _extract_function_bodies(
        project_root,
        min_lines=min_lines,
        max_files=max_files,
        path_filter=path_filter,
    )
    if not functions:
        return []

    fingerprint_map: dict[str, list[SimilarFunction]] = defaultdict(list)

    for file_path, name, start_line, end_line, language, body in functions:
        fp = _text_fingerprint(body)
        fingerprint_map[fp].append(
            SimilarFunction(
                file=file_path,
                name=name,
                line=start_line,
                end_line=end_line,
                language=language,
                body_snippet=_body_snippet(body),
            )
        )

    groups: list[SimilarityGroup] = []
    for fp, funcs in fingerprint_map.items():
        if len(funcs) < min_group_size:
            continue
        groups.append(
            SimilarityGroup(
                fingerprint=fp,
                method="textual",
                similarity=1.0,
                functions=funcs,
            )
        )

    groups.sort(key=lambda g: -len(g.functions))
    return groups[:max_groups]


def _extract_cached_functions(
    cache: Any,
    project_root: str,
    min_lines: int = 5,
    path_filter: str | None = None,
) -> list[tuple[str, str, int, int, str, str]]:
    """Extract function bodies using pre-indexed AST cache.

    Reads function metadata (name, line range) from SQLite, then reads
    source files directly to extract bodies. Avoids re-parsing entirely
    when the cache is populated — CodeGraph parity for instant clone detection.

    Returns list of (file_path, name, start_line, end_line, language, body_text).
    """

    functions = cache.get_functions()
    if not functions:
        return []

    conn = cache.get_conn()
    rows_by_file: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT file_path, content_hash, language FROM ast_index"
    ).fetchall():
        rows_by_file[row["file_path"]] = {
            "content_hash": row["content_hash"],
            "language": row["language"],
        }

    results: list[tuple[str, str, int, int, str, str]] = []
    root = os.path.abspath(project_root)
    file_sources: dict[str, str] = {}

    for func in functions:
        file_rel = func["file"]
        if not _matches_path_filter(file_rel, path_filter):
            continue
        start_line = func.get("line", 0)
        end_line = func.get("end_line", 0)
        if end_line == 0:
            end_line = start_line
        line_count = end_line - start_line + 1
        if line_count < min_lines:
            continue

        if file_rel not in file_sources:
            abs_path = os.path.join(root, file_rel)
            content = _read_file_content(abs_path)
            if content is None:
                continue
            file_meta = rows_by_file.get(file_rel) or {}
            indexed_hash = file_meta.get("content_hash")
            if indexed_hash and indexed_hash != _source_hash(content):
                return []
            file_sources[file_rel] = content

        source = file_sources.get(file_rel)
        if source is None:
            continue

        source_lines = source.splitlines(keepends=True)
        start_idx = max(0, start_line - 1)
        end_idx = min(len(source_lines), end_line)
        body = "".join(source_lines[start_idx:end_idx])

        file_meta = rows_by_file.get(file_rel) or {}
        fallback_lang = file_meta.get("language", "")
        language = func.get("language", fallback_lang)
        results.append((file_rel, func["name"], start_line, end_line, language, body))

    return results


def detect_structural_clones_cached(
    cache: Any,
    project_root: str,
    *,
    min_lines: int = 5,
    min_group_size: int = 2,
    max_groups: int = 30,
    path_filter: str | None = None,
) -> list[SimilarityGroup]:
    """Find structural clones using pre-indexed AST cache (no re-parsing).

    Reads function metadata from the SQLite cache, extracts source bodies
    directly, then computes structural fingerprints. Falls back to
    detect_structural_clones() when the cache is empty.

    CodeGraph parity: instant clone detection from pre-indexed data.
    """
    functions = _extract_cached_functions(
        cache, project_root, min_lines, path_filter=path_filter
    )
    if not functions:
        return detect_structural_clones(
            project_root,
            min_lines=min_lines,
            min_group_size=min_group_size,
            max_groups=max_groups,
            path_filter=path_filter,
        )

    parser = Parser()
    fingerprint_map: dict[str, list[SimilarFunction]] = defaultdict(list)

    for file_path, name, start_line, end_line, language, body in functions:
        try:
            result = parser.parse_code(body, language)
        except Exception:
            continue
        if not result or not result.tree:
            continue

        fp = _ast_fingerprint(result.tree.root_node, body)
        fingerprint_map[fp].append(
            SimilarFunction(
                file=file_path,
                name=name,
                line=start_line,
                end_line=end_line,
                language=language,
                body_snippet=_body_snippet(body),
            )
        )

    groups: list[SimilarityGroup] = []
    for fp, funcs in fingerprint_map.items():
        if len(funcs) < min_group_size:
            continue
        groups.append(
            SimilarityGroup(
                fingerprint=fp,
                method="structural_cached",
                similarity=1.0,
                functions=funcs,
            )
        )

    groups.sort(key=lambda g: -len(g.functions))
    return groups[:max_groups]


def detect_textual_clones_cached(
    cache: Any,
    project_root: str,
    *,
    min_lines: int = 5,
    min_group_size: int = 2,
    max_groups: int = 30,
    path_filter: str | None = None,
) -> list[SimilarityGroup]:
    """Find textual clones using pre-indexed AST cache (no parsing at all).

    Reads function metadata from the SQLite cache, extracts source bodies
    directly, then computes normalized text fingerprints. Zero parsing —
    instant lookup. Falls back to detect_textual_clones() when cache is empty.

    CodeGraph parity: instant clone detection from pre-indexed data.
    """
    functions = _extract_cached_functions(
        cache, project_root, min_lines, path_filter=path_filter
    )
    if not functions:
        return detect_textual_clones(
            project_root,
            min_lines=min_lines,
            min_group_size=min_group_size,
            max_groups=max_groups,
            path_filter=path_filter,
        )

    fingerprint_map: dict[str, list[SimilarFunction]] = defaultdict(list)

    for file_path, name, start_line, end_line, language, body in functions:
        fp = _text_fingerprint(body)
        fingerprint_map[fp].append(
            SimilarFunction(
                file=file_path,
                name=name,
                line=start_line,
                end_line=end_line,
                language=language,
                body_snippet=_body_snippet(body),
            )
        )

    groups: list[SimilarityGroup] = []
    for fp, funcs in fingerprint_map.items():
        if len(funcs) < min_group_size:
            continue
        groups.append(
            SimilarityGroup(
                fingerprint=fp,
                method="textual_cached",
                similarity=1.0,
                functions=funcs,
            )
        )

    groups.sort(key=lambda g: -len(g.functions))
    return groups[:max_groups]


def analyze_code_similarity(
    project_root: str,
    *,
    mode: str = "all",
    min_lines: int = 5,
    min_group_size: int = 2,
    max_files: int = 1000,
    max_groups: int = 30,
    use_cache: bool = True,
    path_filter: str | None = None,
) -> SimilarityResult:
    """Comprehensive code similarity analysis.

    When use_cache=True (default), uses the pre-indexed AST cache for instant
    detection — no re-parsing required (CodeGraph parity). Falls back to
    full project scan when the cache is empty.

    Args:
        project_root: Root directory of the project.
        mode: "all", "structural", or "textual".
        min_lines: Minimum function body length to consider.
        min_group_size: Minimum group size to report.
        max_files: Maximum source files to scan (fallback only).
        max_groups: Maximum similarity groups to return.
        use_cache: Use pre-indexed AST cache for instant detection.
        path_filter: Optional glob or comma-separated globs limiting files.

    Returns:
        SimilarityResult with grouped similar functions.
    """
    cache: Any = None
    if use_cache:
        try:
            from .ast_cache import ASTCache

            cache = ASTCache(project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) == 0:
                cache.close()
                cache = None
        except Exception:
            cache = None

    all_groups: list[SimilarityGroup] = []

    if mode in ("all", "structural"):
        if cache is not None:
            structural = detect_structural_clones_cached(
                cache,
                project_root,
                min_lines=min_lines,
                min_group_size=min_group_size,
                max_groups=max_groups,
                path_filter=path_filter,
            )
        else:
            structural = detect_structural_clones(
                project_root,
                min_lines=min_lines,
                min_group_size=min_group_size,
                max_files=max_files,
                max_groups=max_groups,
                path_filter=path_filter,
            )
        all_groups.extend(structural)

    if mode in ("all", "textual"):
        if cache is not None:
            textual = detect_textual_clones_cached(
                cache,
                project_root,
                min_lines=min_lines,
                min_group_size=min_group_size,
                max_groups=max_groups,
                path_filter=path_filter,
            )
        else:
            textual = detect_textual_clones(
                project_root,
                min_lines=min_lines,
                min_group_size=min_group_size,
                max_files=max_files,
                max_groups=max_groups,
                path_filter=path_filter,
            )
        seen_fps: set[str] = set()
        for g in textual:
            if g.fingerprint not in seen_fps:
                seen_fps.add(g.fingerprint)
                all_groups.append(g)

    if cache is not None:
        cache.close()

    total_clones = sum(len(g.functions) for g in all_groups)
    cached = cache is not None

    return SimilarityResult(
        groups=all_groups[:max_groups],
        stats={
            "total_groups": len(all_groups),
            "total_clone_instances": total_clones,
            "mode": mode,
            "min_lines": min_lines,
            "cache_used": cached,
            "path_filter": path_filter or "",
        },
    )
