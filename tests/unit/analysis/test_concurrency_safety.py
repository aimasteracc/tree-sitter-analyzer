"""Tests for Concurrency Safety Analyzer — Python + Multi-Language."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.concurrency_safety import (
    ISSUE_CHECK_THEN_ACT,
    ISSUE_MISSING_SYNC,
    ISSUE_SHARED_MUTABLE,
    ISSUE_UNSAFE_CONCURRENT,
    ConcurrencyIssue,
    ConcurrencyResult,
    ConcurrencySafetyAnalyzer,
    _empty_result,
    _severity_counts,
)

ANALYZER = ConcurrencySafetyAnalyzer


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = ConcurrencyIssue(
            line=1,
            issue_type=ISSUE_SHARED_MUTABLE,
            severity="high",
            variable="counter",
            description="desc",
            suggestion="fix",
        )
        assert issue.line == 1
        with pytest.raises(AttributeError):
            issue.line = 5  # type: ignore[misc]

    def test_result_frozen(self) -> None:
        result = ConcurrencyResult(
            issues=(),
            total_issues=0,
            high_severity=0,
            medium_severity=0,
            low_severity=0,
            file_path="test.py",
            language="python",
        )
        assert result.total_issues == 0
        with pytest.raises(AttributeError):
            result.total_issues = 99  # type: ignore[misc]

    def test_result_to_dict(self) -> None:
        issue = ConcurrencyIssue(
            line=1,
            issue_type=ISSUE_SHARED_MUTABLE,
            severity="high",
            variable="counter",
            description="desc",
            suggestion="fix",
        )
        result = ConcurrencyResult(
            issues=(issue,),
            total_issues=1,
            high_severity=1,
            medium_severity=0,
            low_severity=0,
            file_path="test.py",
            language="python",
        )
        d = result.to_dict()
        assert d["total_issues"] == 1
        assert len(d["issues"]) == 1
        assert d["issues"][0]["variable"] == "counter"

    def test_empty_result(self) -> None:
        result = _empty_result("f.py", "python")
        assert result.total_issues == 0
        assert result.file_path == "f.py"

    def test_severity_counts(self) -> None:
        issues = (
            ConcurrencyIssue(1, "a", "high", "x", "d", "s"),
            ConcurrencyIssue(2, "b", "high", "y", "d", "s"),
            ConcurrencyIssue(3, "c", "medium", "z", "d", "s"),
        )
        h, m, l = _severity_counts(issues)
        assert h == 2
        assert m == 1
        assert l == 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        analyzer = ANALYZER()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self) -> None:
        p = _write_tmp("x = 1", ".txt")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "unknown"

    def test_empty_file(self) -> None:
        p = _write_tmp("", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0

    def test_safe_code_no_issues(self) -> None:
        p = _write_tmp("x = 42\nprint(x)\n", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0

    def test_no_concurrency_no_issues(self) -> None:
        code = """\
class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0


# ── Python analysis tests ────────────────────────────────────────────────


class TestPythonAnalysis:
    def test_shared_mutable_state(self) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
    def run(self):
        t = threading.Thread(target=self.increment)
        t.start()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1
        assert any(
            i.issue_type == ISSUE_SHARED_MUTABLE for i in result.issues
        )

    def test_shared_mutable_with_lock_safe(self) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()
    def increment(self):
        with self.lock:
            self.count += 1
    def run(self):
        t = threading.Thread(target=self.increment)
        t.start()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        mutable_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_SHARED_MUTABLE and i.variable == "self.lock"
        ]
        assert len(mutable_issues) == 0

    def test_missing_sync_primitive(self) -> None:
        code = """\
import threading

def worker():
    pass

t = threading.Thread(target=worker)
t.start()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_MISSING_SYNC for i in result.issues
        )

    def test_check_then_act(self) -> None:
        code = """\
if status == "active":
    status = "processed"
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHECK_THEN_ACT for i in result.issues
        )

    def test_unsafe_concurrent_access(self) -> None:
        code = """\
import threading

data = []
t = threading.Thread(target=lambda: data.append(1))
t.start()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1

    def test_result_language(self) -> None:
        p = _write_tmp("x = 1\n", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "python"

    def test_severity_levels(self) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
    def run(self):
        t = threading.Thread(target=self.increment)
        t.start()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        for issue in result.issues:
            if issue.issue_type == ISSUE_SHARED_MUTABLE:
                assert issue.severity == "high"
            elif issue.issue_type == ISSUE_MISSING_SYNC:
                assert issue.severity == "medium"


# ── JavaScript/TypeScript analysis tests ─────────────────────────────────


class TestJavaScriptAnalysis:
    def test_shared_mutable_in_async(self) -> None:
        code = """\
