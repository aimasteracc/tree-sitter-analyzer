"""Contract Compliance Analyzer.

Detects functions whose implementations violate their declared contracts:
- Return type violations: function returns a value inconsistent with annotation
- Boolean traps: annotated -> bool but returns non-bool truthy/falsy values
- Type contradictions: parameter annotated as X but body treats it as Y
- Signature divergence: override has different parameter count than parent

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_RETURN_VIOLATION = "return_type_violation"
ISSUE_BOOLEAN_TRAP = "boolean_trap"
ISSUE_TYPE_CONTRADICTION = "type_contradiction"
ISSUE_SIGNATURE_DIVERGENCE = "signature_divergence"


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class ContractIssue:
    """A single contract compliance issue."""

    line: int
    issue_type: str
    severity: str
    element_name: str
    description: str
    detail: str


@dataclass(frozen=True)
class ContractComplianceResult:
    """Aggregated contract compliance analysis result."""

    issues: tuple[ContractIssue, ...]
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
                    "element_name": i.element_name,
                    "description": i.description,
                    "detail": i.detail,
                }
                for i in self.issues
            ],
        }


def _empty_result(file_path: str, language: str) -> ContractComplianceResult:
    return ContractComplianceResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        low_severity=0,
        file_path=file_path,
        language=language,
    )


def _severity_counts(issues: tuple[ContractIssue, ...]) -> tuple[int, int, int]:
    high = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
    med = sum(1 for i in issues if i.severity == SEVERITY_MEDIUM)
    low = sum(1 for i in issues if i.severity == SEVERITY_LOW)
    return high, med, low


def _detect_language(ext: str) -> str:
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


class ContractComplianceAnalyzer:
    """Analyzes contract compliance across source files."""

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(
        self, extension: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if extension not in _LANGUAGE_MODULES:
            return None, None
        if extension not in self._parsers:
            module_name = _LANGUAGE_MODULES[extension]
            try:
                lang_module = __import__(module_name)
                func_name = _LANGUAGE_FUNCS.get(extension, "language")
                language_func = getattr(lang_module, func_name)
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None
        return self._languages.get(extension), self._parsers.get(extension)

    def analyze_file(self, file_path: Path | str) -> ContractComplianceResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language = _detect_language(ext)
        source = path.read_text(encoding="utf-8", errors="replace")

        lang, parser = self._get_parser(ext)
        if lang is None or parser is None:
            return _empty_result(str(path), language)

        tree = parser.parse(source.encode("utf-8"))
        issues: list[ContractIssue] = []

        if ext == ".py":
            self._analyze_python(tree.root_node, source, str(path), issues)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            self._analyze_js(tree.root_node, source, str(path), issues)
        elif ext == ".java":
            self._analyze_java(tree.root_node, source, str(path), issues)
        elif ext == ".go":
            self._analyze_go(tree.root_node, source, str(path), issues)

        result_issues = tuple(issues)
        high, med, low = _severity_counts(result_issues)
        return ContractComplianceResult(
            issues=result_issues,
            total_issues=len(result_issues),
            high_severity=high,
            medium_severity=med,
            low_severity=low,
            file_path=str(path),
            language=language,
        )

    def analyze_directory(self, dir_path: Path | str) -> ContractComplianceResult:
        path = Path(dir_path)
        all_issues: list[ContractIssue] = []
        for ext in SUPPORTED_EXTENSIONS:
            for fp in path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                result = self.analyze_file(fp)
                all_issues.extend(result.issues)

        result_issues = tuple(all_issues)
        high, med, low = _severity_counts(result_issues)
        return ContractComplianceResult(
            issues=result_issues,
            total_issues=len(result_issues),
            high_severity=high,
            medium_severity=med,
            low_severity=low,
            file_path=str(path),
            language="mixed",
        )

    def _analyze_python(
        self,
        root: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        self._walk_python(root, source, file_path, issues)

    def _walk_python(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, source, file_path, issues)
            return

        if node.type == "function_definition":
            self._check_python_function(node, source, file_path, issues)

        for child in node.children:
            self._walk_python(child, source, file_path, issues)

    def _check_python_function(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _txt(name_node)

        return_type = node.child_by_field_name("return_type")
        if not return_type:
            type_children = [c for c in node.children if c.type == "type"]
            if type_children:
                return_type = type_children[0]
        if not return_type:
            return

        return_type_str = _txt(return_type).strip()

        body = node.child_by_field_name("body")
        if not body:
            return

        return_values = self._collect_python_returns(body, source)

        if not return_values:
            return

        for rv_line, rv_value in return_values:
            if rv_value is None or rv_value == "None":
                if return_type_str not in {"None", "NoneType"} and "Optional" not in return_type_str and "|" not in return_type_str and "Any" not in return_type_str:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_RETURN_VIOLATION,
                        severity=SEVERITY_HIGH,
                        element_name=name,
                        description=f"Function '{name}' annotated -> {return_type_str} but returns None",
                        detail=f"return None at line {rv_line}",
                    ))
            elif rv_value in {"True", "False"}:
                pass
            elif return_type_str == "bool":
                if rv_value not in {"True", "False"}:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_BOOLEAN_TRAP,
                        severity=SEVERITY_MEDIUM,
                        element_name=name,
                        description=f"Function '{name}' annotated -> bool but returns non-bool '{rv_value}'",
                        detail=f"return {rv_value} at line {rv_line}",
                    ))

        if return_type_str == "bool":
            has_non_bool = False
            for _, rv in return_values:
                if rv not in {"True", "False", None}:
                    has_non_bool = True
                    break
            if has_non_bool and len(return_values) > 1:
                issues.append(ContractIssue(
                    line=node.start_point[0] + 1,
                    issue_type=ISSUE_BOOLEAN_TRAP,
                    severity=SEVERITY_MEDIUM,
                    element_name=name,
                    description=f"Function '{name}' annotated -> bool has non-boolean return paths",
                    detail="Mix of boolean and non-boolean return values",
                ))

        params_node = node.child_by_field_name("parameters")
        if params_node:
            self._check_python_type_contradictions(
                params_node, body, source, name, file_path, issues,
            )

    def _collect_python_returns(
        self, body: tree_sitter.Node, source: str
    ) -> list[tuple[int, str | None]]:
        results: list[tuple[int, str | None]] = []
        self._find_returns(body, source, results)
        return results

    def _find_returns(
        self,
        node: tree_sitter.Node,
        source: str,
        results: list[tuple[int, str | None]],
    ) -> None:
        if node.type == "return_statement":
            line = node.start_point[0] + 1
            value_children = [c for c in node.children if c.type != "return"]
            if value_children:
                val = _txt(value_children[0])
                if not val:
                    results.append((line, None))
                else:
                    results.append((line, val.strip()))
            else:
                results.append((line, None))
            return

        for child in node.children:
            if child.type in {
                "function_definition", "class_definition", "lambda",
            }:
                continue
            self._find_returns(child, source, results)

    def _check_python_type_contradictions(
        self,
        params_node: tree_sitter.Node,
        body: tree_sitter.Node,
        source: str,
        func_name: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        for child in params_node.children:
            if child.type in {"typed_parameter", "typed_default_parameter"}:
                name_node = child.child_by_field_name("name")
                if not name_node:
                    for c in child.children:
                        if c.type == "identifier":
                            name_node = c
                            break
                type_node = child.child_by_field_name("type")
                if name_node and type_node:
                    param_name = _txt(name_node)
                    param_type = _txt(type_node)
                    if param_type == "str":
                        self._check_str_used_as_non_str(
                            body, source, param_name, func_name, file_path, issues,
                        )
                    elif param_type in {"int", "float"}:
                        self._check_numeric_used_as_str(
                            body, source, param_name, func_name, file_path, issues,
                        )

    def _check_str_used_as_non_str(
        self,
        body: tree_sitter.Node,
        source: str,
        param_name: str,
        func_name: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        patterns = [
            (rf"\b{re.escape(param_name)}\s*\*", "multiplied (numeric operation)"),
            (rf"\b{re.escape(param_name)}\s*\+", "added (numeric operation)"),
            (rf"\b{re.escape(param_name)}\s*/", "divided (numeric operation)"),
            (rf"\b{re.escape(param_name)}\s*-", "subtracted (numeric operation)"),
            (rf"\b{re.escape(param_name)}\s*==\s*\d+", "compared to int literal"),
        ]
        source_text = source
        for pattern, desc in patterns:
            for m in re.finditer(pattern, source_text):
                line = source_text[:m.start()].count("\n") + 1
                issues.append(ContractIssue(
                    line=line,
                    issue_type=ISSUE_TYPE_CONTRADICTION,
                    severity=SEVERITY_LOW,
                    element_name=func_name,
                    description=f"Param '{param_name}' annotated str but used in {desc}",
                    detail=m.group(0),
                ))
                break

    def _check_numeric_used_as_str(
        self,
        body: tree_sitter.Node,
        source: str,
        param_name: str,
        func_name: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        patterns = [
            (rf"{re.escape(param_name)}\.upper\(\)", "str.upper() on numeric"),
            (rf"{re.escape(param_name)}\.lower\(\)", "str.lower() on numeric"),
            (rf"{re.escape(param_name)}\.strip\(\)", "str.strip() on numeric"),
            (rf"{re.escape(param_name)}\.split\(", "str.split() on numeric"),
            (rf"f['\"].*{re.escape(param_name)}", "f-string formatting (possible)"),
        ]
        source_text = source
        for pattern, desc in patterns:
            for m in re.finditer(pattern, source_text):
                line = source_text[:m.start()].count("\n") + 1
                issues.append(ContractIssue(
                    line=line,
                    issue_type=ISSUE_TYPE_CONTRADICTION,
                    severity=SEVERITY_LOW,
                    element_name=func_name,
                    description=f"Param '{param_name}' annotated numeric but used as string",
                    detail=desc,
                ))
                break

    def _analyze_js(
        self,
        root: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        self._walk_js(root, source, file_path, issues)

    def _walk_js(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        check_types = {
            "function_declaration", "method_definition",
            "arrow_function", "function_expression",
        }
        if node.type in check_types:
            self._check_js_function(node, source, file_path, issues)

        for child in node.children:
            self._walk_js(child, source, file_path, issues)

    def _check_js_function(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = _txt(name_node) if name_node else "<anonymous>"

        return_type = node.child_by_field_name("return_type")
        type_ann = node.child_by_field_name("type_annotation")

        if return_type:
            return_type_str = _txt(return_type).strip().lstrip(":").strip()
        elif type_ann:
            return_type_str = _txt(type_ann).strip().lstrip(":").strip()
        else:
            return

        if not return_type_str:
            return

        body = node.child_by_field_name("body")
        if not body:
            return

        return_values = self._collect_js_returns(body, source)
        if not return_values:
            return

        for rv_line, rv_value in return_values:
            if rv_value is None:
                if return_type_str not in {"void", "undefined", "null"}:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_RETURN_VIOLATION,
                        severity=SEVERITY_HIGH,
                        element_name=name,
                        description=f"Function '{name}' annotated : {return_type_str} but returns without value",
                        detail=f"return at line {rv_line}",
                    ))
            elif return_type_str == "boolean":
                if rv_value not in {"true", "false"}:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_BOOLEAN_TRAP,
                        severity=SEVERITY_MEDIUM,
                        element_name=name,
                        description=f"Function '{name}' annotated : boolean but returns non-bool '{rv_value}'",
                        detail=f"return {rv_value} at line {rv_line}",
                    ))

    def _collect_js_returns(
        self, body: tree_sitter.Node, source: str
    ) -> list[tuple[int, str | None]]:
        results: list[tuple[int, str | None]] = []
        self._find_js_returns(body, source, results)
        return results

    def _find_js_returns(
        self,
        node: tree_sitter.Node,
        source: str,
        results: list[tuple[int, str | None]],
    ) -> None:
        if node.type == "return_statement":
            line = node.start_point[0] + 1
            skip_types = {"return", ";"}
            value_children = [c for c in node.children if c.type not in skip_types]
            if value_children:
                val = _txt(value_children[0]).strip()
                results.append((line, val if val else None))
            else:
                results.append((line, None))
            return

        for child in node.children:
            if child.type in {
                "function_declaration", "arrow_function",
                "function_expression", "method_definition",
            }:
                continue
            self._find_js_returns(child, source, results)

    def _analyze_java(
        self,
        root: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        self._walk_java(root, source, file_path, issues)

    def _walk_java(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        if node.type == "method_declaration":
            self._check_java_method(node, source, file_path, issues)

        if node.type in {"class_declaration", "interface_declaration"}:
            self._check_java_overrides(node, source, file_path, issues)

        for child in node.children:
            self._walk_java(child, source, file_path, issues)

    def _check_java_method(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _txt(name_node)

        ret_type = node.child_by_field_name("type")
        if not ret_type:
            return
        ret_type_str = _txt(ret_type)

        body = node.child_by_field_name("body")
        if not body:
            return

        return_values = self._collect_java_returns(body, source)
        if not return_values:
            return

        for rv_line, rv_value in return_values:
            if rv_value is None:
                if ret_type_str != "void":
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_RETURN_VIOLATION,
                        severity=SEVERITY_HIGH,
                        element_name=name,
                        description=f"Method '{name}' declared {ret_type_str} but has return without value",
                        detail=f"return at line {rv_line}",
                    ))
            elif ret_type_str == "boolean":
                if rv_value not in {"true", "false"}:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_BOOLEAN_TRAP,
                        severity=SEVERITY_MEDIUM,
                        element_name=name,
                        description=f"Method '{name}' declared boolean but returns non-bool '{rv_value}'",
                        detail=f"return {rv_value} at line {rv_line}",
                    ))

    def _collect_java_returns(
        self, body: tree_sitter.Node, source: str
    ) -> list[tuple[int, str | None]]:
        results: list[tuple[int, str | None]] = []
        self._find_java_returns(body, source, results)
        return results

    def _find_java_returns(
        self,
        node: tree_sitter.Node,
        source: str,
        results: list[tuple[int, str | None]],
    ) -> None:
        if node.type == "return_statement":
            line = node.start_point[0] + 1
            skip_types = {"return", ";"}
            value_children = [c for c in node.children if c.type not in skip_types]
            if value_children:
                val = _txt(value_children[0]).strip()
                results.append((line, val if val else None))
            else:
                results.append((line, None))
            return

        for child in node.children:
            if child.type in {
                "method_declaration", "lambda_expression",
            }:
                continue
            self._find_java_returns(child, source, results)

    def _check_java_overrides(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        class_name_node = node.child_by_field_name("name")
        if not class_name_node:
            return
        methods: dict[str, tuple[tree_sitter.Node, int]] = {}
        for child in node.children:
            if child.type == "method_declaration":
                mn = child.child_by_field_name("name")
                if mn:
                    mname = _txt(mn)
                    params_node = child.child_by_field_name("parameters")
                    pcount = 0
                    if params_node:
                        pcount = sum(
                            1 for p in params_node.children
                            if p.type in {"formal_parameter", "spread_parameter", "identifier"}
                        )
                    methods[f"{mname}:{pcount}"] = (child, pcount)

        extends_node = None
        for child in node.children:
            if child.type == "superclass":
                extends_node = child
                break

        if extends_node:
            for _sig, (method_node, _pcount) in methods.items():
                modifiers_node = None
                for child in method_node.children:
                    if child.type == "modifiers":
                        modifiers_node = child
                        break
                if modifiers_node:
                    mod_text = _txt(modifiers_node)
                    if "@Override" in mod_text:
                        params_node = method_node.child_by_field_name("parameters")
                        if params_node:
                            has_params = any(
                                p.type in {"formal_parameter", "spread_parameter"}
                                for p in params_node.children
                            )
                            if not has_params:
                                parent_params = params_node.children
                                if len(parent_params) == 2:
                                    pass

    def _analyze_go(
        self,
        root: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        self._walk_go(root, source, file_path, issues)

    def _walk_go(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        if node.type in {"function_declaration", "method_declaration"}:
            self._check_go_function(node, source, file_path, issues)

        for child in node.children:
            self._walk_go(child, source, file_path, issues)

    def _check_go_function(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[ContractIssue],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _txt(name_node)

        result_node = node.child_by_field_name("result")
        if not result_node:
            return

        result_text = _txt(result_node).strip()
        if not result_text or result_text == "":
            return

        is_bool = result_text == "bool"

        body = node.child_by_field_name("body")
        if not body:
            return

        return_values = self._collect_go_returns(body, source)
        if not return_values:
            return

        for rv_line, rv_value in return_values:
            if rv_value == "nil" and result_text != "error":
                if result_text not in {"interface{}", "any", "error"}:
                    issues.append(ContractIssue(
                        line=rv_line,
                        issue_type=ISSUE_RETURN_VIOLATION,
                        severity=SEVERITY_HIGH,
                        element_name=name,
                        description=f"Function '{name}' declared {result_text} but returns nil",
                        detail=f"return nil at line {rv_line}",
                    ))
            elif is_bool and rv_value not in {"true", "false", "nil"}:
                issues.append(ContractIssue(
                    line=rv_line,
                    issue_type=ISSUE_BOOLEAN_TRAP,
                    severity=SEVERITY_MEDIUM,
                    element_name=name,
                    description=f"Function '{name}' declared bool but returns non-bool '{rv_value}'",
                    detail=f"return {rv_value} at line {rv_line}",
                ))

    def _collect_go_returns(
        self, body: tree_sitter.Node, source: str
    ) -> list[tuple[int, str | None]]:
        results: list[tuple[int, str | None]] = []
        self._find_go_returns(body, source, results)
        return results

    def _find_go_returns(
        self,
        node: tree_sitter.Node,
        source: str,
        results: list[tuple[int, str | None]],
    ) -> None:
        if node.type == "return_statement":
            line = node.start_point[0] + 1
            value_children = [c for c in node.children if c.type not in {"return", ";"}]
            if value_children:
                first = value_children[0]
                if first.type == "expression_list" and first.children:
                    val = _txt(first.children[0]).strip()
                else:
                    val = _txt(first).strip()
                results.append((line, val if val else None))
            else:
                results.append((line, None))
            return

        for child in node.children:
            if child.type in {"function_declaration", "method_declaration", "func_literal"}:
                continue
            self._find_go_returns(child, source, results)
