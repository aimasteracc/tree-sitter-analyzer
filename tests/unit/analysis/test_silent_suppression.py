"""Tests for Silent Error Suppression Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.silent_suppression import (
    ISSUE_LOGGING_ONLY,
    ISSUE_SILENT,
    SilentSuppressionAnalyzer,
)

ANALYZER = SilentSuppressionAnalyzer()


class TestPythonSilentSuppression:

    def test_except_pass(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    do_something()\n"
            "except Exception:\n"
            "    pass\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "pass"
            for i in result.issues
        )

    def test_except_continue(self, tmp_path: Path) -> None:
        code = (
            "for item in items:\n"
            "    try:\n"
            "        process(item)\n"
            "    except Exception:\n"
            "        continue\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "continue"
            for i in result.issues
        )

    def test_except_bare_return(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    do_something()\n"
            "except Exception:\n"
            "    return\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "return"
            for i in result.issues
        )

    def test_except_return_none(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    return fetch_data()\n"
            "except Exception:\n"
            "    return None\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and "None" in i.handler_type
            for i in result.issues
        )

    def test_except_return_false(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    return check()\n"
            "except Exception:\n"
            "    return False\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and "False" in i.handler_type
            for i in result.issues
        )

    def test_except_logging_only(self, tmp_path: Path) -> None:
        code = (
            "import logging\n"
            "try:\n"
            "    do_something()\n"
            "except Exception as e:\n"
            "    logging.error(f'Failed: {e}')\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_LOGGING_ONLY
            for i in result.issues
        )

    def test_except_logger_only(self, tmp_path: Path) -> None:
        code = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "try:\n"
            "    do_something()\n"
            "except Exception as e:\n"
            "    logger.warning(f'Failed: {e}')\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_LOGGING_ONLY
            for i in result.issues
        )

    def test_except_empty(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    do_something()\n"
            "except Exception:\n"
            "    pass\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.handler_type == "pass" for i in result.issues)

    def test_except_with_reraise_is_ok(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    do_something()\n"
            "except Exception as e:\n"
            "    raise ValueError('bad') from e\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_except_with_meaningful_handling_is_ok(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    do_something()\n"
            "except Exception as e:\n"
            "    cleanup()\n"
            "    raise\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_except_with_state_update_is_ok(self, tmp_path: Path) -> None:
        code = (
            "class Handler:\n"
            "    def process(self):\n"
            "        try:\n"
            "            self.result = compute()\n"
            "        except Exception:\n"
            "            self.failed = True\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_clean_file_no_issues(self, tmp_path: Path) -> None:
        code = (
            "def hello():\n"
            "    print('hello')\n"
        )
        f = tmp_path / "test.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaScriptSilentSuppression:

    def test_empty_catch(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    doSomething();\n"
            "} catch (e) {\n"
            "}\n"
        )
        f = tmp_path / "test.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "empty"
            for i in result.issues
        )

    def test_console_log_only(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    doSomething();\n"
            "} catch (e) {\n"
            "    console.error(e);\n"
            "}\n"
        )
        f = tmp_path / "test.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_LOGGING_ONLY for i in result.issues)

    def test_return_null_in_catch(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    return fetchData();\n"
            "} catch (e) {\n"
            "    return null;\n"
            "}\n"
        )
        f = tmp_path / "test.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            "null" in i.handler_type for i in result.issues
        )

    def test_catch_with_rethrow_is_ok(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    doSomething();\n"
            "} catch (e) {\n"
            "    throw new Error('Failed');\n"
            "}\n"
        )
        f = tmp_path / "test.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_catch_with_meaningful_handling_is_ok(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    doSomething();\n"
            "} catch (e) {\n"
            "    cleanup();\n"
            "    throw e;\n"
            "}\n"
        )
        f = tmp_path / "test.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestTypeScriptSilentSuppression:

    def test_empty_catch_ts(self, tmp_path: Path) -> None:
        code = (
            "try {\n"
            "    doSomething();\n"
            "} catch (e: unknown) {\n"
            "}\n"
        )
        f = tmp_path / "test.ts"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "empty"
            for i in result.issues
        )


class TestJavaSilentSuppression:

    def test_empty_catch_java(self, tmp_path: Path) -> None:
        code = (
            "public class Test {\n"
            "    void run() {\n"
            "        try {\n"
            "            doSomething();\n"
            "        } catch (Exception e) {\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Test.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "empty"
            for i in result.issues
        )

    def test_print_stack_trace_only(self, tmp_path: Path) -> None:
        code = (
            "public class Test {\n"
            "    void run() {\n"
            "        try {\n"
            "            doSomething();\n"
            "        } catch (Exception e) {\n"
            "            e.printStackTrace();\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Test.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_LOGGING_ONLY for i in result.issues)

    def test_return_null_in_catch_java(self, tmp_path: Path) -> None:
        code = (
            "public class Test {\n"
            "    String run() {\n"
            "        try {\n"
            "            return fetchData();\n"
            "        } catch (Exception e) {\n"
            "            return null;\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Test.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any("null" in i.handler_type for i in result.issues)

    def test_catch_with_rethrow_java_ok(self, tmp_path: Path) -> None:
        code = (
            "public class Test {\n"
            "    void run() throws Exception {\n"
            "        try {\n"
            "            doSomething();\n"
            "        } catch (Exception e) {\n"
            "            throw new RuntimeException(e);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Test.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_log_error_only_java(self, tmp_path: Path) -> None:
        code = (
            "public class Test {\n"
            "    void run() {\n"
            "        try {\n"
            "            doSomething();\n"
            "        } catch (Exception e) {\n"
            "            log.error(\"Failed\", e);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Test.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_LOGGING_ONLY for i in result.issues)


class TestGoSilentSuppression:

    def test_empty_err_check(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "func run() {\n"
            "    _, err := doSomething()\n"
            "    if err != nil {\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "main.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SILENT and i.handler_type == "empty"
            for i in result.issues
        )

    def test_log_only_err_check(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "func run() {\n"
            "    _, err := doSomething()\n"
            "    if err != nil {\n"
            "        log.Println(err)\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "main.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_LOGGING_ONLY for i in result.issues)

    def test_return_err_is_ok(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "func run() error {\n"
            "    _, err := doSomething()\n"
            "    if err != nil {\n"
            "        return err\n"
            "    }\n"
            "    return nil\n"
            "}\n"
        )
        f = tmp_path / "main.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_log_fatal_is_ok(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "func run() {\n"
            "    _, err := doSomething()\n"
            "    if err != nil {\n"
            "        log.Fatal(err)\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "main.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_go_no_err_check_no_issue(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "func run() {\n"
            "    fmt.Println(\"hello\")\n"
            "}\n"
        )
        f = tmp_path / "main.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0
