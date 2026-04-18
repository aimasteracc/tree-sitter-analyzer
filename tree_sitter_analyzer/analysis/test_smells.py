"""
Test Smell Detector.

Detects anti-patterns in test code that make tests unreliable or give
false confidence. Catches the gap between "code is covered" and "code
is actually tested".

Smells detected:
  - assert_none: test body has zero assertions
  - broad_except: test catches generic Exception / bare except
  - sleep_in_test: time.sleep() / setTimeout() inside test functions
  - low_assert: test has fewer than min_assertions (default 1)
"""
from __future__ import annotations

from dataclasses import dataclass
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

SMELL_ASSERT_NONE = "assert_none"
SMELL_BROAD_EXCEPT = "broad_except"
SMELL_SLEEP_IN_TEST = "sleep_in_test"
SMELL_LOW_ASSERT = "low_assert"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_SMELL_SEVERITY: dict[str, str] = {
    SMELL_ASSERT_NONE: SEVERITY_HIGH,
    SMELL_BROAD_EXCEPT: SEVERITY_MEDIUM,
    SMELL_SLEEP_IN_TEST: SEVERITY_MEDIUM,
    SMELL_LOW_ASSERT: SEVERITY_LOW,
}

_PY_TEST_DECORATORS: frozenset[str] = frozenset({
    "pytest.mark.parametrize",
    "pytest.fixture",
})

_PY_ASSERT_TYPES: frozenset[str] = frozenset({
    "assert_statement",
})

_PY_BUILTIN_ASSERT_FUNCS: frozenset[str] = frozenset({
    "assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
    "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
    "assertIn", "assertNotIn", "assertRaises", "assertWarns",
    "assertAlmostEqual", "assertNotAlmostEqual", "assertGreater",
    "assertLess", "assertRegex", "assertCountEqual",
})

_PY_SLEEP_PATTERNS: frozenset[str] = frozenset({
    "time.sleep",
})


@dataclass(frozen=True)
class TestSmell:
    """A single smell detected in a test function."""
    smell_type: str
    function_name: str
    line_number: int
    severity: str
    detail: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "smell_type": self.smell_type,
            "function_name": self.function_name,
            "line_number": self.line_number,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TestFunction:
    """Analysis result for a single test function."""
    name: str
    start_line: int
    end_line: int
    assertion_count: int
    has_broad_except: bool
    has_sleep: bool
    smells: tuple[TestSmell, ...]

    def to_dict(self) -> dict[str, str | int | bool | tuple[dict[str, str | int], ...]]:
        return {
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "assertion_count": self.assertion_count,
            "has_broad_except": self.has_broad_except,
            "has_sleep": self.has_sleep,
            "smells": tuple(s.to_dict() for s in self.smells),
        }


@dataclass(frozen=True)
class TestSmellResult:
    """Per-file analysis result."""
    file_path: str
    test_functions: tuple[TestFunction, ...]
    total_tests: int
    total_smells: int
    smell_counts: dict[str, int]

    def to_dict(self) -> dict[str, str | int | dict[str, int] | tuple[dict[str, str | int | bool | tuple[dict[str, str | int], ...]], ...]]:
        return {
            "file_path": self.file_path,
            "test_functions": tuple(f.to_dict() for f in self.test_functions),
            "total_tests": self.total_tests,
            "total_smells": self.total_smells,
            "smell_counts": self.smell_counts,
        }

    def get_smells_by_type(self, smell_type: str) -> tuple[TestSmell, ...]:
        return tuple(
            s for f in self.test_functions for s in f.smells
            if s.smell_type == smell_type
        )

    def get_high_severity_smells(self) -> tuple[TestSmell, ...]:
        return tuple(
            s for f in self.test_functions for s in f.smells
            if s.severity == SEVERITY_HIGH
        )


def _empty_result(file_path: str) -> TestSmellResult:
    return TestSmellResult(
        file_path=file_path,
        test_functions=(),
        total_tests=0,
        total_smells=0,
        smell_counts={},
    )


def _severity_for(smell_type: str) -> str:
    return _SMELL_SEVERITY.get(smell_type, SEVERITY_LOW)


