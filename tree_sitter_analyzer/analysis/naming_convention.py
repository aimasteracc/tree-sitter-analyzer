"""
Naming Convention Analyzer.

Detects identifiers that violate language naming conventions.
Provides a naming quality score and actionable suggestions.

Violations detected:
  - single_letter_var: single-letter variable name (except common loop vars)
  - inconsistent_style: mixed naming styles in same file
  - language_violation: violates language-specific conventions
  - upper_snake_not_const: UPPER_SNAKE used for non-constant values
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

VIOLATION_SINGLE_LETTER = "single_letter_var"
VIOLATION_INCONSISTENT = "inconsistent_style"
VIOLATION_LANGUAGE = "language_violation"
VIOLATION_UPPER_SNAKE = "upper_snake_not_const"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_VIOLATION_SEVERITY: dict[str, str] = {
    VIOLATION_SINGLE_LETTER: SEVERITY_MEDIUM,
    VIOLATION_INCONSISTENT: SEVERITY_MEDIUM,
    VIOLATION_LANGUAGE: SEVERITY_HIGH,
    VIOLATION_UPPER_SNAKE: SEVERITY_LOW,
}

_LOOP_VARS: frozenset[str] = frozenset({"i", "j", "k", "x", "y", "z", "n", "m", "_"})
_COMMON_SHORT: frozenset[str] = frozenset({"id", "db", "ip", "fp", "fn", "ex", "ok"})
_COMMON_NAMED: frozenset[str] = frozenset({"logger", "logging", "self", "cls", "super", "init", "main"})

# Naming style detection patterns
_RE_SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
_RE_LOWER = re.compile(r"^[a-z][a-z0-9]*$")
_RE_CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_RE_PASCAL = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_RE_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
_RE_SCREAMING = re.compile(r"^[A-Z][A-Z0-9_]*$")

STYLE_SNAKE = "snake_case"
STYLE_CAMEL = "camelCase"
STYLE_PASCAL = "PascalCase"
STYLE_UPPER_SNAKE = "UPPER_SNAKE"
STYLE_LOWER = "lowercase"
STYLE_UNKNOWN = "unknown"

# Per-language convention tables — supplements for languages without knowledge
_CONVENTION_SUPPLEMENT: dict[str, dict[str, str]] = {
    "typescript": {
        "function": STYLE_CAMEL,
        "method": STYLE_CAMEL,
        "variable": STYLE_CAMEL,
        "parameter": STYLE_CAMEL,
        "class": STYLE_PASCAL,
        "constant": STYLE_UPPER_SNAKE,
    },
}

# Node type supplements for extensions where knowledge is not yet available
_NODE_SUPPLEMENTS: dict[str, dict[str, frozenset[str]]] = {
    ".ts": {
        "func": frozenset({
            "function_declaration", "function", "arrow_function",
            "method_definition", "generator_function_declaration",
        }),
        "class": frozenset({"class_declaration", "class"}),
        "var": frozenset({
            "variable_declarator", "assignment_expression", "for_statement",
        }),
        "param": frozenset({
            "required_parameter", "optional_parameter", "rest_parameter",
            "assignment_pattern",
        }),
    },
    ".tsx": {
        "func": frozenset({
            "function_declaration", "function", "arrow_function",
            "method_definition", "generator_function_declaration",
        }),
        "class": frozenset({"class_declaration", "class"}),
        "var": frozenset({
            "variable_declarator", "assignment_expression", "for_statement",
        }),
        "param": frozenset({
            "required_parameter", "optional_parameter", "rest_parameter",
            "assignment_pattern",
        }),
    },
}

# Variable node types per language — not in knowledge protocol, kept local
_PY_VAR_NODES: frozenset[str] = frozenset({
    "assignment", "variable_declarator", "for_statement",
})
_JS_VAR_NODES: frozenset[str] = frozenset({
    "variable_declarator", "assignment_expression", "for_statement",
})
_JAVA_VAR_NODES: frozenset[str] = frozenset({
    "variable_declarator", "local_variable_declaration",
    "field_declaration",
})
_GO_VAR_NODES: frozenset[str] = frozenset({
    "var_spec", "short_var_declaration", "var_declaration",
})

_VAR_NODES: dict[str, frozenset[str]] = {
    ".py": _PY_VAR_NODES,
    ".js": _JS_VAR_NODES,
    ".jsx": _JS_VAR_NODES,
    ".ts": _JS_VAR_NODES,
    ".tsx": _JS_VAR_NODES,
    ".java": _JAVA_VAR_NODES,
    ".go": _GO_VAR_NODES,
}

def _detect_style(name: str) -> str:
    # Strip leading underscores for style detection
    stripped = name.lstrip("_")
    if not stripped:
        return STYLE_LOWER
    if _RE_UPPER_SNAKE.match(stripped) or _RE_SCREAMING.match(stripped):
        return STYLE_UPPER_SNAKE
    if _RE_PASCAL.match(stripped):
        return STYLE_PASCAL
    if _RE_SNAKE.match(stripped):
        return STYLE_SNAKE
    if _RE_LOWER.match(stripped):
        return STYLE_LOWER
    if _RE_CAMEL.match(stripped):
        return STYLE_CAMEL
    return STYLE_UNKNOWN

def _suggest_style(name: str, target_style: str) -> str | None:
    """Suggest a rename if the name doesn't match target style."""
    current = _detect_style(name)
    if current == target_style:
        return None
    if target_style == STYLE_SNAKE:
        parts = _split_identifier(name)
        return "_".join(p.lower() for p in parts)
    if target_style == STYLE_CAMEL:
        parts = _split_identifier(name)
        if not parts:
            return None
        return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
    if target_style == STYLE_PASCAL:
        parts = _split_identifier(name)
        return "".join(p.capitalize() for p in parts)
    return None

