#!/usr/bin/env python3
"""
Test Coverage Analyzer.

Identifies code elements that lack test coverage by analyzing source code
structure and comparing against test files. Uses AST-based analysis without
requiring pytest execution.

Supports:
- Source element extraction (functions, classes, methods)
- Test file detection by naming patterns
- Test reference extraction from test bodies
- Gap analysis: source_elements - tested_elements
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class ElementType(Enum):
    """Type of code element."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


@dataclass(frozen=True)
class SourceElement:
    """A testable element from source code."""

    name: str
    element_type: ElementType
    line: int
    file_path: str

    def __str__(self) -> str:
        return f"{self.name}:{self.line} ({self.element_type.value})"


@dataclass
class TestCoverageResult:
    """Test coverage analysis result for a file."""

    source_file: str
    language: str
    total_elements: int
    tested_elements: int
    untested_elements: list[SourceElement]
    coverage_percent: float

    @property
    def is_fully_covered(self) -> bool:
        return self.coverage_percent == 100.0

    @property
    def coverage_grade(self) -> str:
        if self.coverage_percent >= 80:
            return "A"
        elif self.coverage_percent >= 60:
            return "B"
        elif self.coverage_percent >= 40:
            return "C"
        elif self.coverage_percent >= 20:
            return "D"
        return "F"


