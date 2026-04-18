"""
Function Size Analyzer.

Measures the physical size of functions and methods: lines of code,
parameter count, and body span. Unlike cyclomatic or cognitive complexity
which measure logical complexity, function size catches the "wall of text"
problem that makes code hard to navigate and review.

Thresholds (industry-standard heuristics):
  - Good: <= 20 LOC, <= 4 params
  - Warning: 21-50 LOC or 5-6 params
  - Critical: > 50 LOC or > 6 params
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}

RATING_GOOD = "good"
RATING_WARNING = "warning"
RATING_CRITICAL = "critical"

LOC_GOOD = 20
LOC_CRITICAL = 50
PARAM_GOOD = 4
PARAM_CRITICAL = 6


def _size_rating(loc: int, param_count: int) -> str:
    if loc > LOC_CRITICAL or param_count > PARAM_CRITICAL:
        return RATING_CRITICAL
    if loc > LOC_GOOD or param_count > PARAM_GOOD:
        return RATING_WARNING
    return RATING_GOOD


def _nt(node: tree_sitter.Node, content: bytes) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class FunctionSize:
    """Size metrics for a single function/method."""

    name: str
    start_line: int
    end_line: int
    loc: int
    param_count: int
    rating: str
    element_type: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "loc": self.loc,
            "param_count": self.param_count,
            "rating": self.rating,
            "element_type": self.element_type,
        }


@dataclass(frozen=True)
class FunctionSizeResult:
    """Aggregated function size result for a file."""

    functions: tuple[FunctionSize, ...]
    total_functions: int
    oversized_functions: int
    avg_loc: float
    max_loc: int
    max_params: int
    file_path: str

    def get_oversized(self, loc_threshold: int = LOC_GOOD) -> list[FunctionSize]:
        return [f for f in self.functions if f.loc > loc_threshold]

    def get_high_param(self, threshold: int = PARAM_GOOD) -> list[FunctionSize]:
        return [f for f in self.functions if f.param_count > threshold]

    def to_dict(self) -> dict[str, str | int | float | list[object]]:
        return {
            "functions": [f.to_dict() for f in self.functions],
            "total_functions": self.total_functions,
            "oversized_functions": self.oversized_functions,
            "avg_loc": self.avg_loc,
            "max_loc": self.max_loc,
            "max_params": self.max_params,
            "file_path": self.file_path,
        }


def _empty_result(file_path: str) -> FunctionSizeResult:
    return FunctionSizeResult(
        functions=(),
        total_functions=0,
        oversized_functions=0,
        avg_loc=0.0,
        max_loc=0,
        max_params=0,
        file_path=file_path,
    )


class FunctionSizeAnalyzer:
    """Analyzes the physical size of functions in source code."""

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(
        self, extension: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if extension not in _LANGUAGE_MODULES:
            return None, None
        if extension not in self._parsers:
            module_name = _LANGUAGE_MODULES[extension]
            try:
                lang_module = __import__(module_name)
                func_name = _LANGUAGE_FUNCS.get(extension, "language")
                language_func = getattr(lang_module, func_name)
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None
        return self._languages.get(extension), self._parsers.get(extension)

    def analyze_file(self, file_path: Path | str) -> FunctionSizeResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))

        functions = self._extract_functions(path, ext)
        return self._build_result(functions, str(path))

    def _build_result(
        self, functions: list[FunctionSize], file_path: str
    ) -> FunctionSizeResult:
        total = len(functions)
        if total == 0:
            return _empty_result(file_path)
        oversized = sum(
            1 for f in functions if f.rating != RATING_GOOD
        )
        avg_loc = sum(f.loc for f in functions) / total
        max_loc = max(f.loc for f in functions)
        max_params = max(f.param_count for f in functions)
        return FunctionSizeResult(
            functions=tuple(functions),
            total_functions=total,
            oversized_functions=oversized,
            avg_loc=round(avg_loc, 1),
            max_loc=max_loc,
            max_params=max_params,
            file_path=file_path,
        )

    def _extract_functions(self, path: Path, ext: str) -> list[FunctionSize]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            return self._extract_python(tree.root_node, content)
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content)
        if ext == ".java":
            return self._extract_java(tree.root_node, content)
        if ext == ".go":
            return self._extract_go(tree.root_node, content)
        return []

    # ── Shared helpers ────────────────────────────────────────────────────

    def _count_params(self, node: tree_sitter.Node | None) -> int:
        if node is None:
            return 0
        count = 0
        for child in node.children:
            if child.type == "identifier":
                count += 1
            elif child.type == "typed_parameter":
                count += 1
            elif child.type == "default_parameter":
                count += 1
            elif child.type == "list_splat_pattern":
                count += 1
            elif child.type == "dictionary_splat_pattern":
                count += 1
            elif child.type == "type_annotation":
                pass
            elif child.type == "parameter":
                count += 1
            elif child.type in {"required_parameter", "optional_parameter",
                                "rest_parameter"}:
                count += 1
            elif child.type == "formal_parameter":
                count += 1
            elif child.type == "spread_parameter":
                count += 1
            elif child.type in {"variadic_parameter", "param_identifier"}:
                count += 1
        return count

    # ── Python ────────────────────────────────────────────────────────────

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionSize]:
        results: list[FunctionSize] = []
        self._walk_python(root, content, results, in_class=False)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionSize],
        in_class: bool,
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, content, results, in_class)
            return

        if node.type == "class_definition":
            for child in node.children:
                self._walk_python(child, content, results, in_class=True)
            return

        if node.type == "function_definition":
            fn = self._analyze_python_function(node, content, in_class)
            if fn is not None:
                results.append(fn)

        for child in node.children:
            self._walk_python(child, content, results, in_class)

    def _analyze_python_function(
        self, node: tree_sitter.Node, content: bytes, in_class: bool
    ) -> FunctionSize | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = _nt(name_node, content)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        loc = end_line - start_line + 1

        params_node = node.child_by_field_name("parameters")
        param_count = self._count_params(params_node)

        return FunctionSize(
            name=name,
            start_line=start_line,
            end_line=end_line,
            loc=loc,
            param_count=param_count,
            rating=_size_rating(loc, param_count),
            element_type="method" if in_class else "function",
        )

    # ── JavaScript / TypeScript ───────────────────────────────────────────

    def _extract_js(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionSize]:
        results: list[FunctionSize] = []
        self._walk_js(root, content, results, in_class=False)
        return results

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionSize],
        in_class: bool,
    ) -> None:
        if node.type in {"class_declaration", "class_expression"}:
            for child in node.children:
                self._walk_js(child, content, results, in_class=True)
            return

        if node.type in {"function_declaration",
                         "generator_function_declaration"}:
            fn = self._analyze_js_function(node, content, in_class, "function")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_definition":
            fn = self._analyze_js_function(node, content, True, "method")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "arrow_function":
            fn = self._analyze_js_function(
                node, content, in_class, "arrow_function"
            )
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_js(child, content, results, in_class)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        element_type: str,
    ) -> FunctionSize | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = _nt(name_node, content)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        loc = end_line - start_line + 1

        params_node = node.child_by_field_name("parameters")
        param_count = self._count_params(params_node)

        etype = "method" if in_class else element_type
        return FunctionSize(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            loc=loc,
            param_count=param_count,
            rating=_size_rating(loc, param_count),
            element_type=etype,
        )

    # ── Java ──────────────────────────────────────────────────────────────

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionSize]:
        results: list[FunctionSize] = []
        self._walk_java(root, content, results, in_class=False)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionSize],
        in_class: bool,
    ) -> None:
        if node.type in {"class_declaration", "interface_declaration",
                          "enum_declaration", "record_declaration"}:
            for child in node.children:
                self._walk_java(child, content, results, in_class=True)
            return

        if node.type == "method_declaration":
            fn = self._analyze_java_method(node, content, in_class)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "constructor_declaration":
            fn = self._analyze_java_method(
                node, content, True, "<init>"
            )
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_java(child, content, results, in_class)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        override_name: str | None = None,
    ) -> FunctionSize | None:
        if override_name:
            name = override_name
        else:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = _nt(name_node, content)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        loc = end_line - start_line + 1

        params_node = node.child_by_field_name("parameters")
        param_count = self._count_params(params_node)

        return FunctionSize(
            name=name,
            start_line=start_line,
            end_line=end_line,
            loc=loc,
            param_count=param_count,
            rating=_size_rating(loc, param_count),
            element_type="method" if in_class else "function",
        )

    # ── Go ────────────────────────────────────────────────────────────────

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionSize]:
        results: list[FunctionSize] = []
        self._walk_go(root, content, results)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionSize],
    ) -> None:
        if node.type == "function_declaration":
            fn = self._analyze_go_func(node, content, "function")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_declaration":
            fn = self._analyze_go_func(node, content, "method")
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_go(child, content, results)

    def _analyze_go_func(
        self,
        node: tree_sitter.Node,
        content: bytes,
        element_type: str,
    ) -> FunctionSize | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = _nt(name_node, content)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        loc = end_line - start_line + 1

        params_node = node.child_by_field_name("parameters")
        param_count = self._count_params_go(params_node)

        return FunctionSize(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            loc=loc,
            param_count=param_count,
            rating=_size_rating(loc, param_count),
            element_type=element_type,
        )

    def analyze_directory(
        self,
        directory: str,
    ) -> list[tuple[str, FunctionSizeResult]]:
        dir_path = Path(directory)
        results: list[tuple[str, FunctionSizeResult]] = []

        for ext in SUPPORTED_EXTENSIONS:
            for fp in dir_path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                result = self.analyze_file(str(fp))
                if result.total_functions > 0:
                    results.append((str(fp), result))

        return results

    def _count_params_go(self, node: tree_sitter.Node | None) -> int:
        if node is None:
            return 0
        count = 0
        for child in node.children:
            if child.type == "parameter_declaration":
                count += 1
            elif child.type == "variadic_parameter_declaration":
                count += 1
        return count
