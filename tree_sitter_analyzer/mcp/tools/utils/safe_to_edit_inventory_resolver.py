"""Resolve projected import text against one captured snapshot inventory."""

from __future__ import annotations

import re
from pathlib import Path

from .safe_to_edit_import_parsing import (
    _DEFAULT_PYTHON_LOADERS,
    _jsts_projected_alias_spec,
    _python_projected_call,
    _python_static_import_specs,
)
from .safe_to_edit_paths import _TYPESCRIPT_SOURCE_SUBSTITUTIONS, _target_language

_JSTS_LANGUAGES = frozenset({"javascript", "typescript"})
_JS_RESOLUTION_SUFFIXES = (
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
)
_TS_RESOLUTION_SUFFIXES = (
    ".ts",
    ".tsx",
    ".d.ts",
    ".js",
    ".jsx",
    ".mts",
    ".cts",
    ".mjs",
    ".cjs",
)
#: ``language -> (file suffixes, package entry files)`` probed in order.
_LANGUAGE_RESOLUTION: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "python": ((".py",), ("__init__.py",)),
    "javascript": (
        _JS_RESOLUTION_SUFFIXES,
        tuple(f"index{suffix}" for suffix in _JS_RESOLUTION_SUFFIXES),
    ),
    "typescript": (
        _TS_RESOLUTION_SUFFIXES,
        tuple(f"index{suffix}" for suffix in _TS_RESOLUTION_SUFFIXES),
    ),
    "java": ((".java",), ()),
    "c": ((".c", ".h"), ()),
    "cpp": ((".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"), ()),
}
_TS_EMITTED_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs"})


def _resolve_import_spec_from_inventory(
    spec: str,
    importer_rel_path: str,
    inventory: frozenset[str],
) -> str | None:
    """Resolve an import using one already captured snapshot inventory."""
    if not spec:
        return None

    language = _target_language(importer_rel_path)
    if language == "python" and spec in {"builtins", "__future__"}:
        return None
    if language in _JSTS_LANGUAGES:
        spec = re.split(r"[?#]", spec, maxsplit=1)[0]
        if not spec:
            return None

    candidate_base = _inventory_candidate_base(spec, importer_rel_path)
    if candidate_base is None:
        return None
    if language in _JSTS_LANGUAGES and not spec.startswith(("./", "../")):
        return None
    candidates = _inventory_candidates(candidate_base, language, importer_rel_path)
    if language in {"python", "java"} and not spec.startswith("."):
        decided, resolved = _unique_rooted_match(candidates, inventory)
        if decided:
            return resolved
    else:
        for candidate in candidates:
            if candidate in inventory:
                return candidate
    if language == "java" and not spec.startswith("."):
        return _java_owner_match(candidate_base, inventory)
    return None


def _inventory_candidate_base(spec: str, importer_rel_path: str) -> str | None:
    """Return the inventory-relative base path one spec names, or reject it.

    JavaScript/TypeScript module specifiers use POSIX path syntax.  Resolve
    them separately from Python's leading-dot package syntax so a valid
    ``../shared`` import cannot escape the repository root and ``./setup``
    maps to the importing file's directory.
    """
    if spec.startswith(("./", "../")):
        return _posix_relative_base(spec, importer_rel_path)
    if spec.startswith("."):
        return _python_relative_base(spec, importer_rel_path)
    return spec.replace(".", "/")


def _posix_relative_base(spec: str, importer_rel_path: str) -> str | None:
    parts: list[str] = []
    joined = f"{Path(importer_rel_path).parent.as_posix()}/{spec}"
    for part in joined.split("/"):
        if part in {"", "."}:
            continue
        if part != "..":
            parts.append(part)
            continue
        if not parts:
            return None
        parts.pop()
    return "/".join(parts)


