"""Documentation-code synchronization checker.

Scans markdown files for file path references and validates they still exist,
surfacing documentation drift before it misleads users or agents.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from typing import Any

# File extensions that are worth validating as path references.
_VALIDATABLE_EXTS = frozenset(
    [".py", ".md", ".sh", ".yml", ".yaml", ".json", ".toml", ".txt", ".db"]
)

# Regex for inline code spans (single backtick, no embedded newlines).
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Regex for markdown link targets: [text](target)
_LINK_TARGET_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


@dataclass
class DocRef:
    """A file-path reference found in a documentation file."""

    path: str
    doc_file: str
    line: int


@dataclass
class StaleRef:
    """A DocRef that could not be resolved to an existing file."""

    ref: DocRef
    reason: str  # "file_missing"


def _has_validatable_ext(text: str) -> bool:
    _, ext = os.path.splitext(text)
    if ext.lower() not in _VALIDATABLE_EXTS:
        return False
    # For data/config extensions (.json, .db), require a path prefix — bare filenames
    # like `grammar.json` or `profile.json` are typically runtime outputs or external
    # package files, not project-relative paths worth validating.
    if ext.lower() in {".json", ".db"} and "/" not in text and "\\" not in text:
        return False
    return True


def _is_skippable(text: str) -> bool:
    """True for globs, URLs, anchors, bare directories, templates, or non-path spans."""
    if "*" in text or "?" in text:
        return True
    if text.startswith("http://") or text.startswith("https://"):
        return True
    if text.startswith("#"):
        return True
    if text.endswith("/"):
        return True
    if " " in text or "\n" in text:
        return True
    # OS-specific user paths (~/… or %APPDATA%\…) — valid on the user's machine,
    # not project-relative paths.
    if text.startswith("~/") or text.startswith("%") or text.startswith("~\\"):
        return True
    # Template placeholders with curly braces like `{language}_plugin.py`
    if "{" in text or "}" in text:
        return True
    # Template placeholders like `<lang>` or `<name>_tool.py`
    if "<" in text or ">" in text:
        return True
    return False


def extract_file_refs(content: str, doc_file: str) -> list[DocRef]:
    """Extract file-path references from markdown *content*.

    Recognises:
    - Inline code spans:  ``path/to/file.py``
    - Markdown link targets: ``[label](path/to/file.py)``

    Skips globs, URLs, anchors, bare directories, code-fenced blocks,
    and spans without a recognised file extension.
    """
    refs: list[DocRef] = []
    in_fence = False
    for lineno, line in enumerate(content.splitlines(), 1):
        # Track fenced code blocks (``` or ~~~) — skip their content.
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        candidates: list[str] = []

        for m in _BACKTICK_RE.finditer(line):
            candidates.append(m.group(1).strip())

        for m in _LINK_TARGET_RE.finditer(line):
            candidates.append(m.group(2).strip())

        for text in candidates:
            if _is_skippable(text):
                continue
            if not _has_validatable_ext(text):
                continue
            refs.append(DocRef(path=text, doc_file=doc_file, line=lineno))

    return refs


def _resolve_ref(path: str, doc_file: str, project_root: str) -> bool:
    """Return True if *path* can be resolved to an existing file.

    Resolution order:
    1. Relative to *project_root* (as-is).
    2. Relative to the directory containing *doc_file* (handles ``./`` and ``../``).
    3. Under ``tree_sitter_analyzer/`` prefix (short bare names like ``ast_cache.py``).
    """
    # 1. Direct from project root.
    if os.path.exists(os.path.join(project_root, path)):
        return True
    # 2. Relative to the doc file's directory.
    doc_dir = os.path.dirname(os.path.join(project_root, doc_file))
    rel_candidate = os.path.normpath(os.path.join(doc_dir, path))
    if os.path.exists(rel_candidate):
        return True
    # 3. Under tree_sitter_analyzer/ (for bare names like "ast_cache.py").
    tsa_candidate = os.path.join(project_root, "tree_sitter_analyzer", path)
    if os.path.exists(tsa_candidate):
        return True
    return False


def validate_file_refs(refs: list[DocRef], project_root: str) -> list[StaleRef]:
    """Check each *ref* against the filesystem; return those that are missing."""
    stale: list[StaleRef] = []
    for ref in refs:
        if not _resolve_ref(ref.path, ref.doc_file, project_root):
            stale.append(StaleRef(ref=ref, reason="file_missing"))
    return stale


def _collect_md_files(project_root: str, patterns: list[str]) -> list[str]:
    """Resolve glob *patterns* relative to *project_root*."""
    md_files: list[str] = []
    for pattern in patterns:
        full_pattern = os.path.join(project_root, pattern)
        md_files.extend(glob.glob(full_pattern, recursive=True))
    return sorted(set(md_files))


def run_doc_sync(
    project_root: str,
    doc_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Scan markdown docs under *project_root* for stale file-path references.

    Args:
        project_root:  Absolute path to the project root.
        doc_patterns:  Glob patterns relative to *project_root* (default:
                       ``["docs/**/*.md", "README.md", "CHANGELOG.md"]``).

    Returns:
        Dict with keys: success, stale_count, total_refs_checked, docs_scanned,
        stale_refs (list of dicts).
    """
    if doc_patterns is None:
        doc_patterns = ["docs/**/*.md", "README.md", "CHANGELOG.md"]

    md_files = _collect_md_files(project_root, doc_patterns)

    all_refs: list[DocRef] = []
    docs_scanned: list[str] = []

    for md_path in md_files:
        try:
            content = open(md_path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        rel_doc = os.path.relpath(md_path, project_root)
        docs_scanned.append(rel_doc)
        all_refs.extend(extract_file_refs(content, rel_doc))

    stale = validate_file_refs(all_refs, project_root)

    return {
        "success": True,
        "stale_count": len(stale),
        "total_refs_checked": len(all_refs),
        "docs_scanned": len(docs_scanned),
        "stale_refs": [
            {
                "path": s.ref.path,
                "doc_file": s.ref.doc_file,
                "line": s.ref.line,
                "reason": s.reason,
            }
            for s in stale
        ],
    }
