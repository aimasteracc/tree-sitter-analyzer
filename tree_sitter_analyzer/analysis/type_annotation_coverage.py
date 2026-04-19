"""Type annotation coverage analysis for Python code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat


@dataclass(frozen=True)
class AnnotationStat:
    """Annotation statistics for a single element."""

    name: str
    kind: str  # parameter, return_type, variable
    has_annotation: bool
    annotation_type: str  # specific type name, or "" if missing
    file_path: str
    line: int

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "name": self.name,
            "kind": self.kind,
            "has_annotation": self.has_annotation,
            "annotation_type": self.annotation_type,
            "file_path": self.file_path,
            "line": self.line,
        }

@dataclass(frozen=True)
class CoverageResult:
    """Aggregated annotation coverage for a file."""

    file_path: str
    total_elements: int
    annotated_elements: int
    coverage_pct: float
    stats: tuple[AnnotationStat, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_elements": self.total_elements,
            "annotated_elements": self.annotated_elements,
            "coverage_pct": round(self.coverage_pct, 1),
            "stats": [s.to_dict() for s in self.stats],
        }

class TypeAnnotationAnalyzer(BaseAnalyzer):
    """Analyze type annotation coverage in Python code."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def __init__(self) -> None:
        super().__init__()
        self._language, self._parser = self._get_parser(".py")

    def analyze(self, file_path: str | Path) -> CoverageResult:
        """Analyze type annotation coverage in a single file."""
        file_path = Path(file_path)
        source = file_path.read_bytes()
        assert self._parser is not None  # guaranteed for .py
        tree = self._parser.parse(source)
        root = tree.root_node

        stats: list[AnnotationStat] = []
        stats.extend(self._detect_parameters(root, str(file_path)))
        stats.extend(self._detect_return_types(root, str(file_path)))
        stats.extend(self._detect_variable_annotations(root, str(file_path)))

        total = len(stats)
        annotated = sum(1 for s in stats if s.has_annotation)
        pct = (annotated / total * 100) if total > 0 else 100.0

        return CoverageResult(
            file_path=str(file_path),
            total_elements=total,
            annotated_elements=annotated,
            coverage_pct=pct,
            stats=tuple(stats),
        )

    def analyze_directory(self, dir_path: str | Path) -> list[CoverageResult]:
        """Analyze coverage across all Python files in a directory."""
        dir_path = Path(dir_path)
        results: list[CoverageResult] = []
        for f in sorted(dir_path.rglob("*.py")):
            if f.is_file():
                try:
                    results.append(self.analyze(f))
                except Exception:
                    pass
        return results

    def _detect_parameters(
        self, root: Any, file_path: str
    ) -> list[AnnotationStat]:
        """Detect parameter annotation status."""
        stats: list[AnnotationStat] = []

        # Find all function definitions and analyze their parameters
        func_query = "(function_definition) @func"
        func_matches = TreeSitterQueryCompat.execute_query(
            self._language, func_query, root
        )

        for func_node, _ in func_matches:
            params_node = None
            for child in func_node.children:
                if child.type == "parameters":
                    params_node = child
                    break
            if params_node is None:
                continue

            for child in params_node.children:
                if child.type in ("(", ")", ",", "comment"):
                    continue
                line = child.start_point[0] + 1

                if child.type == "typed_parameter":
                    name = self._first_identifier(child)
                    ann = self._first_type(child)
                    if name:
                        stats.append(
                            AnnotationStat(
                                name=name,
                                kind="parameter",
                                has_annotation=True,
                                annotation_type=ann,
                                file_path=file_path,
                                line=line,
                            )
                        )
                elif child.type == "typed_default_parameter":
                    name = self._first_identifier(child)
                    ann = self._first_type(child)
                    if name:
                        stats.append(
                            AnnotationStat(
                                name=name,
                                kind="parameter",
                                has_annotation=True,
                                annotation_type=ann,
                                file_path=file_path,
                                line=line,
                            )
                        )
                elif child.type == "identifier":
                    name = child.text.decode("utf-8", errors="replace")
                    if name in ("self", "cls"):
                        continue
                    stats.append(
                        AnnotationStat(
                            name=name,
                            kind="parameter",
                            has_annotation=False,
                            annotation_type="",
                            file_path=file_path,
                            line=line,
                        )
                    )
                elif child.type == "default_parameter":
                    name = self._first_identifier(child)
                    if name and name not in ("self", "cls"):
                        stats.append(
                            AnnotationStat(
                                name=name,
                                kind="parameter",
                                has_annotation=False,
                                annotation_type="",
                                file_path=file_path,
                                line=line,
                            )
                        )
                elif child.type == "list_splat_pattern":
                    name = self._first_identifier(child)
                    if name:
                        stats.append(
                            AnnotationStat(
                                name=f"*{name}",
                                kind="parameter",
                                has_annotation=False,
                                annotation_type="",
                                file_path=file_path,
                                line=line,
                            )
                        )
                elif child.type == "dictionary_splat_pattern":
                    name = self._first_identifier(child)
                    if name:
                        stats.append(
                            AnnotationStat(
                                name=f"**{name}",
                                kind="parameter",
                                has_annotation=False,
                                annotation_type="",
                                file_path=file_path,
                                line=line,
                            )
                        )

        return stats

    @staticmethod
    def _first_identifier(node: Any) -> str:
        """Get the first identifier child's text."""
        for child in node.children:
            if child.type == "identifier":
                return str(child.text.decode("utf-8", errors="replace"))
        return ""

    @staticmethod
    def _first_type(node: Any) -> str:
        """Get the first type child's text."""
        for child in node.children:
            if child.type == "type":
                return str(child.text.decode("utf-8", errors="replace"))
        return ""

    def _detect_return_types(
        self, root: Any, file_path: str
    ) -> list[AnnotationStat]:
        """Detect return type annotation status."""
        query_str = "(function_definition) @func"
        matches = TreeSitterQueryCompat.execute_query(
            self._language, query_str, root
        )

        stats: list[AnnotationStat] = []
        for node, _capture_name in matches:
            name_children = [
                c
                for c in node.children
                if c.type == "identifier"
            ]
            if not name_children:
                continue
            func_name = name_children[0].text.decode("utf-8", errors="replace")
            line = node.start_point[0] + 1

            has_arrow = any(c.type == "->" for c in node.children)
            has_return = has_arrow and any(
                c.type == "type" for c in node.children
            )
            ann_type = ""
            if has_return:
                found_arrow = False
                for child in node.children:
                    if child.type == "->":
                        found_arrow = True
                        continue
                    if child.type == "type" and found_arrow:
                        ann_type = child.text.decode(
                            "utf-8", errors="replace"
                        )
                        break

            stats.append(
                AnnotationStat(
                    name=func_name,
                    kind="return_type",
                    has_annotation=has_return,
                    annotation_type=ann_type,
                    file_path=file_path,
                    line=line,
                )
            )
        return stats

    def _detect_variable_annotations(
        self, root: Any, file_path: str
    ) -> list[AnnotationStat]:
        """Detect variable type annotation status."""
        query_str = "(assignment) @assign"
        matches = TreeSitterQueryCompat.execute_query(
            self._language, query_str, root
        )

        stats: list[AnnotationStat] = []
        for node, _capture_name in matches:
            left = node.child_by_field_name("left")
            if left is None or left.type != "identifier":
                continue
            var_name = left.text.decode("utf-8", errors="replace")
            if var_name.startswith("_"):
                continue
            line = node.start_point[0] + 1

            has_type = any(
                c.type == "type" for c in node.children
            )
            ann_type = ""
            for child in node.children:
                if child.type == "type":
                    ann_type = child.text.decode("utf-8", errors="replace")
                    break

            if has_type:
                stats.append(
                    AnnotationStat(
                        name=var_name,
                        kind="variable",
                        has_annotation=True,
                        annotation_type=ann_type,
                        file_path=file_path,
                        line=line,
                    )
                )

        return stats
