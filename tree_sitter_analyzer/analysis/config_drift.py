"""Configuration Drift Detector.

Detects module-level assignments where variable names match configuration
patterns (host, port, url, timeout, api_key, etc.) but are assigned
literal values instead of being read from environment variables.

Cross-references: when the same file also uses os.getenv/process.env/
System.getenv/os.Getenv, confidence is raised to "high".

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_INFO = "info"

ISSUE_HARDCODED_CONFIG = "hardcoded_config"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_HARDCODED_CONFIG: (
        "Configuration-like variable is assigned a literal value "
        "instead of being read from environment variables."
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_HARDCODED_CONFIG: (
        "Externalize this value using os.getenv() / process.env / "
        "System.getenv() / os.Getenv() and move the literal to a "
        ".env file or configuration service."
    ),
}

# Variable name patterns that suggest configuration.
# Matches whole words (case-insensitive) containing these substrings.
_CONFIG_PATTERNS = re.compile(
    r"(?i)"
    r"(?:^|_|[a-z])"
    r"(?:"
    r"host|port|url|uri|endpoint|timeout|retries?|retry"
    r"|api_?key|secret|db_?name|database|username|password"
    r"|token|base_?url|domain|region|bucket|queue|topic"
    r"|broker|redis|mysql|postgres|mongo|elastic|kafka"
    r"|rabbitmq|debug|log_?level|env|config"
    r"|access_?key|auth_?token|private_?key|public_?key"
    r"|server|service|client|connection|conn"
    r")"
    r"(?:_|$|[A-Z])",
)

# Literal value types per language
_LITERAL_TYPES: frozenset[str] = frozenset({
    "string", "string_literal", "number", "integer", "float",
    "true", "false", "boolean_literal",
    "decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
    "binary_integer_literal", "float_literal", "imaginary_literal",
    "int_literal", "raw_string_literal", "interpreted_string_literal",
    "character_literal",
})

# Environment variable call patterns per language
_ENV_CALL_PATTERNS: dict[str, frozenset[str]] = {
    ".py": frozenset({"os.getenv", "os.environ", "os.environ.get"}),
    ".js": frozenset({"process.env"}),
    ".jsx": frozenset({"process.env"}),
    ".ts": frozenset({"process.env"}),
    ".tsx": frozenset({"process.env"}),
    ".java": frozenset({"System.getenv"}),
    ".go": frozenset({"os.Getenv"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _is_config_name(name: str) -> bool:
    return bool(_CONFIG_PATTERNS.search(name))


def _is_literal_value(node: tree_sitter.Node) -> bool:
    if node.type in _LITERAL_TYPES:
        return True
    # Handle negative numbers: unary_operator wrapping a number
    if node.type in ("unary_operator", "prefix_expression"):
        for child in node.children:
            if child.type in _LITERAL_TYPES:
                return True
    return False


def _is_env_call(node: tree_sitter.Node, ext: str) -> bool:
    """Check if a node represents an environment variable access."""
    text = _safe_text(node)
    patterns = _ENV_CALL_PATTERNS.get(ext, frozenset())
    for pattern in patterns:
        if pattern in text:
            return True
    return False


def _file_has_env_usage(root: tree_sitter.Node, ext: str) -> bool:
    """Check if the file has any environment variable usage."""
    patterns = _ENV_CALL_PATTERNS.get(ext, frozenset())
    if not patterns:
        return False

    def visit(node: tree_sitter.Node) -> bool:
        text = _safe_text(node)
        for pattern in patterns:
            if pattern in text:
                return True
        for child in node.children:
            if visit(child):
                return True
        return False

    return visit(root)


def _is_module_level(node: tree_sitter.Node) -> bool:
    """Check if a node is at module/top level (not inside a function/class)."""
    parent = node.parent
    while parent is not None:
        pt = parent.type
        # Python: function/class bodies
        if pt in (
            "function_definition", "class_definition", "decorated_definition",
            "method_definition", "lambda",
        ):
            return False
        # JS/TS: function/arrow bodies
        if pt in (
            "function_declaration", "function_expression", "arrow_function",
            "method_definition", "class_declaration", "class_body",
        ):
            return False
        # Java: method bodies
        if pt in ("method_declaration", "constructor_declaration", "lambda_expression"):
            return False
        # Go: func bodies
        if pt in ("function_declaration", "method_declaration", "func_literal"):
            return False
        parent = parent.parent
    return True


def _is_static_final_field(node: tree_sitter.Node) -> bool:
    """Check if a Java field_declaration has static final modifiers."""
    for child in node.children:
        if child.type == "modifiers":
            mods_text = _safe_text(child)
            if "static" in mods_text and "final" in mods_text:
                return True
    return False


@dataclass(frozen=True)
class ConfigDriftIssue:
    line_number: int
    issue_type: str
    variable_name: str
    literal_value: str
    confidence: str
    severity: str

    @property
    def description(self) -> str:
        return _DESCRIPTIONS.get(self.issue_type, "")

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "variable_name": self.variable_name,
            "literal_value": self.literal_value,
            "confidence": self.confidence,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ConfigDriftResult:
    total_assignments: int
    issues: tuple[ConfigDriftIssue, ...]
    file_path: str

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_assignments": self.total_assignments,
            "issue_count": self.issue_count,
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


class ConfigDriftAnalyzer(BaseAnalyzer):
    """Detects hardcoded configuration values that should be externalized."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: Path | str) -> ConfigDriftResult:
        path = Path(file_path)
        if not path.exists():
            return ConfigDriftResult(
                total_assignments=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ConfigDriftResult(
                total_assignments=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> ConfigDriftResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ConfigDriftResult(
                total_assignments=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)
        root = tree.root_node

        has_env = _file_has_env_usage(root, ext)
        issues: list[ConfigDriftIssue] = []
        total = 0

        if ext == ".py":
            total, issues = self._scan_python(root, has_env)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            total, issues = self._scan_js(root, has_env)
        elif ext == ".java":
            total, issues = self._scan_java(root, has_env)
        elif ext == ".go":
            total, issues = self._scan_go(root, has_env)

        return ConfigDriftResult(
            total_assignments=total,
            issues=tuple(issues),
            file_path=str(path),
        )

    def _scan_python(
        self, root: tree_sitter.Node, has_env: bool,
    ) -> tuple[int, list[ConfigDriftIssue]]:
        total = 0
        issues: list[ConfigDriftIssue] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            if node.type == "assignment":
                total += 1
                self._check_python_assignment(node, has_env, issues)
            for child in node.children:
                visit(child)

        visit(root)
        return total, issues

    def _check_python_assignment(
        self,
        node: tree_sitter.Node,
        has_env: bool,
        issues: list[ConfigDriftIssue],
    ) -> None:
        if not _is_module_level(node):
            return

        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            return

        # Skip augmented assignments (+=, etc.)
        for child in node.children:
            if child.type in ("+=", "-=", "*=", "/="):
                return

        name = _safe_text(left).strip()
        if not _is_config_name(name):
            return

        # Skip if right side is a function call
        if right.type == "call":
            return
        if right.type == "attribute" and _is_env_call(right, ".py"):
            return

        if not _is_literal_value(right):
            return

        confidence = "high" if has_env else "low"
        issues.append(ConfigDriftIssue(
            line_number=node.start_point[0] + 1,
            issue_type=ISSUE_HARDCODED_CONFIG,
            variable_name=name,
            literal_value=_safe_text(right),
            confidence=confidence,
            severity=SEVERITY_INFO,
        ))

    def _scan_js(
        self, root: tree_sitter.Node, has_env: bool,
    ) -> tuple[int, list[ConfigDriftIssue]]:
        total = 0
        issues: list[ConfigDriftIssue] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            if node.type == "variable_declarator":
                total += 1
                self._check_js_declarator(node, has_env, issues)
            for child in node.children:
                visit(child)

        visit(root)
        return total, issues

    def _check_js_declarator(
        self,
        node: tree_sitter.Node,
        has_env: bool,
        issues: list[ConfigDriftIssue],
    ) -> None:
        if not _is_module_level(node):
            return

        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if name_node is None or value_node is None:
            return

        name = _safe_text(name_node).strip()
        if not _is_config_name(name):
            return

        if value_node.type == "call":
            return
        if value_node.type == "member_expression" and _is_env_call(value_node, ".js"):
            return

        if not _is_literal_value(value_node):
            return

        confidence = "high" if has_env else "low"
        issues.append(ConfigDriftIssue(
            line_number=node.start_point[0] + 1,
            issue_type=ISSUE_HARDCODED_CONFIG,
            variable_name=name,
            literal_value=_safe_text(value_node),
            confidence=confidence,
            severity=SEVERITY_INFO,
        ))

    def _scan_java(
        self, root: tree_sitter.Node, has_env: bool,
    ) -> tuple[int, list[ConfigDriftIssue]]:
        total = 0
        issues: list[ConfigDriftIssue] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            if node.type == "field_declaration":
                total += 1
                self._check_java_field(node, has_env, issues)
            for child in node.children:
                visit(child)

        visit(root)
        return total, issues

    def _check_java_field(
        self,
        node: tree_sitter.Node,
        has_env: bool,
        issues: list[ConfigDriftIssue],
    ) -> None:
        if not _is_static_final_field(node):
            return

        declarator = None
        for child in node.children:
            if child.type == "variable_declarator":
                declarator = child
                break
        if declarator is None:
            return

        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if name_node is None or value_node is None:
            return

        name = _safe_text(name_node).strip()
        if not _is_config_name(name):
            return

        if value_node.type == "method_invocation":
            return

        if not _is_literal_value(value_node):
            return

        confidence = "high" if has_env else "low"
        issues.append(ConfigDriftIssue(
            line_number=node.start_point[0] + 1,
            issue_type=ISSUE_HARDCODED_CONFIG,
            variable_name=name,
            literal_value=_safe_text(value_node),
            confidence=confidence,
            severity=SEVERITY_INFO,
        ))

    def _scan_go(
        self, root: tree_sitter.Node, has_env: bool,
    ) -> tuple[int, list[ConfigDriftIssue]]:
        total = 0
        issues: list[ConfigDriftIssue] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            if node.type == "const_declaration":
                total += 1
                self._check_go_const(node, has_env, issues)
            for child in node.children:
                visit(child)

        visit(root)
        return total, issues

    def _check_go_const(
        self,
        node: tree_sitter.Node,
        has_env: bool,
        issues: list[ConfigDriftIssue],
    ) -> None:
        for child in node.children:
            if child.type == "const_spec":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node is None or value_node is None:
                    continue

                name = _safe_text(name_node).strip()
                if not _is_config_name(name):
                    continue

                # Go wraps values in expression_list
                actual_value = value_node
                if value_node.type == "expression_list":
                    inner = [c for c in value_node.children if c.is_named]
                    if inner:
                        actual_value = inner[0]

                if not _is_literal_value(actual_value):
                    continue

                confidence = "high" if has_env else "low"
                issues.append(ConfigDriftIssue(
                    line_number=node.start_point[0] + 1,
                    issue_type=ISSUE_HARDCODED_CONFIG,
                    variable_name=name,
                    literal_value=_safe_text(actual_value),
                    confidence=confidence,
                    severity=SEVERITY_INFO,
                ))
