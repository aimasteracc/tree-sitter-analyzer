"""Regex Safety / ReDoS Detector.

Finds regex patterns in source code that are vulnerable to catastrophic
backtracking (Regular Expression Denial of Service). Detects nested
quantifiers like (x+)+ and overlapping alternations that can cause
exponential time complexity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"


@dataclass(frozen=True)
class RegexVulnerability:
    """A regex pattern vulnerable to ReDoS."""

    line_number: int
    pattern: str
    vulnerability_type: str
    severity: str
    explanation: str


@dataclass(frozen=True)
class RegexSafetyResult:
    """Aggregated regex safety result for a file."""

    total_regex_patterns: int
    vulnerable_count: int
    vulnerabilities: tuple[RegexVulnerability, ...]
    file_path: str

    @property
    def is_safe(self) -> bool:
        return self.vulnerable_count == 0


# Node types that contain regex patterns per language
_PYTHON_REGEX_CALLS: frozenset[str] = frozenset({
    "re.compile", "re.match", "re.search", "re.fullmatch",
    "re.findall", "re.finditer", "re.sub", "re.subn",
    "re.split",
})

_PYTHON_CALL_NODE = "call"
_JS_REGEX_NODE = "regex"
_JS_NEW_EXPRESSION = "new_expression"
_JAVA_CALL_NODE = "method_invocation"
_GO_CALL_NODE = "call_expression"


def _check_nested_quantifiers(pattern: str) -> list[tuple[str, str, str]]:
    """Check regex string for nested quantifier patterns.

    Returns list of (vulnerability_type, severity, explanation).
    """
    issues: list[tuple[str, str, str]] = []

    depth = 0
    group_has_quantifier: list[bool] = []
    i = 0

    while i < len(pattern):
        c = pattern[i]

        if c == "\\" and i + 1 < len(pattern):
            i += 2
            continue

        if c == "[":
            i += 1
            while i < len(pattern) and pattern[i] != "]":
                if pattern[i] == "\\" and i + 1 < len(pattern):
                    i += 2
                    continue
                i += 1
            i += 1
            continue

        if c == "(":
            depth += 1
            group_has_quantifier.append(False)
            i += 1
            continue

        if c == ")":
            depth -= 1
            if depth < 0:
                depth = 0
            i += 1
            if depth < len(group_has_quantifier):
                inner_q = group_has_quantifier.pop() if group_has_quantifier else False
                outer_q = _char_is_quantifier(pattern, i)
                if inner_q and outer_q:
                    issues.append((
                        "nested_quantifier",
                        SEVERITY_HIGH,
                        "Quantified group contains another quantifier — "
                        "catastrophic backtracking risk",
                    ))
                    if outer_q:
                        i = _skip_quantifier(pattern, i)
            continue

        if depth > 0 and _char_is_quantifier(pattern, i):
            if group_has_quantifier:
                group_has_quantifier[-1] = True
            i = _skip_quantifier(pattern, i)
            continue

        if depth > 0 and c == "|":
            i += 1
            continue

        i += 1

    return issues


def _check_overlapping_alternation(pattern: str) -> list[tuple[str, str, str]]:
    """Check for overlapping alternation branches."""
    issues: list[tuple[str, str, str]] = []

    groups = re.findall(r"\(([^)]+)\)", pattern)
    for group in groups:
        branches = group.split("|")
        if len(branches) < 2:
            continue
        for idx_a in range(len(branches)):
            for idx_b in range(idx_a + 1, len(branches)):
                a = branches[idx_a].strip()
                b = branches[idx_b].strip()
                if a and b and (a.startswith(b) or b.startswith(a)):
                    issues.append((
                        "overlapping_alternation",
                        SEVERITY_MEDIUM,
                        f"Overlapping branches: '{a}' and '{b}' — "
                        "can cause excessive backtracking",
                    ))

    return issues


def _check_quantified_overlap(pattern: str) -> list[tuple[str, str, str]]:
    """Check for quantified groups with alternation containing quantifiers."""
    issues: list[tuple[str, str, str]] = []
    alt_groups = re.findall(r"\(([^)]+)\)[+*{]", pattern)
    for group in alt_groups:
        branches = group.split("|")
        for branch in branches:
            if re.search(r"[+*{]", branch):
                issues.append((
                    "quantified_alternation",
                        SEVERITY_LOW,
                    "Quantified group with alternation containing quantifier "
                    "— potential backtracking",
                ))
                break

    return issues


def _char_is_quantifier(pattern: str, i: int) -> bool:
    if i >= len(pattern):
        return False
    c = pattern[i]
    if c in "+*?":
        return True
    if c == "{":
        return True
    return False


def _skip_quantifier(pattern: str, i: int) -> int:
    if i >= len(pattern):
        return i
    c = pattern[i]
    if c in "+*?":
        i += 1
        if i < len(pattern) and pattern[i] == "?":
            i += 1
        return i
    if c == "{":
        end = pattern.find("}", i)
        if end >= 0:
            i = end + 1
            if i < len(pattern) and pattern[i] == "?":
                i += 1
        else:
            i += 1
        return i
    return i + 1


def analyze_regex_pattern(pattern: str) -> list[tuple[str, str, str]]:
    """Analyze a regex pattern string for ReDoS vulnerabilities.

    Returns list of (vulnerability_type, severity, explanation).
    """
    all_issues: list[tuple[str, str, str]] = []
    all_issues.extend(_check_nested_quantifiers(pattern))
    all_issues.extend(_check_overlapping_alternation(pattern))
    all_issues.extend(_check_quantified_overlap(pattern))
    return all_issues


class RegexSafetyAnalyzer(BaseAnalyzer):
    """Detects regex patterns vulnerable to ReDoS in source code."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: Path | str) -> RegexSafetyResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return RegexSafetyResult(
                total_regex_patterns=0,
                vulnerable_count=0,
                vulnerabilities=(),
                file_path=str(path),
            )
        path, ext = check
        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> RegexSafetyResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return RegexSafetyResult(
                total_regex_patterns=0,
                vulnerable_count=0,
                vulnerabilities=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        vulns: list[RegexVulnerability] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            pattern = self._extract_regex(node, ext, content)
            if pattern is not None:
                total += 1
                issues = analyze_regex_pattern(pattern)
                for vuln_type, severity, explanation in issues:
                    vulns.append(RegexVulnerability(
                        line_number=node.start_point[0] + 1,
                        pattern=pattern[:100],
                        vulnerability_type=vuln_type,
                        severity=severity,
                        explanation=explanation,
                    ))

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return RegexSafetyResult(
            total_regex_patterns=total,
            vulnerable_count=len(vulns),
            vulnerabilities=tuple(vulns),
            file_path=str(path),
        )

    def _extract_regex(
        self,
        node: tree_sitter.Node,
        ext: str,
        content: bytes,
    ) -> str | None:
        if ext == ".py":
            return self._extract_python_regex(node, content)
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            return self._extract_js_regex(node, content)
        if ext == ".java":
            return self._extract_java_regex(node, content)
        if ext == ".go":
            return self._extract_go_regex(node, content)
        return None

    def _extract_python_regex(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str | None:
        if node.type != _PYTHON_CALL_NODE:
            return None

        func = node.child_by_field_name("function")
        if func is None:
            return None

        func_text = content[func.start_byte:func.end_byte].decode(
            "utf-8", errors="replace",
        )
        if func_text not in _PYTHON_REGEX_CALLS:
            return None

        args = node.child_by_field_name("arguments")
        if args is None:
            return None
        first_arg = None
        for child in args.children:
            if child.is_named:
                first_arg = child
                break
        if first_arg is None:
            return None

        text = content[first_arg.start_byte:first_arg.end_byte].decode(
            "utf-8", errors="replace",
        )
        return _strip_pattern_delimiters(text)

    def _extract_js_regex(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str | None:
        if node.type == _JS_REGEX_NODE:
            text = content[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace",
            )
            return _strip_js_regex(text)

        if node.type == _JS_NEW_EXPRESSION:
            func = node.child_by_field_name("constructor")
            if func is None:
                return None
            name = content[func.start_byte:func.end_byte].decode(
                "utf-8", errors="replace",
            )
            if name != "RegExp":
                return None
            args = node.child_by_field_name("arguments")
            if args is None:
                return None
            for child in args.children:
                if child.is_named:
                    text = content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace",
                    )
                    return _strip_pattern_delimiters(text)

        return None

    def _extract_java_regex(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str | None:
        if node.type != _JAVA_CALL_NODE:
            return None

        obj = node.child_by_field_name("object")
        name = node.child_by_field_name("name")
        if obj is None or name is None:
            return None

        obj_text = content[obj.start_byte:obj.end_byte].decode(
            "utf-8", errors="replace",
        )
        name_text = content[name.start_byte:name.end_byte].decode(
            "utf-8", errors="replace",
        )

        if obj_text == "Pattern" and name_text == "compile":
            args = node.child_by_field_name("arguments")
            if args is None:
                return None
            for child in args.children:
                if child.is_named:
                    text = content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace",
                    )
                    return _strip_pattern_delimiters(text)

        return None

    def _extract_go_regex(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str | None:
        if node.type != _GO_CALL_NODE:
            return None

        func = node.child_by_field_name("function")
        if func is None:
            return None

        func_text = content[func.start_byte:func.end_byte].decode(
            "utf-8", errors="replace",
        )
        if not func_text.endswith("MustCompile") and not func_text.endswith("Compile"):
            return None

        args = node.child_by_field_name("arguments")
        if args is None:
            return None
        for child in args.children:
            if child.is_named:
                text = content[child.start_byte:child.end_byte].decode(
                    "utf-8", errors="replace",
                )
                return _strip_pattern_delimiters(text)

        return None


def _strip_pattern_delimiters(text: str) -> str:
    if len(text) >= 2:
        if (text[0] == '"' and text[-1] == '"') or \
           (text[0] == "'" and text[-1] == "'"):
            return text[1:-1]
        if text[0] == 'r' and len(text) >= 3:
            quote = text[1]
            if quote in ('"', "'") and text[-1] == quote:
                return text[2:-1]
    return text


def _strip_js_regex(text: str) -> str:
    if len(text) >= 2 and text[0] == "/":
        last_slash = text.rfind("/")
        if last_slash > 0:
            return text[1:last_slash]
    return text
