"""Unit tests for TestSmellDetector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.test_smells import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SMELL_ASSERT_NONE,
    SMELL_BROAD_EXCEPT,
    SMELL_LOW_ASSERT,
    SMELL_SLEEP_IN_TEST,
    TestFunction,
    TestSmell,
    TestSmellDetector,
    TestSmellResult,
    _severity_for,
)


@pytest.fixture
def detector() -> TestSmellDetector:
    return TestSmellDetector()


def _write_tmp(content: str, suffix: str = ".py", prefix: str = "test_") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, prefix=prefix, delete=False)
    f.write(content)
    f.flush()
    f.close()
    return f.name


# --- Severity tests ---

class TestSeverity:
    def test_assert_none_is_high(self) -> None:
        assert _severity_for(SMELL_ASSERT_NONE) == SEVERITY_HIGH

    def test_broad_except_is_medium(self) -> None:
        assert _severity_for(SMELL_BROAD_EXCEPT) == SEVERITY_MEDIUM

    def test_sleep_is_medium(self) -> None:
        assert _severity_for(SMELL_SLEEP_IN_TEST) == SEVERITY_MEDIUM

    def test_low_assert_is_low(self) -> None:
        assert _severity_for(SMELL_LOW_ASSERT) == SEVERITY_LOW


# --- Dataclass tests ---

class TestDataclasses:
    def test_smell_to_dict(self) -> None:
        smell = TestSmell(
            smell_type=SMELL_ASSERT_NONE,
            function_name="test_foo",
            line_number=5,
            severity=SEVERITY_HIGH,
            detail="No assertions",
        )
        d = smell.to_dict()
        assert d["smell_type"] == SMELL_ASSERT_NONE
        assert d["line_number"] == 5

    def test_function_to_dict(self) -> None:
        fn = TestFunction(
            name="test_bar",
            start_line=1,
            end_line=10,
            assertion_count=3,
            has_broad_except=False,
            has_sleep=False,
            smells=(),
        )
        d = fn.to_dict()
        assert d["assertion_count"] == 3
        assert d["smells"] == ()

    def test_result_get_smells_by_type(self) -> None:
        smell1 = TestSmell(SMELL_ASSERT_NONE, "f1", 1, SEVERITY_HIGH, "d")
        smell2 = TestSmell(SMELL_SLEEP_IN_TEST, "f2", 2, SEVERITY_MEDIUM, "d")
        fn1 = TestFunction("test_a", 1, 5, 0, False, False, (smell1,))
        fn2 = TestFunction("test_b", 6, 10, 1, False, True, (smell2,))
        result = TestSmellResult("test.py", (fn1, fn2), 2, 2, {SMELL_ASSERT_NONE: 1, SMELL_SLEEP_IN_TEST: 1})
        assert len(result.get_smells_by_type(SMELL_ASSERT_NONE)) == 1
        assert len(result.get_smells_by_type(SMELL_SLEEP_IN_TEST)) == 1

    def test_result_get_high_severity(self) -> None:
        smell_h = TestSmell(SMELL_ASSERT_NONE, "f1", 1, SEVERITY_HIGH, "d")
        smell_m = TestSmell(SMELL_SLEEP_IN_TEST, "f2", 2, SEVERITY_MEDIUM, "d")
        fn1 = TestFunction("test_a", 1, 5, 0, False, False, (smell_h,))
        fn2 = TestFunction("test_b", 6, 10, 1, False, True, (smell_m,))
        result = TestSmellResult("test.py", (fn1, fn2), 2, 2, {})
        high = result.get_high_severity_smells()
        assert len(high) == 1
        assert high[0].smell_type == SMELL_ASSERT_NONE

    def test_result_to_dict(self) -> None:
        result = TestSmellResult("test.py", (), 0, 0, {})
        d = result.to_dict()
        assert d["file_path"] == "test.py"
        assert d["total_tests"] == 0


# --- Python analysis ---

class TestPythonAnalysis:
    def test_clean_test_no_smells(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_addition():\n"
            "    assert 1 + 1 == 2\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_empty_test_body(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_placeholder():\n"
            "    pass\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 1
        assert result.smell_counts.get(SMELL_ASSERT_NONE, 0) == 1

    def test_bare_except(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_with_bare_except():\n"
            "    try:\n"
            "        do_something()\n"
            "    except:\n"
            "        pass\n"
            "    assert True\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.smell_counts.get(SMELL_BROAD_EXCEPT, 0) == 1

    def test_except_exception(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_with_exception():\n"
            "    try:\n"
            "        do_something()\n"
            "    except Exception:\n"
            "        pass\n"
            "    assert True\n"
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_BROAD_EXCEPT, 0) == 1

    def test_time_sleep(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "import time\n"
            "def test_with_sleep():\n"
            "    time.sleep(1)\n"
            "    assert True\n"
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_SLEEP_IN_TEST, 0) == 1

    def test_unittest_assert(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "import unittest\n"
            "class TestMath(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(1 + 1, 2)\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_multiple_smells(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "import time\n"
            "def test_broken():\n"
            "    try:\n"
            "        do_something()\n"
            "    except Exception:\n"
            "        pass\n"
            "    time.sleep(1)\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 3
        assert SMELL_ASSERT_NONE in result.smell_counts
        assert SMELL_BROAD_EXCEPT in result.smell_counts
        assert SMELL_SLEEP_IN_TEST in result.smell_counts

    def test_non_test_function_ignored(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def helper_function():\n"
            "    pass\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 0

    def test_non_test_file_ignored(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_something():\n"
            "    pass\n",
            prefix="helper_",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 0

    def test_missing_file(self, detector: TestSmellDetector) -> None:
        result = detector.analyze_file("/nonexistent/test_foo.py")
        assert result.total_tests == 0

    def test_min_assertions(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "def test_minimal():\n"
            "    assert True\n"
        )
        result = detector.analyze_file(path, min_assertions=2)
        assert result.total_tests == 1
        assert result.smell_counts.get(SMELL_LOW_ASSERT, 0) == 1

    def test_pytest_raises_is_assert(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "import pytest\n"
            "def test_error():\n"
            "    with pytest.raises(ValueError):\n"
            "        raise ValueError()\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0


# --- JavaScript analysis ---

class TestJavaScriptAnalysis:
    def test_clean_js_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function testAddition() {\n"
            "  assert(1 + 1 === 2);\n"
            "}\n",
            suffix=".js",
            prefix="test_",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_empty_js_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function testEmpty() {\n"
            "}\n",
            suffix=".js",
            prefix="test_",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.smell_counts.get(SMELL_ASSERT_NONE, 0) == 1

    def test_js_setTimeout(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function testAsync() {\n"
            "  setTimeout(() => {}, 1000);\n"
            "  assert(true);\n"
            "}\n",
            suffix=".js",
            prefix="test_",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_SLEEP_IN_TEST, 0) == 1

    def test_js_catch_all(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function testCatch() {\n"
            "  try {\n"
            "    doStuff();\n"
            "  } catch {\n"
            "    // swallow\n"
            "  }\n"
            "  assert(true);\n"
            "}\n",
            suffix=".js",
            prefix="test_",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_BROAD_EXCEPT, 0) == 1

    def test_jest_expect(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function testWithExpect() {\n"
            "  expect(1 + 1).toBe(2);\n"
            "}\n",
            suffix=".test.js",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_non_test_js_ignored(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "function helper() {\n"
            "  return 42;\n"
            "}\n",
            suffix=".js",
            prefix="utils_",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 0


# --- Java analysis ---

class TestJavaAnalysis:
    def test_clean_java_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "public class FooTest {\n"
            "  @Test\n"
            "  public void testAddition() {\n"
            "    assertEquals(2, 1 + 1);\n"
            "  }\n"
            "}\n",
            suffix="Test.java",
            prefix="Foo",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_empty_java_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "public class BarTest {\n"
            "  @Test\n"
            "  public void testPlaceholder() {\n"
            "  }\n"
            "}\n",
            suffix="Test.java",
            prefix="Bar",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_ASSERT_NONE, 0) == 1

    def test_java_thread_sleep(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "public class BazTest {\n"
            "  @Test\n"
            "  public void testWait() throws Exception {\n"
            "    Thread.sleep(1000);\n"
            "    assertTrue(true);\n"
            "  }\n"
            "}\n",
            suffix="Test.java",
            prefix="Baz",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_SLEEP_IN_TEST, 0) == 1

    def test_java_catch_exception(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "public class QuxTest {\n"
            "  @Test\n"
            "  public void testCatch() {\n"
            "    try {\n"
            "      doStuff();\n"
            "    } catch (Exception e) {\n"
            "      // swallow\n"
            "    }\n"
            "    assertTrue(true);\n"
            "  }\n"
            "}\n",
            suffix="Test.java",
            prefix="Qux",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_BROAD_EXCEPT, 0) == 1


# --- Go analysis ---

class TestGoAnalysis:
    def test_clean_go_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            'package main\n\n'
            'import "testing"\n\n'
            'func TestAddition(t *testing.T) {\n'
            '    if 1+1 != 2 {\n'
            '        t.Fatal("bad math")\n'
            '    }\n'
            '}\n',
            suffix="_test.go",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_empty_go_test(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func TestNothing(t *testing.T) {\n"
            "}\n",
            suffix="_test.go",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_ASSERT_NONE, 0) == 1

    def test_go_time_sleep(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            'package main\n\n'
            'import (\n    "testing"\n    "time"\n)\n\n'
            'func TestSlow(t *testing.T) {\n'
            '    time.Sleep(1 * time.Second)\n'
            '    t.Fatal("done")\n'
            '}\n',
            suffix="_test.go",
        )
        result = detector.analyze_file(path)
        assert result.smell_counts.get(SMELL_SLEEP_IN_TEST, 0) == 1

    def test_go_assert_package(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            'package main\n\n'
            'func TestWithAssert(t *testing.T) {\n'
            '    assert.Equal(t, 2, 1+1)\n'
            '}\n',
            suffix="_test.go",
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0


# --- Edge cases ---

class TestEdgeCases:
    def test_class_based_pytest(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "class TestCalculator:\n"
            "    def test_add(self):\n"
            "        assert 1 + 1 == 2\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.total_smells == 0

    def test_class_based_empty(self, detector: TestSmellDetector) -> None:
        path = _write_tmp(
            "class TestMath:\n"
            "    def test_placeholder(self):\n"
            "        pass\n"
        )
        result = detector.analyze_file(path)
        assert result.total_tests == 1
        assert result.smell_counts.get(SMELL_ASSERT_NONE, 0) == 1
