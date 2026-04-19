"""Test Flakiness Detector.

Detects code patterns in test files that cause unreliable/flaky test results:

- sleep_wait: time.sleep(), setTimeout, Thread.sleep — timing-dependent tests
- random_usage: random.*, Math.random, uuid.*, os.urandom — non-deterministic data
- time_dependent: datetime.now(), new Date() in assertions — clock-dependent tests
- mutable_shared_state: mutable class-level variables modified by test methods

Supports Python, JavaScript/TypeScript, Java.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = setup_logger(__name__)


class FlakinessRiskLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class FlakinessFactor:
    factor_type: str
    severity: str
    message: str
    file_path: str
    line_number: int
    code_snippet: str
    suggestion: str
    language: str
    function_name: str = ""


@dataclass
class FlakinessResult:
    file_path: str
    total_factors: int = 0
    factors: list[FlakinessFactor] = field(default_factory=list)
    risk_level: str = FlakinessRiskLevel.LOW.value

    def add_factor(self, factor: FlakinessFactor) -> None:
        self.factors.append(factor)
        self.total_factors += 1
        if factor.severity == "high":
            self.risk_level = FlakinessRiskLevel.HIGH.value
        elif factor.severity == "medium" and self.risk_level != FlakinessRiskLevel.HIGH.value:
            self.risk_level = FlakinessRiskLevel.MEDIUM.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_factors": self.total_factors,
            "factors": [
                {
                    "factor_type": f.factor_type,
                    "severity": f.severity,
                    "message": f.message,
                    "line_number": f.line_number,
                    "code_snippet": f.code_snippet,
                    "suggestion": f.suggestion,
                    "language": f.language,
                    "function_name": f.function_name,
                }
                for f in self.factors
            ],
            "risk_level": self.risk_level,
        }


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(node: tree_sitter.Node) -> int:
    return node.start_point[0] + 1


def _is_test_file(file_path: str) -> bool:
    name = Path(file_path).name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name.endswith("test.java")
    )


def _walk(node: tree_sitter.Node) -> Any:
    yield node
    for child in node.children:
        yield from _walk(child)


def _find_line(source_text: str, pattern: str) -> list[tuple[int, str]]:
    lines = []
    for i, line in enumerate(source_text.split("\n"), 1):
        if pattern in line:
            lines.append((i, line.strip()))
    return lines


class FlakinessAnalyzer(BaseAnalyzer):
    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

    def analyze_file(self, file_path: str | Path) -> FlakinessResult:
        path = Path(file_path)
        ext = path.suffix
        result = FlakinessResult(file_path=str(path))

        if ext not in self.SUPPORTED_EXTENSIONS:
            return result

        if not _is_test_file(str(path)):
            return result

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return result

        try:
            source = path.read_bytes()
        except OSError as e:
            logger.debug(f"Cannot read {path}: {e}")
            return result

        tree = parser.parse(source)
        source_text = source.decode("utf-8", errors="replace")

        if ext == ".py":
            self._analyze_python(source_text, tree, source, str(path), result)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            self._analyze_javascript(source_text, tree, source, str(path), result)
        elif ext == ".java":
            self._analyze_java(source_text, tree, source, str(path), result)

        return result

    # --- Python ---

    def _analyze_python(
        self,
        source_text: str,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        self._detect_python_sleep(source_text, file_path, result)
        self._detect_python_random(source_text, file_path, result)
        self._detect_python_time(source_text, file_path, result)
        self._detect_python_mutable_class(tree, source, file_path, result)

    def _detect_python_sleep(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for line_num, line_text in _find_line(source_text, "sleep"):
            if "time.sleep" in line_text or re.search(r"\bsleep\s*\(", line_text):
                result.add_factor(FlakinessFactor(
                    factor_type="sleep_wait",
                    severity="high",
                    message="Time-based sleep in test makes it timing-dependent",
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=line_text[:120],
                    suggestion="Use mock time or event-based waiting instead of sleep",
                    language="python",
                ))

    def _detect_python_random(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for pattern in ("random.", "uuid.uuid", "os.urandom"):
            for line_num, line_text in _find_line(source_text, pattern):
                result.add_factor(FlakinessFactor(
                    factor_type="random_usage",
                    severity="medium",
                    message=f"Non-deterministic random usage: {pattern}",
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=line_text[:120],
                    suggestion="Use fixed seed or mock random generator",
                    language="python",
                ))

    def _detect_python_time(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for pattern in ("datetime.now", "datetime.today"):
            for line_num, line_text in _find_line(source_text, pattern):
                result.add_factor(FlakinessFactor(
                    factor_type="time_dependent",
                    severity="medium",
                    message="Time-dependent test using datetime.now/today",
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=line_text[:120],
                    suggestion="Use freezegun or inject fixed time",
                    language="python",
                ))

    def _detect_python_mutable_class(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        for node in _walk(tree.root_node):
            if node.type == "class_definition":
                class_name = ""
                for child in node.children:
                    if child.type == "identifier":
                        class_name = _node_text(child, source)
                        break
                if not class_name.startswith("Test"):
                    continue
                for child in node.children:
                    if child.type == "block":
                        self._check_python_class_block(child, source, file_path, result)

    def _check_python_class_block(
        self,
        block: tree_sitter.Node,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        for child in block.children:
            if child.type == "expression_statement":
                text = _node_text(child, source)
                if "=" in text and not text.strip().startswith("def "):
                    if any(
                        mut in text
                        for mut in (" = []", " = {}", " = set()", " = list(", " = dict(")
                    ):
                        result.add_factor(FlakinessFactor(
                            factor_type="mutable_shared_state",
                            severity="medium",
                            message="Mutable class-level variable shared across tests",
                            file_path=file_path,
                            line_number=_line(child),
                            code_snippet=text.split("\n")[0][:120],
                            suggestion="Use setUp() to create fresh instances per test",
                            language="python",
                        ))

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        source_text: str,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        self._detect_js_sleep(source_text, file_path, result)
        self._detect_js_random(source_text, file_path, result)
        self._detect_js_time(tree, source, file_path, result)

    def _detect_js_sleep(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for line_num, line_text in _find_line(source_text, "setTimeout"):
            result.add_factor(FlakinessFactor(
                factor_type="sleep_wait",
                severity="high",
                message="setTimeout in test is timing-dependent",
                file_path=file_path,
                line_number=line_num,
                code_snippet=line_text[:120],
                suggestion="Use fake timers or proper async/await patterns",
                language="javascript",
            ))

    def _detect_js_random(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for line_num, line_text in _find_line(source_text, "Math.random"):
            result.add_factor(FlakinessFactor(
                factor_type="random_usage",
                severity="medium",
                message="Math.random() produces non-deterministic test data",
                file_path=file_path,
                line_number=line_num,
                code_snippet=line_text[:120],
                suggestion="Use seeded random or fixed test data",
                language="javascript",
            ))

    def _detect_js_time(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        for node in _walk(tree.root_node):
            if node.type == "new_expression":
                text = _node_text(node, source)
                if "Date" in text:
                    snippet = text.split("\n")[0]
                    result.add_factor(FlakinessFactor(
                        factor_type="time_dependent",
                        severity="medium",
                        message="new Date() is time-dependent in test",
                        file_path=file_path,
                        line_number=_line(node),
                        code_snippet=snippet[:120],
                        suggestion="Use fake timers (jest.useFakeTimers or sinon)",
                        language="javascript",
                    ))

    # --- Java ---

    def _analyze_java(
        self,
        source_text: str,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        if not str(file_path).endswith("Test.java"):
            return
        self._detect_java_sleep(source_text, file_path, result)
        self._detect_java_random(tree, source, file_path, result)
        self._detect_java_mutable_shared(tree, source, file_path, result)

    def _detect_java_sleep(
        self, source_text: str, file_path: str, result: FlakinessResult,
    ) -> None:
        for line_num, line_text in _find_line(source_text, "Thread.sleep"):
            result.add_factor(FlakinessFactor(
                factor_type="sleep_wait",
                severity="high",
                message="Thread.sleep() makes test timing-dependent",
                file_path=file_path,
                line_number=line_num,
                code_snippet=line_text[:120],
                suggestion="Use Awaitility or proper synchronization",
                language="java",
            ))

    def _detect_java_random(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        for node in _walk(tree.root_node):
            if node.type == "object_creation_expression":
                text = _node_text(node, source)
                if "Random" in text:
                    snippet = text.split("\n")[0]
                    result.add_factor(FlakinessFactor(
                        factor_type="random_usage",
                        severity="medium",
                        message="Random usage produces non-deterministic test data",
                        file_path=file_path,
                        line_number=_line(node),
                        code_snippet=snippet[:120],
                        suggestion="Use fixed seed or parameterized test data",
                        language="java",
                    ))

    def _detect_java_mutable_shared(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: FlakinessResult,
    ) -> None:
        for node in _walk(tree.root_node):
            if node.type == "field_declaration":
                text = _node_text(node, source)
                if "static" in text and any(
                    mut in text
                    for mut in ("ArrayList", "HashMap", "HashSet", "List<", "Map<", "Set<")
                ):
                    snippet = text.split("\n")[0]
                    result.add_factor(FlakinessFactor(
                        factor_type="mutable_shared_state",
                        severity="medium",
                        message="Static mutable field shared across test instances",
                        file_path=file_path,
                        line_number=_line(node),
                        code_snippet=snippet[:120],
                        suggestion="Use @BeforeEach to reset or use instance fields",
                        language="java",
                    ))
