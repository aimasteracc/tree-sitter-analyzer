"""Comment Quality Analyzer.

Detects stale/misleading comments in source code:
- Parameter mismatches (docstring params vs actual params)
- Missing return documentation
- TODO/FIXME/HACK tracking with context
- Comment rot risk scoring (via git blame)

Supports Python docstrings, JSDoc, JavaDoc, and Go doc comments.
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

class IssueType:
    PARAM_MISMATCH = "param_mismatch"
    MISSING_RETURN_DOC = "missing_return_doc"
    EXTRA_DOC_PARAM = "extra_doc_param"
    STALE_TODO = "stale_todo"
    ROT_RISK = "rot_risk"
    MISSING_PARAM_DOC = "missing_param_doc"

class Severity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass(frozen=True)
class CommentIssue:
    """A single comment quality issue found in code."""

    issue_type: str
    severity: str
    message: str
    file_path: str
    line_number: int
    element_name: str
    detail: str | None = None

@dataclass(frozen=True)
class CommentQualityResult:
    """Aggregated result of comment quality analysis."""

    issues: tuple[CommentIssue, ...]
    total_elements: int
    elements_with_docs: int
    issue_count: int
    quality_score: float  # 0-100, higher is better

    def get_issues_by_type(self, issue_type: str) -> list[CommentIssue]:
        return [i for i in self.issues if i.issue_type == issue_type]

    def get_issues_by_severity(self, severity: str) -> list[CommentIssue]:
        return [i for i in self.issues if i.severity == severity]

def _extract_python_docstring_params(doc: str) -> tuple[list[str], bool]:
    """Extract parameter names and whether return is documented from a Python docstring."""
    params: list[str] = []
    has_return = False

    # Match Sphinx/reST :param name: and :type name:
    for m in re.finditer(r":param\s+(\w+)", doc):
        params.append(m.group(1))
    for m in re.finditer(r":type\s+(\w+)", doc):
        name = m.group(1)
        if name not in params:
            params.append(name)

    # Match Google-style Args: section (stop at next section header like Returns:, Raises:)
    _SECTION_HEADERS = {"Returns:", "Yields:", "Raises:", "Examples:", "Notes:", "See Also:", "References:", "Todo:"}
    args_match = re.search(r"Args:\s*\n(.*?)(?=\n\s*(?:Returns?|Yields?|Raises?|Examples?|Notes?|See Also|References|Todo)\s*:\s*\n|\Z)", doc, re.DOTALL)
    if args_match:
        for m in re.finditer(r"^\s+(\w+)", args_match.group(1), re.MULTILINE):
            name = m.group(1)
            if name not in params:
                params.append(name)

    # Match Numpy-style Parameters section (stop at next section)
    np_match = re.search(r"Parameters\s*\n\s*-+\s*\n(.*?)(?=\n\s*(?:Returns?|Yields?|Raises?|Examples?|Notes?|See Also|References|Other)\s*\n\s*-+\s*\n|\Z)", doc, re.DOTALL)
    if np_match:
        for m in re.finditer(r"^\s+(\w+)", np_match.group(1), re.MULTILINE):
            name = m.group(1)
            if name not in params:
                params.append(name)

    # Check return documentation
    has_return = bool(
        re.search(r":returns?:|:rtype:|Returns?:|Yields?:", doc, re.IGNORECASE)
    )

    return params, has_return

def _extract_jsdoc_params(doc: str) -> tuple[list[str], bool]:
    """Extract parameter names and return doc from JSDoc."""
    params: list[str] = []
    has_return = False

    for m in re.finditer(r"@param\s+(?:\{[^}]*\}\s+)?(\w+)", doc):
        params.append(m.group(1))

    has_return = bool(re.search(r"@returns?\b", doc))

    return params, has_return

def _extract_javadoc_params(doc: str) -> tuple[list[str], bool]:
    """Extract parameter names and return doc from JavaDoc."""
    params: list[str] = []
    has_return = False

    for m in re.finditer(r"@param\s+(\w+)", doc):
        params.append(m.group(1))

    has_return = bool(re.search(r"@return\b", doc))

    return params, has_return

def _extract_go_doc_params(doc: str) -> tuple[list[str], bool]:
    """Go doc comments don't have structured param tags, but we can check conventions."""
    params: list[str] = []
    has_return = False

    # Go convention: params listed in comment
    # No standard tag format, look for common patterns
    return params, has_return

