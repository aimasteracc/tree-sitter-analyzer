"""Live-filesystem dependency view for safe-to-edit (non-certified route)."""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path

from .safe_to_edit_paths import (
    _TYPESCRIPT_SOURCE_SUBSTITUTIONS,
    FileDependencyView,
    _module_path_without_suffix,
    _normalize_relative_path,
    to_relative,
)

_DEPENDENCY_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
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
)
_DEPENDENCY_SOURCE_EXTS = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".mts",
        ".cts",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".hxx",
    }
)
_JSTS_SUFFIXES = frozenset(
    {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
)
_TYPESCRIPT_IMPORTER_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts"})
_LIVE_SOURCE_SUFFIXES = (
    ".py",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".java",
)
_LIVE_PACKAGE_ENTRIES = (
    "__init__.py",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
    "index.ts",
    "index.tsx",
    "index.mts",
    "index.cts",
)


def build_file_dependency_view(
    resolved_path: str, project_root: str
) -> FileDependencyView:
    """Build a fast graph-like dependency view for one file.

    ``safe_to_edit`` is latency-sensitive. A whole-project tree-sitter
    dependency graph is useful, but cold-building it for every MCP process
    makes the common pre-edit check too slow. This view keeps the same lookup
    contract while limiting work to the target file plus an incremental
    dependents derivation (RFC-0025 L1, :mod:`dependents_index`).
    """
    from .dependents_index import resolve_dependents

    root = Path(project_root).resolve()
    target = Path(resolved_path).resolve()
    rel_path = _normalize_relative_path(to_relative(str(target), str(root)))
    dependencies = _target_dependencies(target, rel_path, root)
    answer = resolve_dependents(rel_path, root)
    return FileDependencyView(
        rel_path=rel_path,
        dependencies=dependencies,
        dependents=set(answer.dependents),
        dependents_answer=answer,
    )


def _target_dependencies(target: Path, rel_path: str, root: Path) -> set[str]:
    try:
        source = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    dependencies: set[str] = set()
    for spec in _extract_import_specs(source, target.suffix.lower()):
        resolved = _resolve_import_spec(spec, rel_path, root)
        if resolved:
            dependencies.add(resolved)
    return dependencies


def _target_dependents(target: Path, rel_path: str, root: Path) -> set[str]:
    """Return who imports *rel_path*, derived from the persisted AST index.

    RFC-0025 Layer 1. Delegates to :mod:`dependents_index`, which reads
    ``ast_index.imports_json`` and re-reads only the files the index cannot
    vouch for. Falls back to :func:`_target_dependents_by_scan` — the previous
    whole-tree read — when no usable index is present. The import is deferred
    because ``dependents_index`` reuses this module's resolvers.
    """
    from .dependents_index import resolve_dependents

    return set(resolve_dependents(rel_path, root).dependents)


def _target_dependents_by_scan(target: Path, rel_path: str, root: Path) -> set[str]:
    """Return dependents by reading every source file in the tree.

    Kept as the fail-closed fallback for when the index cannot establish the
    set: this is a superset of the derived answer (measured on this repository:
    821 reported, 39 genuine), and returning a superset is the safe direction
    for a pre-edit gate. It is not the primary path because it costs ~1 s per
    call and 95% of what it reports is a prose match, not an import.
    """
    needles = _import_needles_for_target(rel_path)
    if not needles:
        return set()

    dependents: set[str] = set()
    for path in _iter_dependency_source_files(root):
        if path == target:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            dependents.add(_normalize_relative_path(to_relative(str(path), str(root))))
    return dependents


def _iter_dependency_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _DEPENDENCY_SKIP_DIRS and not name.startswith(".")
        ]
        files.extend(
            Path(dirpath) / filename
            for filename in filenames
            if not filename.startswith(".")
            and Path(filename).suffix.lower() in _DEPENDENCY_SOURCE_EXTS
        )
    return files


def _extract_import_specs(source: str, suffix: str) -> set[str]:
    if suffix == ".py":
        return _python_import_specs(source)
    if suffix in _JSTS_SUFFIXES:
        return _jsts_import_specs(source)
    if suffix == ".java":
        return set(re.findall(r"^\s*import\s+([\w.]+);", source, re.M))
    return set()


