#!/usr/bin/env python3
"""
Call Graph — Bidirectional function-level call tracking.

Builds a directed graph of function/method calls within a project using
Tree-sitter AST parsing. Supports Python, JavaScript, TypeScript, Java,
Go, and C/C++.

Key classes:
- CallGraph: Construct and query function-level call relationships
- FunctionRef: Qualified function reference (file, name, line, language)
"""

import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .core.parser import Parser, ParseResult
from .import_extractors import walk_imports
from .project_graph import _language_from_ext

_EXCLUDE_DIRS = {
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


class FunctionRef:
    """A qualified reference to a function/method in the project."""

    __slots__ = ("file_path", "name", "start_line", "end_line", "language", "receiver")

    def __init__(
        self,
        file_path: str,
        name: str,
        start_line: int,
        language: str,
        receiver: str | None = None,
        end_line: int | None = None,
    ) -> None:
        self.file_path = file_path
        self.name = name
        self.start_line = start_line
        self.end_line = end_line if end_line is not None else start_line
        self.language = language
        self.receiver = receiver

    def qualified_name(self) -> str:
        if self.receiver:
            return f"{self.file_path}:{self.receiver}.{self.name}"
        return f"{self.file_path}:{self.name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FunctionRef):
            return NotImplemented
        return (
            self.file_path == other.file_path
            and self.name == other.name
            and self.start_line == other.start_line
        )

    def __hash__(self) -> int:
        return hash((self.file_path, self.name, self.start_line))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.file_path,
            "name": self.name,
            "line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
        }
        if self.receiver:
            d["receiver"] = self.receiver
        return d


_CALL_NODE_TYPES = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "java": {"method_invocation", "class_body"},
    "go": {"call_expression"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
}

_FUNC_DEF_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
}

_CLASS_DEF_TYPES = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "java": {"class_declaration"},
    "go": set(),
    "c": set(),
    "cpp": {"class_specifier"},
}


def _walk_tree(node: Any, source: str, language: str) -> tuple[list[dict], list[dict]]:
    """
    Walk the AST to extract function definitions and call sites.

    Returns (definitions, calls) where each is a list of dicts.
    """
    definitions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    _extract_recursive(node, source, language, definitions, calls, None)
    return definitions, calls


def _extract_recursive(
    node: Any,
    source: str,
    language: str,
    definitions: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    enclosing_class: str | None,
) -> None:
    """Recursively walk AST extracting function defs and call sites."""
    if not hasattr(node, "type"):
        return

    node_type = node.type

    if node_type in _FUNC_DEF_TYPES.get(language, set()):
        func_name = _get_func_name(node, language)
        if func_name:
            parent_class = enclosing_class
            if language == "python":
                parent_class = _find_parent_class_python(node) or enclosing_class
            elif language in ("java",):
                parent_class = _find_parent_class_java(node) or enclosing_class
            elif language == "go" and node.type == "method_declaration":
                parent_class = _find_receiver_type_go(node) or enclosing_class

            definitions.append(
                {
                    "name": func_name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "class": parent_class,
                }
            )

            for child in node.children:
                _extract_recursive(
                    child, source, language, definitions, calls, parent_class
                )
            return

    if node_type in _CALL_NODE_TYPES.get(language, set()):
        call_info = _extract_call(node, source, language)
        if call_info:
            calls.append(call_info)

    for child in node.children:
        _extract_recursive(child, source, language, definitions, calls, enclosing_class)


def _get_func_name(node: Any, language: str) -> str | None:
    """Extract function name from a definition node."""
    try:
        if language == "python":
            for child in node.children:
                if child.type == "identifier":
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        elif language in ("javascript", "typescript"):
            for child in node.children:
                if child.type in ("identifier", "property_identifier"):
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        elif language == "java":
            for child in node.children:
                if child.type == "identifier":
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        elif language == "go":
            for child in node.children:
                if child.type in ("identifier", "field_identifier"):
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        elif language in ("c", "cpp"):
            for child in node.children:
                if child.type in (
                    "identifier",
                    "field_identifier",
                    "destructor_name",
                ):
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
                if child.type == "function_declarator":
                    for sub in child.children:
                        if sub.type in ("identifier", "field_identifier"):
                            text = sub.text
                            return (
                                text.decode("utf-8")
                                if isinstance(text, bytes)
                                else str(text)
                            )
    except Exception:  # nosec B110
        pass
    return None


