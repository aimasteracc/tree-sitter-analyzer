"""Tests for Debug Statement Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.debug_statement import (
    ISSUE_DEBUG_FORMATTER,
    ISSUE_DEBUG_LOG,
    ISSUE_DEBUG_PRINT,
    ISSUE_DEBUG_PRINTLN,
    DebugStatementDetector,
)


@pytest.fixture
def detector() -> DebugStatementDetector:
    return DebugStatementDetector()


# --- Python tests ---

class TestPythonAnalysis:
    def test_detects_print(self, detector: DebugStatementDetector) -> None:
        code = 'print("hello")\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].issue_type == ISSUE_DEBUG_PRINT
        assert result.statements[0].function_name == "print"

    def test_detects_pprint(self, detector: DebugStatementDetector) -> None:
        code = 'from pprint import pprint\npprint(data)\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].function_name == "pprint"

    def test_detects_breakpoint(self, detector: DebugStatementDetector) -> None:
        code = "breakpoint()\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].function_name == "breakpoint"

    def test_no_false_positive_on_function_def(self, detector: DebugStatementDetector) -> None:
        code = "def print_report(data):\n    pass\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_multiple_prints(self, detector: DebugStatementDetector) -> None:
        code = 'print("a")\nprint("b")\nprint("c")\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 3

    def test_by_type_counts(self, detector: DebugStatementDetector) -> None:
        code = 'print("a")\nprint("b")\nbreakpoint()\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.by_type[ISSUE_DEBUG_PRINT] == 3

    def test_clean_file(self, detector: DebugStatementDetector) -> None:
        code = "import logging\nlogger = logging.getLogger(__name__)\nlogger.info('hello')\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- JS/TS tests ---

class TestJSAnalysis:
    def test_detects_console_log(self, detector: DebugStatementDetector) -> None:
        code = 'console.log("debug");\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].issue_type == ISSUE_DEBUG_LOG
        assert result.statements[0].function_name == "console.log"

    def test_detects_console_debug(self, detector: DebugStatementDetector) -> None:
        code = 'console.debug("value", x);\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].function_name == "console.debug"

    def test_detects_debugger_statement(self, detector: DebugStatementDetector) -> None:
        code = "function foo() {\n  debugger;\n}\n"
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].function_name == "debugger"

    def test_detects_console_info(self, detector: DebugStatementDetector) -> None:
        code = 'console.info("info");\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_no_false_positive_on_custom_console(self, detector: DebugStatementDetector) -> None:
        code = 'myConsole.log("test");\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_typescript_file(self, detector: DebugStatementDetector) -> None:
        code = 'console.log("debug");\n'
        with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1


# --- Java tests ---

class TestJavaAnalysis:
    def test_detects_system_out_println(self, detector: DebugStatementDetector) -> None:
        code = 'public class Test {\n  void foo() {\n    System.out.println("debug");\n  }\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].issue_type == ISSUE_DEBUG_PRINTLN
        assert result.statements[0].function_name == "System.out.println"

    def test_detects_system_err_println(self, detector: DebugStatementDetector) -> None:
        code = 'public class Test {\n  void foo() {\n    System.err.println("error");\n  }\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_detects_print_stack_trace(self, detector: DebugStatementDetector) -> None:
        code = 'public class Test {\n  void foo() {\n    e.printStackTrace();\n  }\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_no_false_positive_on_logger(self, detector: DebugStatementDetector) -> None:
        code = 'public class Test {\n  void foo() {\n    logger.info("hello");\n  }\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- Go tests ---

class TestGoAnalysis:
    def test_detects_fmt_println(self, detector: DebugStatementDetector) -> None:
        code = 'package main\nimport "fmt"\nfunc main() {\n  fmt.Println("debug")\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.statements[0].issue_type == ISSUE_DEBUG_FORMATTER
        assert result.statements[0].function_name == "fmt.Println"

    def test_detects_fmt_printf(self, detector: DebugStatementDetector) -> None:
        code = 'package main\nimport "fmt"\nfunc main() {\n  fmt.Printf("val: %d", x)\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_detects_log_println(self, detector: DebugStatementDetector) -> None:
        code = 'package main\nimport "log"\nfunc main() {\n  log.Println("msg")\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_no_false_positive_on_custom_fmt(self, detector: DebugStatementDetector) -> None:
        code = 'package main\nfunc main() {\n  myFmt.Println("msg")\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- Edge cases ---

class TestEdgeCases:
    def test_nonexistent_file(self, detector: DebugStatementDetector) -> None:
        result = detector.analyze_file("/nonexistent/file.py")
        assert result.total_count == 0
        assert result.statements == ()

    def test_unsupported_extension(self, detector: DebugStatementDetector) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write('print("hello")')
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_empty_file(self, detector: DebugStatementDetector) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_to_dict(self, detector: DebugStatementDetector) -> None:
        code = 'print("test")\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        d = result.to_dict()
        assert "file_path" in d
        assert "statements" in d
        assert "total_count" in d
        assert "by_type" in d
        assert d["total_count"] == 1

    def test_statement_to_dict(self, detector: DebugStatementDetector) -> None:
        code = 'print("test")\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        d = result.statements[0].to_dict()
        assert "line" in d
        assert "issue_type" in d
        assert "function_name" in d
        assert "severity" in d
        assert "message" in d
        assert "suggestion" in d
