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

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .core.parser import Parser, ParseResult
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

# r37az: extracted from inline ``build()`` so the extension set is a
# named module-level constant — easier to update + matches the existing
# pattern of _EXCLUDE_DIRS being a module constant.
_SUPPORTED_BUILD_EXTS = frozenset(
    {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".c", ".cpp", ".cc", ".cxx"}
)


class FunctionRef:
    """A qualified reference to a function/method in the project."""

    __slots__ = ("file_path", "name", "start_line", "language", "receiver")

    def __init__(
        self,
        file_path: str,
        name: str,
        start_line: int,
        language: str,
        receiver: str | None = None,
    ) -> None:
        self.file_path = file_path
        self.name = name
        self.start_line = start_line
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


# r37az: per-language allowed identifier node types — extracted from the
# big if/elif chain that drove the nesting-8 smell. Each language picks
# the first child matching its type list; C/C++ also recurses into
# ``function_declarator``.
_FUNC_NAME_NODE_TYPES: dict[str, tuple[str, ...]] = {
    "python": ("identifier",),
    "javascript": ("identifier", "property_identifier"),
    "typescript": ("identifier", "property_identifier"),
    "java": ("identifier",),
    "go": ("identifier",),
    "c": ("identifier", "field_identifier", "destructor_name"),
    "cpp": ("identifier", "field_identifier", "destructor_name"),
}


def _get_func_name(node: Any, language: str) -> str | None:
    """Extract function name from a definition node.

    r37az: replaced the 6-language if/elif chain (each branch a
    near-identical ``for child in node.children: if child.type in (...):``
    loop) with a dispatch table + the C/C++ ``function_declarator``
    recursion in a single helper. Same per-language behaviour preserved.
    """
    accepted = _FUNC_NAME_NODE_TYPES.get(language)
    if accepted is None:
        return None
    try:
        for child in node.children:
            if child.type in accepted:
                return _decode_node_text(child)
            if language in ("c", "cpp") and child.type == "function_declarator":
                name = _find_first_identifier(child)
                if name is not None:
                    return name
    except Exception:  # nosec B110 - best-effort AST walk; missing field is non-fatal
        pass
    return None


def _decode_node_text(node: Any) -> str:
    """Return ``node.text`` as a Python str, decoding bytes when needed."""
    text = node.text
    return text.decode("utf-8") if isinstance(text, bytes) else str(text)


def _find_first_identifier(parent: Any) -> str | None:
    """Find the first identifier/field_identifier child of ``parent``."""
    for sub in parent.children:
        if sub.type in ("identifier", "field_identifier"):
            return _decode_node_text(sub)
    return None


def _extract_c_call_from_children(node: Any, source: str) -> dict[str, Any] | None:
    """Fallback C/C++ call extraction when ``function`` field is absent.

    Some tree-sitter-c parses macro-style invocations (``FOO(x)``)
    without filling the ``function`` field. We then scan children for
    the first ``identifier`` and treat that as the call target.
    Returns ``None`` when no identifier child exists.
    """
    for child in node.children:
        if child.type != "identifier":
            continue
        text = _node_text(child, source)
        return {
            "name": text,
            "full_name": text,
            "line": node.start_point[0] + 1,
            "receiver": None,
        }
    return None


def _extract_java_call(node: Any, source: str) -> dict[str, Any] | None:
    """Extract call target info from a Java call/method-reference node.

    r37df (dogfood): lifted from inline branch of ``_extract_call`` to
    flatten its Java path from depth 6 to 3. Identifiers return as bare
    names; ``field_access`` / ``method_reference`` split the rightmost
    dotted segment so ``foo.bar.baz()`` yields receiver=``foo.bar`` and
    name=``baz``. Returns ``None`` when no child shape matches — the
    caller treats that as "no actionable call info".
    """
    for child in node.children:
        if child.type == "identifier":
            text = _node_text(child, source)
            return {
                "name": text,
                "full_name": text,
                "line": node.start_point[0] + 1,
                "receiver": None,
            }
        if child.type not in ("field_access", "method_reference"):
            continue
        text = _node_text(child, source)
        receiver: str | None = None
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
            # r37df (dogfood): nesting 6 → 3 via _extract_java_call helper.
            return _extract_java_call(node, source)
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
            # r37df (dogfood): nesting 6 → 3 via _extract_c_call_no_func helper.
            func_node = node.child_by_field_name("function")
            if func_node is None:
                return _extract_c_call_from_children(node, source)
            name = _node_text(func_node, source)
            return {
                "name": name,
                "full_name": name,
                "line": node.start_point[0] + 1,
                "receiver": None,
            }
    except Exception:  # nosec B110 - best-effort AST walk; missing field is non-fatal
        pass
    return None


