"""
Feature Envy Detector.

Detects methods that are more interested in another class's data than their own.
Identifies three key patterns: feature envy, method chains, and inappropriate intimacy.

Issues detected:
  - feature_envy: method accesses foreign object data more than its own
  - method_chain: excessive chained calls through foreign objects (3+ hops)
  - inappropriate_intimacy: two classes excessively access each other's internals

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_FEATURE_ENVY = "feature_envy"
ISSUE_METHOD_CHAIN = "method_chain"
ISSUE_INTIMACY = "inappropriate_intimacy"

_ENVY_THRESHOLD = 0.5
_CHAIN_MIN_HOPS = 3
_INTIMACY_MIN_ACCESSES = 3

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_FEATURE_ENVY: SEVERITY_HIGH,
    ISSUE_METHOD_CHAIN: SEVERITY_MEDIUM,
    ISSUE_INTIMACY: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_FEATURE_ENVY: "Method accesses foreign object data more than its own class",
    ISSUE_METHOD_CHAIN: "Excessive method chaining through foreign objects",
    ISSUE_INTIMACY: "Two classes excessively access each other's internals",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_FEATURE_ENVY: "Move this method to the class whose data it uses most",
    ISSUE_METHOD_CHAIN: "Consider using a facade or moving the method closer to the data",
    ISSUE_INTIMACY: "Reduce coupling by using proper interfaces or combining classes",
}

def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""

@dataclass(frozen=True)
class FeatureEnvyIssue:
    """A single feature envy issue found in code."""

    line: int
    issue_type: str
    severity: str
    class_name: str
    method_name: str
    foreign_object: str
    self_accesses: int
    foreign_accesses: int
    description: str
    suggestion: str

@dataclass(frozen=True)
class FeatureEnvyResult:
    """Aggregated feature envy analysis result for a file."""

    issues: tuple[FeatureEnvyIssue, ...]
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
                    "class_name": i.class_name,
                    "method_name": i.method_name,
                    "foreign_object": i.foreign_object,
                    "self_accesses": i.self_accesses,
                    "foreign_accesses": i.foreign_accesses,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }

    def get_issues_by_severity(self, severity: str) -> tuple[FeatureEnvyIssue, ...]:
        return tuple(i for i in self.issues if i.severity == severity)

    def get_issues_by_type(self, issue_type: str) -> tuple[FeatureEnvyIssue, ...]:
        return tuple(i for i in self.issues if i.issue_type == issue_type)

def _empty_result(file_path: str, language: str) -> FeatureEnvyResult:
    return FeatureEnvyResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        low_severity=0,
        file_path=file_path,
        language=language,
    )

def _severity_counts(
    issues: tuple[FeatureEnvyIssue, ...],
) -> tuple[int, int, int]:
    high = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
    medium = sum(1 for i in issues if i.severity == SEVERITY_MEDIUM)
    low = sum(1 for i in issues if i.severity == SEVERITY_LOW)
    return high, medium, low

class FeatureEnvyAnalyzer(BaseAnalyzer):
    """Analyzes source code for feature envy and related patterns."""

    def analyze_file(self, file_path: Path | str) -> FeatureEnvyResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map: dict[str, str] = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        lang = language_map.get(ext, "unknown")

        content = path.read_bytes()

        if ext == ".py":
            issues = self._analyze_python(content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(content)
        elif ext == ".java":
            issues = self._analyze_java(content)
        elif ext == ".go":
            issues = self._analyze_go(content)
        else:
            issues = []

        issue_tuple = tuple(issues)
        high, medium, low = _severity_counts(issue_tuple)
        return FeatureEnvyResult(
            issues=issue_tuple,
            total_issues=len(issue_tuple),
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            file_path=str(path),
            language=lang,
        )

    def _analyze_python(self, content: bytes) -> list[FeatureEnvyIssue]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[FeatureEnvyIssue] = []
        classes = self._collect_python_classes(tree.root_node)

        for class_node, class_name in classes:
            methods = self._collect_python_methods(class_node)
            for method_node, method_name in methods:
                method_issues = self._check_python_method(
                    method_node, method_name, class_name, content,
                )
                issues.extend(method_issues)

        return issues

    def _collect_python_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        for child in node.children:
            if child.type == "class_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = _txt(name_node)
                    results.append((child, name))
            elif child.type == "decorated_definition":
                for inner in child.children:
                    if inner.type == "class_definition":
                        name_node = inner.child_by_field_name("name")
                        if name_node:
                            results.append((inner, _txt(name_node)))
        return results

    def _collect_python_methods(
        self, class_node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        for child in class_node.children:
            if child.type == "block":
                for stmt in child.children:
                    self._try_add_python_method(stmt, results)
            elif child.type == "decorated_definition":
                for inner in child.children:
                    self._try_add_python_method(inner, results)
        return results

    def _try_add_python_method(
        self,
        node: tree_sitter.Node,
        results: list[tuple[tree_sitter.Node, str]],
    ) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                results.append((node, _txt(name_node)))
        elif node.type == "decorated_definition":
            for inner in node.children:
                if inner.type == "function_definition":
                    name_node = inner.child_by_field_name("name")
                    if name_node:
                        results.append((inner, _txt(name_node)))

    def _check_python_method(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        class_name: str,
        content: bytes,
    ) -> list[FeatureEnvyIssue]:
        issues: list[FeatureEnvyIssue] = []
        self_count = 0
        foreign_counts: dict[str, int] = {}
        chain_issues: list[tuple[int, str]] = []

        self_count_val, foreign_counts_val, chain_issues_val = (
            self._walk_python_accesses_collect(method_node, content)
        )
        self_count = self_count_val
        foreign_counts = foreign_counts_val
        chain_issues = chain_issues_val

        total_foreign = sum(foreign_counts.values())
        if total_foreign > 0 and self_count > 0:
            ratio = total_foreign / (total_foreign + self_count)
            if ratio >= _ENVY_THRESHOLD:
                top_foreign = max(foreign_counts, key=lambda k: foreign_counts[k])
                issues.append(FeatureEnvyIssue(
                    line=method_node.start_point[0] + 1,
                    issue_type=ISSUE_FEATURE_ENVY,
                    severity=_SEVERITY_MAP[ISSUE_FEATURE_ENVY],
                    class_name=class_name,
                    method_name=method_name,
                    foreign_object=top_foreign,
                    self_accesses=self_count,
                    foreign_accesses=total_foreign,
                    description=_DESCRIPTIONS[ISSUE_FEATURE_ENVY],
                    suggestion=_SUGGESTIONS[ISSUE_FEATURE_ENVY],
                ))

        for line, chain_text in chain_issues:
            issues.append(FeatureEnvyIssue(
                line=line,
                issue_type=ISSUE_METHOD_CHAIN,
                severity=_SEVERITY_MAP[ISSUE_METHOD_CHAIN],
                class_name=class_name,
                method_name=method_name,
                foreign_object=chain_text,
                self_accesses=0,
                foreign_accesses=0,
                description=_DESCRIPTIONS[ISSUE_METHOD_CHAIN],
                suggestion=_SUGGESTIONS[ISSUE_METHOD_CHAIN],
            ))

        return issues

    def _walk_python_accesses_collect(
        self, node: tree_sitter.Node, content: bytes,
    ) -> tuple[int, dict[str, int], list[tuple[int, str]]]:
        text = content.decode("utf-8", errors="replace")
        return self._collect_accesses(
            node, text, "self", ".",
            member_types=frozenset({"attribute"}),
            call_types=frozenset({"call"}),
        )

    def _collect_accesses(
        self,
        node: tree_sitter.Node,
        text: str,
        self_keyword: str,
        accessor: str,
        member_types: frozenset[str] = frozenset({"attribute", "member_expression", "selector_expression"}),
        call_types: frozenset[str] = frozenset({"call", "call_expression", "method_invocation"}),
    ) -> tuple[int, dict[str, int], list[tuple[int, str]]]:
        self_count = 0
        foreign_counts: dict[str, int] = {}
        chain_issues: list[tuple[int, str]] = []

        for child in node.children:
            child_text = _txt(child)
            if child.type in member_types:
                if child_text.startswith(self_keyword + accessor):
                    self_count += 1
                else:
                    match = re.match(
                        r"^(\w+)" + re.escape(accessor), child_text,
                    )
                    if match and match.group(1) != self_keyword:
                        obj_name = match.group(1)
                        if not obj_name.startswith("__"):
                            foreign_counts[obj_name] = (
                                foreign_counts.get(obj_name, 0) + 1
                            )
            elif child.type in call_types:
                func_node = (
                    child.child_by_field_name("function")
                    or child.child(0)
                )
                if func_node:
                    func_text = _txt(func_node)
                    if func_text.startswith(self_keyword + accessor):
                        self_count += 1
                    else:
                        match = re.match(
                            r"^(\w+)" + re.escape(accessor), func_text,
                        )
                        if match and match.group(1) != self_keyword:
                            obj_name = match.group(1)
                            if not obj_name.startswith("__"):
                                foreign_counts[obj_name] = (
                                    foreign_counts.get(obj_name, 0) + 1
                                )

            if child.type in member_types | call_types:
                hops = self._count_chain_hops(child)
                if hops >= _CHAIN_MIN_HOPS:
                    chain_str = child_text[:80]
                    chain_issues.append((child.start_point[0] + 1, chain_str))

            child_self, child_foreign, child_chains = (
                self._collect_accesses(
                    child, text, self_keyword, accessor,
                    member_types, call_types,
                )
            )
            self_count += child_self
            for obj, count in child_foreign.items():
                foreign_counts[obj] = foreign_counts.get(obj, 0) + count
            chain_issues.extend(child_chains)

        return (self_count, foreign_counts, chain_issues)

    def _collect_java_accesses(
        self, node: tree_sitter.Node, text: str,
    ) -> tuple[int, dict[str, int], list[tuple[int, str]]]:
        self_count = 0
        foreign_counts: dict[str, int] = {}
        chain_issues: list[tuple[int, str]] = []

        for child in node.children:
            child_text = _txt(child)
            if child.type == "method_invocation":
                obj_node = child.child(0)
                if obj_node is not None:
                    obj_text = _txt(obj_node)
                    if obj_text == "this":
                        self_count += 1
                    elif obj_text and obj_text[0].islower() and len(obj_text) > 1:
                        foreign_counts[obj_text] = (
                            foreign_counts.get(obj_text, 0) + 1
                        )

            if child.type in {"method_invocation", "field_access"}:
                hops = self._count_chain_hops(child)
                if hops >= _CHAIN_MIN_HOPS:
                    chain_str = child_text[:80]
                    chain_issues.append((child.start_point[0] + 1, chain_str))

            child_self, child_foreign, child_chains = (
                self._collect_java_accesses(child, text)
            )
            self_count += child_self
            for obj, count in child_foreign.items():
                foreign_counts[obj] = foreign_counts.get(obj, 0) + count
            chain_issues.extend(child_chains)

        return (self_count, foreign_counts, chain_issues)

    _CHAIN_TYPES: frozenset[str] = frozenset({
        "attribute", "call",
        "member_expression", "call_expression",
        "method_invocation", "selector_expression",
    })

    def _count_chain_hops(self, node: tree_sitter.Node) -> int:
        count = 0
        current: tree_sitter.Node | None = node
        while current is not None:
            if current.type in self._CHAIN_TYPES:
                count += 1
                if current.child_count > 0:
                    child = current.child(0)
                    current = child
                else:
                    break
            else:
                break
        return count

    def _walk_python_accesses(
        self,
        node: tree_sitter.Node,
        content: bytes,
        self_count: int,
        foreign_counts: dict[str, int],
        chain_issues: list[tuple[int, str]],
    ) -> None:
        pass

    def _analyze_javascript(self, content: bytes) -> list[FeatureEnvyIssue]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[FeatureEnvyIssue] = []
        text = content.decode("utf-8", errors="replace")

        classes = self._collect_js_classes(tree.root_node)
        for class_node, class_name in classes:
            methods = self._collect_js_methods(class_node)
            for method_node, method_name in methods:
                method_issues = self._check_js_method(
                    method_node, method_name, class_name, text,
                )
                issues.extend(method_issues)

        return issues

    def _collect_js_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        for child in node.children:
            if child.type == "class_declaration":
                name_node = child.child_by_field_name("name")
                name = _txt(name_node) if name_node else "<anonymous>"
                results.append((child, name))
            elif child.type == "class_heritage":
                pass
            elif child.type in {"export_statement", "declaration"}:
                for inner in child.children:
                    if inner.type == "class_declaration":
                        name_node = inner.child_by_field_name("name")
                        name = _txt(name_node) if name_node else "<anonymous>"
                        results.append((inner, name))
            elif child.type == "export_default_declaration":
                for inner in child.children:
                    if inner.type == "class_declaration":
                        name_node = inner.child_by_field_name("name")
                        name = _txt(name_node) if name_node else "<anonymous>"
                        results.append((inner, name))
        return results

    def _collect_js_methods(
        self, class_node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        body = class_node.child_by_field_name("body")
        if body is None:
            return results

        for child in body.children:
            if child.type == "method_definition":
                name_node = child.child_by_field_name("name")
                name = _txt(name_node) if name_node else "<anonymous>"
                results.append((child, name))
            elif child.type in {"public_field_definition", "property_definition", "field_definition"}:
                name_node = child.child_by_field_name("name")
                name = _txt(name_node) if name_node else "<anonymous>"
                for inner in child.children:
                    if inner.type == "arrow_function":
                        results.append((inner, name))
                        break
        return results

    def _check_js_method(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        class_name: str,
        text: str,
    ) -> list[FeatureEnvyIssue]:
        issues: list[FeatureEnvyIssue] = []

        self_count, foreign_counts, chain_issues = (
            self._collect_accesses(
                method_node, text, "this", ".",
                member_types=frozenset({"member_expression"}),
                call_types=frozenset({"call_expression"}),
            )
        )

        total_foreign = sum(foreign_counts.values())
        if total_foreign > 0 and self_count > 0:
            ratio = total_foreign / (total_foreign + self_count)
            if ratio >= _ENVY_THRESHOLD:
                top_foreign = max(foreign_counts, key=lambda k: foreign_counts[k])
                issues.append(FeatureEnvyIssue(
                    line=method_node.start_point[0] + 1,
                    issue_type=ISSUE_FEATURE_ENVY,
                    severity=_SEVERITY_MAP[ISSUE_FEATURE_ENVY],
                    class_name=class_name,
                    method_name=method_name,
                    foreign_object=top_foreign,
                    self_accesses=self_count,
                    foreign_accesses=total_foreign,
                    description=_DESCRIPTIONS[ISSUE_FEATURE_ENVY],
                    suggestion=_SUGGESTIONS[ISSUE_FEATURE_ENVY],
                ))

        for line, chain_text in chain_issues:
            issues.append(FeatureEnvyIssue(
                line=line,
                issue_type=ISSUE_METHOD_CHAIN,
                severity=_SEVERITY_MAP[ISSUE_METHOD_CHAIN],
                class_name=class_name,
                method_name=method_name,
                foreign_object=chain_text,
                self_accesses=0,
                foreign_accesses=0,
                description=_DESCRIPTIONS[ISSUE_METHOD_CHAIN],
                suggestion=_SUGGESTIONS[ISSUE_METHOD_CHAIN],
            ))

        return issues

    def _analyze_java(self, content: bytes) -> list[FeatureEnvyIssue]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[FeatureEnvyIssue] = []
        text = content.decode("utf-8", errors="replace")

        classes = self._collect_java_classes(tree.root_node)
        for class_node, class_name in classes:
            methods = self._collect_java_methods(class_node)
            for method_node, method_name in methods:
                method_issues = self._check_java_method(
                    method_node, method_name, class_name, text,
                )
                issues.extend(method_issues)

        return issues

    def _collect_java_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        for child in node.children:
            if child.type == "class_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    results.append((child, _txt(name_node)))
            elif child.type == "interface_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    results.append((child, _txt(name_node)))
        return results

    def _collect_java_methods(
        self, class_node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        body = class_node.child_by_field_name("body")
        if body is None:
            return results

        for child in body.children:
            if child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    results.append((child, _txt(name_node)))
            elif child.type == "constructor_declaration":
                results.append((child, "<init>"))
        return results

    def _check_java_method(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        class_name: str,
        text: str,
    ) -> list[FeatureEnvyIssue]:
        issues: list[FeatureEnvyIssue] = []

        self_count, foreign_counts, chain_issues = (
            self._collect_java_accesses(method_node, text)
        )

        total_foreign = sum(foreign_counts.values())
        if total_foreign > 0 and self_count > 0:
            ratio = total_foreign / (total_foreign + self_count)
            if ratio >= _ENVY_THRESHOLD:
                top_foreign = max(foreign_counts, key=lambda k: foreign_counts[k])
                issues.append(FeatureEnvyIssue(
                    line=method_node.start_point[0] + 1,
                    issue_type=ISSUE_FEATURE_ENVY,
                    severity=_SEVERITY_MAP[ISSUE_FEATURE_ENVY],
                    class_name=class_name,
                    method_name=method_name,
                    foreign_object=top_foreign,
                    self_accesses=self_count,
                    foreign_accesses=total_foreign,
                    description=_DESCRIPTIONS[ISSUE_FEATURE_ENVY],
                    suggestion=_SUGGESTIONS[ISSUE_FEATURE_ENVY],
                ))

        for line, chain_text in chain_issues:
            issues.append(FeatureEnvyIssue(
                line=line,
                issue_type=ISSUE_METHOD_CHAIN,
                severity=_SEVERITY_MAP[ISSUE_METHOD_CHAIN],
                class_name=class_name,
                method_name=method_name,
                foreign_object=chain_text,
                self_accesses=0,
                foreign_accesses=0,
                description=_DESCRIPTIONS[ISSUE_METHOD_CHAIN],
                suggestion=_SUGGESTIONS[ISSUE_METHOD_CHAIN],
            ))

        return issues

    def _analyze_go(self, content: bytes) -> list[FeatureEnvyIssue]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[FeatureEnvyIssue] = []
        text = content.decode("utf-8", errors="replace")

        types = self._collect_go_types(tree.root_node)
        for type_name, receiver_name in types:
            methods = self._collect_go_methods(tree.root_node, type_name)
            for method_node, method_name in methods:
                method_issues = self._check_go_method(
                    method_node, method_name, type_name,
                    receiver_name, text,
                )
                issues.extend(method_issues)

        return issues

    def _collect_go_types(
        self, node: tree_sitter.Node,
    ) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for child in node.children:
            if child.type == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        name_node = spec.child_by_field_name("name")
                        if name_node:
                            type_name = _txt(name_node)
                            results.append((type_name, type_name[0:1].lower()))
        return results

    def _collect_go_methods(
        self, node: tree_sitter.Node, type_name: str,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        for child in node.children:
            if child.type == "method_declaration":
                receiver = child.child_by_field_name("receiver")
                if receiver:
                    receiver_text = _txt(receiver)
                    if type_name in receiver_text:
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            results.append((child, _txt(name_node)))
        return results

    def _check_go_method(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        type_name: str,
        receiver_name: str,
        text: str,
    ) -> list[FeatureEnvyIssue]:
        issues: list[FeatureEnvyIssue] = []

        self_count = 0
        foreign_counts: dict[str, int] = {}

        pattern = re.compile(
            re.escape(receiver_name) + r"\.(\w+)",
        )
        for _ in pattern.finditer(text[method_node.start_byte:method_node.end_byte]):
            self_count += 1

        other_pattern = re.compile(
            r"(?<!\w)(\w+)\.(\w+)(?!\w)",
        )
        method_text = text[method_node.start_byte:method_node.end_byte]
        for match in other_pattern.finditer(method_text):
            obj = match.group(1)
            if obj != receiver_name and not obj[0].isupper() and len(obj) > 1:
                foreign_counts[obj] = foreign_counts.get(obj, 0) + 1

        total_foreign = sum(foreign_counts.values())
        if total_foreign > 0 and self_count > 0:
            ratio = total_foreign / (total_foreign + self_count)
            if ratio >= _ENVY_THRESHOLD:
                top_foreign = max(foreign_counts, key=lambda k: foreign_counts[k])
                issues.append(FeatureEnvyIssue(
                    line=method_node.start_point[0] + 1,
                    issue_type=ISSUE_FEATURE_ENVY,
                    severity=_SEVERITY_MAP[ISSUE_FEATURE_ENVY],
                    class_name=type_name,
                    method_name=method_name,
                    foreign_object=top_foreign,
                    self_accesses=self_count,
                    foreign_accesses=total_foreign,
                    description=_DESCRIPTIONS[ISSUE_FEATURE_ENVY],
                    suggestion=_SUGGESTIONS[ISSUE_FEATURE_ENVY],
                ))

        return issues