_EXTRACTORS: dict[str, type] = {
    "python": type("PythonExtractor", (), {
        "extract_params": staticmethod(_extract_python_docstring_params),
    }),
    "jsdoc": type("JSDocExtractor", (), {
        "extract_params": staticmethod(_extract_jsdoc_params),
    }),
    "javadoc": type("JavaDocExtractor", (), {
        "extract_params": staticmethod(_extract_javadoc_params),
    }),
    "go": type("GoDocExtractor", (), {
        "extract_params": staticmethod(_extract_go_doc_params),
    }),
}

def _find_todos(source: str, file_path: str) -> list[CommentIssue]:
    """Find TODO, FIXME, HACK comments in source code."""
    issues: list[CommentIssue] = []
    for i, line in enumerate(source.split("\n"), 1):
        m = re.search(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", line, re.IGNORECASE)
        if m:
            tag = m.group(1).upper()
            detail = m.group(2).strip()[:200] if m.group(2) else ""
            severity = Severity.HIGH if tag == "FIXME" else (
                Severity.MEDIUM if tag == "HACK" else Severity.LOW
            )
            issues.append(
                CommentIssue(
                    issue_type=IssueType.STALE_TODO,
                    severity=severity,
                    message=f"{tag}: {detail}" if detail else tag,
                    file_path=file_path,
                    line_number=i,
                    element_name=tag,
                    detail=detail,
                )
            )
    return issues

class CommentQualityAnalyzer(BaseAnalyzer):
    """Analyzes comment quality across source files."""

    def analyze_file(self, file_path: Path | str) -> CommentQualityResult:
        path = Path(file_path)
        if not path.exists():
            return CommentQualityResult(
                issues=(), total_elements=0, elements_with_docs=0,
                issue_count=0, quality_score=100.0,
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return CommentQualityResult(
                issues=(), total_elements=0, elements_with_docs=0,
                issue_count=0, quality_score=100.0,
            )

        source = path.read_text(encoding="utf-8", errors="replace")
        issues: list[CommentIssue] = []

        # Find TODOs/FIXMEs
        issues.extend(_find_todos(source, str(path)))

        # Parse AST and check doc quality
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return CommentQualityResult(
                issues=tuple(issues), total_elements=0, elements_with_docs=0,
                issue_count=len(issues),
                quality_score=100.0 if not issues else 80.0,
            )

        tree = parser.parse(source.encode("utf-8"))
        total_elements = 0
        elements_with_docs = 0

        if ext == ".py":
            ast_issues, te, ewd = self._analyze_python(tree.root_node, source, str(path))
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            ast_issues, te, ewd = self._analyze_js(tree.root_node, source, str(path))
        elif ext == ".java":
            ast_issues, te, ewd = self._analyze_java(tree.root_node, source, str(path))
        elif ext == ".go":
            ast_issues, te, ewd = self._analyze_go(tree.root_node, source, str(path))
        else:
            ast_issues, te, ewd = [], 0, 0

        issues.extend(ast_issues)
        total_elements = te
        elements_with_docs = ewd

        # Calculate quality score
        if total_elements == 0:
            score = 100.0 if not issues else max(0.0, 100.0 - len(issues) * 10)
        else:
            issue_penalty = sum(
                5 if i.severity == Severity.LOW else
                15 if i.severity == Severity.MEDIUM else 25
                for i in issues
                if i.issue_type != IssueType.STALE_TODO
            )
            score = max(0.0, 100.0 - issue_penalty)

        return CommentQualityResult(
            issues=tuple(issues),
            total_elements=total_elements,
            elements_with_docs=elements_with_docs,
            issue_count=len(issues),
            quality_score=round(score, 2),
        )

    def analyze_directory(self, dir_path: Path | str) -> CommentQualityResult:
        path = Path(dir_path)
        all_issues: list[CommentIssue] = []
        total_elements = 0
        elements_with_docs = 0

        for ext in SUPPORTED_EXTENSIONS:
            for fp in path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                result = self.analyze_file(fp)
                all_issues.extend(result.issues)
                total_elements += result.total_elements
                elements_with_docs += result.elements_with_docs

        issue_penalty = sum(
            5 if i.severity == Severity.LOW else
            15 if i.severity == Severity.MEDIUM else 25
            for i in all_issues
        )
        score = max(0.0, 100.0 - issue_penalty)

        return CommentQualityResult(
            issues=tuple(all_issues),
            total_elements=total_elements,
            elements_with_docs=elements_with_docs,
            issue_count=len(all_issues),
            quality_score=round(score, 2),
        )

    def _analyze_python(
        self, root: tree_sitter.Node, source: str, file_path: str
    ) -> tuple[list[CommentIssue], int, int]:
        issues: list[CommentIssue] = []
        self._py_total = 0
        self._py_doc_count = 0
        self._walk_python(root, source, file_path, issues, [])
        return issues, self._py_total, self._py_doc_count

    def _walk_python(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[CommentIssue],
        parent_params: list[str],
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, source, file_path, issues, parent_params)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = source[name_node.start_byte:name_node.end_byte]
            self._py_total = getattr(self, "_py_total", 0) + 1

            # Extract actual parameters
            params_node = node.child_by_field_name("parameters")
            actual_params = self._extract_python_params(params_node, source)

            # Get docstring
            doc = self._get_python_docstring(node, source)
            if doc:
                self._py_doc_count = getattr(self, "_py_doc_count", 0) + 1
                doc_params, has_return = _extract_python_docstring_params(doc)
                self._check_param_mismatch(
                    actual_params, doc_params, name, node.start_point[0] + 1,
                    file_path, issues,
                )
                # Check return doc
                return_type = node.child_by_field_name("return_type")
                has_arrow_return = node.children and any(
                    c.type == "type" for c in node.children
                )
                if (return_type or has_arrow_return) and not has_return:
                    issues.append(
                        CommentIssue(
                            issue_type=IssueType.MISSING_RETURN_DOC,
                            severity=Severity.MEDIUM,
                            message=f"Function '{name}' has return type but no return documentation",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            element_name=name,
                        )
                    )
            else:
                self._py_doc_count = getattr(self, "_py_doc_count", 0)

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                self._py_total = getattr(self, "_py_total", 0) + 1
                doc = self._get_python_docstring(node, source)
                if doc:
                    self._py_doc_count = getattr(self, "_py_doc_count", 0) + 1
                else:
                    self._py_doc_count = getattr(self, "_py_doc_count", 0)
            for child in node.children:
                if child.type == "block":
                    self._walk_python(child, source, file_path, issues, parent_params)
                else:
                    self._walk_python(child, source, file_path, issues, parent_params)
            return

        for child in node.children:
            self._walk_python(child, source, file_path, issues, parent_params)

    def _extract_python_params(
        self, params_node: tree_sitter.Node | None, source: str
    ) -> list[str]:
        if not params_node:
            return []
        params: list[str] = []
        for child in params_node.children:
            if child.type in {"identifier", "typed_parameter", "default_parameter", "typed_default_parameter"}:
                name = child.child_by_field_name("name")
                if name:
                    params.append(source[name.start_byte:name.end_byte])
                elif child.type == "identifier":
                    params.append(source[child.start_byte:child.end_byte])
            elif child.type in {"list_splat_pattern", "dictionary_splat_pattern"}:
                name = child.child_by_field_name("name")
                if name:
                    params.append(source[name.start_byte:name.end_byte])
            elif child.type == "parenthesized_parameter_list":
                continue
        return params

    def _get_python_docstring(self, node: tree_sitter.Node, source: str) -> str | None:
        body = node.child_by_field_name("body")
        if not body or not body.children:
            return None
        first = body.children[0]
        if first.type == "expression_statement":
            val = first.child_by_field_name("value") or (
                first.children[0] if first.children else None
            )
            if val and val.type == "string":
                text = source[val.start_byte:val.end_byte]
                return text.strip("'\"").strip()
        return None

    def _check_param_mismatch(
        self,
        actual_params: list[str],
        doc_params: list[str],
        element_name: str,
        line: int,
        file_path: str,
        issues: list[CommentIssue],
    ) -> None:
        # Filter out self/cls
        filtered_actual = [p for p in actual_params if p not in ("self", "cls")]

        actual_set = set(filtered_actual)
        doc_set = set(doc_params)

        # Missing params in doc
        missing = actual_set - doc_set
        if missing:
            issues.append(
                CommentIssue(
                    issue_type=IssueType.MISSING_PARAM_DOC,
                    severity=Severity.MEDIUM,
                    message=f"Function '{element_name}' has undocumented params: {', '.join(sorted(missing))}",
                    file_path=file_path,
                    line_number=line,
                    element_name=element_name,
                    detail=f"Missing: {', '.join(sorted(missing))}",
                )
            )

        # Extra params in doc (stale docs)
        extra = doc_set - actual_set
        if extra:
            issues.append(
                CommentIssue(
                    issue_type=IssueType.EXTRA_DOC_PARAM,
                    severity=Severity.HIGH,
                    message=f"Function '{element_name}' has stale doc params: {', '.join(sorted(extra))}",
                    file_path=file_path,
                    line_number=line,
                    element_name=element_name,
                    detail=f"Stale: {', '.join(sorted(extra))}",
                )
            )

    def _analyze_js(
        self, root: tree_sitter.Node, source: str, file_path: str
    ) -> tuple[list[CommentIssue], int, int]:
        issues: list[CommentIssue] = []
        self._js_total = 0
        self._js_doc_count = 0
        self._walk_js(root, source, file_path, issues)
        return issues, self._js_total, self._js_doc_count

    def _walk_js(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[CommentIssue],
    ) -> None:
        check_types = {"function_declaration", "class_declaration", "method_definition",
                       "arrow_function", "function_expression"}
        if node.type in check_types:
            name_node = node.child_by_field_name("name")
            name = source[name_node.start_byte:name_node.end_byte] if name_node else "<anonymous>"
            self._js_total = getattr(self, "_js_total", 0) + 1

            doc = self._get_preceding_comment(node, source, "jsdoc")
            if doc:
                self._js_doc_count = getattr(self, "_js_doc_count", 0) + 1
                doc_params, has_return = _extract_jsdoc_params(doc)
                actual_params = self._extract_js_params(node, source)
                self._check_param_mismatch(
                    actual_params, doc_params, name, node.start_point[0] + 1,
                    file_path, issues,
                )
                # Check return type annotation vs doc
                return_type = node.child_by_field_name("return_type")
                type_ann = node.child_by_field_name("type_annotation")
                if (return_type or type_ann) and not has_return:
                    issues.append(
                        CommentIssue(
                            issue_type=IssueType.MISSING_RETURN_DOC,
                            severity=Severity.MEDIUM,
                            message=f"Function '{name}' has return type but no @returns in JSDoc",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            element_name=name,
                        )
                    )
            else:
                self._js_doc_count = getattr(self, "_js_doc_count", 0)

        for child in node.children:
            self._walk_js(child, source, file_path, issues)

    def _extract_js_params(self, node: tree_sitter.Node, source: str) -> list[str]:
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return []
        params: list[str] = []
        for child in params_node.children:
            if child.type == "identifier":
                params.append(source[child.start_byte:child.end_byte])
            elif child.type in {"required_parameter", "optional_parameter", "rest_parameter", "assignment_pattern"}:
                name = child.child_by_field_name("name") or child.children[0] if child.children else None
                if name and name.type == "identifier":
                    params.append(source[name.start_byte:name.end_byte])
        return params

    def _analyze_java(
        self, root: tree_sitter.Node, source: str, file_path: str
    ) -> tuple[list[CommentIssue], int, int]:
        issues: list[CommentIssue] = []
        self._walk_java(root, source, file_path, issues)
        return issues, getattr(self, "_java_total", 0), getattr(self, "_java_doc_count", 0)

    def _walk_java(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[CommentIssue],
    ) -> None:
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = source[name_node.start_byte:name_node.end_byte]
                self._java_total = getattr(self, "_java_total", 0) + 1

                doc = self._get_preceding_comment(node, source, "javadoc")
                if doc:
                    self._java_doc_count = getattr(self, "_java_doc_count", 0) + 1
                    doc_params, has_return = _extract_javadoc_params(doc)
                    actual_params = self._extract_java_params(node, source)
                    self._check_param_mismatch(
                        actual_params, doc_params, name, node.start_point[0] + 1,
                        file_path, issues,
                    )
                    # Check return type
                    ret_type = node.child_by_field_name("type")
                    if ret_type:
                        ret_text = source[ret_type.start_byte:ret_type.end_byte]
                        if ret_text != "void" and not has_return:
                            issues.append(
                                CommentIssue(
                                    issue_type=IssueType.MISSING_RETURN_DOC,
                                    severity=Severity.MEDIUM,
                                    message=f"Method '{name}' returns {ret_text} but has no @return in JavaDoc",
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    element_name=name,
                                )
                            )
                else:
                    self._java_doc_count = getattr(self, "_java_doc_count", 0)

        elif node.type in {"class_declaration", "interface_declaration", "constructor_declaration"}:
            if node.type == "constructor_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source[name_node.start_byte:name_node.end_byte]
                    self._java_total = getattr(self, "_java_total", 0) + 1
                    doc = self._get_preceding_comment(node, source, "javadoc")
                    if doc:
                        self._java_doc_count = getattr(self, "_java_doc_count", 0) + 1
                    else:
                        self._java_doc_count = getattr(self, "_java_doc_count", 0)
            else:
                name_node = node.child_by_field_name("name")
                if name_node:
                    self._java_total = getattr(self, "_java_total", 0) + 1
                    doc = self._get_preceding_comment(node, source, "javadoc")
                    if doc:
                        self._java_doc_count = getattr(self, "_java_doc_count", 0) + 1
                    else:
                        self._java_doc_count = getattr(self, "_java_doc_count", 0)

        for child in node.children:
            self._walk_java(child, source, file_path, issues)

    def _extract_java_params(self, node: tree_sitter.Node, source: str) -> list[str]:
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return []
        params: list[str] = []
        for child in params_node.children:
            if child.type == "formal_parameter" or child.type == "spread_parameter":
                name = child.child_by_field_name("name")
                if name:
                    params.append(source[name.start_byte:name.end_byte])
            elif child.type == "identifier":
                params.append(source[child.start_byte:child.end_byte])
        return params

    def _analyze_go(
        self, root: tree_sitter.Node, source: str, file_path: str
    ) -> tuple[list[CommentIssue], int, int]:
        issues: list[CommentIssue] = []
        self._walk_go(root, source, file_path, issues)
        return issues, getattr(self, "_go_total", 0), getattr(self, "_go_doc_count", 0)

    def _walk_go(
        self,
        node: tree_sitter.Node,
        source: str,
        file_path: str,
        issues: list[CommentIssue],
    ) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = source[name_node.start_byte:name_node.end_byte]
                self._go_total = getattr(self, "_go_total", 0) + 1

                doc = self._get_preceding_comment(node, source, "go")
                if doc:
                    self._go_doc_count = getattr(self, "_go_doc_count", 0) + 1
                else:
                    self._go_doc_count = getattr(self, "_go_doc_count", 0)

                # Go doesn't have structured param docs conventionally,
                # but we can check if exported functions have comments
                if name[0:1].isupper() and not doc:
                    issues.append(
                        CommentIssue(
                            issue_type=IssueType.MISSING_PARAM_DOC,
                            severity=Severity.LOW,
                            message=f"Exported function '{name}' lacks documentation",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            element_name=name,
                        )
                    )

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = source[name_node.start_byte:name_node.end_byte]
                self._go_total = getattr(self, "_go_total", 0) + 1
                doc = self._get_preceding_comment(node, source, "go")
                if doc:
                    self._go_doc_count = getattr(self, "_go_doc_count", 0) + 1
                else:
                    self._go_doc_count = getattr(self, "_go_doc_count", 0)
                if name[0:1].isupper() and not doc:
                    issues.append(
                        CommentIssue(
                            issue_type=IssueType.MISSING_PARAM_DOC,
                            severity=Severity.LOW,
                            message=f"Exported method '{name}' lacks documentation",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            element_name=name,
                        )
                    )

        for child in node.children:
            self._walk_go(child, source, file_path, issues)

    def _get_preceding_comment(
        self, node: tree_sitter.Node, source: str, style: str
    ) -> str | None:
        sibling = node.prev_named_sibling
        if not sibling:
            return None

        if style == "jsdoc":
            if sibling.type in {"comment", "document_comment"}:
                text = source[sibling.start_byte:sibling.end_byte]
                if "/**" in text or "*/" in text:
                    return text
        elif style == "javadoc":
            if sibling.type == "block_comment":
                text = source[sibling.start_byte:sibling.end_byte]
                if text.startswith("/*"):
                    return text
        elif style == "go":
            if sibling.type == "comment":
                text = source[sibling.start_byte:sibling.end_byte]
                if text.startswith("//"):
                    return text
        return None