def _python_relative_base(spec: str, importer_rel_path: str) -> str | None:
    dot_count = len(spec) - len(spec.lstrip("."))
    module_tail = spec[dot_count:]
    package_parts = tuple(
        part for part in Path(importer_rel_path).parent.parts if part != "."
    )
    parent_hops = dot_count - 1
    if not package_parts or parent_hops >= len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parent_hops]
    tail_parts = tuple(part for part in module_tail.split(".") if part)
    return "/".join((*base_parts, *tail_parts))


def _inventory_candidates(
    candidate_base: str, language: str, importer_rel_path: str
) -> list[str]:
    """Return the ordered inventory paths probed for one candidate base."""
    suffixes, package_entries = _LANGUAGE_RESOLUTION.get(
        language, ((Path(importer_rel_path).suffix.lower(),), ())
    )
    allowed_suffixes = {suffix for suffix in suffixes if suffix}
    explicit_suffix = Path(candidate_base).suffix.lower()
    if not candidate_base:
        return list(package_entries)
    if explicit_suffix in allowed_suffixes:
        if language == "typescript" and explicit_suffix in _TS_EMITTED_SUFFIXES:
            source_base = candidate_base.removesuffix(explicit_suffix)
            substitutions = _TYPESCRIPT_SOURCE_SUBSTITUTIONS[explicit_suffix]
            return [f"{source_base}{suffix}" for suffix in substitutions]
        return [candidate_base]
    if explicit_suffix:
        return []
    package_candidates = [f"{candidate_base}/{entry}" for entry in package_entries]
    file_candidates = [f"{candidate_base}{suffix}" for suffix in suffixes]
    if language == "python":
        return [*package_candidates, *file_candidates]
    return [*file_candidates, *package_candidates]


def _unique_rooted_match(
    candidates: list[str], inventory: frozenset[str]
) -> tuple[bool, str | None]:
    """Match candidates anywhere under one inferred source root.

    Returns ``(decided, resolved)``: ``decided`` is False only when no
    candidate matched at all, so the caller may try further fallbacks.
    """
    matches_by_candidate = [
        (
            candidate,
            {
                indexed
                for indexed in inventory
                if indexed == candidate or indexed.endswith(f"/{candidate}")
            },
        )
        for candidate in candidates
    ]
    source_roots = {
        Path(indexed).parts[: -len(Path(candidate).parts)]
        for candidate, matches in matches_by_candidate
        for indexed in matches
    }
    if len(source_roots) > 1:
        return True, None
    for _candidate, matches in matches_by_candidate:
        if len(matches) == 1:
            return True, next(iter(matches))
        if len(matches) > 1:
            return True, None
    return False, None


def _java_owner_match(candidate_base: str, inventory: frozenset[str]) -> str | None:
    """Resolve a member/nested-class import to its unique owning ``.java``."""
    parts = candidate_base.split("/")
    owner_matches: set[str] = set()
    for end in range(len(parts) - 1, 0, -1):
        owner_candidate = f"{'/'.join(parts[:end])}.java"
        if owner_candidate in inventory:
            owner_matches.add(owner_candidate)
        owner_matches.update(
            indexed for indexed in inventory if indexed.endswith(f"/{owner_candidate}")
        )
    if len(owner_matches) == 1:
        return next(iter(owner_matches))
    return None


def _python_import_root(spec: str, resolved: str) -> Path | None:
    """Return the inferred source root for one absolute Python import."""

    if spec.startswith("."):
        return None
    module_path = spec.replace(".", "/")
    for candidate in (f"{module_path}.py", f"{module_path}/__init__.py"):
        if resolved == candidate:
            return Path()
        suffix = f"/{candidate}"
        if resolved.endswith(suffix):
            root_parts = Path(resolved).parts[: -len(Path(candidate).parts)]
            return Path(*root_parts)
    return None


def _python_package_initializers(
    resolved: str,
    inventory: frozenset[str],
    *,
    source_root: Path | None,
) -> set[str]:
    """Return indexed package initializers executed while importing a module."""

    initializers: set[str] = set()
    parent = Path(resolved).parent
    while parent.parts and parent != source_root:
        candidate = (parent / "__init__.py").as_posix()
        if candidate in inventory:
            initializers.add(candidate)
        parent = parent.parent
    return initializers