def _extract_call(node: Any, source: str, language: str) -> dict[str, Any] | None:
    """Extract call target info from a call node."""
    try:
        if language == "python":
            func_node = node.child_by_field_name("function")
            if func_node is None:
                return None
            name = _node_text(func_node, source)
            receiver = None
            if "." in name:
                parts = name.rsplit(".", 1)
                receiver = parts[0]
                name = parts[1]
            return {
                "name": name,
                "full_name": _node_text(func_node, source),
                "line": node.start_point[0] + 1,
                "receiver": receiver,
            }
        elif language in ("javascript", "typescript"):
            func_node = node.child_by_field_name("function")
            if func_node is None:
                return None
            name = _node_text(func_node, source)
            receiver = None
            if "." in name:
                parts = name.rsplit(".", 1)
                receiver = parts[0]
                name = parts[1]
            return {
                "name": name,
                "full_name": _node_text(func_node, source),
                "line": node.start_point[0] + 1,
                "receiver": receiver,
            }
        elif language == "java":
            for child in node.children:
                if child.type == "identifier":
                    text = _node_text(child, source)
                    return {
                        "name": text,
                        "full_name": text,
                        "line": node.start_point[0] + 1,
                        "receiver": None,
                    }
                if child.type in ("field_access", "method_reference"):
                    text = _node_text(child, source)
                    receiver = None
                    name = text
                    if "." in text:
                        parts = text.rsplit(".", 1)
                        receiver = parts[0]
                        name = parts[1]
                    return {
                        "name": name,
                        "full_name": text,
                        "line": node.start_point[0] + 1,
                        "receiver": receiver,
                    }
            return None
        elif language == "go":
            func_node = node.child_by_field_name("function")
            if func_node is None:
                return None
            name = _node_text(func_node, source)
            receiver = None
            if "." in name:
                parts = name.rsplit(".", 1)
                receiver = parts[0]
                name = parts[1]
            return {
                "name": name,
                "full_name": _node_text(func_node, source),
                "line": node.start_point[0] + 1,
                "receiver": receiver,
            }
        elif language in ("c", "cpp"):
            func_node = node.child_by_field_name("function")
            if func_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        text = _node_text(child, source)
                        return {
                            "name": text,
                            "full_name": text,
                            "line": node.start_point[0] + 1,
                            "receiver": None,
                        }
                return None
            name = _node_text(func_node, source)
            return {
                "name": name,
                "full_name": name,
                "line": node.start_point[0] + 1,
                "receiver": None,
            }
    except Exception:  # nosec B110
        pass
    return None


def _node_text(node: Any, source: str) -> str:
    """Extract text from a node given the full source string.

    Tree-sitter exposes start_byte/end_byte as UTF-8 *byte* offsets.
    Slicing a Python str with byte indices produces correct results for
    pure-ASCII but silently shifts after any multi-byte character.  The
    same class of bug that was fixed in ast_cache._node_text.

    Fix: prefer node.text (bytes view from tree-sitter, canonical
    source-of-truth).  Fall back to byte-level slicing on the encoded
    source so legacy callers still work.
    """
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        try:
            return text_attr.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return ""
    if isinstance(text_attr, str):
        return text_attr
    try:
        return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except (IndexError, TypeError, UnicodeDecodeError):
        return ""


def _find_parent_class_python(node: Any) -> str | None:
    """Walk up from a function node to find enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            for child in current.children:
                if child.type == "identifier":
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        current = current.parent
    return None


def _find_parent_class_java(node: Any) -> str | None:
    """Walk up from a method node to find enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_declaration":
            for child in current.children:
                if child.type == "identifier":
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        current = current.parent
    return None


def _find_receiver_type_go(node: Any) -> str | None:
    """Extract receiver type from a Go method_declaration node.

    For ``func (e *Engine) ServeHTTP(...)`` returns ``Engine``.
    """
    if node is None or node.type != "method_declaration":
        return None
    for child in node.children:
        if child.type == "parameter_list":
            for param in child.children:
                for sub in param.children if hasattr(param, "children") else []:
                    if sub.type in ("type_identifier", "generic_type", "pointer_type"):
                        text = sub.text
                        raw = (
                            text.decode("utf-8")
                            if isinstance(text, bytes)
                            else str(text)
                        )
                        return raw.lstrip("*")
                    for leaf in sub.children if hasattr(sub, "children") else []:
                        if leaf.type in (
                            "type_identifier",
                            "generic_type",
                        ):
                            text = leaf.text
                            raw = (
                                text.decode("utf-8")
                                if isinstance(text, bytes)
                                else str(text)
                            )
                            return raw.lstrip("*")
    return None


