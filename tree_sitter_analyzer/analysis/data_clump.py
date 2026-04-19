"""Data Clump Detector.

Detects parameter groups (3+) that appear together across multiple functions,
indicating they should be extracted into a class or data structure.

Issues detected:
  - data_clump: parameter group of 3+ appearing in 2+ functions

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from collections import Counter
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

ISSUE_DATA_CLUMP = "data_clump"

SEVERITY_MAP: dict[str, str] = {
    ISSUE_DATA_CLUMP: SEVERITY_MEDIUM,
}

DESCRIPTIONS: dict[str, str] = {
    ISSUE_DATA_CLUMP: "Parameter group appears together in multiple functions",
}

SUGGESTIONS: dict[str, str] = {
    ISSUE_DATA_CLUMP: "Extract these parameters into a class or data structure",
}

DEFAULT_MIN_PARAMS = 3
DEFAULT_MIN_OCCURRENCES = 2

_FILTERED_PARAMS: frozenset[str] = frozenset({
    "self", "cls", "this", "super",
})

_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition", "decorated_definition"}),
    ".js": frozenset({"function_declaration", "method_definition",
                      "arrow_function", "function_expression"}),
    ".jsx": frozenset({"function_declaration", "method_definition",
                       "arrow_function", "function_expression"}),
    ".ts": frozenset({"function_declaration", "method_definition",
                      "arrow_function", "function_expression"}),
    ".tsx": frozenset({"function_declaration", "method_definition",
                       "arrow_function", "function_expression"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}

_PARAM_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"identifier", "default_parameter", "typed_parameter",
                      "typed_default_parameter", "list_splat_pattern",
                      "dictionary_splat_pattern", "keyword_separator"}),
    ".js": frozenset({"identifier", "required_parameter", "rest_parameter",
                      "assignment_pattern"}),
    ".jsx": frozenset({"identifier", "required_parameter", "rest_parameter",
                       "assignment_pattern"}),
    ".ts": frozenset({"identifier", "required_parameter", "rest_parameter",
                      "assignment_pattern"}),
    ".tsx": frozenset({"identifier", "required_parameter", "rest_parameter",
                       "assignment_pattern"}),
    ".java": frozenset({"formal_parameter", "spread_parameter"}),
    ".go": frozenset({"parameter_list"}),
}

@dataclass(frozen=True)
class DataClumpIssue:
    """A single data clump issue."""

    issue_type: str
    line: int
    message: str
    severity: str
    params: tuple[str, ...]
    occurrences: int
    locations: tuple[str, ...]

    def to_dict(self) -> dict[str, str | int | tuple[str, ...]]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "params": self.params,
            "occurrences": self.occurrences,
            "locations": self.locations,
        }

@dataclass(frozen=True)
class FunctionParams:
    """Parameter info for a single function."""

    name: str
    line: int
    params: tuple[str, ...]

@dataclass(frozen=True)
class DataClumpResult:
    """Aggregated result of data clump analysis."""

    issues: tuple[DataClumpIssue, ...]
    functions_analyzed: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(self, severity: str) -> list[DataClumpIssue]:
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "functions_analyzed": self.functions_analyzed,
            "total_issues": self.total_issues,
            "high_severity_count": self.high_severity_count,
            "issues": [i.to_dict() for i in self.issues],
        }

class DataClumpAnalyzer(BaseAnalyzer):
    """Detects data clumps: parameter groups appearing together across functions."""

    def __init__(
        self,
        min_params: int = DEFAULT_MIN_PARAMS,
        min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    ) -> None:
        self._min_params = min_params
        self._min_occurrences = min_occurrences
        super().__init__()

    def analyze_file(self, file_path: Path | str) -> DataClumpResult:
        path = Path(file_path)
        if not path.exists():
            return self._empty_result(str(path))

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return self._empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return self._empty_result(str(path))

        tree = parser.parse(content)

        func_params = self._extract_function_params(tree.root_node, content, ext)
        issues = self._detect_clumps(func_params)

        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)

        return DataClumpResult(
            issues=tuple(issues),
            functions_analyzed=len(func_params),
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=str(path),
        )

    def _extract_function_params(
        self,
        node: tree_sitter.Node,
        content: bytes,
        ext: str,
    ) -> list[FunctionParams]:
        func_types = _FUNCTION_NODE_TYPES.get(ext, frozenset())
        results: list[FunctionParams] = []

        def _walk(n: tree_sitter.Node) -> None:
            if n.type in func_types:
                actual = n
                if n.type == "decorated_definition":
                    for child in n.children:
                        if child.type == "function_definition":
                            actual = child
                            break
                    else:
                        _walk_children(n)
                        return

                params = self._extract_params(actual, content, ext)
                if params:
                    func_name = self._get_function_name(actual, content)
                    results.append(FunctionParams(
                        name=func_name,
                        line=actual.start_point[0] + 1,
                        params=tuple(params),
                    ))

            _walk_children(n)

        def _walk_children(n: tree_sitter.Node) -> None:
            for child in n.children:
                _walk(child)

        _walk(node)
        return results

    def _extract_params(
        self,
        func_node: tree_sitter.Node,
        content: bytes,
        ext: str,
    ) -> list[str]:
        params_node = None
        for child in reversed(func_node.children):
            if child.type in ("parameters", "formal_parameters",
                              "parameter_list", "argument_list"):
                params_node = child
                break

        if params_node is None:
            return []

        param_names: list[str] = []

        if ext == ".go":
            return self._extract_go_params(params_node, content)

        param_types = _PARAM_NODE_TYPES.get(ext, frozenset())
        for child in params_node.children:
            name = self._get_param_name(child, content, ext, param_types)
            if name:
                param_names.append(name)

        return [p for p in param_names if p not in _FILTERED_PARAMS]

    def _extract_go_params(
        self,
        params_node: tree_sitter.Node,
        content: bytes,
    ) -> list[str]:
        names: list[str] = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                for sub in child.children:
                    if sub.type == "identifier":
                        name = content[sub.start_byte:sub.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                        names.append(name)
                        break
        return [p for p in names if p not in _FILTERED_PARAMS]

    def _get_param_name(
        self,
        node: tree_sitter.Node,
        content: bytes,
        ext: str,
        param_types: frozenset[str],
    ) -> str | None:
        if node.type not in param_types:
            return None

        if ext == ".java" and node.type == "formal_parameter":
            for child in node.children:
                if child.type == "identifier":
                    return content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace"
                    )
            return None

        if node.type == "identifier":
            return content[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )

        first_id = node.child_by_field_name("name")
        if first_id is None:
            for child in node.children:
                if child.type == "identifier":
                    first_id = child
                    break

        if first_id is not None:
            return content[first_id.start_byte:first_id.end_byte].decode(
                "utf-8", errors="replace"
            )

        return None

    def _get_function_name(
        self, func_node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = func_node.child_by_field_name("name")
        if name_node is not None:
            return content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        return "<anonymous>"

    def _detect_clumps(
        self, func_params: list[FunctionParams]
    ) -> list[DataClumpIssue]:
        if len(func_params) < self._min_occurrences:
            return []

        param_set_counter: Counter[frozenset[str]] = Counter()
        param_set_locations: dict[frozenset[str], list[tuple[str, int]]] = {}

        for fp in func_params:
            if len(fp.params) < self._min_params:
                continue

            full_set = frozenset(fp.params)
            param_set_counter[full_set] += 1
            locations = param_set_locations.setdefault(full_set, [])
            locations.append((fp.name, fp.line))

        issues: list[DataClumpIssue] = []
        seen_sets: set[frozenset[str]] = set()

        for param_set, count in param_set_counter.most_common():
            if count < self._min_occurrences:
                continue
            if len(param_set) < self._min_params:
                continue
            if param_set in seen_sets:
                continue

            seen_sets.add(param_set)
            locations = param_set_locations[param_set]
            sorted_params = tuple(sorted(param_set))
            loc_strs = tuple(f"{name} (line {line})" for name, line in locations)
            first_line = locations[0][1]

            issues.append(DataClumpIssue(
                issue_type=ISSUE_DATA_CLUMP,
                line=first_line,
                message=(
                    f"Parameter group {', '.join(sorted_params)} appears in "
                    f"{count} functions"
                ),
                severity=SEVERITY_MAP[ISSUE_DATA_CLUMP],
                params=sorted_params,
                occurrences=count,
                locations=loc_strs,
            ))

        return issues

    def _empty_result(self, file_path: str) -> DataClumpResult:
        return DataClumpResult(
            issues=(),
            functions_analyzed=0,
            total_issues=0,
            high_severity_count=0,
            file_path=file_path,
        )