def _split_identifier(name: str) -> list[str]:
    """Split identifier into word parts."""
    if "_" in name and name == name.upper():
        return [p.lower() for p in name.split("_") if p]
    if "_" in name:
        snake_parts = name.split("_")
        return [p.lower() for p in snake_parts if p]
    parts: list[str] = []
    current = ""
    for ch in name:
        if ch.isupper() and current:
            parts.append(current)
            current = ch.lower()
        else:
            current += ch.lower()
    if current:
        parts.append(current)
    return parts

@dataclass(frozen=True)
class NamingViolation:
    name: str
    line_number: int
    element_type: str
    violation_type: str
    severity: str
    current_style: str
    expected_style: str
    suggestion: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "line_number": self.line_number,
            "element_type": self.element_type,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "current_style": self.current_style,
            "expected_style": self.expected_style,
            "suggestion": self.suggestion,
        }

@dataclass(frozen=True)
class StyleDistribution:
    style: str
    count: int
    percentage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "count": self.count,
            "percentage": round(self.percentage, 1),
        }

@dataclass(frozen=True)
class NamingResult:
    file_path: str
    language: str
    total_identifiers: int
    violations: tuple[NamingViolation, ...]
    naming_score: float
    style_distribution: tuple[StyleDistribution, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_identifiers": self.total_identifiers,
            "naming_score": round(self.naming_score, 1),
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "style_distribution": [s.to_dict() for s in self.style_distribution],
        }

    def get_high_severity(self) -> tuple[NamingViolation, ...]:
        return tuple(
            v for v in self.violations if v.severity == SEVERITY_HIGH
        )