let items = [];
async function addItems() {
    await fetch('/api');
    items = items.concat([1, 2, 3]);
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_SHARED_MUTABLE for i in result.issues
        )

    def test_promise_all_no_catch(self) -> None:
        code = """\
async function fetchAll() {
    const results = await Promise.all([
        fetch('/a'),
        fetch('/b'),
    ]);
    return results;
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_MISSING_SYNC for i in result.issues
        )

    def test_check_then_act_await(self) -> None:
        code = """\
let cache = null;
async function getCache() {
    if (cache === null) {
        await loadData();
        cache = "loaded";
    }
    return cache;
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHECK_THEN_ACT for i in result.issues
        )

    def test_const_no_shared_mutable(self) -> None:
        code = """\
const items = [];
async function addItems() {
    return items;
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        mutable_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_SHARED_MUTABLE
        ]
        assert len(mutable_issues) == 0

    def test_result_language_js(self) -> None:
        p = _write_tmp("let x = 1;\n", ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "javascript"

    def test_result_language_ts(self) -> None:
        p = _write_tmp("let x = 1;\n", ".ts")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "typescript"


# ── Java analysis tests ──────────────────────────────────────────────────


class TestJavaAnalysis:
    def test_shared_mutable_collection(self) -> None:
        code = """\
import java.util.ArrayList;
import java.util.List;

public class Worker implements Runnable {
    private List<String> items = new ArrayList<>();

    public void run() {
        items.add("item");
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_SHARED_MUTABLE for i in result.issues
        )

    def test_concurrent_hash_map_safe(self) -> None:
        code = """\
import java.util.concurrent.ConcurrentHashMap;
import java.util.Map;

public class Worker implements Runnable {
    private Map<String, String> data = new ConcurrentHashMap<>();

    public void run() {
        data.put("key", "value");
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        mutable_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_SHARED_MUTABLE
        ]
        assert len(mutable_issues) == 0

    def test_double_checked_locking_without_volatile(self) -> None:
        code = """\
public class Singleton {
    private static Singleton instance;

    public static Singleton getInstance() {
        if (instance == null) {
            synchronized (Singleton.class) {
                if (instance == null) {
                    instance = new Singleton();
                }
            }
        }
        return instance;
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_MISSING_SYNC for i in result.issues
        )

    def test_check_then_act_in_runnable(self) -> None:
        code = """\
public class Worker implements Runnable {
    private boolean active = true;

    public void run() {
        if (active) {
            active = false;
        }
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHECK_THEN_ACT for i in result.issues
        )

    def test_result_language_java(self) -> None:
        p = _write_tmp("public class Foo {}\n", ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "java"


# ── Go analysis tests ────────────────────────────────────────────────────


class TestGoAnalysis:
    def test_shared_mutable_near_goroutine(self) -> None:
        code = """\
package main

func main() {
    counter := 0
    go func() {
        counter = counter + 1
    }()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_SHARED_MUTABLE for i in result.issues
        )

    def test_map_near_goroutine(self) -> None:
        code = """\
package main

func main() {
    m := map[string]int{}
    go func() {
        m["key"] = 1
    }()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_UNSAFE_CONCURRENT for i in result.issues
        )

    def test_mutex_protected_safe(self) -> None:
        code = """\
package main

import "sync"

func main() {
    var mu sync.Mutex
    counter := 0
    go func() {
        mu.Lock()
        counter = counter + 1
        mu.Unlock()
    }()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        mutable_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_SHARED_MUTABLE
            and i.variable == "counter"
        ]
        assert len(mutable_issues) == 0

    def test_waitgroup_add_inside_goroutine(self) -> None:
        code = """\
package main

import "sync"

func main() {
    var wg sync.WaitGroup
    go func() {
        wg.Add(1)
        defer wg.Done()
    }()
    wg.Wait()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_MISSING_SYNC for i in result.issues
        )

    def test_check_then_act_near_goroutine(self) -> None:
        code = """\
package main

func main() {
    done := false
    go func() {
        if done == false {
            done = true
        }
    }()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHECK_THEN_ACT for i in result.issues
        )

    def test_result_language_go(self) -> None:
        p = _write_tmp("package main\n", ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "go"
