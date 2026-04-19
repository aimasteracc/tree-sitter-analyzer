"""Error Message Quality Analyzer.

Detects poor error messages in raise/throw statements. Identifies
generic, empty, or unhelpful error messages that degrade developer
experience.
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

_GENERIC_MESSAGES: frozenset[str] = frozenset({
    "error", "Error", "ERROR",
    "failed", "Failed", "FAILED",
    "failure", "Failure",
    "exception", "Exception",
    "invalid", "Invalid",
    "bad", "Bad",
    "wrong", "Wrong",
    "oops", "Oops",
    "unknown error",
    "unexpected error",
    "something went wrong",
})

def _classify_quality(message: str | None) -> str:
    if message is None or message.strip() == "":
        return "empty"
    stripped = message.strip().strip("\"'")
    if stripped.lower() in _GENERIC_MESSAGES:
        return "generic"
    if len(stripped) < 5:
        return "vague"
    return "good"

@dataclass(frozen=True)
class PoorMessage:
    """A poor error message."""

    line_number: int
    message: str
    quality: str
    error_type: str

@dataclass(frozen=True)
class ErrorMessageResult:
    """Aggregated error message quality result for a file."""

    total_raises: int
    poor_messages: int
    messages: tuple[PoorMessage, ...]
    file_path: str

class ErrorMessageQualityAnalyzer(BaseAnalyzer):
    """Analyzes error message quality in source code."""

    def analyze_file(self, file_path: Path | str) -> ErrorMessageResult:
        path = Path(file_path)
        if not path.exists():
            return ErrorMessageResult(
                total_raises=0, poor_messages=0, messages=(), file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return ErrorMessageResult(
                total_raises=0, poor_messages=0, messages=(), file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> ErrorMessageResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ErrorMessageResult(
                total_raises=0, poor_messages=0, messages=(), file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        poor: list[PoorMessage] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total

            msg_text: str | None = None
            error_type = "unknown"

            if ext == ".py":
                msg_text, error_type = self._extract_python(node, content)
            elif ext in {".js", ".ts", ".tsx", ".jsx"}:
                msg_text, error_type = self._extract_js(node, content)
            elif ext == ".java":
                msg_text, error_type = self._extract_java(node, content)
            elif ext == ".go":
                msg_text, error_type = self._extract_go(node, content)

            if msg_text is not None or self._is_raise_node(node, ext):
                total += 1
                quality = _classify_quality(msg_text)
                if quality != "good":
                    poor.append(PoorMessage(
                        line_number=node.start_point[0] + 1,
                        message=msg_text or "",
                        quality=quality,
                        error_type=error_type,
                    ))

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return ErrorMessageResult(
            total_raises=total,
            poor_messages=len(poor),
            messages=tuple(poor),
            file_path=str(path),
        )

    def _is_raise_node(self, node: tree_sitter.Node, ext: str) -> bool:
        if ext == ".py":
            return node.type == "raise_statement"
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return node.type == "throw_statement"
        if ext == ".java":
            return node.type == "throw_statement"
        if ext == ".go":
            return node.type == "call_expression"
        return False

    def _extract_python(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[str | None, str]:
        if node.type != "raise_statement":
            return None, ""
        children = node.children
        if not children:
            return None, ""

        error_type = ""
        for child in children:
            if child.type == "call":
                for arg in child.children:
                    if arg.type == "identifier":
                        error_type = content[
                            arg.start_byte:arg.end_byte
                        ].decode("utf-8", errors="replace")
                    if arg.type == "argument_list":
                        real_args = [
                            a for a in arg.children
                            if a.type not in ("(", ")", ",")
                        ]
                        if real_args:
                            return (
                                content[
                                    real_args[0].start_byte:real_args[0].end_byte
                                ].decode("utf-8", errors="replace"),
                                error_type,
                            )
            elif child.type == "identifier":
                error_type = content[
                    child.start_byte:child.end_byte
                ].decode("utf-8", errors="replace")

        return None, error_type

    def _extract_js(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[str | None, str]:
        if node.type != "throw_statement":
            return None, ""

        for child in node.children:
            if child.type == "new_expression":
                for arg in child.children:
                    if arg.type == "arguments":
                        real_args = [
                            a for a in arg.children
                            if a.type not in ("(", ")", ",")
                        ]
                        if real_args:
                            return (
                                content[
                                    real_args[0].start_byte:real_args[0].end_byte
                                ].decode("utf-8", errors="replace"),
                                "Error",
                            )
            elif child.type in ("string", "template_string"):
                return (
                    content[
                        child.start_byte:child.end_byte
                    ].decode("utf-8", errors="replace"),
                    "string",
                )
        return None, ""

    def _extract_java(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[str | None, str]:
        if node.type != "throw_statement":
            return None, ""

        for child in node.children:
            if child.type == "object_creation_expression":
                error_type = ""
                for arg in child.children:
                    if arg.type == "argument_list":
                        real_args = [
                            a for a in arg.children
                            if a.type not in ("(", ")", ",")
                        ]
                        if real_args:
                            return (
                                content[
                                    real_args[0].start_byte:real_args[0].end_byte
                                ].decode("utf-8", errors="replace"),
                                error_type or "Exception",
                            )
                    if arg.type == "type_identifier":
                        error_type = content[
                            arg.start_byte:arg.end_byte
                        ].decode("utf-8", errors="replace")
        return None, ""

    def _extract_go(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[str | None, str]:
        if node.type != "call_expression":
            return None, ""

        func_name = ""
        for child in node.children:
            if child.type in ("selector_expression", "identifier"):
                func_name = content[
                    child.start_byte:child.end_byte
                ].decode("utf-8", errors="replace")
            if child.type == "argument_list":
                if "errors" in func_name or "Errorf" in func_name or "fmt" in func_name:
                    real_args = [
                        a for a in child.children
                        if a.type not in ("(", ")", ",")
                    ]
                    if real_args:
                        return (
                            content[
                                real_args[0].start_byte:real_args[0].end_byte
                            ].decode("utf-8", errors="replace"),
                            func_name,
                        )
        return None, ""
