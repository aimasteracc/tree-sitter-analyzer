"""Debug Statement Detector.

Detects leftover debug output statements that should be removed:
  - debug_print: print/pprint/breakpoint calls (Python)
  - debug_log: console.log/debug/info/warn, debugger (JS/TS)
  - debug_println: System.out/err.println, printStackTrace (Java)
  - debug_formatter: fmt.Println/Printf, log.Println (Go)

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_DEBUG_PRINT = "debug_print"
ISSUE_DEBUG_LOG = "debug_log"
ISSUE_DEBUG_PRINTLN = "debug_println"
ISSUE_DEBUG_FORMATTER = "debug_formatter"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_DEBUG_PRINT: SEVERITY_MEDIUM,
    ISSUE_DEBUG_LOG: SEVERITY_MEDIUM,
    ISSUE_DEBUG_PRINTLN: SEVERITY_MEDIUM,
    ISSUE_DEBUG_FORMATTER: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_DEBUG_PRINT: "Debug print statement — remove before production",
    ISSUE_DEBUG_LOG: "Debug console output — remove before production",
    ISSUE_DEBUG_PRINTLN: "Debug print statement — remove before production",
    ISSUE_DEBUG_FORMATTER: "Debug format print — remove before production",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_DEBUG_PRINT: "Remove print() call or replace with proper logging.",
    ISSUE_DEBUG_LOG: "Remove console.* call or debugger statement.",
    ISSUE_DEBUG_PRINTLN: "Remove System.out.println() or use proper logger.",
    ISSUE_DEBUG_FORMATTER: "Remove fmt.Print* call or use structured logging.",
}

# Python debug functions
_PYTHON_DEBUG_FUNCTIONS: frozenset[str] = frozenset({
    "print", "pprint", "breakpoint", "pprint.pprint",
})

# JS/TS debug patterns
_JS_DEBUG_OBJECTS: frozenset[str] = frozenset({"console"})
_JS_DEBUG_METHODS: frozenset[str] = frozenset({
    "log", "debug", "info", "warn", "dir", "table", "trace",
})

# Java debug patterns
_JAVA_DEBUG_CLASSES: frozenset[str] = frozenset({"System"})
_JAVA_DEBUG_OUT_METHODS: frozenset[str] = frozenset({"println", "printf", "print"})
_JAVA_DEBUG_ERR_METHODS: frozenset[str] = frozenset({"println", "printf", "print"})
_JAVA_DEBUG_EXTRA: frozenset[str] = frozenset({"printStackTrace"})

# Go debug functions
_GO_DEBUG_FUNCTIONS: frozenset[str] = frozenset({
    "Println", "Printf", "Print", "Fprintf", "Fprint", "Fprintln",
})
_GO_DEBUG_PACKAGES: frozenset[str] = frozenset({"fmt", "log"})


@dataclass(frozen=True)
class DebugStatement:
    """A detected debug statement."""

    line: int
    issue_type: str
    function_name: str
    severity: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "function_name": self.function_name,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class DebugStatementResult:
    """Result of debug statement analysis."""

    file_path: str
    statements: tuple[DebugStatement, ...]
    total_count: int
    by_type: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "statements": [s.to_dict() for s in self.statements],
            "total_count": self.total_count,
            "by_type": self.by_type,
        }


class DebugStatementDetector(BaseAnalyzer):
    """Detects leftover debug output statements in source code."""

    def analyze_file(self, file_path: str) -> DebugStatementResult:
        result = self._check_file(file_path)
        if not result:
            return DebugStatementResult(
                file_path=file_path,
                statements=(),
                total_count=0,
                by_type={},
            )
        path, ext = result

        try:
            lang, parser = self._get_parser(ext)
        except (ValueError, RuntimeError):
            return DebugStatementResult(
                file_path=file_path,
                statements=(),
                total_count=0,
                by_type={},
            )

        if parser is None:
            return DebugStatementResult(
                file_path=file_path,
                statements=(),
                total_count=0,
                by_type={},
            )

        source = Path(path).read_bytes()
        tree = parser.parse(source)
        root = tree.root_node

        extractors: dict[str, Callable[[tree_sitter.Node, str], list[DebugStatement]]] = {
            ".py": self._extract_python,
            ".js": self._extract_js,
            ".ts": self._extract_js,
            ".tsx": self._extract_js,
            ".jsx": self._extract_js,
            ".java": self._extract_java,
            ".go": self._extract_go,
        }

        extractor = extractors.get(ext)
        if not extractor:
            return DebugStatementResult(
                file_path=file_path,
                statements=(),
                total_count=0,
                by_type={},
            )

        statements = extractor(root, source.decode("utf-8", errors="replace"))
        by_type: dict[str, int] = {}
        for s in statements:
            by_type[s.issue_type] = by_type.get(s.issue_type, 0) + 1

        return DebugStatementResult(
            file_path=file_path,
            statements=tuple(statements),
            total_count=len(statements),
            by_type=by_type,
        )

    def _extract_python(
        self, root: tree_sitter.Node, source: str
    ) -> list[DebugStatement]:
        results: list[DebugStatement] = []
        self._walk_python(root, source, results)
        return results

    def _walk_python(
        self, node: tree_sitter.Node, source: str, results: list[DebugStatement]
    ) -> None:
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func:
                name = source[func.start_byte:func.end_byte]
                # Handle both "print" and "pprint.pprint"
                base_name = name.split("(")[0].strip()
                if base_name in _PYTHON_DEBUG_FUNCTIONS:
                    results.append(DebugStatement(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_DEBUG_PRINT,
                        function_name=base_name,
                        severity=_SEVERITY_MAP[ISSUE_DEBUG_PRINT],
                        message=_DESCRIPTIONS[ISSUE_DEBUG_PRINT],
                        suggestion=_SUGGESTIONS[ISSUE_DEBUG_PRINT],
                    ))
        for child in node.children:
            self._walk_python(child, source, results)

    def _extract_js(
        self, root: tree_sitter.Node, source: str
    ) -> list[DebugStatement]:
        results: list[DebugStatement] = []
        self._walk_js(root, source, results)
        return results

    def _walk_js(
        self, node: tree_sitter.Node, source: str, results: list[DebugStatement]
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "member_expression":
                obj = func.child_by_field_name("object")
                prop = func.child_by_field_name("property")
                if obj and prop:
                    obj_name = source[obj.start_byte:obj.end_byte]
                    method_name = source[prop.start_byte:prop.end_byte]
                    if obj_name in _JS_DEBUG_OBJECTS and method_name in _JS_DEBUG_METHODS:
                        results.append(DebugStatement(
                            line=node.start_point[0] + 1,
                            issue_type=ISSUE_DEBUG_LOG,
                            function_name=f"{obj_name}.{method_name}",
                            severity=_SEVERITY_MAP[ISSUE_DEBUG_LOG],
                            message=_DESCRIPTIONS[ISSUE_DEBUG_LOG],
                            suggestion=_SUGGESTIONS[ISSUE_DEBUG_LOG],
                        ))
        elif node.type == "debugger_statement":
            results.append(DebugStatement(
                line=node.start_point[0] + 1,
                issue_type=ISSUE_DEBUG_LOG,
                function_name="debugger",
                severity=SEVERITY_HIGH,
                message="Debugger statement — remove before production",
                suggestion="Remove debugger statement.",
            ))
        for child in node.children:
            self._walk_js(child, source, results)

    def _extract_java(
        self, root: tree_sitter.Node, source: str
    ) -> list[DebugStatement]:
        results: list[DebugStatement] = []
        self._walk_java(root, source, results)
        return results

    def _walk_java(
        self, node: tree_sitter.Node, source: str, results: list[DebugStatement]
    ) -> None:
        if node.type == "method_invocation":
            obj = node.child_by_field_name("object")
            method = node.child_by_field_name("name")
            if obj and method:
                method_text = source[method.start_byte:method.end_byte]
                is_debug = False
                func_name = ""

                if obj.type == "field_access":
                    inner_obj = obj.child_by_field_name("object")
                    inner_field = obj.child_by_field_name("field")
                    if inner_obj and inner_field:
                        root_obj = source[inner_obj.start_byte:inner_obj.end_byte]
                        mid_field = source[inner_field.start_byte:inner_field.end_byte]
                        if root_obj == "System":
                            if mid_field == "out" and method_text in _JAVA_DEBUG_OUT_METHODS:
                                is_debug = True
                                func_name = f"System.out.{method_text}"
                            elif mid_field == "err" and method_text in _JAVA_DEBUG_ERR_METHODS:
                                is_debug = True
                                func_name = f"System.err.{method_text}"
                # .printStackTrace()
                if not is_debug and method_text in _JAVA_DEBUG_EXTRA:
                    is_debug = True
                    func_name = f"{source[obj.start_byte:obj.end_byte]}.{method_text}"

                if is_debug:
                    results.append(DebugStatement(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_DEBUG_PRINTLN,
                        function_name=func_name,
                        severity=_SEVERITY_MAP[ISSUE_DEBUG_PRINTLN],
                        message=_DESCRIPTIONS[ISSUE_DEBUG_PRINTLN],
                        suggestion=_SUGGESTIONS[ISSUE_DEBUG_PRINTLN],
                    ))
        for child in node.children:
            self._walk_java(child, source, results)

    def _extract_go(
        self, root: tree_sitter.Node, source: str
    ) -> list[DebugStatement]:
        results: list[DebugStatement] = []
        self._walk_go(root, source, results)
        return results

    def _walk_go(
        self, node: tree_sitter.Node, source: str, results: list[DebugStatement]
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "selector_expression":
                operand = func.child_by_field_name("operand")
                field = func.child_by_field_name("field")
                if operand and field:
                    pkg_name = source[operand.start_byte:operand.end_byte]
                    func_name = source[field.start_byte:field.end_byte]
                    if pkg_name in _GO_DEBUG_PACKAGES and func_name in _GO_DEBUG_FUNCTIONS:
                        results.append(DebugStatement(
                            line=node.start_point[0] + 1,
                            issue_type=ISSUE_DEBUG_FORMATTER,
                            function_name=f"{pkg_name}.{func_name}",
                            severity=_SEVERITY_MAP[ISSUE_DEBUG_FORMATTER],
                            message=_DESCRIPTIONS[ISSUE_DEBUG_FORMATTER],
                            suggestion=_SUGGESTIONS[ISSUE_DEBUG_FORMATTER],
                        ))
        for child in node.children:
            self._walk_go(child, source, results)