def _node_text(node: Any, source: str) -> str:
    """Extract text from a node given the full source string.

    H2 fix: tree-sitter exposes ``start_byte``/``end_byte`` as UTF-8 BYTE
    offsets, not character offsets. Indexing into ``source`` (a ``str``)
    with byte offsets returns garbage when the file contains any multi-
    byte characters (e.g. em-dashes ``—`` in comments). Symptom: callees
    extracted from a source file with non-ASCII text would have their
    ``name`` truncated/shifted, so ``_resolve_callee`` could not match
    them against the function-name index — caller/callee edges were
    silently dropped for any function indirectly downstream of such a
    file. Prefer ``node.text`` (already bytes from tree-sitter) and fall
    back to a byte-slice of the source only if ``node.text`` is missing.
    """
    text = getattr(node, "text", None)
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    if isinstance(text, str):
        return text
    try:
        start = node.start_byte
        end = node.end_byte
        return source.encode("utf-8")[start:end].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _find_parent_class_python(node: Any) -> str | None:
    """Walk up from a function node to find the enclosing class.

    r37df (dogfood): flattened nesting 6 → 3 via
    ``_python_class_name`` helper. Walk stays a while-loop; the
    identifier scan inside each ``class_definition`` is its own helper.
    """
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            name = _python_class_name(current)
            if name is not None:
                return name
        current = current.parent
    return None


def _python_class_name(class_node: Any) -> str | None:
    """Return the first ``identifier`` child's text from a Python class.

    Decodes bytes to str when needed (tree-sitter returns ``bytes`` on
    some bindings, ``str`` on others). Returns ``None`` if no identifier
    is found — caller treats that as "anonymous / can't name".
    """
    for child in class_node.children:
        if child.type != "identifier":
            continue
        text = child.text
        return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    return None


def _find_parent_class_java(node: Any) -> str | None:
    """Walk up from a method node to find the enclosing class.

    r37df (dogfood): flattened nesting 6 → 3 via ``_java_class_name``
    helper (mirror of ``_python_class_name``).
    """
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_declaration":
            name = _java_class_name(current)
            if name is not None:
                return name
        current = current.parent
    return None


