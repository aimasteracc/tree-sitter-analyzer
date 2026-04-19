"""Hardcoded IP Address Detector.

Detects hardcoded IP addresses and port numbers that should be externalized:
  - hardcoded_ip: IP address literal in source code (medium)
  - hardcoded_port: Port number assigned to port-like variable (low)

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_HARDCODED_IP = "hardcoded_ip"
ISSUE_HARDCODED_PORT = "hardcoded_port"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_HARDCODED_IP: SEVERITY_MEDIUM,
    ISSUE_HARDCODED_PORT: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_HARDCODED_IP: "Hardcoded IP address — externalize to configuration or DNS",
    ISSUE_HARDCODED_PORT: "Hardcoded port number — externalize to configuration",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_HARDCODED_IP: "Move IP address to environment variable or config file.",
    ISSUE_HARDCODED_PORT: "Move port number to environment variable or config file.",
}

# IPv4 pattern (matches 0.0.0.0 to 255.255.255.255)
_IPV4_RE = re.compile(
    r"\b(?!0\.0\.0\.0\b)"
    r"(?!127\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)"
    r"(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"
)

# Port variable name patterns (case-insensitive)
_PORT_NAME_PATTERNS: frozenset[str] = frozenset({
    "port", "PORT", "Port",
    "db_port", "DB_PORT",
    "redis_port", "REDIS_PORT",
    "mysql_port", "MYSQL_PORT",
    "postgres_port", "POSTGRES_PORT",
    "server_port", "SERVER_PORT",
    "listen_port", "LISTEN_PORT",
    "http_port", "HTTP_PORT",
    "https_port", "HTTPS_PORT",
})

# Valid port range
_PORT_MIN = 1
_PORT_MAX = 65535

# Well-known ports to skip (these are obviously intentional)
_WELL_KNOWN_PORTS: frozenset[int] = frozenset({
    80, 443, 8080, 8443, 3000, 3001, 4000, 5000, 5500,
    8000, 8888, 9000, 9090, 5432, 3306, 6379, 27017,
})

# String literal node types per language
_STRING_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"string"}),
    ".js": frozenset({"string", "template_string"}),
    ".jsx": frozenset({"string", "template_string"}),
    ".ts": frozenset({"string", "template_string"}),
    ".tsx": frozenset({"string", "template_string"}),
    ".java": frozenset({"string_literal"}),
    ".go": frozenset({"interpreted_string_literal", "raw_string_literal"}),
}

# Integer literal node types per language
_INT_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"integer"}),
    ".js": frozenset({"number"}),
    ".jsx": frozenset({"number"}),
    ".ts": frozenset({"number"}),
    ".tsx": frozenset({"number"}),
    ".java": frozenset({"decimal_integer_literal", "octal_integer_literal", "hex_integer_literal"}),
    ".go": frozenset({"int_literal"}),
}

# Comment node types to skip
_COMMENT_NODE_TYPES: frozenset[str] = frozenset({
    "comment", "line_comment", "block_comment",
})

# Assignment node types per language
_ASSIGNMENT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"assignment"}),
    ".js": frozenset({"assignment_expression", "variable_declarator"}),
    ".jsx": frozenset({"assignment_expression", "variable_declarator"}),
    ".ts": frozenset({"assignment_expression", "variable_declarator"}),
    ".tsx": frozenset({"assignment_expression", "variable_declarator"}),
    ".java": frozenset({"variable_declarator"}),
    ".go": frozenset({"short_var_declaration", "assignment_statement"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _is_inside_comment(node: tree_sitter.Node) -> bool:
    """Check if a node is inside a comment."""
    current: tree_sitter.Node | None = node
    while current is not None:
        if current.type in _COMMENT_NODE_TYPES:
            return True
        current = current.parent
    return False


def _get_string_content(node: tree_sitter.Node, ext: str) -> str:
    """Extract the actual string content, stripping quotes."""
    text = _safe_text(node)
    if ext == ".py":
        # Python: strip quotes (single, double, triple, f-string, etc.)
        if text.startswith(('"""', "'''")):
            return text[3:-3]
        if text.startswith(('"', "'", "f'", 'f"', "r'", 'r"', "b'", 'b"')):
            return text[2:-1] if text[1] in "frbFRB" else text[1:-1]
        return text
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        if node.type == "template_string":
            # Strip backticks
            return text[1:-1] if text.startswith("`") else text
        # Strip quotes
        return text[1:-1] if text.startswith(('"', "'", "`")) else text
    if ext == ".java":
        return text[1:-1] if text.startswith('"') else text
    if ext == ".go":
        if node.type == "raw_string_literal":
            return text[1:-1] if text.startswith("`") else text
        return text[1:-1] if text.startswith('"') else text
    return text