class NamingConventionAnalyzer(BaseAnalyzer):
    """Analyzes naming conventions in source code files."""

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

    def analyze_file(self, file_path: Path | str) -> NamingResult:
        """Analyze naming conventions in a file."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            return NamingResult(
                file_path=str(path),
                language="unknown",
                total_identifiers=0,
                violations=(),
                naming_score=100.0,
                style_distribution=(),
            )

        language = self._detect_language(str(path))
        _, parser = self._get_parser(ext)
        if parser is None:
            return NamingResult(
                file_path=str(path),
                language=language,
                total_identifiers=0,
                violations=(),
                naming_score=100.0,
                style_distribution=(),
            )

        try:
            content = path.read_bytes()
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return NamingResult(
                file_path=str(path),
                language=language,
                total_identifiers=0,
                violations=(),
                naming_score=0.0,
                style_distribution=(),
            )

        tree = parser.parse(content)
        identifiers = self._extract_identifiers(tree.root_node, content, language, ext)
        violations = self._check_conventions(identifiers, ext, language)
        style_dist = self._compute_style_distribution(identifiers)
        score = self._compute_score(len(identifiers), len(violations))

        return NamingResult(
            file_path=str(path),
            language=language,
            total_identifiers=len(identifiers),
            violations=tuple(violations),
            naming_score=score,
            style_distribution=tuple(style_dist),
        )

    def _extract_identifiers(
        self,
        node: tree_sitter.Node,
        content: bytes,
        language: str,
        ext: str,
    ) -> list[dict[str, Any]]:
        """Extract named identifiers from AST."""
        identifiers: list[dict[str, Any]] = []

        if language == "python":
            self._walk_python(node, content, identifiers, ext)
        elif language in ("javascript", "typescript"):
            self._walk_js(node, content, identifiers, ext)
        elif language == "java":
            self._walk_java(node, content, identifiers, ext)
        elif language == "go":
            self._walk_go(node, content, identifiers, ext)

        return identifiers

    def _get_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str | None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        return content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        result: list[dict[str, Any]],
        ext: str,
    ) -> None:
        knowledge = self._get_knowledge(ext)
        func_nodes = knowledge.function_nodes
        class_nodes = knowledge.class_nodes
        for child in node.children:
            if child.type in func_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "function",
                    })
            elif child.type in class_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "class",
                    })
            elif child.type == "assignment":
                left = child.child_by_field_name("left")
                if left and left.type == "identifier":
                    name = content[left.start_byte:left.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "variable",
                    })
            elif child.type == "for_statement":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        name = content[
                            grandchild.start_byte:grandchild.end_byte
                        ].decode("utf-8", errors="replace")
                        result.append({
                            "name": name,
                            "line": child.start_point[0] + 1,
                            "element_type": "variable",
                        })
                        break

            if child.children:
                self._walk_python(child, content, result, ext)

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        result: list[dict[str, Any]],
        ext: str,
    ) -> None:
        knowledge = self._get_knowledge(ext)
        func_nodes = knowledge.function_nodes
        if not func_nodes:
            supplement = _NODE_SUPPLEMENTS.get(ext, {})
            func_nodes = supplement.get("func", frozenset())
        class_nodes = knowledge.class_nodes
        if not class_nodes:
            supplement = _NODE_SUPPLEMENTS.get(ext, {})
            class_nodes = supplement.get("class", frozenset())
        for child in node.children:
            if child.type in func_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "function",
                    })
            elif child.type in class_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "class",
                    })
            elif child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = content[
                        name_node.start_byte:name_node.end_byte
                    ].decode("utf-8", errors="replace")
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "variable",
                    })

            if child.children:
                self._walk_js(child, content, result, ext)

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        result: list[dict[str, Any]],
        ext: str,
    ) -> None:
        knowledge = self._get_knowledge(ext)
        func_nodes = knowledge.function_nodes
        class_nodes = knowledge.class_nodes
        for child in node.children:
            if child.type in func_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "method",
                    })
            elif child.type in class_nodes:
                name = self._get_name(child, content)
                if name:
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "class",
                    })
            elif child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = content[
                        name_node.start_byte:name_node.end_byte
                    ].decode("utf-8", errors="replace")
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": "variable",
                    })

            if child.children:
                self._walk_java(child, content, result, ext)

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        result: list[dict[str, Any]],
        ext: str,
    ) -> None:
        knowledge = self._get_knowledge(ext)
        func_nodes = knowledge.function_nodes
        for child in node.children:
            if child.type in func_nodes:
                name = self._get_name(child, content)
                if name:
                    # In Go, first letter case determines visibility
                    element = "function"
                    if child.type == "method_declaration":
                        element = "method"
                    result.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "element_type": element,
                    })
            elif child.type in _GO_VAR_NODES:
                for decl in child.children:
                    if decl.type == "assignment_statement":
                        for assign_child in decl.children:
                            if assign_child.type == "identifier":
                                name = content[
                                    assign_child.start_byte:assign_child.end_byte
                                ].decode("utf-8", errors="replace")
                                result.append({
                                    "name": name,
                                    "line": child.start_point[0] + 1,
                                    "element_type": "variable",
                                })
                                break

            if child.children:
                self._walk_go(child, content, result, ext)

    def _get_conventions(self, ext: str, language: str) -> dict[str, str]:
        """Get naming conventions from knowledge, falling back to supplement."""
        knowledge = self._get_knowledge(ext)
        conventions = knowledge.naming_conventions
        if conventions:
            return conventions
        return _CONVENTION_SUPPLEMENT.get(language, {})

    def _check_conventions(
        self,
        identifiers: list[dict[str, Any]],
        ext: str,
        language: str,
    ) -> list[NamingViolation]:
        violations: list[NamingViolation] = []
        conventions = self._get_conventions(ext, language)

        for ident in identifiers:
            name = ident["name"]
            line = ident["line"]
            element_type = ident["element_type"]
            current_style = _detect_style(name)

            # Check single letter vars
            if (
                len(name) == 1
                and name not in _LOOP_VARS
                and element_type not in ("class",)
            ):
                violations.append(NamingViolation(
                    name=name,
                    line_number=line,
                    element_type=element_type,
                    violation_type=VIOLATION_SINGLE_LETTER,
                    severity=_VIOLATION_SEVERITY[VIOLATION_SINGLE_LETTER],
                    current_style=current_style,
                    expected_style=conventions.get(element_type, STYLE_UNKNOWN),
                    suggestion=None,
                ))
                continue

            # Skip common short names and well-known identifiers
            if name.lower() in _COMMON_SHORT or name in _COMMON_NAMED:
                continue

            # Skip UPPER_SNAKE module-level names (constants)
            if current_style == STYLE_UPPER_SNAKE:
                continue

            # Check language convention
            expected = conventions.get(element_type)
            if expected and current_style != expected:
                # lowercase is compatible with snake_case (single-word names)
                if (
                    expected == STYLE_SNAKE
                    and current_style == STYLE_LOWER
                ):
                    continue
                suggestion = _suggest_style(name, expected)
                violations.append(NamingViolation(
                    name=name,
                    line_number=line,
                    element_type=element_type,
                    violation_type=VIOLATION_LANGUAGE,
                    severity=_VIOLATION_SEVERITY[VIOLATION_LANGUAGE],
                    current_style=current_style,
                    expected_style=expected,
                    suggestion=suggestion,
                ))

        return violations

    def _compute_style_distribution(
        self, identifiers: list[dict[str, Any]]
    ) -> list[StyleDistribution]:
        if not identifiers:
            return []

        style_counts: dict[str, int] = {}
        for ident in identifiers:
            style = _detect_style(ident["name"])
            style_counts[style] = style_counts.get(style, 0) + 1

        total = len(identifiers)
        return [
            StyleDistribution(
                style=style,
                count=count,
                percentage=(count / total) * 100,
            )
            for style, count in sorted(
                style_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]

    def _compute_score(
        self, total: int, violation_count: int
    ) -> float:
        if total == 0:
            return 100.0
        return max(0.0, (1.0 - violation_count / total) * 100.0)
