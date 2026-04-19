"""Tests for Test Flakiness Detector."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.test_flakiness import (
    FlakinessAnalyzer,
    FlakinessFactor,
    FlakinessRiskLevel,
    FlakinessResult,
)


@pytest.fixture
def analyzer() -> FlakinessAnalyzer:
    return FlakinessAnalyzer()


def _write_tmp(content: str, suffix: str, prefix: str = "test_") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, prefix=prefix, delete=False, dir="/tmp",
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def _write_java_test(content: str, class_name: str = "FooTest") -> Path:
    path = Path(f"/tmp/{class_name}.java")
    path.write_text(textwrap.dedent(content))
    return path


# --- Python tests ---

class TestPythonFlakiness:
    def test_detect_sleep(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import time
            def test_slow():
                time.sleep(2)
                assert True
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_factors >= 1
        types = [f.factor_type for f in result.factors]
        assert "sleep_wait" in types

    def test_detect_random(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import random
            def test_random():
                val = random.randint(1, 100)
                assert val > 0
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "random_usage" in types

    def test_detect_datetime_now(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            from datetime import datetime
            def test_time():
                now = datetime.now()
                assert now is not None
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "time_dependent" in types

    def test_detect_mutable_class_var(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            class TestShared:
                shared_list = []
                def test_append(self):
                    self.shared_list.append(1)
                    assert len(self.shared_list) == 1
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "mutable_shared_state" in types

    def test_no_flakiness_in_clean_test(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            def test_addition():
                assert 1 + 1 == 2
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_factors == 0

    def test_multiple_factors(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import time
            import random
            from datetime import datetime
            def test_flaky():
                time.sleep(1)
                val = random.random()
                now = datetime.now()
                assert val >= 0
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_factors >= 3

    def test_uuid_usage(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import uuid
            def test_uuid():
                id = uuid.uuid4()
                assert id is not None
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "random_usage" in types

    def test_non_test_file_skipped(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import time
            def production_code():
                time.sleep(1)
        """, ".py", prefix="prod_")
        result = analyzer.analyze_file(path)
        assert result.total_factors == 0

    def test_os_random(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import os
            def test_os_random():
                val = os.urandom(16)
                assert len(val) == 16
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "random_usage" in types

    def test_risk_level_assignment(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import time
            import random
            def test_mixed():
                time.sleep(1)
                random.randint(1, 10)
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.risk_level in (
            FlakinessRiskLevel.LOW.value,
            FlakinessRiskLevel.MEDIUM.value,
            FlakinessRiskLevel.HIGH.value,
        )


# --- JavaScript/TypeScript tests ---

class TestJSFlakiness:
    def test_detect_settimeout(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            function testAsync() {
                setTimeout(() => {
                    expect(true).toBe(true);
                }, 100);
            }
        """, ".test.js")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "sleep_wait" in types

    def test_detect_math_random(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            test('random', () => {
                const val = Math.random();
                expect(val).toBeGreaterThan(0);
            });
        """, ".test.js")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "random_usage" in types

    def test_detect_new_date(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            test('time', () => {
                const now = new Date();
                expect(now).toBeDefined();
            });
        """, ".test.js")
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "time_dependent" in types

    def test_spec_file(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            it('should work', () => {
                const val = Math.random();
                expect(val).toBeDefined();
            });
        """, ".spec.ts")
        result = analyzer.analyze_file(path)
        assert result.total_factors >= 1

    def test_clean_test(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            test('addition', () => {
                expect(1 + 1).toBe(2);
            });
        """, ".test.js")
        result = analyzer.analyze_file(path)
        assert result.total_factors == 0


# --- Java tests ---

class TestJavaFlakiness:
    def test_detect_thread_sleep(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_java_test("""
            public class FooTest {
                @Test
                public void testSleep() throws Exception {
                    Thread.sleep(1000);
                    assertTrue(true);
                }
            }
        """)
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "sleep_wait" in types

    def test_detect_random_java(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_java_test("""
            public class FooTest {
                @Test
                public void testRandom() {
                    int val = new Random().nextInt(100);
                    assertTrue(val >= 0);
                }
            }
        """)
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "random_usage" in types

    def test_non_test_java_skipped(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void bar() {
                    Thread.sleep(1000);
                }
            }
        """, ".java", prefix="prod_")
        result = analyzer.analyze_file(path)
        assert result.total_factors == 0

    def test_shared_static_mutable(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_java_test("""
            public class FooTest {
                private static List<String> shared = new ArrayList<>();
                @Test
                public void testAdd() {
                    shared.add("item");
                    assertTrue(shared.contains("item"));
                }
            }
        """)
        result = analyzer.analyze_file(path)
        types = [f.factor_type for f in result.factors]
        assert "mutable_shared_state" in types


# --- Result structure ---

class TestResultStructure:
    def test_to_dict(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("""
            import time
            def test_f():
                time.sleep(1)
        """, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_factors" in d
        assert "factors" in d
        assert "risk_level" in d

    def test_unsupported_file(self, analyzer: FlakinessAnalyzer) -> None:
        path = _write_tmp("data", ".csv")
        result = analyzer.analyze_file(path)
        assert result.total_factors == 0