def _is_port_assignment(node: tree_sitter.Node, ext: str) -> bool:
    """Check if an integer node is being assigned to a port-like variable."""
    parent = node.parent
    if parent is None:
        return False

    assignment_types = _ASSIGNMENT_TYPES.get(ext, frozenset())
    if parent.type not in assignment_types:
        return False

    # Get the variable name from the assignment
    if ext == ".py":
        left = parent.child_by_field_name("left")
        if left is not None and left.type == "identifier":
            return _safe_text(left) in _PORT_NAME_PATTERNS
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        if parent.type == "variable_declarator":
            name_node = parent.child_by_field_name("name")
            if name_node is not None:
                return _safe_text(name_node) in _PORT_NAME_PATTERNS
        if parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            if left is not None:
                return _safe_text(left) in _PORT_NAME_PATTERNS
    elif ext == ".java":
        name_node = parent.child_by_field_name("name")
        if name_node is not None:
            return _safe_text(name_node) in _PORT_NAME_PATTERNS
    elif ext == ".go":
        for child in parent.children:
            if child.type == "identifier":
                return _safe_text(child) in _PORT_NAME_PATTERNS
            if child.type == "expression_list":
                for gc in child.children:
                    if gc.type == "identifier":
                        return _safe_text(gc) in _PORT_NAME_PATTERNS

    return False


@dataclass(frozen=True)
class HardcodedIPResult:
    total_ips: int
    total_ports: int
    issues: tuple[HardcodedIPIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_ips": self.total_ips,
            "total_ports": self.total_ports,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


@dataclass(frozen=True)
class HardcodedIPIssue:
    line_number: int
    issue_type: str
    value: str
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "value": self.value,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


def _scan_for_ips(
    node: tree_sitter.Node,
    ext: str,
    string_types: frozenset[str],
    issues: list[HardcodedIPIssue],
    ip_count: list[int],
) -> None:
    """Walk AST and detect hardcoded IP addresses in string literals."""
    if _is_inside_comment(node):
        return

    if node.type in string_types:
        content = _get_string_content(node, ext)
        matches = _IPV4_RE.findall(content)
        for match in matches:
            # Validate octets
            octets = match.split(".")
            if all(0 <= int(o) <= 255 for o in octets):
                ip_count[0] += 1
                issues.append(HardcodedIPIssue(
                    line_number=node.start_point[0] + 1,
                    issue_type=ISSUE_HARDCODED_IP,
                    value=match,
                    severity=_SEVERITY_MAP[ISSUE_HARDCODED_IP],
                    description=_DESCRIPTIONS[ISSUE_HARDCODED_IP],
                ))

    for child in node.children:
        _scan_for_ips(child, ext, string_types, issues, ip_count)


def _scan_for_ports(
    node: tree_sitter.Node,
    ext: str,
    int_types: frozenset[str],
    issues: list[HardcodedIPIssue],
    port_count: list[int],
) -> None:
    """Walk AST and detect hardcoded port numbers."""
    if _is_inside_comment(node):
        return

    if node.type in int_types:
        text = _safe_text(node)
        try:
            # Parse integer (handle hex, octal, etc.)
            if text.startswith("0x") or text.startswith("0X"):
                value = int(text, 16)
            elif text.startswith("0") and len(text) > 1 and text[1:].isdigit():
                value = int(text, 8)
            else:
                value = int(text)
        except ValueError:
            value = 0

        if _PORT_MIN <= value <= _PORT_MAX and _is_port_assignment(node, ext):
            port_count[0] += 1
            issues.append(HardcodedIPIssue(
                line_number=node.start_point[0] + 1,
                issue_type=ISSUE_HARDCODED_PORT,
                value=str(value),
                severity=_SEVERITY_MAP[ISSUE_HARDCODED_PORT],
                description=_DESCRIPTIONS[ISSUE_HARDCODED_PORT],
            ))

    for child in node.children:
        _scan_for_ports(child, ext, int_types, issues, port_count)


class HardcodedIPAnalyzer(BaseAnalyzer):
    """Analyzes code for hardcoded IP addresses and port numbers."""

    def analyze_file(self, file_path: Path | str) -> HardcodedIPResult:
        path = Path(file_path)
        if not path.exists():
            return HardcodedIPResult(
                total_ips=0,
                total_ports=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return HardcodedIPResult(
                total_ips=0,
                total_ports=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> HardcodedIPResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return HardcodedIPResult(
                total_ips=0,
                total_ports=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        string_types = _STRING_NODE_TYPES.get(ext, frozenset())
        int_types = _INT_NODE_TYPES.get(ext, frozenset())

        issues: list[HardcodedIPIssue] = []
        ip_count: list[int] = [0]
        port_count: list[int] = [0]

        if string_types:
            _scan_for_ips(tree.root_node, ext, string_types, issues, ip_count)
        if int_types:
            _scan_for_ports(tree.root_node, ext, int_types, issues, port_count)

        return HardcodedIPResult(
            total_ips=ip_count[0],
            total_ports=port_count[0],
            issues=tuple(issues),
            file_path=str(path),
        )