class CallGraph:
    """
    Project-level function call graph.

    Nodes: FunctionRef objects representing function/method definitions.
    Edges: A -> B means function A calls function B.

    The call graph supports bidirectional queries:
    - callers_of(func_name): who calls this function?
    - callees_of(func_name): what does this function call?
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root).resolve()
        self._functions: list[FunctionRef] = []
        self._func_by_name: dict[str, list[FunctionRef]] = defaultdict(list)
        self._func_by_qualified: dict[str, FunctionRef] = {}
        self._func_by_file: dict[str, list[FunctionRef]] = defaultdict(list)
        self._callees: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._callers: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._call_edges: list[tuple[FunctionRef, FunctionRef, int]] = []
        self._built = False
        self._file_imports: dict[str, dict[str, str]] = {}
        self._file_module_map: dict[str, str] = {}
        self._imported_names: dict[str, dict[str, str]] = {}
        self._module_to_file: dict[str, str] = {}

    def build(self) -> None:
        """Scan the project and build the call graph."""
        if self._built:
            return

        supported_exts = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".go",
            ".c",
            ".cpp",
            ".cc",
            ".cxx",
        }

        all_files = self._iter_source_files(supported_exts)

        rel_to_abs: dict[str, str] = {}
        for f in all_files:
            try:
                rel = str(f.relative_to(self.project_root))
                rel_to_abs[rel] = str(f)
            except ValueError:
                continue

        parser = Parser()

        # Two-pass build so cross-file call resolution doesn't depend on
        # filesystem iteration order. Pass 1 indexes every file's defs into
        # ``self._func_by_name`` / ``_func_by_qualified``; Pass 2 then walks
        # the saved calls and resolves them against a now-complete index.
        # Previously the def-add and call-resolve ran in the same loop body,
        # so file A calling into file B would silently drop the edge when A
        # was iterated first — macOS APFS happens to iterate ``main.py``
        # last in test fixtures so it passed there, while Linux ext4 +
        # Windows hit the trap. Tracked across PR #133.
        per_file: list[
            tuple[str, str, str, dict[str, FunctionRef], list[dict[str, Any]]]
        ] = []

        for rel_path, abs_path in rel_to_abs.items():
            language = _language_from_ext(rel_path)
            if language is None:
                continue

            result: ParseResult = parser.parse_file(abs_path, language)
            if not result.success or result.tree is None:
                continue

            source = result.source_code
            tree = result.tree

            definitions, calls = _walk_tree(tree.root_node, source, language)

            imports: list[dict[str, Any]] = []
            walk_imports(tree.root_node, source, language, imports)
            self._collect_import_map(rel_path, imports, rel_to_abs)

            file_funcs: dict[str, FunctionRef] = {}
            for defn in definitions:
                ref = FunctionRef(
                    file_path=rel_path,
                    name=defn["name"],
                    start_line=defn["start_line"],
                    language=language,
                    receiver=defn.get("class"),
                    end_line=defn.get("end_line", defn["start_line"]),
                )
                self._functions.append(ref)
                self._func_by_name[defn["name"]].append(ref)
                self._func_by_file[rel_path].append(ref)
                qname = ref.qualified_name()
                self._func_by_qualified[qname] = ref
                file_funcs[defn["name"]] = ref

            per_file.append((rel_path, abs_path, language, file_funcs, calls))

        # Pass 2: resolve calls against the fully-populated index.
        for rel_path, _abs_path, _language, file_funcs, calls in per_file:
            for call in calls:
                caller_ref = self._find_enclosing_func(file_funcs, call["line"])
                if caller_ref is None:
                    continue

                callee_refs = self._resolve_callee(call, rel_path, rel_to_abs)

                for callee_ref in callee_refs:
                    self._callees[caller_ref].append(callee_ref)
                    self._callers[callee_ref].append(caller_ref)
                    self._call_edges.append((caller_ref, callee_ref, call["line"]))

        self._build_module_to_file_map(rel_to_abs)
        self._built = True

    def _is_excluded(self, path: Path) -> bool:
        try:
            rel_parts = path.relative_to(self.project_root).parts
        except ValueError:
            rel_parts = path.parts
        return any(part in _EXCLUDE_DIRS or part.startswith(".") for part in rel_parts)

    def _iter_source_files(self, supported_exts: set[str]) -> list[Path]:
        """Return source files while pruning generated and hidden work dirs."""
        files: list[Path] = []
        for root, dirs, names in os.walk(self.project_root):
            dirs[:] = [
                name
                for name in dirs
                if name not in _EXCLUDE_DIRS and not name.startswith(".")
            ]
            for name in names:
                if name.startswith("."):
                    continue
                if Path(name).suffix.lower() in supported_exts:
                    files.append(Path(root) / name)
        return files

    def _collect_import_map(
        self,
        rel_path: str,
        imports: list[dict[str, Any]],
        rel_to_abs: dict[str, str],
    ) -> None:
        name_to_source: dict[str, str] = {}
        for imp in imports:
            resolved = imp.get("resolved_path", "")
            names = imp.get("names", [])
            is_relative = imp.get("is_relative", False)
            target_file = self._resolve_import_path(
                rel_path, resolved, is_relative, rel_to_abs
            )
            if target_file:
                for name in names:
                    name_to_source[name] = target_file
        if name_to_source:
            self._imported_names[rel_path] = name_to_source

    def _resolve_import_path(
        self,
        source_rel: str,
        resolved_path: str,
        is_relative: bool,
        rel_to_abs: dict[str, str],
    ) -> str:
        if not resolved_path:
            return ""
        if is_relative:
            source_dir = str(Path(source_rel).parent)
            candidate = str(Path(source_dir) / resolved_path)
            for ext in ("", ".py", ".js", ".ts", ".jsx", ".tsx"):
                check = candidate + ext
                if check in rel_to_abs:
                    return check
                idx_path = str(Path(candidate) / "__init__.py")
                if idx_path in rel_to_abs:
                    return idx_path
        else:
            candidate = resolved_path
            for ext in ("", ".py", ".js", ".ts", ".jsx", ".tsx"):
                check = candidate + ext
                if check in rel_to_abs:
                    return check
                idx_path = str(Path(candidate) / "__init__.py")
                if idx_path in rel_to_abs:
                    return idx_path
        return ""

    def _build_module_to_file_map(self, rel_to_abs: dict[str, str]) -> None:
        for rel_path in rel_to_abs:
            p = Path(rel_path)
            stem = p.stem
            if stem == "__init__":
                module_name = str(p.parent).replace("/", ".").replace("\\", ".")
            else:
                module_name = (
                    str(p.with_suffix("")).replace("/", ".").replace("\\", ".")
                )
            self._module_to_file[module_name] = rel_path

    def _find_enclosing_func(
        self,
        file_funcs: dict[str, FunctionRef],
        call_line: int,
    ) -> FunctionRef | None:
        """Find the function that contains the given line number.

        Uses both start_line and end_line for accurate range containment.
        Falls back to closest start_line when end_line is unreliable.
        """
        best: FunctionRef | None = None
        for ref in file_funcs.values():
            if ref.start_line <= call_line <= ref.end_line:
                if best is None or (
                    (ref.end_line - ref.start_line) < (best.end_line - best.start_line)
                ):
                    best = ref
        if best is not None:
            return best
        for ref in file_funcs.values():
            if ref.start_line <= call_line:
                if best is None or ref.start_line > best.start_line:
                    best = ref
        return best

    def _resolve_callee(
        self,
        call: dict[str, Any],
        source_rel: str,
        rel_to_abs: dict[str, str],
    ) -> list[FunctionRef]:
        name = call["name"]
        results: list[FunctionRef] = []
        seen: set[str] = set()

        same_file = self._func_by_name.get(name, [])
        local = [c for c in same_file if c.file_path == source_rel]
        if local:
            for c in local:
                if c.qualified_name() not in seen:
                    seen.add(c.qualified_name())
                    results.append(c)
            return results

        imported_names = self._imported_names.get(source_rel, {})
        target_file = imported_names.get(name)
        if target_file:
            candidates = self._func_by_name.get(name, [])
            for c in candidates:
                if c.file_path == target_file and c.qualified_name() not in seen:
                    seen.add(c.qualified_name())
                    results.append(c)
            if results:
                return results

        if same_file:
            for c in same_file:
                if c.qualified_name() not in seen:
                    seen.add(c.qualified_name())
                    results.append(c)
            return results

        return results

    def callers_of(
        self, func_name: str, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Find all functions that call the given function.

        Args:
            func_name: Name of the target function
            file_path: Optional file path to disambiguate overloaded functions

        Returns:
            List of caller FunctionRef dicts
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for caller in self._callers.get(target, []):
                key = caller.qualified_name()
                if key not in seen:
                    seen.add(key)
                    result.append(caller.to_dict())
        return result

    def callees_of(
        self, func_name: str, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Find all functions called by the given function.

        Args:
            func_name: Name of the source function
            file_path: Optional file path to disambiguate overloaded functions

        Returns:
            List of callee FunctionRef dicts
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for callee in self._callees.get(target, []):
                key = callee.qualified_name()
                if key not in seen:
                    seen.add(key)
                    result.append(callee.to_dict())
        return result

    def call_chain(
        self, func_name: str, file_path: str | None = None, depth: int = 5
    ) -> list[dict[str, Any]]:
        """
        Trace the full call chain from a function (callees, transitively).

        Args:
            func_name: Starting function name
            file_path: Optional file to disambiguate
            depth: Maximum depth to traverse

        Returns:
            List of dicts with 'caller', 'callee', 'depth' keys
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        result: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for callee in self._callees.get(current, []):
                key = f"{current.qualified_name()}->{callee.qualified_name()}"
                if key not in visited:
                    visited.add(key)
                    result.append(
                        {
                            "caller": current.to_dict(),
                            "callee": callee.to_dict(),
                            "depth": d + 1,
                        }
                    )
                    queue.append((callee, d + 1))
        return result

    def all_functions(self) -> list[dict[str, Any]]:
        """Return all discovered functions."""
        self.build()
        return [f.to_dict() for f in self._functions]

    def functions_in_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return all functions defined in the given file."""
        self.build()
        return [f.to_dict() for f in self._func_by_file.get(file_path, [])]

    def file_impact(self, file_path: str) -> dict[str, Any]:
        """Analyze call-graph impact of changes to a file.

        Returns functions defined in the file, their callers (who depends
        on this file), and their callees (what this file depends on).
        """
        self.build()
        funcs = self._func_by_file.get(file_path, [])
        upstream: list[dict[str, Any]] = []
        downstream: list[dict[str, Any]] = []
        seen_up: set[str] = set()
        seen_down: set[str] = set()
        for func in funcs:
            for caller in self._callers.get(func, []):
                key = caller.qualified_name()
                if key not in seen_up:
                    seen_up.add(key)
                    upstream.append(caller.to_dict())
            for callee in self._callees.get(func, []):
                key = callee.qualified_name()
                if key not in seen_down:
                    seen_down.add(key)
                    downstream.append(callee.to_dict())
        return {
            "file": file_path,
            "function_count": len(funcs),
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "upstream": upstream,
            "downstream": downstream,
        }

    def summary(self) -> dict[str, Any]:
        """Return call graph summary statistics."""
        self.build()
        return {
            "function_count": len(self._functions),
            "call_edge_count": len(self._call_edges),
            "file_count": len({f.file_path for f in self._functions}),
        }

    def _resolve_targets(
        self, func_name: str, file_path: str | None = None
    ) -> list[FunctionRef]:
        """Resolve a function name (and optional file) to FunctionRef(s).

        Accepts three shapes for ``func_name``:

        - bare name ``foo`` — returns every ``FunctionRef`` named ``foo``
        - qualified ``Class.method`` — returns only refs whose receiver
          equals ``Class`` AND whose bare name is ``method``. Falls back
          to the bare-name list when no receiver matches, so callers that
          pass dotted names (e.g. ``utils.helper`` from JS) keep working.
        - ``file:func`` via the explicit ``file_path`` argument.
        """
        if file_path:
            qname = f"{file_path}:{func_name}"
            ref = self._func_by_qualified.get(qname)
            if ref:
                return [ref]

        # Qualified ``Class.method`` lookup: rsplit on the last dot and
        # require an exact receiver match before falling back. We only
        # treat the dotted form as qualified when neither half is empty
        # so plain names (``.foo`` etc.) keep their literal lookup.
        if "." in func_name:
            receiver, _, suffix = func_name.rpartition(".")
            if receiver and suffix:
                bare_candidates = self._func_by_name.get(suffix, [])
                receiver_matches = [
                    c for c in bare_candidates if c.receiver == receiver
                ]
                if receiver_matches:
                    if file_path:
                        same = [c for c in receiver_matches if c.file_path == file_path]
                        return same if same else receiver_matches
                    return receiver_matches

        candidates = self._func_by_name.get(func_name, [])
        if file_path:
            same = [c for c in candidates if c.file_path == file_path]
            return same if same else candidates
        return candidates


class CachedCallGraph(CallGraph):
    """
    CallGraph built from pre-indexed AST cache (SQLite).

    Instead of re-parsing every file, reads function definitions and call
    edges from the ASTCache SQLite database. Falls back to full parse when
    the cache is empty or unavailable.

    CodeGraph parity: like CodeGraph's pre-indexed call graph, queries are
    instant after initial indexing.
    """

    def __init__(
        self,
        project_root: str,
        cache: Any | None = None,
        fallback: bool = True,
    ) -> None:
        super().__init__(project_root)
        self._cache = cache
        self._fallback = fallback

    def build(self) -> None:
        if self._built:
            return

        if self._cache is not None:
            self._build_from_cache()
        if not self._built and self._fallback:
            super().build()

    def close(self) -> None:
        if self._cache is not None and hasattr(self._cache, "close"):
            self._cache.close()

    def __del__(self) -> None:
        self.close()

    def _build_from_cache(self) -> None:
        try:
            if self._cache is None:
                return
            edges = self._cache.get_call_edges()
            functions = self._cache.get_functions()
            imports_raw = self._cache.get_imports()
        except Exception:
            return

        if not functions and not edges:
            return

        rel_files: set[str] = set()
        for func in functions:
            ref = FunctionRef(
                file_path=func["file"],
                name=func["name"],
                start_line=func["line"],
                language=func["language"],
                end_line=func.get("end_line", func["line"]),
            )
            self._functions.append(ref)
            self._func_by_name[func["name"]].append(ref)
            self._func_by_file[func["file"]].append(ref)
            qname = ref.qualified_name()
            self._func_by_qualified[qname] = ref
            rel_files.add(func["file"])

        module_to_file: dict[str, str] = {}
        for rel in rel_files:
            p = Path(rel)
            stem = p.stem
            if stem == "__init__":
                mod = str(p.parent).replace("/", ".").replace("\\", ".")
            else:
                mod = str(p.with_suffix("")).replace("/", ".").replace("\\", ".")
            module_to_file[mod] = rel

        file_import_map: dict[str, dict[str, str]] = {}
        for file_path, import_texts in imports_raw.items():
            name_map: dict[str, str] = {}
            for imp_text in import_texts:
                parts = imp_text.split()
                if len(parts) >= 4 and parts[0] == "from":
                    mod_name = parts[1]
                    imported_names = [n.strip(",") for n in parts[3:] if n != "import"]
                    target_file = module_to_file.get(mod_name, "")
                    if target_file:
                        for name in imported_names:
                            name_map[name] = target_file
                elif len(parts) >= 2 and parts[0] == "import":
                    mod_name = parts[1].split(".")[0]
                    target_file = module_to_file.get(mod_name, "")
                    if target_file:
                        name_map[mod_name] = target_file
            if name_map:
                file_import_map[file_path] = name_map

        for edge in edges:
            caller_file = edge["caller_file"]
            caller_candidates = self._func_by_name.get(edge["caller_name"], [])
            caller_ref = None
            for c in caller_candidates:
                if c.file_path == caller_file:
                    caller_ref = c
                    break
            if caller_ref is None and caller_candidates:
                caller_ref = caller_candidates[0]
            if caller_ref is None:
                continue

            callee_name = edge["callee_name"]
            dot_parts = callee_name.rsplit(".", 1)
            if len(dot_parts) == 2:
                base_name = dot_parts[0]
                callee_name = dot_parts[1]
            else:
                base_name = callee_name

            callee_candidates = self._func_by_name.get(callee_name, [])
            if not callee_candidates:
                continue

            resolved = self._resolve_callee_from_cache(
                callee_name, base_name, caller_file, callee_candidates, file_import_map
            )

            for callee_ref in resolved:
                self._callees[caller_ref].append(callee_ref)
                self._callers[callee_ref].append(caller_ref)
                self._call_edges.append(
                    (caller_ref, callee_ref, edge.get("callee_line", 0))
                )

        self._built = True

    def _resolve_callee_from_cache(
        self,
        callee_name: str,
        base_name: str,
        caller_file: str,
        candidates: list[FunctionRef],
        file_import_map: dict[str, dict[str, str]],
    ) -> list[FunctionRef]:
        same_file = [c for c in candidates if c.file_path == caller_file]
        if same_file:
            return same_file

        imports = file_import_map.get(caller_file, {})
        target_file = imports.get(base_name) or imports.get(callee_name)
        if target_file:
            imported = [c for c in candidates if c.file_path == target_file]
            if imported:
                return imported

        return candidates[:1]
