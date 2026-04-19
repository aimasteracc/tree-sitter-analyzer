"""
Null Safety Analyzer.

Detects potential None/null dereference risks in source code.
Identifies places where a nullable value is accessed without a
safety check: attribute access on potential None, dict bracket
access without key check, missing Optional validation, and
chained calls without null guards.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_UNCHECKED_ACCESS = "unchecked_access"
ISSUE_MISSING_NULL_CHECK = "missing_null_check"
ISSUE_CHAINED_ACCESS = "chained_access"
ISSUE_DICT_UNSAFE_ACCESS = "dict_unsafe_access"

def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""

@dataclass(frozen=True)
class NullSafetyIssue:
    """A single null safety issue found in code."""

    line: int
    issue_type: str
    severity: str
    variable: str
    description: str
    suggestion: str

@dataclass(frozen=True)
class NullSafetyResult:
    """Aggregated null safety analysis result for a file."""

    issues: tuple[NullSafetyIssue, ...]
    total_issues: int
    high_severity: int
    medium_severity: int
    low_severity: int
    file_path: str
    language: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_issues": self.total_issues,
            "high_severity": self.high_severity,
            "medium_severity": self.medium_severity,
            "low_severity": self.low_severity,
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "variable": i.variable,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }

def _empty_result(file_path: str, language: str) -> NullSafetyResult:
    return NullSafetyResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        low_severity=0,
        file_path=file_path,
        language=language,
    )

def _severity_counts(issues: tuple[NullSafetyIssue, ...]) -> tuple[int, int, int]:
    high = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
    medium = sum(1 for i in issues if i.severity == SEVERITY_MEDIUM)
    low = sum(1 for i in issues if i.severity == SEVERITY_LOW)
    return high, medium, low

class NullSafetyAnalyzer(BaseAnalyzer):
    """Analyzes source code for potential None/null dereference risks."""

    def analyze_file(self, file_path: Path | str) -> NullSafetyResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map: dict[str, str] = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        lang = language_map.get(ext, "unknown")

        content = path.read_bytes()
        text = content.decode("utf-8", errors="replace")

        if ext == ".py":
            issues = self._analyze_python(content, text)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(content, text)
        elif ext == ".java":
            issues = self._analyze_java(content, text)
        elif ext == ".go":
            issues = self._analyze_go(content, text)
        else:
            issues = []

        issue_tuple = tuple(issues)
        high, medium, low = _severity_counts(issue_tuple)
        return NullSafetyResult(
            issues=issue_tuple,
            total_issues=len(issue_tuple),
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            file_path=str(path),
            language=lang,
        )

    # ── Python analysis ────────────────────────────────────────────────────

    def _analyze_python(self, content: bytes, text: str) -> list[NullSafetyIssue]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[NullSafetyIssue] = []
        lines = text.splitlines()

        none_sources = self._find_python_none_sources(tree.root_node)
        null_checked = self._find_python_null_checks(tree.root_node)

        for var_name, line_num in none_sources.items():
            if var_name in null_checked:
                continue
            for idx in range(line_num, len(lines)):
                line = lines[idx]
                if re.search(rf"\b{re.escape(var_name)}\.\w+", line):
                    attr_match = re.search(
                        rf"\b{re.escape(var_name)}\.(\w+)", line
                    )
                    if attr_match:
                        issues.append(NullSafetyIssue(
                            line=idx + 1,
                            issue_type=ISSUE_UNCHECKED_ACCESS,
                            severity=SEVERITY_HIGH,
                            variable=var_name,
                            description=(
                                f"'{var_name}' may be None, accessed as "
                                f"'{var_name}.{attr_match.group(1)}'"
                            ),
                            suggestion=(
                                f"Add a None check before accessing: "
                                f"if {var_name} is not None: ..."
                            ),
                        ))
                    break

        issues.extend(self._find_python_dict_access(tree.root_node, lines))

        return issues

    def _find_python_none_sources(
        self, node: tree_sitter.Node
    ) -> dict[str, int]:
        sources: dict[str, int] = {}
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right:
                right_text = _txt(right).strip()
                left_text = _txt(left).strip()
                if right_text == "None" or right_text.startswith(".get("):
                    if left_text.isidentifier():
                        sources[left_text] = node.start_point[0] + 1
        if node.type == "default_parameter":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node:
                val_text = _txt(value_node).strip()
                if val_text == "None":
                    name_text = _txt(name_node)
                    sources[name_text] = node.start_point[0] + 1
        if node.type == "typed_parameter":
            for child in node.children:
                if child.type == "type" and "None" in _txt(child):
                    for sc in node.children:
                        if sc.type == "identifier":
                            sources[_txt(sc)] = node.start_point[0] + 1
        for child in node.children:
            sources.update(self._find_python_none_sources(child))
        return sources

    def _find_python_null_checks(
        self, node: tree_sitter.Node
    ) -> set[str]:
        checked: set[str] = set()
        if node.type == "if_statement":
            condition = node.child_by_field_name("condition")
            if condition:
                cond_text = _txt(condition)
                for m in re.finditer(r"(\w+)\s+is\s+not\s+None", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"(\w+)\s+is\s+None", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"if\s+(\w+)(?:\s*:|\s+and|\s+or|\))", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"isinstance\s*\(\s*(\w+)", cond_text):
                    checked.add(m.group(1))
        for child in node.children:
            checked.update(self._find_python_null_checks(child))
        return checked

    def _find_python_dict_access(
        self,
        node: tree_sitter.Node,
        lines: list[str],
    ) -> list[NullSafetyIssue]:
        issues: list[NullSafetyIssue] = []
        if node.type == "subscript":
            value_node = node.child_by_field_name("value")
            if value_node:
                value_text = _txt(value_node)
                parent_text = _txt(node.parent) if node.parent else ""
                is_get_call = ".get(" in parent_text
                if not is_get_call and re.match(r"^\w+$", value_text):
                    line_num = node.start_point[0] + 1
                    line_text = lines[line_num - 1] if line_num <= len(lines) else ""
                    if "in " + value_text not in line_text and (
                        f"{value_text}.get(" not in line_text
                    ):
                        issues.append(NullSafetyIssue(
                            line=line_num,
                            issue_type=ISSUE_DICT_UNSAFE_ACCESS,
                            severity=SEVERITY_MEDIUM,
                            variable=value_text,
                            description=(
                                f"Dict '{value_text}' accessed with [] "
                                f"instead of .get()"
                            ),
                            suggestion=(
                                f"Use {value_text}.get(key) or check "
                                f"'if key in {value_text}' first"
                            ),
                        ))
        for child in node.children:
            issues.extend(self._find_python_dict_access(child, lines))
        return issues

    # ── JavaScript/TypeScript analysis ─────────────────────────────────────

    def _analyze_javascript(
        self, content: bytes, text: str
    ) -> list[NullSafetyIssue]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[NullSafetyIssue] = []
        lines = text.splitlines()

        null_sources = self._find_js_null_sources(tree.root_node)
        null_checked = self._find_js_null_checks(tree.root_node)

        for var_name, line_num in null_sources.items():
            if var_name in null_checked:
                continue
            for idx in range(line_num - 1, len(lines)):
                line = lines[idx]
                dot_match = re.search(
                    rf"\b{re.escape(var_name)}\.(\w+)", line
                )
                optional_match = re.search(
                    rf"\b{re.escape(var_name)}\?\.", line
                )
                if dot_match and not optional_match:
                    issues.append(NullSafetyIssue(
                        line=idx + 1,
                        issue_type=ISSUE_UNCHECKED_ACCESS,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"'{var_name}' may be null/undefined, "
                            f"accessed as '{var_name}.{dot_match.group(1)}'"
                        ),
                        suggestion=(
                            f"Use optional chaining: "
                            f"{var_name}?.{dot_match.group(1)}"
                        ),
                    ))
                    break

        issues.extend(self._find_js_chained_access(tree.root_node))
        return issues

    def _find_js_null_sources(
        self, node: tree_sitter.Node
    ) -> dict[str, int]:
        sources: dict[str, int] = {}
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node:
                val_text = _txt(value_node).strip()
                name_text = _txt(name_node)
                if val_text in ("null", "undefined"):
                    if name_text.isidentifier():
                        sources[name_text] = node.start_point[0] + 1
        for child in node.children:
            sources.update(self._find_js_null_sources(child))
        return sources

    def _find_js_null_checks(
        self, node: tree_sitter.Node
    ) -> set[str]:
        checked: set[str] = set()
        if node.type == "if_statement":
            condition = node.child_by_field_name("condition")
            if condition:
                cond_text = _txt(condition)
                for m in re.finditer(r"(\w+)\s*!==?\s*(?:null|undefined)", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"(\w+)\s*==?\s*(?:null|undefined)", cond_text):
                    checked.add(m.group(1))
        for child in node.children:
            checked.update(self._find_js_null_checks(child))
        return checked

    def _find_js_chained_access(
        self,
        node: tree_sitter.Node,
    ) -> list[NullSafetyIssue]:
        issues: list[NullSafetyIssue] = []
        if node.type == "member_expression":
            obj_node = node.child_by_field_name("object")
            if obj_node and obj_node.type == "member_expression":
                obj_text = _txt(obj_node)
                full_text = _txt(node)
                if "?." not in full_text:
                    line_num = node.start_point[0] + 1
                    issues.append(NullSafetyIssue(
                        line=line_num,
                        issue_type=ISSUE_CHAINED_ACCESS,
                        severity=SEVERITY_MEDIUM,
                        variable=obj_text,
                        description=(
                            f"Chained access '{full_text}' without "
                            f"optional chaining"
                        ),
                        suggestion="Use ?. for safe chaining: obj?.prop?.method()",
                    ))
        for child in node.children:
            issues.extend(self._find_js_chained_access(child))
        return issues

    # ── Java analysis ──────────────────────────────────────────────────────

    def _analyze_java(self, content: bytes, text: str) -> list[NullSafetyIssue]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[NullSafetyIssue] = []
        lines = text.splitlines()

        null_sources = self._find_java_null_sources(tree.root_node)
        null_checked = self._find_java_null_checks(tree.root_node)

        for var_name, line_num in null_sources.items():
            if var_name in null_checked:
                continue
            for idx in range(line_num - 1, len(lines)):
                line = lines[idx]
                dot_match = re.search(
                    rf"\b{re.escape(var_name)}\.(\w+)", line
                )
                if dot_match and ".ifPresent(" not in line and ".orElse(" not in line:
                    issues.append(NullSafetyIssue(
                        line=idx + 1,
                        issue_type=ISSUE_UNCHECKED_ACCESS,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"'{var_name}' may be null, "
                            f"accessed as '{var_name}.{dot_match.group(1)}'"
                        ),
                        suggestion=(
                            f"Add null check: "
                            f"if ({var_name} != null) {{ ... }}"
                        ),
                    ))
                    break

        issues.extend(self._find_java_chained_access(tree.root_node))
        return issues

    def _find_java_null_sources(
        self, node: tree_sitter.Node
    ) -> dict[str, int]:
        sources: dict[str, int] = {}
        if node.type == "local_variable_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if name_node and value_node:
                        val_text = _txt(value_node).strip()
                        name_text = _txt(name_node)
                        if val_text == "null":
                            sources[name_text] = node.start_point[0] + 1
        for child in node.children:
            sources.update(self._find_java_null_sources(child))
        return sources

    def _find_java_null_checks(
        self, node: tree_sitter.Node
    ) -> set[str]:
        checked: set[str] = set()
        if node.type == "if_statement":
            condition = node.child_by_field_name("condition")
            if condition:
                cond_text = _txt(condition)
                for m in re.finditer(r"(\w+)\s*!=\s*null", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"(\w+)\s*==\s*null", cond_text):
                    checked.add(m.group(1))
        for child in node.children:
            checked.update(self._find_java_null_checks(child))
        return checked

    def _find_java_chained_access(
        self,
        node: tree_sitter.Node,
    ) -> list[NullSafetyIssue]:
        issues: list[NullSafetyIssue] = []
        if node.type == "method_invocation":
            for child in node.children:
                if child.type == "method_invocation":
                    obj_text = _txt(child)
                    full_text = _txt(node)
                    if "Optional" not in full_text:
                        line_num = node.start_point[0] + 1
                        issues.append(NullSafetyIssue(
                            line=line_num,
                            issue_type=ISSUE_CHAINED_ACCESS,
                            severity=SEVERITY_MEDIUM,
                            variable=obj_text,
                            description=(
                                f"Chained method call '{full_text}' "
                                f"without null guard"
                            ),
                            suggestion=(
                                "Break chain with null checks or use Optional"
                            ),
                        ))
                    break
        for child in node.children:
            issues.extend(self._find_java_chained_access(child))
        return issues

    # ── Go analysis ────────────────────────────────────────────────────────

    def _analyze_go(self, content: bytes, text: str) -> list[NullSafetyIssue]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[NullSafetyIssue] = []
        lines = text.splitlines()

        nil_sources = self._find_go_nil_sources(tree.root_node)
        nil_checked = self._find_go_nil_checks(tree.root_node)

        for var_name, line_num in nil_sources.items():
            if var_name in nil_checked:
                continue
            for idx in range(line_num - 1, len(lines)):
                line = lines[idx]
                deref_match = re.search(
                    rf"\*\s*{re.escape(var_name)}", line
                )
                if deref_match:
                    issues.append(NullSafetyIssue(
                        line=idx + 1,
                        issue_type=ISSUE_UNCHECKED_ACCESS,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"'{var_name}' may be nil, "
                            f"dereferenced with *"
                        ),
                        suggestion=(
                            f"Check before dereferencing: "
                            f"if {var_name} != nil {{ ... }}"
                        ),
                    ))
                    break
                call_match = re.search(
                    rf"\b{re.escape(var_name)}\.(\w+)\s*\(", line
                )
                if call_match:
                    issues.append(NullSafetyIssue(
                        line=idx + 1,
                        issue_type=ISSUE_MISSING_NULL_CHECK,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"'{var_name}' may be nil, "
                            f"method '{call_match.group(1)}' called"
                        ),
                        suggestion=(
                            f"Add nil check: "
                            f"if {var_name} != nil {{ {var_name}.{call_match.group(1)}() }}"
                        ),
                    ))
                    break

        issues.extend(self._find_go_map_access(tree.root_node, lines))
        return issues

    def _find_go_nil_sources(
        self, node: tree_sitter.Node
    ) -> dict[str, int]:
        sources: dict[str, int] = {}
        if node.type == "short_var_declaration":
            left_list = node.child_by_field_name("left")
            right_list = node.child_by_field_name("right")
            if left_list and right_list:
                right_text = _txt(right_list).strip()
                if right_text == "nil":
                    for child in left_list.children:
                        if child.type == "identifier":
                            sources[_txt(child)] = node.start_point[0] + 1
        elif node.type == "var_spec":
            name: str | None = None
            has_nil_value = False
            for child in node.children:
                if child.type == "identifier" and name is None:
                    name = _txt(child)
                elif child.type == "expression_list":
                    child_text = _txt(child).strip()
                    if child_text == "nil":
                        has_nil_value = True
                elif child.type == "nil":
                    has_nil_value = True
            if name and has_nil_value:
                sources[name] = node.start_point[0] + 1
        for child in node.children:
            sources.update(self._find_go_nil_sources(child))
        return sources

    def _find_go_nil_checks(
        self, node: tree_sitter.Node
    ) -> set[str]:
        checked: set[str] = set()
        if node.type == "if_statement":
            condition = node.child_by_field_name("condition")
            if condition:
                cond_text = _txt(condition)
                for m in re.finditer(r"(\w+)\s*!=\s*nil", cond_text):
                    checked.add(m.group(1))
                for m in re.finditer(r"(\w+)\s*==\s*nil", cond_text):
                    checked.add(m.group(1))
        for child in node.children:
            checked.update(self._find_go_nil_checks(child))
        return checked

    def _find_go_map_access(
        self,
        node: tree_sitter.Node,
        lines: list[str],
    ) -> list[NullSafetyIssue]:
        issues: list[NullSafetyIssue] = []
        if node.type == "index_expression":
            operand = node.child_by_field_name("operand")
            if operand:
                operand_text = _txt(operand)
                line_num = node.start_point[0] + 1
                line_text = lines[line_num - 1] if line_num <= len(lines) else ""
                has_comma_ok = ", ok" in line_text or ",ok" in line_text
                if not has_comma_ok and re.match(r"^\w+$", operand_text):
                    issues.append(NullSafetyIssue(
                        line=line_num,
                        issue_type=ISSUE_DICT_UNSAFE_ACCESS,
                        severity=SEVERITY_MEDIUM,
                        variable=operand_text,
                        description=(
                            f"Map '{operand_text}' accessed without "
                            f"comma-ok check"
                        ),
                        suggestion=(
                            f"Use comma-ok idiom: "
                            f"val, ok := {operand_text}[key]"
                        ),
                    ))
        for child in node.children:
            issues.extend(self._find_go_map_access(child, lines))
        return issues