def _import_targets_from_text(
    import_text: str,
    importer_rel_path: str,
    inventory: frozenset[str],
    *,
    python_dynamic_loaders: frozenset[str] | None = None,
) -> set[str]:
    """Resolve every inventory-covered file named by one import statement.

    Import projections preserve source text, not a normalized target list.
    Parse the small syntax surface needed by the supported Python and
    JavaScript/TypeScript forms and always resolve against the immutable
    snapshot inventory.  In particular, a member import is bound to its
    module (``from other import app`` -> ``other/app.py``), never to an
    unrelated repository-wide basename match.
    """

    importer_language = _target_language(importer_rel_path)
    import_text = _normalize_import_text(import_text, importer_language)
    specs, java_wildcard_packages = _statement_specs(import_text, importer_language)
    specs.update(_quoted_loader_specs(import_text))
    specs.update(
        _language_call_specs(import_text, importer_language, python_dynamic_loaders)
    )

    targets = _java_wildcard_targets(java_wildcard_packages, inventory)
    targets.update(
        _quoted_include_targets(
            import_text, importer_language, importer_rel_path, inventory
        )
    )
    for spec in specs:
        resolved = _resolve_import_spec_from_inventory(
            spec, importer_rel_path, inventory
        )
        if resolved is None:
            continue
        targets.add(resolved)
        if importer_language == "python":
            targets.update(
                _python_package_initializers(
                    resolved,
                    inventory,
                    source_root=_python_import_root(spec, resolved),
                )
            )
    return targets


def _normalize_import_text(import_text: str, importer_language: str) -> str:
    """Fold line continuations / ``module['require']`` into parseable text."""
    if importer_language == "python":
        return re.sub(r"\\\r?\n", "", import_text)
    if importer_language in _JSTS_LANGUAGES:
        return re.sub(
            r"\bmodule(?:\?\.)?\s*\[\s*(['\"`])require\1\s*\]",
            "module.require",
            import_text,
        )
    return import_text


def _statement_specs(
    import_text: str, importer_language: str
) -> tuple[set[str], set[str]]:
    """Return ``(specs, java_wildcard_packages)`` named by the statement form."""
    specs: set[str] = set()
    if importer_language in _JSTS_LANGUAGES:
        projected_alias_spec = _jsts_projected_alias_spec(import_text)
        if projected_alias_spec is not None:
            specs.add(projected_alias_spec)
    if importer_language == "python":
        static_specs = _python_static_import_specs(import_text)
        if static_specs is not None:
            specs.update(static_specs)
        return specs, set()
    direct_specs, java_wildcard_packages = _direct_import_specs(
        import_text, importer_language
    )
    specs.update(direct_specs)
    return specs, java_wildcard_packages


def _direct_import_specs(
    import_text: str, importer_language: str
) -> tuple[set[str], set[str]]:
    """Java direct imports; aliases and the trailing semicolon are ignored."""
    specs: set[str] = set()
    java_wildcard_packages: set[str] = set()
    direct_match = re.match(r"^\s*import\s+(.+)$", import_text, re.S)
    if not direct_match or direct_match.group(1).lstrip().startswith(("'", '"')):
        return specs, java_wildcard_packages
    for item in direct_match.group(1).split(","):
        raw_spec = item.strip().rstrip(";")
        if raw_spec.startswith("static "):
            static_target = raw_spec.removeprefix("static ").strip()
            spec, _, _member = static_target.rpartition(".")
        else:
            spec = raw_spec.split(maxsplit=1)[0]
            if importer_language == "java" and spec.endswith(".*"):
                java_wildcard_packages.add(spec.removesuffix(".*"))
                continue
        if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", spec):
            specs.add(spec)
    return specs, java_wildcard_packages


