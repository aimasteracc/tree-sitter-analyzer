#!/usr/bin/env python3
"""
Class Inspect MCP Tool — full class contract inspection.

Reports for a single class:
- extends: direct base class names
- fields: class-level attributes and self.* instance attributes (with visibility)
- methods: direct class-body functions only (closures excluded), with visibility
           and override detection
- inherited_methods: methods from the nearest in-project ancestor (if resolvable)

Visibility convention (Python):
  __name (dunder)  → private
  _name            → protected
  name             → public
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ...ast_cache import ASTCache
from ...class_hierarchy import ClassHierarchy
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Regex patterns for Python field extraction from source text
# Class-level attribute: <identifier>: ... = ... OR <UPPER_IDENT> = ... at class body
_CLS_ATTR_RE = re.compile(
    r"^    ([A-Za-z_]\w*)(?:\s*:\s*[^=\n]+)?\s*=\s*",
    re.MULTILINE,
)
# Instance attribute in __init__: self.<name> = ...
_SELF_ATTR_RE = re.compile(
    r"^\s+self\.([A-Za-z_]\w*)\s*=\s*",
    re.MULTILINE,
)


def _compute_visibility(name: str) -> str:
    """Derive Python visibility from name convention.

    __name (two leading underscores, no trailing)  → private
    _name  (one leading underscore)                → protected
    otherwise                                      → public

    Note: dunder methods (__init__, __str__) are considered public by
    Python convention, even though they start with double underscores on
    both sides. We treat them as public here because they ARE part of the
    public interface.
    """
    if name.startswith("__") and name.endswith("__"):
        # dunder / special method — public by Python convention
        return "public"
    if name.startswith("__"):
        return "private"
    if name.startswith("_"):
        return "protected"
    return "public"


def _filter_closures(
    raw_methods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove closures — functions whose line range is fully contained within
    another method's line range in the same file.

    Algorithm: for each method m, if there exists another method `outer`
    (same file) where outer.line <= m.line and outer.end_line >= m.end_line
    and outer != m, then m is a closure/nested function and is excluded.
    """
    result: list[dict[str, Any]] = []
    for i, m in enumerate(raw_methods):
        m_file = m["file"]
        m_start = m["line"]
        m_end = m["end_line"]
        is_closure = False
        for j, outer in enumerate(raw_methods):
            if i == j:
                continue
            if outer["file"] != m_file:
                continue
            # m is fully inside outer
            if outer["line"] <= m_start and outer["end_line"] >= m_end:
                is_closure = True
                break
        if not is_closure:
            result.append(m)
    return result