class TestSmellDetector:
    """Detects test smells across Python, JS/TS, Java, and Go."""

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}
        self._languages: dict[str, tree_sitter.Language] = {}

    def _get_parser(self, ext: str) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
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

    def analyze_file(
        self,
        file_path: Path | str,
        min_assertions: int = 1,
    ) -> TestSmellResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))
        if not self._is_test_file(path, ext):
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            functions = self._extract_python(tree.root_node, content, min_assertions)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            functions = self._extract_javascript(tree.root_node, content, min_assertions)
        elif ext == ".java":
            functions = self._extract_java(tree.root_node, content, min_assertions)
        elif ext == ".go":
            functions = self._extract_go(tree.root_node, content, min_assertions)
        else:
            functions = []

        total_smells = sum(len(f.smells) for f in functions)
        smell_counts: dict[str, int] = {}
        for f in functions:
            for s in f.smells:
                smell_counts[s.smell_type] = smell_counts.get(s.smell_type, 0) + 1

        return TestSmellResult(
            file_path=str(path),
            test_functions=tuple(functions),
            total_tests=len(functions),
            total_smells=total_smells,
            smell_counts=smell_counts,
        )

    @staticmethod
    def _is_test_file(path: Path, ext: str) -> bool:
        name = path.name.lower()
        if ext == ".py":
            return name.startswith("test_") or name.endswith("_test.py") or name == "tests.py"
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return name.startswith("test_") or name.endswith("_test.js") or name.endswith("_test.ts") or name.endswith(".test.js") or name.endswith(".test.ts") or name.endswith(".spec.js") or name.endswith(".spec.ts")
        if ext == ".java":
            return name.endswith("test.java") or name.endswith("tests.java") or name.endswith("it.java")
        if ext == ".go":
            return name.endswith("_test.go")
        return False

    # --- Python ---

    def _extract_python(
        self,
        root: tree_sitter.Node,
        content: bytes,
        min_assertions: int,
    ) -> list[TestFunction]:
        results: list[TestFunction] = []
        self._walk_python(root, content, results, min_assertions, in_class=False)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunction],
        min_assertions: int,
        in_class: bool,
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                self._walk_python(child, content, results, min_assertions, in_class)
            return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                if name.startswith("Test"):
                    body = node.child_by_field_name("body")
                    if body is not None:
                        for child in body.children:
                            self._walk_python(child, content, results, min_assertions, in_class=True)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name.startswith("test_"):
                fn = self._analyze_python_function(node, content, name, min_assertions)
                results.append(fn)
            return

        for child in node.children:
            self._walk_python(child, content, results, min_assertions, in_class)

    def _analyze_python_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        name: str,
        min_assertions: int,
    ) -> TestFunction:
        body = node.child_by_field_name("body")
        assert_count = 0
        has_broad_except = False
        has_sleep = False
        smells: list[TestSmell] = []

        if body is not None:
            assert_count = self._count_python_asserts(body, content)
            has_broad_except = self._check_python_broad_except(body)
            has_sleep = self._check_python_sleep(body, content)

        if assert_count == 0:
            smells.append(TestSmell(
                smell_type=SMELL_ASSERT_NONE,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_ASSERT_NONE),
                detail="Test has zero assertions",
            ))

        if has_broad_except:
            smells.append(TestSmell(
                smell_type=SMELL_BROAD_EXCEPT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_BROAD_EXCEPT),
                detail="Test catches generic Exception",
            ))

        if has_sleep:
            smells.append(TestSmell(
                smell_type=SMELL_SLEEP_IN_TEST,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SLEEP_IN_TEST),
                detail="Test contains time.sleep()",
            ))

        if assert_count > 0 and assert_count < min_assertions:
            smells.append(TestSmell(
                smell_type=SMELL_LOW_ASSERT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_LOW_ASSERT),
                detail=f"Test has only {assert_count} assertion(s), minimum is {min_assertions}",
            ))

        return TestFunction(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=assert_count,
            has_broad_except=has_broad_except,
            has_sleep=has_sleep,
            smells=tuple(smells),
        )

    def _count_python_asserts(self, body: tree_sitter.Node, content: bytes) -> int:
        count = 0
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type in _PY_ASSERT_TYPES:
                count += 1
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text in _PY_BUILTIN_ASSERT_FUNCS or func_text.startswith("self.assert"):
                        count += 1
                    if func_text.startswith("pytest.raises") or func_text.startswith("pytest.warns") or func_text.startswith("pytest.deprecated_call"):
                        count += 1
            stack.extend(node.children)
        return count

    def _check_python_broad_except(self, body: tree_sitter.Node) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "except_clause":
                for child in node.children:
                    if child.type == "identifier":
                        text = child.text.decode("utf-8", errors="replace") if child.text else ""
                        if text == "Exception":
                            return True
                    if child.type == "attribute":
                        text = child.text.decode("utf-8", errors="replace") if child.text else ""
                        if text == "Exception":
                            return True
                has_type = False
                for child in node.children:
                    if child.type in ("identifier", "attribute", "as_pattern"):
                        has_type = True
                if not has_type:
                    return True
            stack.extend(node.children)
        return False

    def _check_python_sleep(self, body: tree_sitter.Node, content: bytes) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text == "time.sleep" or func_text == "sleep":
                        return True
            stack.extend(node.children)
        return False

    # --- JavaScript/TypeScript ---

    def _extract_javascript(
        self,
        root: tree_sitter.Node,
        content: bytes,
        min_assertions: int,
    ) -> list[TestFunction]:
        results: list[TestFunction] = []
        self._walk_javascript(root, content, results, min_assertions)
        return results

    def _walk_javascript(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunction],
        min_assertions: int,
    ) -> None:
        if node.type in ("function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name.startswith("test") or name.startswith("it") or name.startswith("should"):
                fn = self._analyze_js_function(node, content, name, min_assertions)
                results.append(fn)
            return

        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node is not None:
                func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                if func_text in ("test", "it") or func_text.startswith("test.") or func_text.startswith("it."):
                    callback = None
                    for child in node.children:
                        if child.type in ("arrow_function", "function_expression"):
                            callback = child
                            break
                        if child.type == "arguments":
                            for arg in child.children:
                                if arg.type in ("arrow_function", "function_expression"):
                                    callback = arg
                                    break
                    if callback is not None:
                        label = ""
                        args_node = None
                        for child in node.children:
                            if child.type == "arguments":
                                args_node = child
                                break
                        if args_node is not None:
                            for arg in args_node.children:
                                if arg.type in ("string", "string_fragment", "template_string"):
                                    label = content[arg.start_byte:arg.end_byte].decode("utf-8", errors="replace").strip("'\"`")
                                    break
                        fn_name = f"{func_text}({label})" if label else func_text
                        fn = self._analyze_js_function(callback, content, fn_name, min_assertions)
                        results.append(fn)

        for child in node.children:
            self._walk_javascript(child, content, results, min_assertions)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        name: str,
        min_assertions: int,
    ) -> TestFunction:
        body = node.child_by_field_name("body")
        assert_count = 0
        has_broad_except = False
        has_sleep = False
        smells: list[TestSmell] = []

        if body is not None:
            assert_count = self._count_js_asserts(body, content)
            has_broad_except = self._check_js_broad_except(body)
            has_sleep = self._check_js_sleep(body, content)

        if assert_count == 0:
            smells.append(TestSmell(
                smell_type=SMELL_ASSERT_NONE,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_ASSERT_NONE),
                detail="Test has zero assertions",
            ))

        if has_broad_except:
            smells.append(TestSmell(
                smell_type=SMELL_BROAD_EXCEPT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_BROAD_EXCEPT),
                detail="Test catches all exceptions",
            ))

        if has_sleep:
            smells.append(TestSmell(
                smell_type=SMELL_SLEEP_IN_TEST,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SLEEP_IN_TEST),
                detail="Test contains setTimeout/sleep",
            ))

        if assert_count > 0 and assert_count < min_assertions:
            smells.append(TestSmell(
                smell_type=SMELL_LOW_ASSERT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_LOW_ASSERT),
                detail=f"Test has only {assert_count} assertion(s), minimum is {min_assertions}",
            ))

        return TestFunction(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=assert_count,
            has_broad_except=has_broad_except,
            has_sleep=has_sleep,
            smells=tuple(smells),
        )

    def _count_js_asserts(self, body: tree_sitter.Node, content: bytes) -> int:
        count = 0
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text in ("assert", "expect", "assertTrue", "assertFalse", "assertEqual", "assertNotNull", "fail") or func_text.startswith("assert.") or func_text.startswith("expect("):
                        count += 1
            stack.extend(node.children)
        return count

    def _check_js_broad_except(self, body: tree_sitter.Node) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "catch_clause":
                param = node.child_by_field_name("parameter")
                if param is not None:
                    pass
                else:
                    return True
                annotation = node.child_by_field_name("type_annotation")
                if annotation is None:
                    return True
            stack.extend(node.children)
        return False

    def _check_js_sleep(self, body: tree_sitter.Node, content: bytes) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text in ("setTimeout", "sleep"):
                        return True
            stack.extend(node.children)
        return False

    # --- Java ---

    def _extract_java(
        self,
        root: tree_sitter.Node,
        content: bytes,
        min_assertions: int,
    ) -> list[TestFunction]:
        results: list[TestFunction] = []
        self._walk_java(root, content, results, min_assertions)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunction],
        min_assertions: int,
    ) -> None:
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name.startswith("test") or name.startswith("should") or name.startswith("verify"):
                fn = self._analyze_java_method(node, content, name, min_assertions)
                results.append(fn)
            return

        for child in node.children:
            self._walk_java(child, content, results, min_assertions)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        name: str,
        min_assertions: int,
    ) -> TestFunction:
        body = node.child_by_field_name("body")
        assert_count = 0
        has_broad_except = False
        has_sleep = False
        smells: list[TestSmell] = []

        if body is not None:
            assert_count = self._count_java_asserts(body, content)
            has_broad_except = self._check_java_broad_except(body)
            has_sleep = self._check_java_sleep(body, content)

        if assert_count == 0:
            smells.append(TestSmell(
                smell_type=SMELL_ASSERT_NONE,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_ASSERT_NONE),
                detail="Test has zero assertions",
            ))

        if has_broad_except:
            smells.append(TestSmell(
                smell_type=SMELL_BROAD_EXCEPT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_BROAD_EXCEPT),
                detail="Test catches generic Exception",
            ))

        if has_sleep:
            smells.append(TestSmell(
                smell_type=SMELL_SLEEP_IN_TEST,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SLEEP_IN_TEST),
                detail="Test contains Thread.sleep()",
            ))

        if assert_count > 0 and assert_count < min_assertions:
            smells.append(TestSmell(
                smell_type=SMELL_LOW_ASSERT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_LOW_ASSERT),
                detail=f"Test has only {assert_count} assertion(s), minimum is {min_assertions}",
            ))

        return TestFunction(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=assert_count,
            has_broad_except=has_broad_except,
            has_sleep=has_sleep,
            smells=tuple(smells),
        )

    def _count_java_asserts(self, body: tree_sitter.Node, content: bytes) -> int:
        count = 0
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "method_invocation":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name_text = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    if name_text in ("assertEquals", "assertTrue", "assertFalse", "assertNotNull",
                                     "assertNull", "assertSame", "assertNotSame", "assertArrayEquals",
                                     "assertThrows", "assertTimeout", "assertTimeoutPreemptively",
                                     "assertThat", "fail", "verify"):
                        count += 1
            stack.extend(node.children)
        return count

    def _check_java_broad_except(self, body: tree_sitter.Node) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "catch_clause":
                type_node = node.child_by_field_name("type")
                if type_node is not None:
                    type_text = type_node.text.decode("utf-8", errors="replace") if type_node.text else ""
                    if type_text == "Exception" or type_text == "Throwable":
                        return True
                else:
                    return True
            stack.extend(node.children)
        return False

    def _check_java_sleep(self, body: tree_sitter.Node, content: bytes) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "method_invocation":
                obj_node = node.child_by_field_name("object")
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name_text = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    if name_text == "sleep":
                        if obj_node is not None:
                            obj_text = content[obj_node.start_byte:obj_node.end_byte].decode("utf-8", errors="replace")
                            if obj_text == "Thread":
                                return True
                        else:
                            return True
            stack.extend(node.children)
        return False

    # --- Go ---

    def _extract_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        min_assertions: int,
    ) -> list[TestFunction]:
        results: list[TestFunction] = []
        self._walk_go(root, content, results, min_assertions)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunction],
        min_assertions: int,
    ) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name.startswith("Test"):
                fn = self._analyze_go_function(node, content, name, min_assertions)
                results.append(fn)
            return

        for child in node.children:
            self._walk_go(child, content, results, min_assertions)

    def _analyze_go_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        name: str,
        min_assertions: int,
    ) -> TestFunction:
        body = node.child_by_field_name("body")
        assert_count = 0
        has_sleep = False
        smells: list[TestSmell] = []

        if body is not None:
            assert_count = self._count_go_asserts(body, content)
            has_sleep = self._check_go_sleep(body, content)

        if assert_count == 0:
            smells.append(TestSmell(
                smell_type=SMELL_ASSERT_NONE,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_ASSERT_NONE),
                detail="Test has zero assertions",
            ))

        if has_sleep:
            smells.append(TestSmell(
                smell_type=SMELL_SLEEP_IN_TEST,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SLEEP_IN_TEST),
                detail="Test contains time.Sleep()",
            ))

        if assert_count > 0 and assert_count < min_assertions:
            smells.append(TestSmell(
                smell_type=SMELL_LOW_ASSERT,
                function_name=name,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_LOW_ASSERT),
                detail=f"Test has only {assert_count} assertion(s), minimum is {min_assertions}",
            ))

        return TestFunction(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=assert_count,
            has_broad_except=False,
            has_sleep=has_sleep,
            smells=tuple(smells),
        )

    def _count_go_asserts(self, body: tree_sitter.Node, content: bytes) -> int:
        count = 0
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text in ("t.Fatal", "t.Fatalf", "t.Error", "t.Errorf",
                                     "assert.Equal", "assert.NotEqual", "assert.True", "assert.False",
                                     "assert.Nil", "assert.NotNil", "assert.NoError",
                                     "require.Equal", "require.NoError", "require.NotNil"):
                        count += 1
            stack.extend(node.children)
        return count

    def _check_go_sleep(self, body: tree_sitter.Node, content: bytes) -> bool:
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    func_text = content[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                    if func_text == "time.Sleep":
                        return True
            stack.extend(node.children)
        return False