class TestCoverageAnalyzer:
    """
    Analyzes test coverage by comparing source code elements against test files.

    Uses AST-based analysis to identify:
    - Functions, classes, methods in source files
    - Test functions and their referenced symbols
    - Coverage gaps: untested elements
    """

    # Test file patterns
    TEST_PATTERNS = [
        "test_*.py",
        "*_test.py",
        "test_*.js",
        "*_test.js",
        "test_*.ts",
        "*_test.ts",
    ]

    # Test directory patterns
    TEST_DIR_PATTERNS = [
        "tests",
        "test",
        "__tests__",
        "spec",
    ]

    def __init__(self) -> None:
        """Initialize the analyzer."""
        pass

    def is_test_file(self, file_path: str) -> bool:
        """
        Check if a file is a test file.

        Args:
            file_path: Path to the file

        Returns:
            True if the file matches test patterns
        """
        path = Path(file_path)
        filename = path.name

        # Check filename patterns
        for pattern in self.TEST_PATTERNS:
            if path.match(pattern):
                return True

        # Check if file is in a test directory
        for part in path.parts:
            if part.lower() in self.TEST_DIR_PATTERNS:
                return True

        return False

    def extract_testable_elements(
        self, language: str, content: str, file_path: str
    ) -> list[SourceElement]:
        """
        Extract testable elements from source code.

        Args:
            language: Programming language
            content: File content
            file_path: Path to the source file

        Returns:
            List of SourceElement objects
        """
        import tree_sitter

        # Get tree-sitter language for the given language name
        ts_language = self._get_tree_sitter_language(language)
        if ts_language is None:
            logger.warning(f"Unsupported language: {language}")
            return []

        # Parse with tree-sitter
        try:
            parser = tree_sitter.Parser()
            parser.language = ts_language
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

        # Extract elements based on language
        elements: list[SourceElement] = []

        if language in ("python", "py"):
            elements.extend(self._extract_python_elements(tree, file_path))
        elif language in ("javascript", "js", "typescript", "ts"):
            elements.extend(self._extract_javascript_elements(tree, file_path))
        elif language in ("java",):
            elements.extend(self._extract_java_elements(tree, file_path))
        elif language in ("go",):
            elements.extend(self._extract_go_elements(tree, file_path))

        return elements

    def _get_tree_sitter_language(self, language: str):
        """Get tree-sitter Language object for the given language name."""
        import tree_sitter

        try:
            if language in ("python", "py"):
                import tree_sitter_python as tspython
                language_capsule = tspython.language()
            elif language in ("javascript", "js"):
                import tree_sitter_javascript as tsjs
                language_capsule = tsjs.language()
            elif language in ("typescript", "ts"):
                import tree_sitter_typescript as tsts
                language_capsule = tsts.language()
            elif language in ("java",):
                import tree_sitter_java as tsjava
                language_capsule = tsjava.language()
            elif language in ("go",):
                import tree_sitter_go as tsgo
                language_capsule = tsgo.language()
            else:
                return None

            return tree_sitter.Language(language_capsule)
        except ImportError as e:
            logger.warning(f"tree-sitter-{language} not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to load {language} language: {e}")
            return None

    def _extract_python_elements(
        self, tree, file_path: str
    ) -> list[SourceElement]:
        """Extract Python functions and classes."""
        import tree_sitter

        elements: list[SourceElement] = []

        def traverse(node: tree_sitter.Node, parent_class: str | None = None) -> None:
            if node.type == "function_definition":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                element_type = ElementType.METHOD if parent_class else ElementType.FUNCTION
                elements.append(
                    SourceElement(
                        name=name,
                        element_type=element_type,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )
            elif node.type == "class_definition":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                elements.append(
                    SourceElement(
                        name=name,
                        element_type=ElementType.CLASS,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )

                # Traverse class methods
                for child in node.children:
                    if child.type == "block":
                        for grandchild in child.children:
                            if grandchild.type == "function_definition":
                                traverse(grandchild, name)
            else:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return elements

    def _extract_javascript_elements(
        self, tree, file_path: str
    ) -> list[SourceElement]:
        """Extract JavaScript/TypeScript functions and classes."""
        import tree_sitter

        elements: list[SourceElement] = []

        def traverse(node: tree_sitter.Node, parent_class: str | None = None) -> None:
            if node.type in ("function_declaration", "function_expression"):
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                element_type = ElementType.METHOD if parent_class else ElementType.FUNCTION
                if name:  # Anonymous functions skip
                    elements.append(
                        SourceElement(
                            name=name,
                            element_type=element_type,
                            line=node.start_point[0] + 1,
                            file_path=file_path,
                        )
                    )
            elif node.type == "class_declaration":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                elements.append(
                    SourceElement(
                        name=name,
                        element_type=ElementType.CLASS,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )

                # Traverse class methods
                for child in node.children:
                    if child.type == "class_body":
                        for grandchild in child.children:
                            if grandchild.type == "method_definition":
                                traverse(grandchild, name)
            else:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return elements

    def _extract_java_elements(self, tree, file_path: str) -> list[SourceElement]:
        """Extract Java classes and methods."""
        import tree_sitter

        elements: list[SourceElement] = []

        def traverse(node: tree_sitter.Node, parent_class: str | None = None) -> None:
            if node.type == "method_declaration":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                element_type = ElementType.METHOD if parent_class else ElementType.FUNCTION
                elements.append(
                    SourceElement(
                        name=name,
                        element_type=element_type,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )
            elif node.type == "class_declaration":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                elements.append(
                    SourceElement(
                        name=name,
                        element_type=ElementType.CLASS,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )

                # Traverse class methods
                for child in node.children:
                    if child.type == "class_body":
                        for grandchild in child.children:
                            if grandchild.type == "method_declaration":
                                traverse(grandchild, name)
            else:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return elements

    def _extract_go_elements(self, tree, file_path: str) -> list[SourceElement]:
        """Extract Go functions and methods."""
        import tree_sitter

        elements: list[SourceElement] = []

        def traverse(node: tree_sitter.Node, parent_class: str | None = None) -> None:
            if node.type == "function_declaration":
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8")
                        break

                # Check if receiver exists (method)
                has_receiver = any(
                    c.type == "parameter_list" and c.children
                    for c in node.children
                )
                element_type = ElementType.METHOD if has_receiver else ElementType.FUNCTION

                elements.append(
                    SourceElement(
                        name=name,
                        element_type=element_type,
                        line=node.start_point[0] + 1,
                        file_path=file_path,
                    )
                )
            else:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return elements

    def extract_test_references(self, content: str) -> set[str]:
        """
        Extract symbol references from test code.

        Args:
            content: Test file content

        Returns:
            Set of referenced symbol names
        """
        import re

        references: set[str] = set()

        # Common test patterns:
        # - assert func_name(...)
        # - ClassName(...)
        # - mock.patch("module.func_name")
        # - describe("func_name", ...)
        # - test("func_name does X", ...)

        patterns = [
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",  # Function calls
            r"\b([A-Z][a-zA-Z0-9_]*)\s*\(",  # Class instantiations
            r'["\'](?:[\w.]+)?\.?([A-Za-z_][A-Za-z0-9_]*)["\']',  # String references
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            references.update(matches)

        # Filter out common test keywords
        test_keywords = {
            "assert",
            "test",
            "it",
            "describe",
            "before",
            "after",
            "setUp",
            "tearDown",
            "given",
            "when",
            "then",
            "expect",
            "should",
            "mock",
            "patch",
            "return",
            "if",
            "else",
            "for",
            "while",
            "with",
            "def",
            "class",
            "import",
            "from",
            "True",
            "False",
            "None",
            "self",
        }

        return references - test_keywords

    def analyze_file(
        self,
        file_path: str,
        test_files: list[str] | None = None,
    ) -> TestCoverageResult:
        """
        Analyze test coverage for a single source file.

        Args:
            file_path: Path to the source file
            test_files: Optional list of test file paths to search

        Returns:
            TestCoverageResult with coverage information
        """
        source_path = Path(file_path)

        # Detect language
        language = self._detect_language(file_path)

        # Read source content
        try:
            source_content = source_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return TestCoverageResult(
                source_file=file_path,
                language=language,
                total_elements=0,
                tested_elements=0,
                untested_elements=[],
                coverage_percent=0.0,
            )

        # Extract source elements
        source_elements = self.extract_testable_elements(
            language, source_content, file_path
        )

        if not source_elements:
            return TestCoverageResult(
                source_file=file_path,
                language=language,
                total_elements=0,
                tested_elements=0,
                untested_elements=[],
                coverage_percent=100.0,  # No elements = fully covered
            )

        # Extract test references
        tested_names: set[str] = set()

        if test_files:
            for test_file in test_files:
                try:
                    test_content = Path(test_file).read_text(encoding="utf-8")
                    refs = self.extract_test_references(test_content)
                    tested_names.update(refs)
                except Exception:
                    pass

        # Match tested elements
        untested: list[SourceElement] = []
        tested_count = 0

        for element in source_elements:
            if element.name in tested_names:
                tested_count += 1
            else:
                untested.append(element)

        coverage_percent = (
            (tested_count / len(source_elements) * 100) if source_elements else 100.0
        )

        return TestCoverageResult(
            source_file=file_path,
            language=language,
            total_elements=len(source_elements),
            tested_elements=tested_count,
            untested_elements=untested,
            coverage_percent=round(coverage_percent, 1),
        )

    def analyze_project(
        self, project_root: str
    ) -> dict[str, TestCoverageResult]:
        """
        Analyze test coverage for an entire project.

        Args:
            project_root: Path to the project root

        Returns:
            Dictionary mapping file paths to TestCoverageResult
        """
        project_path = Path(project_root)
        results: dict[str, TestCoverageResult] = {}

        # Find all source files
        source_extensions = [".py", ".js", ".ts", ".java", ".go"]

        source_files: list[Path] = []
        for ext in source_extensions:
            source_files.extend(project_path.rglob(f"*{ext}"))

        # Find test files
        test_files: list[Path] = []
        for path in source_files:
            if self.is_test_file(str(path)):
                test_files.append(path)

        # Analyze each source file
        for source_file in source_files:
            if not self.is_test_file(str(source_file)):
                result = self.analyze_file(
                    str(source_file),
                    test_files=[str(tf) for tf in test_files],
                )
                results[str(source_file)] = result

        return results

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()

        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
        }

        return mapping.get(ext, "unknown")