def _extract_fields_from_source(
    source: str,
    class_name: str,
    class_start: int,
    class_end: int,
) -> list[dict[str, Any]]:
    """Extract class-level and instance attributes from source text.

    Scans the class body (lines class_start..class_end) for:
    1. Class-level assignments at 4-space indent: ``name = ...``
    2. Self-assignments anywhere in the class body: ``self.name = ...``
       (not just __init__ — e.g. BaseMCPTool delegates its attribute
       writes to ``_apply_project_root``, the very repro of issue #455)

    Returns a list of field dicts: {name, line, visibility, kind}
    where kind is "class" or "instance".
    """
    lines = source.splitlines()
    class_lines = lines[class_start - 1 : class_end]

    fields: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. Class-level attributes: lines at indent == 4, assignment, not starting with def/class/@
    for rel_i, line in enumerate(class_lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent != 4:
            continue
        if (
            stripped.startswith("def ")
            or stripped.startswith("class ")
            or stripped.startswith("@")
        ):
            continue
        if stripped.startswith("#"):
            continue
        # Match: name = ... / name: type = ... / annotation-only name: type
        # (dataclass / Pydantic required fields have no default value)
        m = re.match(
            r"([A-Za-z_]\w*)(?:\s*:\s*[^=\n]+?)?\s*=\s*[^=]", stripped
        ) or re.match(r"([A-Za-z_]\w*)\s*:\s*[^=\n]+$", stripped)
        if m and not m.group(1).startswith("__"):
            # Skip dunder class attributes (likely __slots__, __doc__ etc)
            attr_name = m.group(1)
            if attr_name not in seen:
                seen.add(attr_name)
                abs_line = class_start + rel_i
                fields.append(
                    {
                        "name": attr_name,
                        "line": abs_line,
                        "visibility": _compute_visibility(attr_name),
                        "kind": "class",
                    }
                )

    # 2. Instance attributes: self.x = ... anywhere in the class body
    # (annotated assignments ``self.x: T = ...`` included)
    for rel_i, line in enumerate(class_lines):
        m = re.match(r"\s+self\.([A-Za-z_]\w*)(?:\s*:\s*[^=\n]+)?\s*=\s*", line)
        if m:
            attr_name = m.group(1)
            if attr_name not in seen:
                seen.add(attr_name)
                abs_line = class_start + rel_i
                fields.append(
                    {
                        "name": attr_name,
                        "line": abs_line,
                        "visibility": _compute_visibility(attr_name),
                        "kind": "instance",
                    }
                )

    fields.sort(key=lambda f: f["line"])
    return fields


# Decorator patterns that mark a method as abstract in Python.
_ABSTRACTMETHOD_PATTERN = re.compile(r"^\s*@(?:abc\.)?abstractmethod\s*$")


def _is_method_abstract(source_lines: list[str], def_line_1indexed: int) -> bool:
    """Return True if the line immediately before *def_line_1indexed* is ``@abstractmethod``.

    *def_line_1indexed* is the 1-based line number of the ``def`` keyword.
    Looks at the preceding line (and up to 3 lines back to handle stacked
    decorators like ``@property`` + ``@abstractmethod``).

    Falls back to False when the line is out of range or no match is found.
    """
    # Convert to 0-based index
    def_idx = def_line_1indexed - 1
    # Scan up to 4 preceding lines (covers stacked decorators)
    for offset in range(1, 5):
        check_idx = def_idx - offset
        if check_idx < 0:
            break
        line = source_lines[check_idx]
        stripped = line.strip()
        if not stripped or stripped == "":
            continue
        if _ABSTRACTMETHOD_PATTERN.match(line):
            return True
        # If we hit a non-decorator, non-blank line, stop scanning upward
        if not stripped.startswith("@"):
            break
    return False


def _read_source_lines(file_path: str, project_root: str) -> list[str]:
    """Read and return source lines for *file_path*, resolved against *project_root*.

    Returns [] on any IO error so callers can safely fall back.
    """
    abs_path = (
        file_path if os.path.isabs(file_path) else os.path.join(project_root, file_path)
    )
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except OSError:
        return []


class ClassInspectTool(BaseMCPTool):
    """Inspect a single class: fields, methods (no closures), visibility, extends."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_class_inspect",
            "description": (
                "Detailed class inspection: fields (class-level + instance), "
                "methods (direct only — closures excluded), visibility for each, "
                "base classes (extends), and inherited methods from the nearest "
                "in-project ancestor when resolvable. "
                "Requires ast_cache index to be built first."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "Name of the class to inspect",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "required": ["class_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("class_name"):
            raise ValueError("class_name is required")
        return True

    def _get_cache(self) -> ASTCache:
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        return ASTCache(self.project_root)

    def _collect_class_info(
        self, cache: ASTCache, class_name: str
    ) -> dict[str, Any] | None:
        """Return the raw class symbol dict for class_name (first match)."""
        try:
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT file_path, symbols_json FROM ast_index"
            ).fetchall()
        except Exception:
            return None

        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") == "class" and sym.get("name") == class_name:
                    return {
                        "file": row["file_path"],
                        "line": sym.get("line", 0),
                        "end_line": sym.get("end_line", 0),
                        "parents": sym.get("parents", []),
                    }
        return None

    def _collect_raw_methods(
        self,
        cache: ASTCache,
        class_name: str,
        file_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return method/function symbols whose enclosing class is class_name.

        When *file_path* is given only symbols from that file are returned,
        preventing same-named classes in different files from being merged
        (issue #660).

        This includes closures — caller is responsible for filtering via
        :func:`_filter_closures`.
        """
        try:
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT file_path, symbols_json FROM ast_index"
            ).fetchall()
        except Exception:
            return []

        methods: list[dict[str, Any]] = []
        for row in rows:
            # When a file_path scope is requested, skip other files.
            if file_path is not None and row["file_path"] != file_path:
                continue
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                if sym.get("class") != class_name:
                    continue
                methods.append(
                    {
                        "name": sym.get("name", ""),
                        "line": sym.get("line", 0),
                        "end_line": sym.get("end_line", 0),
                        "file": row["file_path"],
                    }
                )
        methods.sort(key=lambda m: (m["file"], m["line"]))
        return methods

    def _parent_method_names(
        self, hierarchy: ClassHierarchy, class_name: str, cache: ASTCache
    ) -> set[str]:
        """Collect method names defined in any ancestor of class_name."""
        ancestors = hierarchy.superclasses_of(class_name)
        ancestor_names = {a["name"] for a in ancestors}
        if not ancestor_names:
            return set()

        try:
            conn = cache.get_conn()
            rows = conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        except Exception:
            return set()

        parent_methods: set[str] = set()
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                if sym.get("class") in ancestor_names:
                    parent_methods.add(sym["name"])
        return parent_methods

    def _find_override_source(
        self,
        hierarchy: ClassHierarchy,
        class_name: str,
        method_name: str,
        cache: ASTCache,
    ) -> str | None:
        """Return the name of the ancestor class that first defines method_name."""
        ancestors = hierarchy.superclasses_of(class_name)
        # superclasses_of returns nearest first (BFS)
        ancestor_names = [a["name"] for a in ancestors]
        if not ancestor_names:
            return None

        try:
            conn = cache.get_conn()
            rows = conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        except Exception:
            return None

        ancestor_methods: dict[str, set[str]] = {}
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                cls = sym.get("class")
                if cls in ancestor_names:
                    ancestor_methods.setdefault(cls, set()).add(sym["name"])

        for ancestor in ancestor_names:
            if method_name in ancestor_methods.get(ancestor, set()):
                return str(ancestor)
        return None

    def _collect_fields(
        self,
        cache: ASTCache,
        class_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract class-level and instance fields by scanning source.

        Falls back to [] when the file cannot be read.
        """
        file_path: str = class_info["file"]
        class_start: int = class_info["line"]
        class_end: int = class_info["end_line"]

        # Resolve to absolute path
        project_root = self.project_root or ""
        abs_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_root, file_path)
        )

        try:
            source = open(abs_path, encoding="utf-8", errors="replace").read()
        except OSError:
            return []

        return _extract_fields_from_source(
            source, class_info.get("name", ""), class_start, class_end
        )

    def _collect_inherited_methods(
        self,
        hierarchy: ClassHierarchy,
        class_name: str,
        cache: ASTCache,
    ) -> dict[str, Any]:
        """Collect inherited methods from the nearest in-project ancestor.

        Returns:
          {"available": True, "methods": [...]}  when the parent is indexed
          {"available": False, "reason": "..."}  when it cannot be resolved
        """
        ancestors = hierarchy.superclasses_of(class_name)
        if not ancestors:
            return {"available": False, "reason": "no ancestors found in index"}

        # nearest ancestor = first in BFS order
        nearest = ancestors[0]
        ancestor_name = nearest["name"]

        try:
            conn = cache.get_conn()
            rows = conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        except Exception:
            return {"available": False, "reason": "cache query failed"}

        inherited: list[dict[str, Any]] = []
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                if sym.get("class") == ancestor_name:
                    inherited.append(
                        {
                            "name": sym.get("name", ""),
                            "defined_in": ancestor_name,
                        }
                    )

        if not inherited:
            return {
                "available": False,
                "reason": (
                    f"ancestor '{ancestor_name}' found in hierarchy but has no "
                    "indexed methods (external library or unindexed file)"
                ),
            }

        return {"available": True, "methods": inherited}

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        class_name: str = arguments["class_name"]
        output_format: str = arguments.get("output_format", "toon")

        cache = self._get_cache()
        hierarchy = ClassHierarchy(cache)
        hierarchy.build()

        # Check the class is known
        if class_name not in hierarchy._classes:  # noqa: SLF001
            not_found: dict[str, Any] = {
                "success": True,
                "verdict": "NOT_FOUND",
                "class_name": class_name,
                "message": f"Class '{class_name}' not found in AST index.",
                "methods": [],
                "method_count": 0,
                "fields": [],
                "extends": [],
            }
            from ..utils.format_helper import apply_toon_format_to_response

            return apply_toon_format_to_response(not_found, output_format)

        # Collect class metadata (parents, file, line range)
        class_info = self._collect_class_info(cache, class_name)
        extends: list[str] = class_info["parents"] if class_info else []

        # Scope method collection to the same file as the class definition
        # to prevent same-named classes across files from being merged (#660).
        class_file: str | None = class_info["file"] if class_info else None

        # Collect all raw method symbols, then filter closures
        raw_methods = self._collect_raw_methods(cache, class_name, file_path=class_file)
        direct_methods = _filter_closures(raw_methods)

        # Read source once for is_abstract detection (falls back to [] on IO error)
        project_root = self.project_root or ""
        source_lines: list[str] = (
            _read_source_lines(class_file, project_root) if class_file else []
        )

        # Override detection
        parent_method_names = self._parent_method_names(hierarchy, class_name, cache)

        methods: list[dict[str, Any]] = []
        for m in direct_methods:
            is_override = m["name"] in parent_method_names
            is_abstract = (
                _is_method_abstract(source_lines, m["line"]) if source_lines else False
            )
            entry: dict[str, Any] = {
                "name": m["name"],
                "line": m["line"],
                "end_line": m["end_line"],
                "file": m["file"],
                "visibility": _compute_visibility(m["name"]),
                "is_override": is_override,
                "is_abstract": is_abstract,
            }
            if is_override:
                src = self._find_override_source(
                    hierarchy, class_name, m["name"], cache
                )
                if src:
                    entry["overrides_from"] = src
            methods.append(entry)

        # Fields
        fields: list[dict[str, Any]] = []
        if class_info:
            class_info["name"] = class_name
            fields = self._collect_fields(cache, class_info)

        # Inherited members
        inherited_result = self._collect_inherited_methods(hierarchy, class_name, cache)

        response: dict[str, Any] = {
            "success": True,
            "verdict": "INFO",
            "class": class_name,
            "extends": extends,
            "method_count": len(methods),
            "methods": methods,
            "fields": fields,
        }

        if inherited_result.get("available"):
            response["inherited_methods"] = inherited_result["methods"]
        else:
            response["inherited"] = {
                "available": False,
                "reason": inherited_result.get("reason", "unknown"),
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)