def _java_class_name(class_node: Any) -> str | None:
    """Return the first ``identifier`` child's text from a Java class."""
    for child in class_node.children:
        if child.type != "identifier":
            continue
        text = child.text
        return text.decode("utf-8") if isinstance(text, bytes) else str(text)
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
        self._callees: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._callers: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._call_edges: list[tuple[FunctionRef, FunctionRef, int]] = []
        self._built = False

    def build(self) -> None:
        """Scan the project and build the call graph.

        Two-pass deterministic build (H3 fix preserved). r37az: the main
        ``build`` body was 130 lines — refactored into
        ``_discover_source_files`` + ``_register_definitions_pass`` +
        ``_resolve_calls_pass``. Behaviour preserved, including the H3
        determinism guarantee (file-order = sorted relative path; pass-1
        completes before pass-2 starts).
        """
        if self._built:
            return

        rel_to_abs = self._discover_source_files()
        parser = Parser()
        parsed = self._register_definitions_pass(parser, rel_to_abs)
        self._resolve_calls_pass(parsed, rel_to_abs)
        self._built = True

    def _discover_source_files(self) -> dict[str, str]:
        """Pass 0: enumerate source files in deterministic relative-path order.

        Returns an insertion-ordered ``{rel_path: abs_path}`` dict so both
        passes traverse files identically across runs (no PYTHONHASHSEED
        sensitivity, no filesystem-order dependency).
        """
        all_files: list[Path] = []
        for ext in _SUPPORTED_BUILD_EXTS:
            for f in self.project_root.rglob(f"*{ext}"):
                if not self._is_excluded(f):
                    all_files.append(f)

        rel_to_abs_pairs: list[tuple[str, str]] = []
        for f in all_files:
            try:
                rel = str(f.relative_to(self.project_root))
                rel_to_abs_pairs.append((rel, str(f)))
            except ValueError:
                continue
        rel_to_abs_pairs.sort(key=lambda p: p[0])

        # De-dup while preserving sorted order (defensive — _SUPPORTED_BUILD_EXTS
        # is disjoint but rglob can still yield duplicates on case-insensitive FS).
        seen_rel: set[str] = set()
        rel_to_abs: dict[str, str] = {}
        for rel, abs_path in rel_to_abs_pairs:
            if rel in seen_rel:
                continue
            seen_rel.add(rel)
            rel_to_abs[rel] = abs_path
        return rel_to_abs

    def _register_definitions_pass(
        self,
        parser: Parser,
        rel_to_abs: dict[str, str],
    ) -> dict[
        str,
        tuple[
            str, Any, list[dict[str, Any]], list[dict[str, Any]], dict[str, FunctionRef]
        ],
    ]:
        """Pass 1: parse every file, register every FunctionRef, return parsed cache.

        Cache shape is ``{rel_path: (language, tree, definitions, calls, file_funcs)}``.
        Files that fail to parse are skipped silently — pass 2 will skip them too.
        """
        parsed: dict[
            str,
            tuple[
                str,
                Any,
                list[dict[str, Any]],
                list[dict[str, Any]],
                dict[str, FunctionRef],
            ],
        ] = {}
        for rel_path, abs_path in rel_to_abs.items():
            language = _language_from_ext(rel_path)
            if language is None:
                continue
            result: ParseResult = parser.parse_file(abs_path, language)
            if not result.success or result.tree is None:
                continue

            definitions, calls = _walk_tree(
                result.tree.root_node, result.source_code, language
            )
            file_funcs = self._register_file_definitions(
                rel_path, language, definitions
            )
            parsed[rel_path] = (language, result.tree, definitions, calls, file_funcs)
        return parsed

    def _register_file_definitions(
        self,
        rel_path: str,
        language: str,
        definitions: list[dict[str, Any]],
    ) -> dict[str, FunctionRef]:
        """Append each definition to the global indices and return ``{name: ref}``."""
        file_funcs: dict[str, FunctionRef] = {}
        for defn in definitions:
            ref = FunctionRef(
                file_path=rel_path,
                name=defn["name"],
                start_line=defn["start_line"],
                language=language,
                receiver=defn.get("class"),
            )
            self._functions.append(ref)
            self._func_by_name[defn["name"]].append(ref)
            self._func_by_qualified[ref.qualified_name()] = ref
            file_funcs[defn["name"]] = ref
        return file_funcs

    def _resolve_calls_pass(
        self,
        parsed: dict[
            str,
            tuple[
                str,
                Any,
                list[dict[str, Any]],
                list[dict[str, Any]],
                dict[str, FunctionRef],
            ],
        ],
        rel_to_abs: dict[str, str],
    ) -> None:
        """Pass 2: resolve every call against the now-complete definition index."""
        for rel_path in rel_to_abs:  # already sorted insertion order
            entry = parsed.get(rel_path)
            if entry is None:
                continue
            _language, _tree, _definitions, calls, file_funcs = entry
            for call in calls:
                self._record_edges_for_call(call, rel_path, rel_to_abs, file_funcs)

    def _record_edges_for_call(
        self,
        call: dict[str, Any],
        rel_path: str,
        rel_to_abs: dict[str, str],
        file_funcs: dict[str, FunctionRef],
    ) -> None:
        """Resolve a single call site and append every (caller, callee) edge."""
        caller_ref = self._find_enclosing_func(file_funcs, call["line"])
        if caller_ref is None:
            return
        for callee_ref in self._resolve_callee(call, rel_path, rel_to_abs):
            self._callees[caller_ref].append(callee_ref)
            self._callers[callee_ref].append(caller_ref)
            self._call_edges.append((caller_ref, callee_ref, call["line"]))

    def _is_excluded(self, path: Path) -> bool:
        return any(part in _EXCLUDE_DIRS for part in path.parts)

    def _find_enclosing_func(
        self,
        file_funcs: dict[str, FunctionRef],
        call_line: int,
    ) -> FunctionRef | None:
        """Find the function that contains the given line number."""
        best: FunctionRef | None = None
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
        """Resolve a call site to FunctionRef(s) in the project."""
        name = call["name"]
        results: list[FunctionRef] = []

        candidates = self._func_by_name.get(name, [])
        if candidates:
            same_file = [c for c in candidates if c.file_path == source_rel]
            results.extend(same_file if same_file else candidates)

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

        # r37df (dogfood): nesting 6 → 4 via early-continue on visited edges.
        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for callee in self._callees.get(current, []):
                key = f"{current.qualified_name()}->{callee.qualified_name()}"
                if key in visited:
                    continue
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

        Accepts three forms:
        - bare name (e.g. ``foo``) — returns all functions with that name.
        - ``Class.method`` (e.g. ``BaseMCPTool.__init__``) — splits on the
          last ``.``, looks up ``method``, and filters by ``receiver == Class``.
          When the qualified form matches no definitions, falls back to the
          bare name so partial qualifiers (e.g. a stale class prefix) still
          yield results instead of a silent zero.
        - file-qualified name via the explicit ``file_path`` argument.
        """
        if file_path:
            qname = f"{file_path}:{func_name}"
            ref = self._func_by_qualified.get(qname)
            if ref:
                return [ref]

        # Class.method form — split off the receiver prefix.
        if (
            "." in func_name
            and ":" not in func_name
            and "/" not in func_name
            and "\\" not in func_name
        ):
            receiver, _, suffix = func_name.rpartition(".")
            suffix_candidates = self._func_by_name.get(suffix, [])
            qualified = [c for c in suffix_candidates if c.receiver == receiver]
            if qualified:
                if file_path:
                    same = [c for c in qualified if c.file_path == file_path]
                    return same if same else qualified
                return qualified
            # Receiver filter found nothing — fall back to bare suffix below.
            candidates = suffix_candidates
        else:
            candidates = self._func_by_name.get(func_name, [])

        if file_path:
            same = [c for c in candidates if c.file_path == file_path]
            return same if same else candidates
        return candidates