def _quoted_loader_specs(import_text: str) -> set[str]:
    """ESM/CommonJS/dynamic-import and Python loader literal specifiers.

    ESM side-effect/default/named imports and re-exports, plus CommonJS and
    dynamic import expressions.  All capture the quoted module specifier.
    """
    specs = set(
        re.findall(
            r"(?:\bfrom\s*|^\s*import\s*)['\"]([^'\"]+)['\"]",
            import_text,
            re.M,
        )
    )
    specs.update(
        match.group(1)
        for match in re.finditer(
            r"\b(?:require|import)(?:\?\.)?\s*\(\s*`([^`]*)`\s*(?=[,)])",
            import_text,
        )
        if "${" not in match.group(1)
    )
    specs.update(
        match.group(2)
        for match in re.finditer(
            r"\b(?:importlib\.import_module|builtins\.__import__|__import__)\s*"
            r"\(\s*(['\"])([^'\"]+)\1",
            import_text,
        )
    )
    specs.update(
        match.group(2)
        for match in re.finditer(
            r"\b(?:require|import)(?:\?\.)?\s*\(\s*(['\"])([^'\"]+)\1"
            r"\s*(?=[,)])",
            import_text,
        )
    )
    return specs


def _language_call_specs(
    import_text: str,
    importer_language: str,
    python_dynamic_loaders: frozenset[str] | None,
) -> set[str]:
    """Python loader aliases, Java ``Class.forName`` and TS path references."""
    if importer_language == "python":
        projected_call = _python_projected_call(import_text)
        loader_names = (
            _DEFAULT_PYTHON_LOADERS
            if python_dynamic_loaders is None
            else python_dynamic_loaders
        )
        if (
            projected_call is not None
            and projected_call[0] in loader_names
            and projected_call[1] is not None
        ):
            return {projected_call[1]}
        return set()
    if importer_language == "java":
        reflection = re.match(
            r"^\s*(?:(?:java\.lang\.)?Class\.)?forName\s*"
            r"\(\s*(['\"])([^'\"]+)\1",
            import_text,
            re.S,
        )
        if reflection is not None:
            return {reflection.group(2).split("$", 1)[0]}
        return set()
    if importer_language == "typescript":
        path_reference = re.match(
            r"^\s*///\s*<reference\b[^>]*\bpath\s*=\s*(['\"])([^'\"]+)\1",
            import_text,
        )
        if path_reference is not None:
            return {path_reference.group(2)}
    return set()


def _quoted_include_targets(
    import_text: str,
    importer_language: str,
    importer_rel_path: str,
    inventory: frozenset[str],
) -> set[str]:
    """Resolve ``#include "x"`` and C++ header units to a unique target."""
    include_match = re.match(r'^\s*#\s*include\s*"([^"]+)"', import_text)
    cpp_header_unit = (
        re.match(r'^\s*(?:export\s+)?import\s+"([^"]+)"\s*;', import_text)
        if importer_language == "cpp"
        else None
    )
    targets: set[str] = set()
    for match in (include_match, cpp_header_unit):
        if not match:
            continue
        matched = _quoted_include_matches(match.group(1), importer_rel_path, inventory)
        if len(matched) == 1:
            targets.update(matched)
    return targets


def _java_wildcard_targets(packages: set[str], inventory: frozenset[str]) -> set[str]:
    """Expand Java package wildcards over direct, inventory-covered classes."""

    package_paths = {package.replace(".", "/") for package in packages}
    return {
        indexed
        for indexed in inventory
        if indexed.endswith(".java")
        and any(
            Path(indexed).parent.as_posix() == package
            or Path(indexed).parent.as_posix().endswith(f"/{package}")
            for package in package_paths
        )
    }


def _quoted_include_matches(
    spec: str,
    importer_rel_path: str,
    inventory: frozenset[str],
) -> set[str]:
    """Return the ordered-search result set for a quoted C/C++ include."""

    relative = _resolve_import_spec_from_inventory(
        f"./{spec}", importer_rel_path, inventory
    )
    if relative is not None:
        return {relative}
    # The snapshot does not capture compiler -iquote/-I search order. A
    # repository-wide suffix match therefore cannot certify a quoted include.
    return set()
