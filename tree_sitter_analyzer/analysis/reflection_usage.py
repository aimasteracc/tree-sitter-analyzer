"""Reflection Usage Detector.

Detects reflection and dynamic code execution patterns that make code
hard to audit, test, and secure.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_DYNAMIC_EXEC = "dynamic_execution"
ISSUE_DYNAMIC_ACCESS = "dynamic_access"
ISSUE_REFLECTION = "reflection"

_PY_EXEC_FUNCTIONS = frozenset({"eval", "exec", "compile"})
_PY_ACCESS_FUNCTIONS = frozenset({"getattr", "setattr", "delattr", "hasattr"})
_PY_IMPORT = "__import__"

_JS_EXEC_FUNCTIONS = frozenset({"eval"})
_JS_DYNAMIC_CONSTRUCTOR = frozenset({"Function"})

_JAVA_REFLECTION_METHODS = frozenset({
    "forName", "newInstance", "invoke",
    "getDeclaredMethod", "getDeclaredField", "setAccessible",
})

_GO_REFLECT_FUNCTIONS = frozenset({
    "DeepEqual", "ValueOf", "TypeOf", "MakeFunc",
    "New", "Zero", "SliceOf", "PtrTo",
})


@dataclass(frozen=True)
class ReflectionFinding:
    issue_type: str
    name: str
    line: int
    severity: str
    description: str
    suggestion: str


@dataclass
class ReflectionResult:
    file_path: str
    findings: list[ReflectionFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_findings": len(self.findings),
            "high_severity": sum(
                1 for f in self.findings if f.severity == SEVERITY_HIGH
            ),
            "findings": [
                {
                    "issue_type": f.issue_type,
                    "name": f.name,
                    "line": f.line,
                    "severity": f.severity,
                    "description": f.description,
                    "suggestion": f.suggestion,
                }
                for f in self.findings
            ],
        }


class ReflectionUsageAnalyzer(BaseAnalyzer):
    """Detects reflection and dynamic code execution patterns."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: str) -> ReflectionResult:
        path = Path(file_path)
        if not path.exists():
            return ReflectionResult(file_path=file_path)

        extension = path.suffix
        if extension not in self.SUPPORTED_EXTENSIONS:
            return ReflectionResult(file_path=file_path)

        language, parser = self._get_parser(extension)
        if language is None or parser is None:
            return ReflectionResult(file_path=file_path)

        source = path.read_bytes()
        tree = parser.parse(source)
        return self._analyze(tree, file_path, extension, source)

    def _analyze(
        self,
        tree: tree_sitter.Tree,
        file_path: str,
        extension: str,
        source: bytes,
    ) -> ReflectionResult:
        result = ReflectionResult(file_path=file_path)

        if extension == ".py":
            self._analyze_python(tree, source, result)
        elif extension in (".js", ".jsx", ".ts", ".tsx"):
            self._analyze_js_ts(tree, source, result)
        elif extension == ".java":
            self._analyze_java(tree, source, result)
        elif extension == ".go":
            self._analyze_go(tree, source, result)

        return result

    def _get_text(self, node: tree_sitter.Node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _add_finding(
        self,
        result: ReflectionResult,
        issue_type: str,
        name: str,
        line: int,
        severity: str,
        description: str,
        suggestion: str,
    ) -> None:
        result.findings.append(
            ReflectionFinding(
                issue_type=issue_type,
                name=name,
                line=line,
                severity=severity,
                description=description,
                suggestion=suggestion,
            )
        )

    def _analyze_python(
        self, tree: tree_sitter.Tree, source: bytes, result: ReflectionResult
    ) -> None:
        self._walk_python(tree.root_node, source, result)

    def _walk_python(
        self,
        node: tree_sitter.Node,
        source: bytes,
        result: ReflectionResult,
    ) -> None:
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func is not None:
                name = self._get_text(func, source)
                line = node.start_point[0] + 1
                if name in _PY_EXEC_FUNCTIONS:
                    self._add_finding(
                        result, ISSUE_DYNAMIC_EXEC, name, line,
                        SEVERITY_HIGH,
                        f"Dynamic code execution via {name}() is a security risk",
                        f"Replace {name}() with a safer alternative",
                    )
                elif name in _PY_ACCESS_FUNCTIONS:
                    self._add_finding(
                        result, ISSUE_DYNAMIC_ACCESS, name, line,
                        SEVERITY_MEDIUM,
                        f"Dynamic attribute access via {name}() hides dependencies",
                        "Use direct attribute access when possible",
                    )
                elif name == _PY_IMPORT:
                    self._add_finding(
                        result, ISSUE_DYNAMIC_EXEC, name, line,
                        SEVERITY_HIGH,
                        "Dynamic import via __import__() is hard to audit",
                        "Use static import statements",
                    )

        for child in node.children:
            self._walk_python(child, source, result)

    def _analyze_js_ts(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: ReflectionResult,
    ) -> None:
        self._walk_js_ts(tree.root_node, source, result)

    def _walk_js_ts(
        self,
        node: tree_sitter.Node,
        source: bytes,
        result: ReflectionResult,
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None:
                name = self._get_text(func, source)
                line = node.start_point[0] + 1
                if name == "eval":
                    self._add_finding(
                        result, ISSUE_DYNAMIC_EXEC, "eval", line,
                        SEVERITY_HIGH,
                        "eval() executes arbitrary code, major security risk",
                        "Use JSON.parse() for data, Function constructor only when necessary",
                    )

        if node.type == "new_expression":
            constructor = node.child_by_field_name("constructor")
            if constructor is not None:
                name = self._get_text(constructor, source)
                line = node.start_point[0] + 1
                if name == "Function":
                    self._add_finding(
                        result, ISSUE_DYNAMIC_EXEC, "new Function", line,
                        SEVERITY_HIGH,
                        "new Function() creates functions from strings at runtime",
                        "Use static function definitions",
                    )

        for child in node.children:
            self._walk_js_ts(child, source, result)

    def _analyze_java(
        self, tree: tree_sitter.Tree, source: bytes, result: ReflectionResult
    ) -> None:
        self._walk_java(tree.root_node, source, result)

    def _walk_java(
        self,
        node: tree_sitter.Node,
        source: bytes,
        result: ReflectionResult,
    ) -> None:
        if node.type == "method_invocation":
            obj = node.child_by_field_name("object")
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                method_name = self._get_text(name_node, source)
                line = node.start_point[0] + 1

                if method_name in _JAVA_REFLECTION_METHODS:
                    obj_text = self._get_text(obj, source) if obj is not None else ""
                    self._add_java_finding(result, method_name, obj_text, line)

        for child in node.children:
            self._walk_java(child, source, result)

    _JAVA_FINDINGS: dict[str, tuple[str, str, str, str]] = {
        "forName": (
            ISSUE_REFLECTION, SEVERITY_MEDIUM,
            "Reflection via Class.forName() bypasses compile-time checks",
            "Use direct class references when possible",
        ),
        "newInstance": (
            ISSUE_REFLECTION, SEVERITY_MEDIUM,
            "Reflection via newInstance() bypasses constructors",
            "Use standard constructor calls",
        ),
        "invoke": (
            ISSUE_REFLECTION, SEVERITY_MEDIUM,
            "Reflection via Method.invoke() is hard to audit",
            "Use direct method calls or interfaces",
        ),
        "getDeclaredMethod": (
            ISSUE_REFLECTION, SEVERITY_MEDIUM,
            "Accessing private methods via reflection breaks encapsulation",
            "Restructure to use public APIs",
        ),
        "getDeclaredField": (
            ISSUE_REFLECTION, SEVERITY_MEDIUM,
            "Accessing private fields via reflection breaks encapsulation",
            "Restructure to use public accessors",
        ),
        "setAccessible": (
            ISSUE_REFLECTION, SEVERITY_HIGH,
            "setAccessible(true) bypasses access controls",
            "Redesign to avoid needing private access",
        ),
    }

    def _add_java_finding(
        self,
        result: ReflectionResult,
        method_name: str,
        obj_text: str,
        line: int,
    ) -> None:
        entry = self._JAVA_FINDINGS.get(method_name)
        if entry is not None:
            issue_type, severity, desc, suggestion = entry
            display = f"{obj_text}.{method_name}" if obj_text else method_name
            self._add_finding(
                result, issue_type, display, line, severity, desc, suggestion,
            )

    def _analyze_go(
        self, tree: tree_sitter.Tree, source: bytes, result: ReflectionResult
    ) -> None:
        self._walk_go(tree.root_node, source, result)

    def _walk_go(
        self,
        node: tree_sitter.Node,
        source: bytes,
        result: ReflectionResult,
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None:
                func_text = self._get_text(func, source)
                line = node.start_point[0] + 1
                if func_text.startswith("reflect."):
                    method_name = func_text.split(".", 1)[1] if "." in func_text else ""
                    if method_name in _GO_REFLECT_FUNCTIONS:
                        self._add_finding(
                            result, ISSUE_REFLECTION, func_text, line,
                            SEVERITY_MEDIUM,
                            f"reflect.{method_name} uses runtime type inspection",
                            "Use type assertions or interfaces when possible",
                        )

        for child in node.children:
            self._walk_go(child, source, result)
