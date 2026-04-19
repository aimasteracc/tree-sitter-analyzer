"""Method Chain Analyzer.

Detects excessively long method/attribute chains (a.b.c.d) that indicate
Law of Demeter violations. Long chains couple code to deep object internals,
making them fragile and hard to debug.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_OK = "ok"
SEVERITY_LONG = "long_chain"
SEVERITY_TRAIN_WRECK = "train_wreck"

DEFAULT_CHAIN_THRESHOLD = 4
TRAIN_WRECK_THRESHOLD = 6

def _severity(chain_length: int) -> str:
    if chain_length < DEFAULT_CHAIN_THRESHOLD:
        return SEVERITY_OK
    if chain_length < TRAIN_WRECK_THRESHOLD:
        return SEVERITY_LONG
    return SEVERITY_TRAIN_WRECK

@dataclass(frozen=True)
class ChainHotspot:
    """A method/attribute chain that exceeds the threshold."""

    line_number: int
    chain_length: int
    severity: str
    expression: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "chain_length": self.chain_length,
            "severity": self.severity,
            "expression": self.expression,
        }

@dataclass(frozen=True)
class MethodChainResult:
    """Aggregated method chain analysis result for a file."""

    max_chain_length: int
    total_chains: int
    hotspots: tuple[ChainHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chain_length": self.max_chain_length,
            "total_chains": self.total_chains,
            "hotspot_count": len(self.hotspots),
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }

_CHAIN_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"attribute"}),
    ".js": frozenset({"member_expression"}),
    ".jsx": frozenset({"member_expression"}),
    ".ts": frozenset({"member_expression"}),
    ".tsx": frozenset({"member_expression"}),
    ".java": frozenset({"field_access", "method_invocation"}),
    ".go": frozenset({"selector_expression"}),
}

class MethodChainAnalyzer(BaseAnalyzer):
    """Analyzes method/attribute chain length in source code."""

    def analyze_file(self, file_path: Path | str) -> MethodChainResult:
        path = Path(file_path)
        if not path.exists():
            return MethodChainResult(
                max_chain_length=0,
                total_chains=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return MethodChainResult(
                max_chain_length=0,
                total_chains=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> MethodChainResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MethodChainResult(
                max_chain_length=0,
                total_chains=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        max_len = 0
        hotspots: list[ChainHotspot] = []
        chain_types = _CHAIN_NODE_TYPES.get(ext, frozenset())

        counted_ranges: set[tuple[int, int]] = set()

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total, max_len

            if node.type in chain_types:
                parent_range = (node.start_byte, node.end_byte)
                is_outer = True
                for r in counted_ranges:
                    if (
                        parent_range[0] >= r[0]
                        and parent_range[1] <= r[1]
                    ):
                        is_outer = False
                        break

                if is_outer:
                    length = self._count_chain(node, ext)
                    if length >= 2:
                        counted_ranges.add(parent_range)
                        total += 1
                        if length > max_len:
                            max_len = length
                        if length >= DEFAULT_CHAIN_THRESHOLD:
                            text = content[
                                node.start_byte:node.end_byte
                            ].decode("utf-8", errors="replace")
                            if len(text) > 80:
                                text = text[:77] + "..."
                            hotspots.append(
                                ChainHotspot(
                                    line_number=node.start_point[0] + 1,
                                    chain_length=length,
                                    severity=_severity(length),
                                    expression=text,
                                )
                            )

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return MethodChainResult(
            max_chain_length=max_len,
            total_chains=total,
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    @staticmethod
    def _count_chain(node: tree_sitter.Node, ext: str) -> int:
        if ext == ".py":
            return _count_python_chain(node)
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            return _count_js_chain(node)
        if ext == ".java":
            return _count_java_chain(node)
        if ext == ".go":
            return _count_go_chain(node)
        return 1

def _count_python_chain(node: tree_sitter.Node) -> int:
    if node.type == "attribute":
        obj = node.child_by_field_name("object")
        if obj is not None and obj.type == "attribute":
            return _count_python_chain(obj) + 1
        if obj is not None and obj.type == "call":
            callee = obj.child_by_field_name("function")
            if callee is not None and callee.type == "attribute":
                return _count_python_chain(callee) + 1
        return 2
    if node.type == "call":
        callee = node.child_by_field_name("function")
        if callee is not None and callee.type == "attribute":
            return _count_python_chain(callee) + 1
    return 1

def _count_js_chain(node: tree_sitter.Node) -> int:
    if node.type == "member_expression":
        obj = node.child_by_field_name("object")
        if obj is not None and obj.type == "member_expression":
            return _count_js_chain(obj) + 1
        if obj is not None and obj.type == "call_expression":
            callee = obj.child_by_field_name("function")
            if callee is not None and callee.type == "member_expression":
                return _count_js_chain(callee) + 1
        return 2
    return 1

def _count_java_chain(node: tree_sitter.Node) -> int:
    if node.type == "field_access":
        obj = node.child_by_field_name("object")
        if obj is not None:
            if obj.type in ("field_access", "method_invocation"):
                return _count_java_chain(obj) + 1
        return 2
    if node.type == "method_invocation":
        obj = node.child_by_field_name("object")
        if obj is not None:
            if obj.type in ("field_access", "method_invocation"):
                return _count_java_chain(obj) + 1
        return 2
    return 1

def _count_go_chain(node: tree_sitter.Node) -> int:
    if node.type == "selector_expression":
        operand = node.child_by_field_name("operand")
        if operand is not None:
            if operand.type == "selector_expression":
                return _count_go_chain(operand) + 1
            if operand.type == "call_expression":
                func_node = operand.child_by_field_name("function")
                if (
                    func_node is not None
                    and func_node.type == "selector_expression"
                ):
                    return _count_go_chain(func_node) + 1
        return 2
    return 1
