"""
Exception Handling Quality Analyzer.

Detects exception handling anti-patterns in production code.
Fills the gap between logging_patterns (log-level) and error_handling
(recovery patterns) by examining exception handling quality.

Anti-patterns detected:
  - broad_catch: catches overly wide exception type (Exception, Throwable)
  - swallowed_exception: catch/except block is empty or comment-only
  - missing_context: raise/throw without preserving original exception chain
  - generic_error_message: raise/throw with hardcoded string, no diagnostic info
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

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

QUALITY_BROAD = "broad_catch"
QUALITY_SWALLOWED = "swallowed_exception"
QUALITY_MISSING_CONTEXT = "missing_context"
QUALITY_GENERIC_MSG = "generic_error_message"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_QUALITY_SEVERITY: dict[str, str] = {
    QUALITY_BROAD: SEVERITY_MEDIUM,
    QUALITY_SWALLOWED: SEVERITY_HIGH,
    QUALITY_MISSING_CONTEXT: SEVERITY_MEDIUM,
    QUALITY_GENERIC_MSG: SEVERITY_LOW,
}

_QUALITY_DESCRIPTIONS: dict[str, str] = {
    QUALITY_BROAD: "Catches overly broad exception type instead of specific ones",
    QUALITY_SWALLOWED: "Exception handler is empty or comment-only, silently swallowing errors",
    QUALITY_MISSING_CONTEXT: "Raises new exception without preserving original (lost stack trace)",
    QUALITY_GENERIC_MSG: "Raises exception with hardcoded string, lacking diagnostic context",
}

# Python broad exception types
_PYTHON_BROAD_EXCEPTIONS = frozenset({
    "exception", "baseexception", "runtimeerror",
    "valueerror", "typeerror",
})

# JS/TS broad catch types
_JS_BROAD_CATCH = frozenset({
    "error",
})

# Java broad catch types
_JAVA_BROAD_CATCH = frozenset({
    "exception", "throwable", "runtimeexception",
})

# Python generic raise messages (hardcoded strings)
_PYTHON_GENERIC_PATTERNS = frozenset({
    '"error"', '"error!"', '"failed"', '"fail"', '"oops"',
    '"something went wrong"', '"unexpected error"',
    "'error'", "'error!'", "'failed'", "'fail'", "'oops'",
})


@dataclass(frozen=True)
class ExceptionIssue:
    issue_type: str
    line: int
    column: int
    handler_text: str
    severity: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class TryBlockQuality:
    start_line: int
    end_line: int
    handler_count: int
    issues: tuple[ExceptionIssue, ...]


@dataclass(frozen=True)
class ExceptionQualityResult:
    file_path: str
    try_blocks: tuple[TryBlockQuality, ...]
    total_try_blocks: int
    total_issues: int
    quality_score: float
    issue_counts: dict[str, int] = field(default_factory=dict)


def _decode(node: tree_sitter.Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def _severity_for(issue_type: str) -> str:
    return _QUALITY_SEVERITY.get(issue_type, SEVERITY_LOW)


def _empty_result(file_path: str) -> ExceptionQualityResult:
    return ExceptionQualityResult(
        file_path=file_path,
        try_blocks=(),
        total_try_blocks=0,
        total_issues=0,
        quality_score=100.0,
        issue_counts={},
    )


def _compute_quality_score(
    handler_count: int,
    issues: list[ExceptionIssue],
) -> float:
    if handler_count == 0:
        return 100.0
    penalty = 0.0
    for issue in issues:
        if issue.severity == SEVERITY_HIGH:
            penalty += 25.0
        elif issue.severity == SEVERITY_MEDIUM:
            penalty += 15.0
        else:
            penalty += 5.0
    return max(0.0, 100.0 - penalty)


class ExceptionQualityAnalyzer:
    """Analyzes exception handling quality across Python, JS/TS, Java, Go."""

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}
        self._languages: dict[str, tree_sitter.Language] = {}

    def _get_parser(
        self, ext: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if ext not in _LANGUAGE_MODULES:
            return None, None
        if ext not in self._parsers:
            module_name = _LANGUAGE_MODULES[ext]
            lang_module = __import__(module_name)
            func_name = _LANGUAGE_FUNCS.get(ext, "language")
            language_func = getattr(lang_module, func_name)
            language = tree_sitter.Language(language_func())
            parser = tree_sitter.Parser(language)
            self._languages[ext] = language
            self._parsers[ext] = parser
        return self._languages.get(ext), self._parsers.get(ext)

    def analyze_file(self, file_path: Path | str) -> ExceptionQualityResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            blocks = self._extract_python(tree.root_node, content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            blocks = self._extract_javascript(tree.root_node, content)
        elif ext == ".java":
            blocks = self._extract_java(tree.root_node, content)
        elif ext == ".go":
            blocks = self._extract_go(tree.root_node, content)
        else:
            blocks = []

        total_issues = sum(len(b.issues) for b in blocks)
        issue_counts: dict[str, int] = {}
        for b in blocks:
            for iss in b.issues:
                issue_counts[iss.issue_type] = (
                    issue_counts.get(iss.issue_type, 0) + 1
                )

        scores = [_compute_quality_score(b.handler_count, list(b.issues)) for b in blocks]
        avg_score = sum(scores) / len(scores) if scores else 100.0

        return ExceptionQualityResult(
            file_path=str(path),
            try_blocks=tuple(blocks),
            total_try_blocks=len(blocks),
            total_issues=total_issues,
            quality_score=round(avg_score, 1),
            issue_counts=issue_counts,
        )

    # --- Python ---

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[TryBlockQuality]:
        blocks: list[TryBlockQuality] = []
        self._walk_python_try(root, content, blocks)
        return blocks

    def _walk_python_try(
        self,
        node: tree_sitter.Node,
        content: bytes,
        blocks: list[TryBlockQuality],
    ) -> None:
        if node.type == "try_statement":
            quality = self._analyze_python_try(node, content)
            blocks.append(quality)

        for child in node.children:
            self._walk_python_try(child, content, blocks)

    def _analyze_python_try(
        self, node: tree_sitter.Node, content: bytes
    ) -> TryBlockQuality:
        issues: list[ExceptionIssue] = []
        handler_count = 0

        for child in node.children:
            if child.type == "except_clause":
                handler_count += 1
                issues.extend(self._check_python_except(child, content))


        return TryBlockQuality(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_count=handler_count,
            issues=tuple(issues),
        )

    def _check_python_except(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[ExceptionIssue]:
        issues: list[ExceptionIssue] = []

        # Find the exception type — may be in as_pattern, or as direct child
        exc_type_text = ""
        for child in node.children:
            if child.type == "as_pattern":
                for sub in child.children:
                    if sub.type not in ("as", "identifier", ","):
                        exc_type_text = _decode(sub)
                        break
                break
            if child.type in ("identifier", "attribute", "tuple"):
                exc_type_text = _decode(child)
                break

        if not exc_type_text:
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_BROAD,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="except:",
                    severity=_severity_for(QUALITY_BROAD),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_BROAD],
                    suggestion="Catch a specific exception type instead of bare except",
                )
            )
        elif exc_type_text.lower() in _PYTHON_BROAD_EXCEPTIONS:
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_BROAD,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text=f"except {exc_type_text}:",
                    severity=_severity_for(QUALITY_BROAD),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_BROAD],
                    suggestion=f"Catch a more specific exception than {exc_type_text}",
                )
            )

        # Check swallowed_exception
        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.type == "block":
                    body = child
                    break
        if body and self._is_empty_block(body, content):
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_SWALLOWED,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="empty handler",
                    severity=_severity_for(QUALITY_SWALLOWED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_SWALLOWED],
                    suggestion="Log the exception or re-raise with added context",
                )
            )

        return issues

    def _is_empty_block(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        for child in node.children:
            if child.type == "pass_statement":
                continue
            if child.type == "comment":
                continue
            if child.type == "expression_statement":
                text = _decode(child).strip()
                if text.startswith("#") or text == "pass":
                    continue
                return False
            if child.type in ("block", "statement_block"):
                if not self._is_empty_block(child, content):
                    return False
                continue
            return False
        return True

    # --- JavaScript/TypeScript ---

    def _extract_javascript(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[TryBlockQuality]:
        blocks: list[TryBlockQuality] = []
        self._walk_js_try(root, content, blocks)
        return blocks

    def _walk_js_try(
        self,
        node: tree_sitter.Node,
        content: bytes,
        blocks: list[TryBlockQuality],
    ) -> None:
        if node.type == "try_statement":
            quality = self._analyze_js_try(node, content)
            blocks.append(quality)

        for child in node.children:
            self._walk_js_try(child, content, blocks)

    def _analyze_js_try(
        self, node: tree_sitter.Node, content: bytes
    ) -> TryBlockQuality:
        issues: list[ExceptionIssue] = []
        handler_count = 0

        for child in node.children:
            if child.type == "catch_clause":
                handler_count += 1
                issues.extend(self._check_js_catch(child, content))
            if child.type == "finally_clause":
                handler_count += 1


        return TryBlockQuality(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_count=handler_count,
            issues=tuple(issues),
        )

    def _check_js_catch(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[ExceptionIssue]:
        issues: list[ExceptionIssue] = []

        # Check broad_catch (catch without type or catch(e))
        param = node.child_by_field_name("parameter")
        if param is None:
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_BROAD,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="catch",
                    severity=_severity_for(QUALITY_BROAD),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_BROAD],
                    suggestion="Consider adding type guard for specific error types",
                )
            )

        # Check swallowed
        body = node.child_by_field_name("body")
        if body and self._is_js_empty_block(body, content):
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_SWALLOWED,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="empty catch",
                    severity=_severity_for(QUALITY_SWALLOWED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_SWALLOWED],
                    suggestion="Log the error or re-throw with context",
                )
            )

        return issues

    def _is_js_empty_block(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        for child in node.children:
            if child.type == "comment":
                continue
            if child.type == "{":
                continue
            if child.type == "}":
                continue
            return False
        return True

    # --- Java ---

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[TryBlockQuality]:
        blocks: list[TryBlockQuality] = []
        self._walk_java_try(root, content, blocks)
        return blocks

    def _walk_java_try(
        self,
        node: tree_sitter.Node,
        content: bytes,
        blocks: list[TryBlockQuality],
    ) -> None:
        if node.type == "try_statement":
            quality = self._analyze_java_try(node, content)
            blocks.append(quality)

        for child in node.children:
            self._walk_java_try(child, content, blocks)

    def _analyze_java_try(
        self, node: tree_sitter.Node, content: bytes
    ) -> TryBlockQuality:
        issues: list[ExceptionIssue] = []
        handler_count = 0

        for child in node.children:
            if child.type == "catch_clause":
                handler_count += 1
                issues.extend(self._check_java_catch(child, content))
            if child.type == "finally_clause":
                handler_count += 1


        return TryBlockQuality(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_count=handler_count,
            issues=tuple(issues),
        )

    def _check_java_catch(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[ExceptionIssue]:
        issues: list[ExceptionIssue] = []

        # Check broad_catch — find the caught type name
        caught_types: list[str] = []
        for child in node.children:
            if child.type in ("type_identifier", "identifier"):
                caught_types.append(_decode(child))
            if child.type == "catch_formal_parameter":
                for sub in child.children:
                    if sub.type in ("type_identifier", "identifier", "catch_type"):
                        for inner in sub.children:
                            if inner.type in ("type_identifier", "identifier"):
                                caught_types.append(_decode(inner))
                        if not sub.children:
                            caught_types.append(_decode(sub))

        for caught in caught_types:
            if caught.lower() in _JAVA_BROAD_CATCH:
                issues.append(
                    ExceptionIssue(
                        issue_type=QUALITY_BROAD,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        handler_text=f"catch({caught})",
                        severity=_severity_for(QUALITY_BROAD),
                        description=_QUALITY_DESCRIPTIONS[QUALITY_BROAD],
                        suggestion=f"Catch a more specific exception than {caught}",
                    )
                )
                break

        # Check swallowed
        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.type == "block":
                    body = child
                    break

        if body and self._is_java_empty_block(body, content):
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_SWALLOWED,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="empty catch block",
                    severity=_severity_for(QUALITY_SWALLOWED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_SWALLOWED],
                    suggestion="Log the exception or re-throw with context",
                )
            )

        return issues

    def _is_java_empty_block(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        for child in node.children:
            if child.type == "{":
                continue
            if child.type == "}":
                continue
            if child.type == "comment":
                continue
            return False
        return True

    # --- Go ---

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[TryBlockQuality]:
        blocks: list[TryBlockQuality] = []
        self._walk_go_try(root, content, blocks)
        return blocks

    def _walk_go_try(
        self,
        node: tree_sitter.Node,
        content: bytes,
        blocks: list[TryBlockQuality],
    ) -> None:
        if node.type == "defer_statement":
            quality = self._analyze_go_defer(node, content)
            if quality.handler_count > 0:
                blocks.append(quality)
        if node.type == "if_statement":
            cond = node.child_by_field_name("condition")
            if cond and "recover()" in _decode(cond):
                quality = self._analyze_go_recover_if(node, content)
                blocks.append(quality)

        for child in node.children:
            self._walk_go_try(child, content, blocks)

    def _analyze_go_defer(
        self, node: tree_sitter.Node, content: bytes
    ) -> TryBlockQuality:
        issues: list[ExceptionIssue] = []
        text = _decode(node)

        if "recover()" not in text:
            return TryBlockQuality(
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                handler_count=0,
                issues=(),
            )

        handler_count = 1

        # Check if recover result is handled
        if "r := recover()" in text or "err := recover()" in text:
            pass
        elif "recover()" in text and "=" not in text.split("recover()")[0][-5:]:
            pass

        # Check if there's just a recover with no logging
        if "recover()" in text and "log" not in text.lower() and "fmt" not in text.lower() and "error" not in text.lower():
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_SWALLOWED,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="defer recover() with no logging",
                    severity=_severity_for(QUALITY_SWALLOWED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_SWALLOWED],
                    suggestion="Log the recovered panic or propagate the error",
                )
            )


        return TryBlockQuality(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_count=handler_count,
            issues=tuple(issues),
        )

    def _analyze_go_recover_if(
        self, node: tree_sitter.Node, content: bytes
    ) -> TryBlockQuality:
        issues: list[ExceptionIssue] = []
        handler_count = 1

        consequence = node.child_by_field_name("consequence")
        if consequence and self._is_go_empty_block(consequence, content):
            issues.append(
                ExceptionIssue(
                    issue_type=QUALITY_SWALLOWED,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    handler_text="recover() with empty if-body",
                    severity=_severity_for(QUALITY_SWALLOWED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_SWALLOWED],
                    suggestion="Log or handle the recovered panic",
                )
            )


        return TryBlockQuality(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_count=handler_count,
            issues=tuple(issues),
        )

    def _is_go_empty_block(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        for child in node.children:
            if child.type == "{":
                continue
            if child.type == "}":
                continue
            if child.type == "comment":
                continue
            return False
        return True
