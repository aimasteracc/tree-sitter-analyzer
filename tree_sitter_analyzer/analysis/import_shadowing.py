"""Import Shadowing Detector.

Detects when imported names are shadowed by subsequent assignments:

  - shadowed_import: import x; x = something (imported name reassigned)
  - shadowed_from_import: from y import x; x = something

Shadowed imports silently replace module references with arbitrary
values, which can cause confusing runtime errors.

Supports Python only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_SHADOWED_IMPORT = "shadowed_import"
ISSUE_SHADOWED_FROM_IMPORT = "shadowed_from_import"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_SHADOWED_IMPORT: "Import statement is shadowed by a later assignment",
    ISSUE_SHADOWED_FROM_IMPORT: "From-import is shadowed by a later assignment",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_SHADOWED_IMPORT: "Rename either the import or the variable to avoid confusion.",
    ISSUE_SHADOWED_FROM_IMPORT: "Rename either the imported name or the variable to avoid confusion.",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _collect_import_names(node: tree_sitter.Node) -> list[tuple[str, int, str]]:
    names: list[tuple[str, int, str]] = []
    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                text = _node_text(child)
                parts = text.split(".")
                names.append((parts[0], child.start_point[0] + 1, ISSUE_SHADOWED_IMPORT))
            elif child.type == "aliased_import":
                alias = child.child_by_field_name("alias")
                if alias:
                    names.append((
                        _node_text(alias),
                        child.start_point[0] + 1,
                        ISSUE_SHADOWED_IMPORT,
                    ))
    elif node.type == "import_from_statement":
        found_import_keyword = False
        for child in node.children:
            if child.type == "import":
                found_import_keyword = True
                continue
            if not found_import_keyword:
                continue
            if child.type == "wildcard_import":
                continue
            if child.type == "aliased_import":
                alias = child.child_by_field_name("alias")
                if alias:
                    names.append((
                        _node_text(alias),
                        child.start_point[0] + 1,
                        ISSUE_SHADOWED_FROM_IMPORT,
                    ))
            elif child.type == "dotted_name":
                names.append((
                    _node_text(child).split(".")[0],
                    child.start_point[0] + 1,
                    ISSUE_SHADOWED_FROM_IMPORT,
                ))
            elif child.type == "identifier":
                names.append((
                    _node_text(child),
                    child.start_point[0] + 1,
                    ISSUE_SHADOWED_FROM_IMPORT,
                ))
    return names


def _collect_assignment_targets(node: tree_sitter.Node) -> list[tuple[str, int]]:
    names: list[tuple[str, int]] = []
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        if left:
            _extract_names_from_target(left, names)
    elif node.type == "augmented_assignment":
        left = node.child_by_field_name("left")
        if left:
            _extract_names_from_target(left, names)
    elif node.type == "for_statement":
        left = node.child_by_field_name("left")
        if left:
            _extract_names_from_target(left, names)
    return names


def _extract_names_from_target(
    node: tree_sitter.Node,
    names: list[tuple[str, int]],
) -> None:
    if node.type == "identifier":
        names.append((
            _node_text(node),
            node.start_point[0] + 1,
        ))
    elif node.type in ("tuple", "list", "pattern_list"):
        for child in node.children:
            _extract_names_from_target(child, names)
    elif node.type == "identifier":
        names.append((
            _node_text(node),
            node.start_point[0] + 1,
        ))


@dataclass(frozen=True)
class ImportShadowIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str
    import_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "import_line": self.import_line,
        }


@dataclass
class ImportShadowResult:
    file_path: str
    total_imports: int
    issues: list[ImportShadowIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_imports": self.total_imports,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ImportShadowingAnalyzer(BaseAnalyzer):
    """Detects when imported names are shadowed by assignments."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> ImportShadowResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ImportShadowResult(
                file_path=str(path),
                total_imports=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ImportShadowResult(
                file_path=str(path),
                total_imports=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        import_names: dict[str, tuple[int, str]] = {}
        assignment_names: list[tuple[str, int]] = []
        total_imports = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()

            import_infos = _collect_import_names(node)
            if import_infos:
                total_imports += 1
                for name, line, issue_type in import_infos:
                    if name not in import_names:
                        import_names[name] = (line, issue_type)

            assign_infos = _collect_assignment_targets(node)
            if assign_infos:
                assignment_names.extend(assign_infos)

            for child in node.children:
                stack.append(child)

        issues: list[ImportShadowIssue] = []
        for name, assign_line in assignment_names:
            if name in import_names:
                import_line, issue_type = import_names[name]
                if assign_line > import_line:
                    issues.append(ImportShadowIssue(
                        line=assign_line,
                        issue_type=issue_type,
                        severity=SEVERITY_MEDIUM,
                        description=_DESCRIPTIONS[issue_type],
                        suggestion=_SUGGESTIONS[issue_type],
                        context=f"{name} (imported at L{import_line})",
                        import_line=import_line,
                    ))

        return ImportShadowResult(
            file_path=str(path),
            total_imports=total_imports,
            issues=issues,
        )
