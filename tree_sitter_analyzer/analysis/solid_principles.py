"""
SOLID Principles Analyzer.

Detects violations of the 5 SOLID design principles:
  - SRP: Single Responsibility (classes doing too many things)
  - OCP: Open/Closed (type-checking dispatch instead of polymorphism)
  - LSP: Liskov Substitution (subclass signature mismatches)
  - ISP: Interface Segregation (fat interfaces with too many methods)
  - DIP: Dependency Inversion (depending on concrete classes)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# Violation types
SRP_VIOLATION = "srp_violation"
OCP_VIOLATION = "ocp_violation"
LSP_VIOLATION = "lsp_violation"
ISP_VIOLATION = "isp_violation"
DIP_VIOLATION = "dip_violation"

# Severity levels
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_VIOLATION_SEVERITY: dict[str, str] = {
    SRP_VIOLATION: SEVERITY_MEDIUM,
    OCP_VIOLATION: SEVERITY_HIGH,
    LSP_VIOLATION: SEVERITY_HIGH,
    ISP_VIOLATION: SEVERITY_MEDIUM,
    DIP_VIOLATION: SEVERITY_MEDIUM,
}

# SRP thresholds per language
_SRP_METHOD_THRESHOLD: dict[str, int] = {
    "python": 10,
    "javascript": 10,
    "typescript": 10,
    "java": 12,
    "go": 10,
}
_SRP_LINE_THRESHOLD: dict[str, int] = {
    "python": 300,
    "javascript": 300,
    "typescript": 300,
    "java": 400,
    "go": 300,
}

# ISP thresholds
_ISP_METHOD_THRESHOLD: dict[str, int] = {
    "python": 15,
    "javascript": 15,
    "typescript": 15,
    "java": 15,
    "go": 10,
}

# Node types for class detection
_PY_CLASS_NODES: frozenset[str] = frozenset({"class_definition"})
_JS_CLASS_NODES: frozenset[str] = frozenset({"class_declaration", "class"})
_JAVA_CLASS_NODES: frozenset[str] = frozenset({
    "class_declaration", "interface_declaration",
})
_JAVA_INTERFACE_NODES: frozenset[str] = frozenset({"interface_declaration"})
_GO_INTERFACE_NODES: frozenset[str] = frozenset({"interface_type"})

# Node types for method/function detection
_PY_METHOD_NODES: frozenset[str] = frozenset({
    "function_definition", "async_function_definition",
})
_JS_METHOD_NODES: frozenset[str] = frozenset({
    "method_definition", "function_declaration",
})
_JAVA_METHOD_NODES: frozenset[str] = frozenset({
    "method_declaration", "constructor_declaration",
})
_GO_METHOD_NODES: frozenset[str] = frozenset({
    "method_declaration", "function_declaration",
})

# OCP patterns — type-checking dispatch
_PY_TYPE_CHECK_PATTERNS: frozenset[str] = frozenset({
    "isinstance", "type(", "issubclass",
})
_JS_TYPE_CHECK_PATTERNS: frozenset[str] = frozenset({
    "typeof", "instanceof",
})
_JAVA_TYPE_CHECK_PATTERNS: frozenset[str] = frozenset({
    "instanceof",
})

# Abstract indicators for DIP
_PY_ABSTRACT_INDICATORS: frozenset[str] = frozenset({
    "ABC", "Protocol", "Abstract", "Interface", "Base",
})
_JAVA_ABSTRACT_INDICATORS: frozenset[str] = frozenset({
    "Interface", "Abstract", "Base",
})

@dataclass(frozen=True)
class SOLIDViolation:
    principle: str
    violation_type: str
    line_number: int
    element_name: str
    severity: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle": self.principle,
            "violation_type": self.violation_type,
            "line_number": self.line_number,
            "element_name": self.element_name,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }

@dataclass(frozen=True)
class PrincipleScore:
    principle: str
    score: float
    violation_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle": self.principle,
            "score": round(self.score, 1),
            "violation_count": self.violation_count,
        }

@dataclass(frozen=True)
class SOLIDResult:
    file_path: str
    language: str
    overall_score: float
    violations: tuple[SOLIDViolation, ...]
    principle_scores: tuple[PrincipleScore, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "overall_score": round(self.overall_score, 1),
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "principle_scores": [s.to_dict() for s in self.principle_scores],
        }

def _get_node_text(node: tree_sitter.Node, content: bytes) -> str:
    return content[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

def _get_name(
    node: tree_sitter.Node, content: bytes
) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return _get_node_text(name_node, content)

class SOLIDPrinciplesAnalyzer(BaseAnalyzer):
    """Analyzes SOLID principle violations in source code files."""

    def _detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        mapping: dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
        }
        return mapping.get(ext, "unknown")

    def analyze_file(self, file_path: Path | str) -> SOLIDResult:
        """Analyze SOLID principles in a file."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            return self._empty_result(str(path), "unknown")

        language = self._detect_language(str(path))
        _, parser = self._get_parser(ext)
        if parser is None:
            return self._empty_result(str(path), language)

        try:
            content = path.read_bytes()
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return self._empty_result(str(path), language)

        tree = parser.parse(content)
        violations = self._analyze(tree.root_node, content, language, str(path))
        return self._build_result(str(path), language, violations)

    def _empty_result(self, file_path: str, language: str) -> SOLIDResult:
        return SOLIDResult(
            file_path=file_path,
            language=language,
            overall_score=100.0,
            violations=(),
            principle_scores=tuple(
                PrincipleScore(p, 100.0, 0)
                for p in ("SRP", "OCP", "LSP", "ISP", "DIP")
            ),
        )

    def _build_result(
        self,
        file_path: str,
        language: str,
        violations: list[SOLIDViolation],
    ) -> SOLIDResult:
        principle_counts: dict[str, int] = {
            "SRP": 0, "OCP": 0, "LSP": 0, "ISP": 0, "DIP": 0,
        }
        for v in violations:
            principle_counts[v.principle] = principle_counts.get(v.principle, 0) + 1

        scores: list[PrincipleScore] = []
        for principle, count in principle_counts.items():
            score = max(0.0, 100.0 - count * 20.0)
            scores.append(PrincipleScore(principle, score, count))

        total = len(violations)
        overall = max(0.0, 100.0 - total * 8.0) if total > 0 else 100.0

        return SOLIDResult(
            file_path=file_path,
            language=language,
            overall_score=overall,
            violations=tuple(violations),
            principle_scores=tuple(scores),
        )

    def _analyze(
        self,
        root: tree_sitter.Node,
        content: bytes,
        language: str,
        file_path: str,
    ) -> list[SOLIDViolation]:
        violations: list[SOLIDViolation] = []

        if language == "python":
            self._analyze_python(root, content, violations)
        elif language in ("javascript", "typescript"):
            self._analyze_js(root, content, violations)
        elif language == "java":
            self._analyze_java(root, content, violations)
        elif language == "go":
            self._analyze_go(root, content, violations)

        return violations

    # ── Python Analysis ──

    def _analyze_python(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        classes = self._collect_python_classes(root, content)
        for cls in classes:
            self._check_srp_python(cls, content, violations)
            self._check_ocp_python(cls, content, violations)
            self._check_isp_python(cls, content, violations)
            self._check_lsp_python(cls, content, violations)
        self._check_dip_python(root, content, violations)

    def _collect_python_classes(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> list[tree_sitter.Node]:
        result: list[tree_sitter.Node] = []
        for child in node.children:
            if child.type in _PY_CLASS_NODES:
                result.append(child)
            if child.children:
                result.extend(self._collect_python_classes(child, content))
        return result

    def _check_srp_python(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(class_node, content) or "<anonymous>"
        methods = self._collect_methods(class_node, content, _PY_METHOD_NODES)
        class_lines = class_node.end_point[0] - class_node.start_point[0] + 1
        threshold = _SRP_METHOD_THRESHOLD["python"]
        line_threshold = _SRP_LINE_THRESHOLD["python"]

        if len(methods) > threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' has {len(methods)} methods (threshold: {threshold})",
                suggestion=f"Split '{name}' into smaller, focused classes",
            ))

        if class_lines > line_threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' is {class_lines} lines (threshold: {line_threshold})",
                suggestion=f"Extract responsibilities from '{name}' into separate classes",
            ))

    def _check_ocp_python(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        methods = self._collect_methods(class_node, content, _PY_METHOD_NODES)
        for child in methods:
            method_text = _get_node_text(child, content)
            for pattern in _PY_TYPE_CHECK_PATTERNS:
                if pattern in method_text:
                    method_name = _get_name(child, content) or "<method>"
                    violations.append(SOLIDViolation(
                        principle="OCP",
                        violation_type=OCP_VIOLATION,
                        line_number=child.start_point[0] + 1,
                        element_name=method_name,
                        severity=SEVERITY_HIGH,
                        message=(
                            f"Method '{method_name}' uses '{pattern}' "
                            f"for type-based dispatch"
                        ),
                        suggestion="Use polymorphism instead of type checking",
                    ))
                    break

    def _check_isp_python(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(class_node, content) or "<anonymous>"
        # Check bases from argument_list (Python's inheritance syntax)
        base_text = ""
        for child in class_node.children:
            if child.type == "argument_list":
                base_text = _get_node_text(child, content)
                break

        is_protocol = any(
            indicator in base_text for indicator in ("Protocol", "ABC", "abstractmethod")
        )
        if not is_protocol:
            return

        methods = self._collect_methods(class_node, content, _PY_METHOD_NODES)
        threshold = _ISP_METHOD_THRESHOLD["python"]
        if len(methods) > threshold:
            violations.append(SOLIDViolation(
                principle="ISP",
                violation_type=ISP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=(
                    f"Protocol/ABC '{name}' has {len(methods)} methods "
                    f"(threshold: {threshold})"
                ),
                suggestion=f"Split '{name}' into smaller, more focused protocols",
            ))

    def _check_lsp_python(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(class_node, content) or "<anonymous>"
        # Check for NotImplementedError raises in methods
        methods = self._collect_methods(class_node, content, _PY_METHOD_NODES)
        for method in methods:
            method_name = _get_name(method, content) or "<method>"
            self._check_lsp_method_python(method, method_name, name, content, violations)

    def _check_lsp_method_python(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        class_name: str,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        """Check for LSP violations in a Python method."""
        method_text = _get_node_text(method_node, content)

        if "NotImplementedError" in method_text:
            violations.append(SOLIDViolation(
                principle="LSP",
                violation_type=LSP_VIOLATION,
                line_number=method_node.start_point[0] + 1,
                element_name=method_name,
                severity=SEVERITY_HIGH,
                message=(
                    f"Method '{method_name}' raises NotImplementedError, "
                    f"violating LSP substitutability"
                ),
                suggestion="Provide a default implementation or redesign the hierarchy",
            ))

    def _check_dip_python(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        """Check for DIP violations — importing concrete classes."""
        imports = self._collect_python_imports(root, content)
        for imp in imports:
            module_name = imp["name"]
            line = imp["line"]
            # Skip stdlib and abstract indicators
            if any(
                indicator in module_name for indicator in _PY_ABSTRACT_INDICATORS
            ):
                continue
            # Flag imports of likely concrete implementation modules
            if any(suffix in module_name.lower() for suffix in (
                "impl", "concrete", "serviceimpl", "daoimpl",
            )):
                violations.append(SOLIDViolation(
                    principle="DIP",
                    violation_type=DIP_VIOLATION,
                    line_number=line,
                    element_name=module_name,
                    severity=SEVERITY_MEDIUM,
                    message=(
                        f"Importing concrete implementation '{module_name}'"
                    ),
                    suggestion="Depend on abstract interfaces instead of concrete implementations",
                ))

    def _collect_python_imports(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "import_statement":
                for sub in child.children:
                    if sub.type in ("dotted_name", "identifier"):
                        name = _get_node_text(sub, content)
                        result.append({"name": name, "line": child.start_point[0] + 1})
            elif child.type == "import_from_statement":
                module = child.child_by_field_name("module_name")
                if module:
                    name = _get_node_text(module, content)
                    result.append({"name": name, "line": child.start_point[0] + 1})
            if child.children:
                result.extend(self._collect_python_imports(child, content))
        return result

    # ── JavaScript/TypeScript Analysis ──

    def _analyze_js(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        classes = self._collect_nodes(root, _JS_CLASS_NODES)
        for cls in classes:
            self._check_srp_js(cls, content, violations)
            self._check_ocp_js(cls, content, violations)
        self._check_dip_js(root, content, violations)

    def _check_srp_js(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(class_node, content) or "<anonymous>"
        methods = self._collect_methods(class_node, content, _JS_METHOD_NODES)
        class_lines = class_node.end_point[0] - class_node.start_point[0] + 1
        lang = "javascript"
        threshold = _SRP_METHOD_THRESHOLD[lang]
        line_threshold = _SRP_LINE_THRESHOLD[lang]

        if len(methods) > threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' has {len(methods)} methods (threshold: {threshold})",
                suggestion=f"Split '{name}' into smaller, focused classes",
            ))

        if class_lines > line_threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' is {class_lines} lines (threshold: {line_threshold})",
                suggestion=f"Extract responsibilities from '{name}' into separate classes",
            ))

    def _check_ocp_js(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        methods = self._collect_methods(class_node, content, _JS_METHOD_NODES)
        for child in methods:
            method_text = _get_node_text(child, content)
            for pattern in _JS_TYPE_CHECK_PATTERNS:
                if pattern in method_text:
                    method_name = _get_name(child, content) or "<method>"
                    violations.append(SOLIDViolation(
                        principle="OCP",
                        violation_type=OCP_VIOLATION,
                        line_number=child.start_point[0] + 1,
                        element_name=method_name,
                        severity=SEVERITY_HIGH,
                        message=(
                            f"Method '{method_name}' uses '{pattern}' "
                            f"for type-based dispatch"
                        ),
                        suggestion="Use polymorphism instead of type checking",
                    ))
                    break

    def _check_dip_js(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        """Check for DIP violations in JS imports."""
        imports = self._collect_js_imports(root, content)
        for imp in imports:
            name = imp["name"]
            line = imp["line"]
            if any(suffix in name.lower() for suffix in (
                "impl", "concrete", "serviceimpl",
            )):
                violations.append(SOLIDViolation(
                    principle="DIP",
                    violation_type=DIP_VIOLATION,
                    line_number=line,
                    element_name=name,
                    severity=SEVERITY_MEDIUM,
                    message=f"Importing concrete implementation '{name}'",
                    suggestion="Depend on abstract interfaces instead",
                ))

    def _collect_js_imports(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "import_statement":
                source = child.child_by_field_name("source")
                if source:
                    name = _get_node_text(source, content).strip("'\"")
                    result.append({"name": name, "line": child.start_point[0] + 1})
            if child.children:
                result.extend(self._collect_js_imports(child, content))
        return result

    # ── Java Analysis ──

    def _analyze_java(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        classes = self._collect_nodes(root, _JAVA_CLASS_NODES)
        for cls in classes:
            self._check_srp_java(cls, content, violations)
            self._check_ocp_java(cls, content, violations)
        interfaces = self._collect_nodes(root, _JAVA_INTERFACE_NODES)
        for iface in interfaces:
            self._check_isp_java(iface, content, violations)
        self._check_dip_java(root, content, violations)

    def _check_srp_java(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(class_node, content) or "<anonymous>"
        methods = self._collect_methods(class_node, content, _JAVA_METHOD_NODES)
        class_lines = class_node.end_point[0] - class_node.start_point[0] + 1
        threshold = _SRP_METHOD_THRESHOLD["java"]
        line_threshold = _SRP_LINE_THRESHOLD["java"]

        if len(methods) > threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' has {len(methods)} methods (threshold: {threshold})",
                suggestion=f"Split '{name}' into smaller, focused classes",
            ))

        if class_lines > line_threshold:
            violations.append(SOLIDViolation(
                principle="SRP",
                violation_type=SRP_VIOLATION,
                line_number=class_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=f"Class '{name}' is {class_lines} lines (threshold: {line_threshold})",
                suggestion=f"Extract responsibilities from '{name}' into separate classes",
            ))

    def _check_ocp_java(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        methods = self._collect_methods(class_node, content, _JAVA_METHOD_NODES)
        for child in methods:
            method_text = _get_node_text(child, content)
            if "instanceof" in method_text:
                method_name = _get_name(child, content) or "<method>"
                violations.append(SOLIDViolation(
                    principle="OCP",
                    violation_type=OCP_VIOLATION,
                    line_number=child.start_point[0] + 1,
                    element_name=method_name,
                    severity=SEVERITY_HIGH,
                    message=(
                        f"Method '{method_name}' uses 'instanceof' "
                        f"for type-based dispatch"
                    ),
                    suggestion="Use polymorphism and method overriding instead",
                ))

    def _check_isp_java(
        self,
        iface_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        name = _get_name(iface_node, content) or "<anonymous>"
        methods = self._collect_methods(iface_node, content, frozenset({
            "method_declaration", "abstract_method_declaration",
            "interface_method_declaration",
        }))
        threshold = _ISP_METHOD_THRESHOLD["java"]
        if len(methods) > threshold:
            violations.append(SOLIDViolation(
                principle="ISP",
                violation_type=ISP_VIOLATION,
                line_number=iface_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=(
                    f"Interface '{name}' has {len(methods)} methods "
                    f"(threshold: {threshold})"
                ),
                suggestion=f"Split '{name}' into smaller, more focused interfaces",
            ))

    def _check_dip_java(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        imports = self._collect_java_imports(root, content)
        for imp in imports:
            name = imp["name"]
            line = imp["line"]
            if any(suffix in name.lower() for suffix in (
                "impl", "concrete", "serviceimpl", "daoimpl",
            )):
                violations.append(SOLIDViolation(
                    principle="DIP",
                    violation_type=DIP_VIOLATION,
                    line_number=line,
                    element_name=name,
                    severity=SEVERITY_MEDIUM,
                    message=f"Importing concrete implementation '{name}'",
                    suggestion="Depend on abstract interfaces instead",
                ))

    def _collect_java_imports(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "import_declaration":
                text = _get_node_text(child, content)
                name = text.replace("import ", "").replace(";", "").strip()
                result.append({"name": name, "line": child.start_point[0] + 1})
            if child.children:
                result.extend(self._collect_java_imports(child, content))
        return result

    # ── Go Analysis ──

    def _analyze_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        interfaces = self._collect_nodes(root, _GO_INTERFACE_NODES)
        for iface in interfaces:
            self._check_isp_go(iface, content, violations)
        self._check_ocp_go(root, content, violations)
        self._check_srp_go(root, content, violations)

    def _check_srp_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        """Check SRP for Go — group methods by receiver type."""
        receiver_methods: dict[str, list[tree_sitter.Node]] = {}
        for node in self._collect_nodes(root, _GO_METHOD_NODES):
            if node.type == "method_declaration":
                # First parameter_list is the receiver
                for child in node.children:
                    if child.type == "parameter_list":
                        recv_text = _get_node_text(child, content)
                        receiver_methods.setdefault(recv_text, []).append(node)
                        break

        threshold = _SRP_METHOD_THRESHOLD["go"]
        for recv, methods in receiver_methods.items():
            if len(methods) > threshold:
                violations.append(SOLIDViolation(
                    principle="SRP",
                    violation_type=SRP_VIOLATION,
                    line_number=methods[0].start_point[0] + 1,
                    element_name=recv,
                    severity=SEVERITY_MEDIUM,
                    message=(
                        f"Type '{recv}' has {len(methods)} methods "
                        f"(threshold: {threshold})"
                    ),
                    suggestion=f"Split '{recv}' into smaller types with focused responsibilities",
                ))

    def _check_ocp_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        """Check OCP for Go — type switch / type assertion dispatch."""
        type_switches = self._collect_nodes(root, frozenset({"type_switch_statement"}))
        for ts_node in type_switches:
            violations.append(SOLIDViolation(
                principle="OCP",
                violation_type=OCP_VIOLATION,
                line_number=ts_node.start_point[0] + 1,
                element_name="<type_switch>",
                severity=SEVERITY_HIGH,
                message="Type switch statement used for dispatch",
                suggestion="Use interface methods instead of type switches",
            ))

        type_asserts = self._collect_nodes(root, frozenset({"type_assertion"}))
        for ta_node in type_asserts:
            text = _get_node_text(ta_node, content)
            if ", ok" in text or "._(" in text:
                continue
            violations.append(SOLIDViolation(
                principle="OCP",
                violation_type=OCP_VIOLATION,
                line_number=ta_node.start_point[0] + 1,
                element_name="<type_assertion>",
                severity=SEVERITY_HIGH,
                message="Type assertion used for dispatch",
                suggestion="Use interface methods instead of type assertions",
            ))

    def _check_isp_go(
        self,
        iface_node: tree_sitter.Node,
        content: bytes,
        violations: list[SOLIDViolation],
    ) -> None:
        # interface_type has no name field; get name from parent type_spec
        name = "<anonymous>"
        parent = iface_node.parent
        if parent and parent.type == "type_spec":
            name_node = parent.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, content)

        method_count = 0
        for child in iface_node.children:
            if child.type == "method_elem":
                method_count += 1

        threshold = _ISP_METHOD_THRESHOLD["go"]
        if method_count > threshold:
            violations.append(SOLIDViolation(
                principle="ISP",
                violation_type=ISP_VIOLATION,
                line_number=iface_node.start_point[0] + 1,
                element_name=name,
                severity=SEVERITY_MEDIUM,
                message=(
                    f"Interface '{name}' has {method_count} methods "
                    f"(threshold: {threshold})"
                ),
                suggestion=f"Split '{name}' into smaller, more focused interfaces",
            ))

    # ── Shared Helpers ──

    def _collect_nodes(
        self,
        node: tree_sitter.Node,
        types: frozenset[str],
    ) -> list[tree_sitter.Node]:
        result: list[tree_sitter.Node] = []
        for child in node.children:
            if child.type in types:
                result.append(child)
            if child.children:
                result.extend(self._collect_nodes(child, types))
        return result

    def _collect_methods(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        method_types: frozenset[str],
    ) -> list[tree_sitter.Node]:
        methods: list[tree_sitter.Node] = []
        for child in class_node.children:
            if child.type in method_types:
                methods.append(child)
            elif child.type in ("block", "class_body", "declaration_list", "interface_body"):
                for grandchild in child.children:
                    if grandchild.type in method_types:
                        methods.append(grandchild)
        return methods