def _python_import_specs(source: str) -> set[str]:
    specs = set(re.findall(r"^\s*import\s+([A-Za-z_][\w.]*)", source, re.M))
    specs.update(re.findall(r"^\s*from\s+([.\w]+)\s+import\b", source, re.M))
    return specs


def _jsts_import_specs(source: str) -> set[str]:
    specs = set(re.findall(r"\bfrom\s+['\"]([^'\"]+)['\"]", source))
    specs.update(re.findall(r"\bimport\s*['\"]([^'\"]+)['\"]", source))
    specs.update(re.findall(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)", source))
    # The closing quote MUST be followed by the call's ``)`` or the ``,``
    # that introduces the import-options object (``import(spec, {with:…})``).
    # Without that anchor, ``import("./dev.js" + suffix)`` recorded the
    # literal prefix ``./dev.js`` as if it were the whole runtime
    # specifier — inventing an edge to a module that is never loaded while
    # omitting the one that actually is. A computed specifier is unknowable
    # statically, so it must contribute no spec at all.
    specs.update(
        match.group(2)
        for match in re.finditer(r"\bimport\s*\(\s*(['\"])([^'\"]+)\1\s*[,)]", source)
    )
    specs.update(re.findall(r"\bimport\s*\(\s*`([^`$]+)`\s*[,)]", source))
    return specs


def _resolve_import_spec(spec: str, rel_path: str, root: Path) -> str | None:
    importer_suffix = Path(rel_path).suffix.lower()
    if importer_suffix in _JSTS_SUFFIXES:
        spec = re.split(r"[?#]", spec, maxsplit=1)[0]
    if not spec or "\\" in spec:
        return None
    candidate_base = _live_candidate_base(spec, rel_path)
    if candidate_base is None:
        return None
    if posixpath.isabs(candidate_base) or Path(candidate_base).is_absolute():
        return None
    for candidate in _live_candidates(candidate_base, importer_suffix):
        if (root / candidate).is_file():
            return candidate
    return None


def _live_candidate_base(spec: str, rel_path: str) -> str | None:
    """Map one import spec to a repository-relative base path (or reject it)."""
    if spec.startswith(("./", "../")):
        base = Path(rel_path).parent
        candidate_base = posixpath.normpath(f"{base.as_posix()}/{spec}")
        if candidate_base == ".." or candidate_base.startswith("../"):
            return None
        return candidate_base
    if spec.startswith(".."):
        return None
    if spec.startswith("."):
        base = Path(rel_path).parent
        return (base / spec.lstrip("./")).as_posix()
    return spec.replace(".", "/")


def _live_candidates(candidate_base: str, importer_suffix: str) -> list[str]:
    """Return the ordered file candidates probed for one candidate base."""
    explicit_suffix = Path(candidate_base).suffix.lower()
    if (
        importer_suffix in _TYPESCRIPT_IMPORTER_SUFFIXES
        and explicit_suffix in _TYPESCRIPT_SOURCE_SUBSTITUTIONS
    ):
        source_base = candidate_base.removesuffix(explicit_suffix)
        return [
            f"{source_base}{suffix}"
            for suffix in _TYPESCRIPT_SOURCE_SUBSTITUTIONS[explicit_suffix]
        ]
    if explicit_suffix:
        return [candidate_base]
    candidates = [candidate_base]
    candidates.extend(f"{candidate_base}{suffix}" for suffix in _LIVE_SOURCE_SUFFIXES)
    candidates.extend(f"{candidate_base}/{entry}" for entry in _LIVE_PACKAGE_ENTRIES)
    return candidates


def _import_needles_for_target(rel_path: str) -> set[str]:
    path = Path(rel_path)
    suffix = path.suffix
    module_path = _module_path_without_suffix(path)
    without_suffix = module_path.as_posix()
    module = without_suffix.replace("/", ".")
    basename = module_path.name
    needles = {without_suffix, module}
    if suffix == ".py" and path.name == "__init__.py":
        package = path.parent.as_posix()
        needles.add(package)
        needles.add(package.replace("/", "."))
    if basename and basename != "__init__":
        needles.add(basename)
    return {needle for needle in needles if needle}
