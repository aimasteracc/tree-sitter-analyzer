"""
Import Dependency Sanitizer.

Detects unused imports, circular import dependencies, and import sort
order violations across Python, JavaScript/TypeScript, Java, and Go.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

@dataclass(frozen=True)
class ImportInfo:
    import_name: str
    module: str
    line: int
    column: int
    alias: str | None = None
    is_star: bool = False
    is_side_effect: bool = False

    @property
    def display_name(self) -> str:
        if self.alias:
            return f"{self.import_name} as {self.alias}"
        return self.import_name

@dataclass(frozen=True)
class SymbolRef:
    name: str
    line: int
    column: int
    context: str = ""

@dataclass(frozen=True)
class SortViolation:
    import_info: ImportInfo
    expected_group: str
    actual_group: str
    message: str

@dataclass(frozen=True)
class CircularImport:
    cycle: tuple[str, ...]
    severity: str = "warning"

    @property
    def display(self) -> str:
        return " -> ".join(self.cycle)

@dataclass
class FileAnalysis:
    file_path: str
    imports: list[ImportInfo] = field(default_factory=list)
    unused_imports: list[ImportInfo] = field(default_factory=list)
    symbols: list[SymbolRef] = field(default_factory=list)
    sort_violations: list[SortViolation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

@dataclass
class ImportAnalysisResult:
    files: list[FileAnalysis] = field(default_factory=list)
    circular_imports: list[CircularImport] = field(default_factory=list)
    total_imports: int = 0
    total_unused: int = 0
    total_sort_violations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_imports": self.total_imports,
            "total_unused": self.total_unused,
            "total_sort_violations": self.total_sort_violations,
            "circular_imports": [c.display for c in self.circular_imports],
            "files": [
                {
                    "path": f.file_path,
                    "imports": [i.display_name for i in f.imports],
                    "unused": [i.display_name for i in f.unused_imports],
                    "sort_violations": [v.message for v in f.sort_violations],
                    "errors": f.errors,
                }
                for f in self.files
            ],
        }

class ImportSanitizer(BaseAnalyzer):
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self._file_analyses: dict[str, FileAnalysis] = {}
        super().__init__()

    def _run_query(
        self,
        language: Any,
        query_string: str,
        root_node: Any,
    ) -> list[tuple[Any, str]]:
        return TreeSitterQueryCompat.execute_query(
            language, query_string, root_node
        )

    def analyze_file(self, file_path: str | Path) -> FileAnalysis:
        file_path = Path(file_path).resolve()
        ext = file_path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return FileAnalysis(file_path=str(file_path), errors=[f"Unsupported file type: {ext}"])

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return FileAnalysis(file_path=str(file_path), errors=[f"No parser for {ext}"])

        try:
            source = file_path.read_bytes()
            tree = parser.parse(source)
        except Exception as e:
            return FileAnalysis(file_path=str(file_path), errors=[str(e)])

        analysis = FileAnalysis(file_path=str(file_path))

        if ext == ".py":
            self._analyze_python(language, tree.root_node, source, analysis)
        elif ext in (".js", ".jsx"):
            self._analyze_javascript(language, tree.root_node, source, analysis, is_ts=False)
        elif ext in (".ts", ".tsx"):
            self._analyze_javascript(language, tree.root_node, source, analysis, is_ts=True)
        elif ext == ".java":
            self._analyze_java(language, tree.root_node, source, analysis)
        elif ext == ".go":
            self._analyze_go(language, tree.root_node, source, analysis)

        self._file_analyses[str(file_path)] = analysis
        return analysis

    def analyze_directory(self, dir_path: str | Path) -> ImportAnalysisResult:
        dir_path = Path(dir_path).resolve()
        result = ImportAnalysisResult()

        source_files = sorted(
            f for f in dir_path.rglob("*")
            if f.suffix in self.SUPPORTED_EXTENSIONS and f.is_file()
        )

        for sf in source_files:
            analysis = self.analyze_file(sf)
            result.files.append(analysis)
            result.total_imports += len(analysis.imports)
            result.total_unused += len(analysis.unused_imports)
            result.total_sort_violations += len(analysis.sort_violations)

        result.circular_imports = self._detect_circular_imports()
        return result

    def detect_unused(self, analysis: FileAnalysis) -> list[ImportInfo]:
        used_names: set[str] = set()
        for sym in analysis.symbols:
            used_names.add(sym.name)

        unused: list[ImportInfo] = []
        for imp in analysis.imports:
            if imp.is_star or imp.is_side_effect:
                continue
            name_to_check = imp.alias if imp.alias else imp.import_name
            if name_to_check not in used_names:
                unused.append(imp)
        return unused

    def _detect_circular_imports(self) -> list[CircularImport]:
        import_graph: dict[str, set[str]] = defaultdict(set)
        for file_path_str, analysis in self._file_analyses.items():
            file_path = Path(file_path_str)
            for imp in analysis.imports:
                resolved = self._resolve_import(imp.module, file_path)
                if resolved:
                    import_graph[file_path_str].add(resolved)

        return self._find_cycles(import_graph)

    def _resolve_import(self, module: str, from_file: Path) -> str | None:
        if not module or module.startswith("."):
            return None
        parts = module.split(".")
        for ext in self.SUPPORTED_EXTENSIONS:
            candidate = from_file.parent / "/".join(parts[:-1]) / (parts[-1] + ext)
            if candidate.exists():
                return str(candidate)
            candidate = from_file.parent / "/".join(parts) / ("__init__" + ext)
            if candidate.exists():
                return str(candidate)
        return None

    def _find_cycles(self, graph: dict[str, set[str]]) -> list[CircularImport]:
        index_counter = [0]
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: set[str] = set()
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlinks[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in graph.get(v, set()):
                if w not in index:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], index[w])

            if lowlinks[v] == index[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

        for node in graph:
            if node not in index:
                strongconnect(node)

        return [CircularImport(cycle=tuple(cycle)) for cycle in sccs]

    # ---- Python ----

    def _analyze_python(
        self, language: Any, root: Any, source: bytes, analysis: FileAnalysis,
    ) -> None:
        source_text = source.decode("utf-8", errors="replace")
        lines = source_text.splitlines()
        import_line_ranges: list[tuple[int, int]] = []

        for child in root.children:
            if child.type == "import_statement":
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1
                import_line_ranges.append((start_line, end_line))
                module_name = ""
                for sub in child.children:
                    if sub.type == "dotted_name":
                        module_name = self._node_text(sub, source)
                        analysis.imports.append(ImportInfo(
                            import_name=module_name,
                            module=module_name,
                            line=sub.start_point[0] + 1,
                            column=sub.start_point[1],
                        ))
                        break
                    elif sub.type == "identifier":
                        module_name = self._node_text(sub, source)
                        analysis.imports.append(ImportInfo(
                            import_name=module_name,
                            module=module_name,
                            line=sub.start_point[0] + 1,
                            column=sub.start_point[1],
                        ))
                        break

            elif child.type == "import_from_statement":
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1
                import_line_ranges.append((start_line, end_line))
                module_name = ""
                for sub in child.children:
                    if sub.type == "dotted_name":
                        module_name = self._node_text(sub, source)
                        break
                    elif sub.type == "identifier":
                        module_name = self._node_text(sub, source)
                        break

                for sub in child.children:
                    if sub.type == "wildcard_import":
                        analysis.imports.append(ImportInfo(
                            import_name="*",
                            module=module_name,
                            line=child.start_point[0] + 1,
                            column=child.start_point[1],
                            is_star=True,
                        ))
                    elif sub.type == "aliased_import":
                        name_str = ""
                        alias_str = ""
                        for inner in sub.children:
                            if inner.type in ("dotted_name", "identifier"):
                                name_str = self._node_text(inner, source)
                            elif inner.type == "identifier" and not name_str:
                                name_str = self._node_text(inner, source)
                            elif inner.type == "identifier":
                                alias_str = self._node_text(inner, source)
                        if not alias_str:
                            for i, inner in enumerate(sub.children):
                                if inner.type == "identifier":
                                    if i == 0:
                                        name_str = self._node_text(inner, source)
                                    else:
                                        alias_str = self._node_text(inner, source)
                                elif inner.type == "dotted_name":
                                    name_str = self._node_text(inner, source)
                        analysis.imports.append(ImportInfo(
                            import_name=name_str,
                            module=module_name,
                            line=sub.start_point[0] + 1,
                            column=sub.start_point[1],
                            alias=alias_str if alias_str else None,
                        ))
                    elif sub.type in ("dotted_name", "identifier"):
                        already_parent_module = (
                            sub.type == "dotted_name"
                            and self._node_text(sub, source) == module_name
                        )
                        if not already_parent_module:
                            name = self._node_text(sub, source)
                            analysis.imports.append(ImportInfo(
                                import_name=name,
                                module=module_name,
                                line=sub.start_point[0] + 1,
                                column=sub.start_point[1],
                            ))

        import_lines: set[int] = set()
        for start, end in import_line_ranges:
            for ln in range(start, end + 1):
                import_lines.add(ln)

        identifier_query = "(identifier) @id"
        for node, _ in self._run_query(language, identifier_query, root):
            line = node.start_point[0] + 1
            if line not in import_lines:
                name = self._node_text(node, source)
                analysis.symbols.append(SymbolRef(
                    name=name,
                    line=line,
                    column=node.start_point[1],
                ))

        analysis.unused_imports = self.detect_unused(analysis)
        analysis.sort_violations = self._check_python_sort(analysis, lines)

    def _check_python_sort(
        self, analysis: FileAnalysis, lines: list[str],
    ) -> list[SortViolation]:
        if not analysis.imports:
            return []

        violations: list[SortViolation] = []
        import_groups: list[tuple[int, str]] = []

        for imp in analysis.imports:
            line_idx = imp.line - 1
            if line_idx >= len(lines):
                continue
            line_text = lines[line_idx].strip()
            if not line_text:
                continue

            if line_text.startswith("from .") or (
                imp.module and imp.module.startswith(".")
            ):
                group = "local"
            elif imp.module and "." in imp.module and not imp.module.startswith("_"):
                top = imp.module.split(".")[0]
                stdlib_modules = {
                    "os", "sys", "re", "json", "io", "pathlib", "collections",
                    "functools", "itertools", "typing", "dataclasses", "abc",
                    "contextlib", "copy", "datetime", "enum", "logging",
                    "math", "random", "string", "textwrap", "time", "unittest",
                    "hashlib", "http", "urllib", "socket", "threading",
                    "multiprocessing", "subprocess", "shutil", "tempfile",
                    "argparse", "configparser", "csv", "sqlite3",
                    "struct", "operator", "pprint", "traceback", "warnings",
                    "weakref", "atexit", "builtins", "codecs", "gc",
                    "importlib", "inspect", "dis", "ast", "token",
                    "tokenize", "pickle", "shelve", "marshal", "base64",
                    "binascii", "gzip", "bz2", "lzma", "zipfile", "tarfile",
                    "ssl", "select", "signal", "mmap", "ctypes", "array",
                    "queue", "heapq", "bisect", "types", "numbers",
                }
                group = "stdlib" if top in stdlib_modules else "third_party"
            elif imp.module:
                top = imp.module.split(".")[0]
                stdlib_modules = {
                    "os", "sys", "re", "json", "io", "pathlib", "collections",
                    "functools", "itertools", "typing", "dataclasses", "abc",
                    "contextlib", "copy", "datetime", "enum", "logging",
                    "math", "random", "string", "textwrap", "time", "unittest",
                }
                group = "stdlib" if top in stdlib_modules else "third_party"
            else:
                group = "third_party"

            import_groups.append((imp.line, group))

        group_order = {"stdlib": 0, "third_party": 1, "local": 2}
        for i in range(1, len(import_groups)):
            prev_line, prev_group = import_groups[i - 1]
            curr_line, curr_group = import_groups[i]
            if abs(curr_line - prev_line) <= 2:
                if group_order.get(curr_group, 99) < group_order.get(prev_group, 99):
                    violations.append(SortViolation(
                        import_info=analysis.imports[i] if i < len(analysis.imports) else analysis.imports[-1],
                        expected_group=f"{prev_group} -> {curr_group}",
                        actual_group=f"{curr_group} before {prev_group}",
                        message=f"Line {curr_line}: '{curr_group}' import before '{prev_group}'",
                    ))
        return violations

    # ---- JavaScript/TypeScript ----

    def _analyze_javascript(
        self, language: Any, root: Any, source: bytes,
        analysis: FileAnalysis, *, is_ts: bool,
    ) -> None:
        import_lines: set[int] = set()

        for child in root.children:
            if child.type != "import_statement":
                continue
            start_line = child.start_point[0] + 1
            import_lines.add(start_line)

            source_str = ""
            for sub in child.children:
                if sub.type == "string":
                    for inner in sub.children:
                        if inner.type == "string_fragment":
                            source_str = self._node_text(inner, source)
                    break

            has_named_or_default = False
            for sub in child.children:
                if sub.type == "import_clause":
                    for clause_child in sub.children:
                        if clause_child.type == "identifier":
                            name = self._node_text(clause_child, source)
                            analysis.imports.append(ImportInfo(
                                import_name=name,
                                module=source_str,
                                line=clause_child.start_point[0] + 1,
                                column=clause_child.start_point[1],
                            ))
                            has_named_or_default = True
                        elif clause_child.type == "named_imports":
                            for spec in clause_child.children:
                                if spec.type == "import_specifier":
                                    for spec_child in spec.children:
                                        if spec_child.type == "identifier":
                                            name = self._node_text(spec_child, source)
                                            analysis.imports.append(ImportInfo(
                                                import_name=name,
                                                module=source_str,
                                                line=spec_child.start_point[0] + 1,
                                                column=spec_child.start_point[1],
                                            ))
                                            has_named_or_default = True
                                            break
                        elif clause_child.type == "namespace_import":
                            for ns_child in clause_child.children:
                                if ns_child.type == "identifier":
                                    name = self._node_text(ns_child, source)
                                    analysis.imports.append(ImportInfo(
                                        import_name=name,
                                        module=source_str,
                                        line=ns_child.start_point[0] + 1,
                                        column=ns_child.start_point[1],
                                        alias=name,
                                        is_star=True,
                                    ))
                                    has_named_or_default = True
                                    break

            if not has_named_or_default and source_str:
                analysis.imports.append(ImportInfo(
                    import_name=source_str,
                    module=source_str,
                    line=start_line,
                    column=child.start_point[1],
                    is_side_effect=True,
                ))

        for node, _ in self._run_query(language, "(identifier) @id", root):
            line = node.start_point[0] + 1
            if line not in import_lines:
                name = self._node_text(node, source)
                analysis.symbols.append(SymbolRef(
                    name=name,
                    line=line,
                    column=node.start_point[1],
                ))

        analysis.unused_imports = self.detect_unused(analysis)

    # ---- Java ----

    def _analyze_java(
        self, language: Any, root: Any, source: bytes, analysis: FileAnalysis,
    ) -> None:
        import_lines: set[int] = set()

        for child in root.children:
            if child.type != "import_declaration":
                continue
            start_line = child.start_point[0] + 1
            import_lines.add(start_line)

            for sub in child.children:
                if sub.type == "scoped_identifier":
                    path_text = self._node_text(sub, source)
                    parts = path_text.rsplit(".", 1)
                    if len(parts) == 2:
                        import_name = parts[1]
                        module = parts[0]
                    else:
                        import_name = path_text
                        module = path_text
                    analysis.imports.append(ImportInfo(
                        import_name=import_name,
                        module=module,
                        line=sub.start_point[0] + 1,
                        column=sub.start_point[1],
                    ))
                elif sub.type == "asterisk":
                    analysis.imports.append(ImportInfo(
                        import_name="*",
                        module="static",
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        is_star=True,
                    ))

        for node, _ in self._run_query(language, "(identifier) @id", root):
            line = node.start_point[0] + 1
            if line not in import_lines:
                name = self._node_text(node, source)
                analysis.symbols.append(SymbolRef(
                    name=name,
                    line=line,
                    column=node.start_point[1],
                ))

        for node, _ in self._run_query(
            language, "(type_identifier) @tid", root
        ):
            line = node.start_point[0] + 1
            if line not in import_lines:
                name = self._node_text(node, source)
                analysis.symbols.append(SymbolRef(
                    name=name,
                    line=line,
                    column=node.start_point[1],
                ))

        analysis.unused_imports = self.detect_unused(analysis)

    # ---- Go ----

    def _analyze_go(
        self, language: Any, root: Any, source: bytes, analysis: FileAnalysis,
    ) -> None:
        import_lines: set[int] = set()

        for child in root.children:
            if child.type != "import_declaration":
                continue
            start_line = child.start_point[0] + 1
            end_line = child.end_point[0] + 1
            for ln in range(start_line, end_line + 1):
                import_lines.add(ln)

            for sub in child.children:
                if sub.type != "import_spec":
                    continue
                alias = ""
                path_text = ""

                for spec_child in sub.children:
                    if spec_child.type == "package_identifier":
                        alias = self._node_text(spec_child, source)
                    elif spec_child.type == "interpreted_string_literal":
                        for lit_child in spec_child.children:
                            if lit_child.type == "interpreted_string_literal_content":
                                path_text = self._node_text(lit_child, source)

                if path_text:
                    pkg_name = (
                        path_text.rsplit("/", 1)[-1]
                        if "/" in path_text
                        else path_text
                    )
                    analysis.imports.append(ImportInfo(
                        import_name=pkg_name if not alias else alias,
                        module=path_text,
                        line=sub.start_point[0] + 1,
                        column=sub.start_point[1],
                        alias=alias if alias else None,
                    ))

        ident_query = "(identifier) @id\n(field_identifier) @id\n(package_identifier) @id"
        for node, _ in self._run_query(language, ident_query, root):
            line = node.start_point[0] + 1
            if line not in import_lines:
                name = self._node_text(node, source)
                analysis.symbols.append(SymbolRef(
                    name=name,
                    line=line,
                    column=node.start_point[1],
                ))

        analysis.unused_imports = self.detect_unused(analysis)

    @staticmethod
    def _node_text(node: Any, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

def analyze_imports(file_path: str | Path) -> FileAnalysis:
    sanitizer = ImportSanitizer(project_root=Path(file_path).resolve().parent)
    return sanitizer.analyze_file(file_path)

def analyze_project(project_root: str | Path) -> ImportAnalysisResult:
    sanitizer = ImportSanitizer(project_root=project_root)
    return sanitizer.analyze_directory(project_root)
