"""
Cognitive Complexity Analyzer (SonarSource specification).

Measures how hard code is to understand by tracking nesting depth,
control flow breaks, and logical operator sequences at the function level.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

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

# Complexity rating thresholds (SonarSource)
RATING_SIMPLE = "simple"          # 1-5
RATING_MODERATE = "moderate"      # 6-10
RATING_COMPLEX = "complex"        # 11-20
RATING_VERY_COMPLEX = "very_complex"  # 21-50
RATING_EXTREME = "extreme"        # 50+


def _rating(score: int) -> str:
    if score <= 5:
        return RATING_SIMPLE
    if score <= 10:
        return RATING_MODERATE
    if score <= 20:
        return RATING_COMPLEX
    if score <= 50:
        return RATING_VERY_COMPLEX
    return RATING_EXTREME


# Node types that increase nesting (children are nested)
_NESTING_NODES_PY: set[str] = {
    "if_statement", "for_statement", "while_statement",
    "with_statement", "match_statement",
}

# Node types that add a flat +1 increment (no nesting increase)
_INCREMENT_NODES_PY: set[str] = {
    "elif_clause", "else_clause",
}

# Node types for logical operators in Python
_LOGICAL_OPS_PY: set[str] = {"and", "or"}


@dataclass(frozen=True)
class ComplexityIncrement:
    """A single cognitive complexity increment."""

    increment_type: str  # nesting, flat, logical_op
    line_number: int
    value: int
    description: str


@dataclass(frozen=True)
class FunctionComplexity:
    """Cognitive complexity of a single function/method."""

    name: str
    start_line: int
    end_line: int
    total_complexity: int
    rating: str
    increments: tuple[ComplexityIncrement, ...]
    element_type: str  # function, method, lambda, arrow_function


@dataclass(frozen=True)
class CognitiveComplexityResult:
    """Aggregated cognitive complexity result for a file."""

    functions: tuple[FunctionComplexity, ...]
    total_functions: int
    total_complexity: int
    avg_complexity: float
    max_complexity: int
    file_path: str

    def get_complex_functions(self, threshold: int = 15) -> list[FunctionComplexity]:
        return [f for f in self.functions if f.total_complexity > threshold]


class CognitiveComplexityAnalyzer:
    """Analyzes cognitive complexity using SonarSource specification."""

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

    def analyze_file(self, file_path: Path | str) -> CognitiveComplexityResult:
        path = Path(file_path)
        if not path.exists():
            return CognitiveComplexityResult(
                functions=(),
                total_functions=0,
                total_complexity=0,
                avg_complexity=0.0,
                max_complexity=0,
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return CognitiveComplexityResult(
                functions=(),
                total_functions=0,
                total_complexity=0,
                avg_complexity=0.0,
                max_complexity=0,
                file_path=str(path),
            )

        functions = self._extract_functions(path, ext)
        total = len(functions)
        total_cc = sum(f.total_complexity for f in functions)
        avg = (total_cc / total) if total > 0 else 0.0
        max_cc = max((f.total_complexity for f in functions), default=0)

        return CognitiveComplexityResult(
            functions=tuple(functions),
            total_functions=total,
            total_complexity=total_cc,
            avg_complexity=round(avg, 2),
            max_complexity=max_cc,
            file_path=str(path),
        )

    def _extract_functions(self, path: Path, ext: str) -> list[FunctionComplexity]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            return self._extract_python(tree.root_node, content, str(path))
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content, str(path))
        if ext == ".java":
            return self._extract_java(tree.root_node, content, str(path))
        if ext == ".go":
            return self._extract_go(tree.root_node, content, str(path))
        return []

    # ── Python ──────────────────────────────────────────────────────────

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionComplexity]:
        results: list[FunctionComplexity] = []
        self._walk_python(root, content, file_path, results, in_class=False)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionComplexity],
        in_class: bool,
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, content, file_path, results, in_class)
            return

        if node.type == "class_definition":
            for child in node.children:
                self._walk_python(child, content, file_path, results, in_class=True)
            return

        if node.type == "function_definition":
            fc = self._analyze_python_function(node, content, in_class)
            if fc is not None:
                results.append(fc)

        if node.type == "lambda":
            # Skip keyword children (tree-sitter-python has 'lambda' keyword
            # inside lambda nodes)
            if node.parent is not None and node.parent.type != "lambda":
                fc = self._analyze_python_lambda(node, content)
                if fc is not None:
                    results.append(fc)
            for child in node.children:
                self._walk_python(child, content, file_path, results, in_class)
            return

        for child in node.children:
            self._walk_python(child, content, file_path, results, in_class)

    def _analyze_python_function(
        self, node: tree_sitter.Node, content: bytes, in_class: bool
    ) -> FunctionComplexity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            return FunctionComplexity(
                name=name,
                start_line=start_line,
                end_line=end_line,
                total_complexity=0,
                rating=_rating(0),
                increments=(),
                element_type="method" if in_class else "function",
            )

        increments: list[ComplexityIncrement] = []
        self._walk_python_complexity(body, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name=name,
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type="method" if in_class else "function",
        )

    def _analyze_python_lambda(
        self, node: tree_sitter.Node, content: bytes
    ) -> FunctionComplexity | None:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        increments: list[ComplexityIncrement] = []
        self._walk_python_complexity(node, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name="<lambda>",
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type="lambda",
        )

    def _walk_python_complexity(
        self,
        node: tree_sitter.Node,
        content: bytes,
        nesting: int,
        increments: list[ComplexityIncrement],
    ) -> None:
        # try_statement: +1+nesting, but except children are flat
        if node.type == "try_statement":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"try at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type == "except_clause":
                    self._walk_python_complexity(child, content, nesting, increments)
                elif child.type == "block":
                    # try body is at nesting+1
                    self._walk_python_complexity(child, content, nesting + 1, increments)
                else:
                    self._walk_python_complexity(child, content, nesting + 1, increments)
            return

        # Other nesting nodes (if, for, while, with, match)
        if node.type in _NESTING_NODES_PY:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"{node.type} at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                self._walk_python_complexity(child, content, nesting + 1, increments)
            return

        # except_clause: flat +1 (no nesting increase)
        if node.type == "except_clause":
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="flat",
                    line_number=line,
                    value=1,
                    description=f"except at line {line} (+1)",
                )
            )
            for child in node.children:
                self._walk_python_complexity(child, content, nesting, increments)
            return

        # elif/else: flat +1 (linear continuation)
        if node.type in _INCREMENT_NODES_PY:
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="flat",
                    line_number=line,
                    value=1,
                    description=f"{node.type} at line {line} (+1)",
                )
            )
            for child in node.children:
                self._walk_python_complexity(child, content, nesting, increments)
            return

        # boolean_operator (and/or sequences)
        if node.type == "boolean_operator":
            self._handle_python_logical_ops(node, content, increments)
            return

        # ternary (conditional_expression)
        if node.type == "conditional_expression":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"ternary at line {line} (+{inc_value})",
                )
            )
            return

        # Comprehensions with if_clause inside
        if node.type in {"list_comprehension", "set_comprehension",
                         "dict_comprehension", "generator_expression"}:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"{node.type} at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type == "if_clause":
                    # if_clause in comprehension: +1 at comprehension nesting
                    if_line = child.start_point[0] + 1
                    comp_nesting = nesting + 1
                    increments.append(
                        ComplexityIncrement(
                            increment_type="nesting",
                            line_number=if_line,
                            value=1 + comp_nesting,
                            description=f"if_clause at line {if_line} (+{1 + comp_nesting})",
                        )
                    )
                else:
                    self._walk_python_complexity(child, content, nesting + 1, increments)
            return

        # Recurse children
        for child in node.children:
            self._walk_python_complexity(child, content, nesting, increments)

    def _handle_python_logical_ops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        increments: list[ComplexityIncrement],
    ) -> None:
        """Count logical operator sequences. Each change of operator adds +1."""
        ops = self._collect_logical_ops(node, content)
        if not ops:
            return

        # SonarSource rule: count sequences of the same operator as 1,
        # each change of operator adds +1
        prev_op: str | None = None
        first = True
        for op_text, line in ops:
            if first:
                increments.append(
                    ComplexityIncrement(
                        increment_type="logical_op",
                        line_number=line,
                        value=1,
                        description=f"{op_text} at line {line} (+1)",
                    )
                )
                prev_op = op_text
                first = False
            elif op_text != prev_op:
                increments.append(
                    ComplexityIncrement(
                        increment_type="logical_op",
                        line_number=line,
                        value=1,
                        description=f"{op_text} at line {line} (+1)",
                    )
                )
                prev_op = op_text

    def _collect_logical_ops(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[tuple[str, int]]:
        """Flatten a boolean_operator tree into ordered list of (op, line)."""
        result: list[tuple[str, int]] = []
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if left:
            if left.type == "boolean_operator":
                result.extend(self._collect_logical_ops(left, content))
            # left is a leaf, we just continue

        # The operator is between children
        op_text = ""
        for child in node.children:
            if child.type in _LOGICAL_OPS_PY:
                op_text = content[child.start_byte:child.end_byte].decode(
                    "utf-8", errors="replace"
                )
                line = child.start_point[0] + 1
                result.append((op_text, line))

        if right:
            if right.type == "boolean_operator":
                result.extend(self._collect_logical_ops(right, content))

        return result

    # ── JavaScript / TypeScript ──────────────────────────────────────────

    # Nesting nodes for JS/TS
    _JS_NESTING: frozenset[str] = frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "do_statement", "switch_statement",
        "try_statement", "with_statement",
    })

    # Flat increment nodes for JS/TS
    _JS_FLAT: frozenset[str] = frozenset({
        "else_clause", "catch_clause", "finally_clause",
    })

    # JS function container types
    _JS_FUNC_TYPES: frozenset[str] = frozenset({
        "function_declaration", "function", "arrow_function",
        "generator_function_declaration", "method_definition",
    })

    def _extract_js(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionComplexity]:
        results: list[FunctionComplexity] = []
        self._walk_js(root, content, file_path, results, in_class=False)
        return results

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionComplexity],
        in_class: bool,
    ) -> None:
        if node.type == "class_declaration" or node.type == "class_expression":
            for child in node.children:
                self._walk_js(child, content, file_path, results, in_class=True)
            return

        if node.type == "function_declaration":
            fc = self._analyze_js_function(node, content, in_class, "function")
            if fc is not None:
                results.append(fc)
            return

        if node.type == "generator_function_declaration":
            fc = self._analyze_js_function(node, content, in_class, "function")
            if fc is not None:
                results.append(fc)
            return

        if node.type == "method_definition":
            fc = self._analyze_js_function(node, content, True, "method")
            if fc is not None:
                results.append(fc)
            return

        if node.type == "arrow_function":
            fc = self._analyze_js_arrow(node, content)
            if fc is not None:
                results.append(fc)
            return

        for child in node.children:
            self._walk_js(child, content, file_path, results, in_class)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        element_type: str,
    ) -> FunctionComplexity | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node  # use full node for scanning

        increments: list[ComplexityIncrement] = []
        self._walk_js_complexity(body, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type="method" if in_class else element_type,
        )

    def _analyze_js_arrow(
        self, node: tree_sitter.Node, content: bytes
    ) -> FunctionComplexity | None:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        increments: list[ComplexityIncrement] = []
        self._walk_js_complexity(body, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name="<arrow>",
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type="arrow_function",
        )

    def _walk_js_complexity(
        self,
        node: tree_sitter.Node,
        content: bytes,
        nesting: int,
        increments: list[ComplexityIncrement],
    ) -> None:
        if node.type == "try_statement":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"try at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type in {"catch_clause", "finally_clause"}:
                    self._walk_js_complexity(child, content, nesting, increments)
                else:
                    self._walk_js_complexity(child, content, nesting + 1, increments)
            return

        if node.type in self._JS_NESTING:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"{node.type} at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                self._walk_js_complexity(child, content, nesting + 1, increments)
            return

        if node.type in self._JS_FLAT:
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="flat",
                    line_number=line,
                    value=1,
                    description=f"{node.type} at line {line} (+1)",
                )
            )
            for child in node.children:
                self._walk_js_complexity(child, content, nesting, increments)
            return

        # binary_expression with && or ||
        if node.type == "binary_expression":
            op = node.child_by_field_name("operator")
            if op is not None:
                op_text = content[op.start_byte:op.end_byte].decode(
                    "utf-8", errors="replace"
                )
                if op_text in {"&&", "||"}:
                    self._handle_js_logical_ops(node, content, increments)
                    return

        # ternary_expression
        if node.type == "ternary_expression":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"ternary at line {line} (+{inc_value})",
                )
            )
            return

        for child in node.children:
            self._walk_js_complexity(child, content, nesting, increments)

    def _handle_js_logical_ops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        increments: list[ComplexityIncrement],
    ) -> None:
        ops = self._collect_js_logical_ops(node, content)
        if not ops:
            return

        prev_op: str | None = None
        first = True
        for op_text, line in ops:
            if first:
                increments.append(
                    ComplexityIncrement(
                        increment_type="logical_op",
                        line_number=line,
                        value=1,
                        description=f"{op_text} at line {line} (+1)",
                    )
                )
                prev_op = op_text
                first = False
            elif op_text != prev_op:
                increments.append(
                    ComplexityIncrement(
                        increment_type="logical_op",
                        line_number=line,
                        value=1,
                        description=f"{op_text} at line {line} (+1)",
                    )
                )
                prev_op = op_text

        # Still walk left/right for non-logical binary expressions
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left and left.type not in {"binary_expression"}:
            pass  # leaf handled
        if right and right.type not in {"binary_expression"}:
            pass

    def _collect_js_logical_ops(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[tuple[str, int]]:
        result: list[tuple[str, int]] = []
        if node.type != "binary_expression":
            return result

        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op = node.child_by_field_name("operator")

        if left and left.type == "binary_expression":
            result.extend(self._collect_js_logical_ops(left, content))

        if op is not None:
            op_text = content[op.start_byte:op.end_byte].decode(
                "utf-8", errors="replace"
            )
            if op_text in {"&&", "||"}:
                line = op.start_point[0] + 1
                result.append((op_text, line))

        if right and right.type == "binary_expression":
            result.extend(self._collect_js_logical_ops(right, content))

        return result

    # ── Java ─────────────────────────────────────────────────────────────

    _JAVA_NESTING: frozenset[str] = frozenset({
        "for_statement", "while_statement",
        "do_statement", "switch_expression",
        "try_with_resources_statement", "synchronized_statement",
    })

    _JAVA_FLAT: frozenset[str] = frozenset({
        "catch_clause", "finally_clause",
    })

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionComplexity]:
        results: list[FunctionComplexity] = []
        self._walk_java(root, content, file_path, results, in_class=False)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionComplexity],
        in_class: bool,
    ) -> None:
        if node.type in {"class_declaration", "interface_declaration",
                         "enum_declaration", "record_declaration"}:
            for child in node.children:
                self._walk_java(child, content, file_path, results, in_class=True)
            return

        if node.type == "method_declaration":
            fc = self._analyze_java_method(node, content, in_class)
            if fc is not None:
                results.append(fc)
            return

        if node.type == "constructor_declaration":
            fc = self._analyze_java_method(node, content, True, "<init>")
            if fc is not None:
                results.append(fc)
            return

        for child in node.children:
            self._walk_java(child, content, file_path, results, in_class)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        override_name: str | None = None,
    ) -> FunctionComplexity | None:
        if override_name:
            name = override_name
        else:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        increments: list[ComplexityIncrement] = []
        self._walk_java_complexity(body, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name=name,
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type="method" if in_class else "function",
        )

    def _walk_java_complexity(
        self,
        node: tree_sitter.Node,
        content: bytes,
        nesting: int,
        increments: list[ComplexityIncrement],
    ) -> None:
        # if_statement in Java: children are [if, (cond), block, else, block]
        # "else" is a bare keyword, not an else_clause
        if node.type == "if_statement":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"if_statement at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type == "else":
                    else_line = child.start_point[0] + 1
                    increments.append(
                        ComplexityIncrement(
                            increment_type="flat",
                            line_number=else_line,
                            value=1,
                            description=f"else at line {else_line} (+1)",
                        )
                    )
                else:
                    self._walk_java_complexity(child, content, nesting + 1, increments)
            return

        if node.type in {"try_statement", "try_with_resources_statement"}:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"try at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type in {"catch_clause", "finally_clause"}:
                    self._walk_java_complexity(child, content, nesting, increments)
                else:
                    self._walk_java_complexity(child, content, nesting + 1, increments)
            return

        if node.type in self._JAVA_NESTING:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"{node.type} at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                self._walk_java_complexity(child, content, nesting + 1, increments)
            return

        if node.type in self._JAVA_FLAT:
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="flat",
                    line_number=line,
                    value=1,
                    description=f"{node.type} at line {line} (+1)",
                )
            )
            for child in node.children:
                self._walk_java_complexity(child, content, nesting, increments)
            return

        # ternary_expression
        if node.type == "ternary_expression":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"ternary at line {line} (+{inc_value})",
                )
            )
            return

        # Binary expressions with && or ||
        if node.type == "binary_expression":
            for child in node.children:
                if child.type in {"&&", "||"}:
                    line = child.start_point[0] + 1
                    op_text = content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    increments.append(
                        ComplexityIncrement(
                            increment_type="logical_op",
                            line_number=line,
                            value=1,
                            description=f"{op_text} at line {line} (+1)",
                        )
                    )
                    break
            for child in node.children:
                self._walk_java_complexity(child, content, nesting, increments)
            return

        for child in node.children:
            self._walk_java_complexity(child, content, nesting, increments)

    # ── Go ───────────────────────────────────────────────────────────────

    _GO_NESTING: frozenset[str] = frozenset({
        "for_statement", "expression_switch_statement", "type_switch_statement",
        "select_statement",
    })

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionComplexity]:
        results: list[FunctionComplexity] = []
        self._walk_go(root, content, file_path, results)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionComplexity],
    ) -> None:
        if node.type == "function_declaration":
            fc = self._analyze_go_func(node, content, "function")
            if fc is not None:
                results.append(fc)
            return

        if node.type == "method_declaration":
            fc = self._analyze_go_func(node, content, "method")
            if fc is not None:
                results.append(fc)
            return

        for child in node.children:
            self._walk_go(child, content, file_path, results)

    def _analyze_go_func(
        self,
        node: tree_sitter.Node,
        content: bytes,
        element_type: str,
    ) -> FunctionComplexity | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        increments: list[ComplexityIncrement] = []
        self._walk_go_complexity(node, content, 0, increments)
        total = sum(i.value for i in increments)

        return FunctionComplexity(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            total_complexity=total,
            rating=_rating(total),
            increments=tuple(increments),
            element_type=element_type,
        )

    def _walk_go_complexity(
        self,
        node: tree_sitter.Node,
        content: bytes,
        nesting: int,
        increments: list[ComplexityIncrement],
    ) -> None:
        # Go if_statement: children are [if, condition, block, else, block]
        # "else" is a bare keyword, not an else_clause
        if node.type == "if_statement":
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"if_statement at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                if child.type == "else":
                    else_line = child.start_point[0] + 1
                    increments.append(
                        ComplexityIncrement(
                            increment_type="flat",
                            line_number=else_line,
                            value=1,
                            description=f"else at line {else_line} (+1)",
                        )
                    )
                else:
                    self._walk_go_complexity(child, content, nesting + 1, increments)
            return

        if node.type in self._GO_NESTING:
            inc_value = 1 + nesting
            line = node.start_point[0] + 1
            increments.append(
                ComplexityIncrement(
                    increment_type="nesting",
                    line_number=line,
                    value=inc_value,
                    description=f"{node.type} at line {line} (+{inc_value})",
                )
            )
            for child in node.children:
                self._walk_go_complexity(child, content, nesting + 1, increments)
            return

        # Binary expressions with && or ||
        if node.type == "binary_expression":
            for child in node.children:
                if child.type in {"&&", "||"}:
                    line = child.start_point[0] + 1
                    op_text = content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    increments.append(
                        ComplexityIncrement(
                            increment_type="logical_op",
                            line_number=line,
                            value=1,
                            description=f"{op_text} at line {line} (+1)",
                        )
                    )
                    break

        for child in node.children:
            self._walk_go_complexity(child, content, nesting, increments)
