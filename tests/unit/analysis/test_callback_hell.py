"""Tests for Callback Hell Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.callback_hell import (
    ISSUE_CALLBACK_HELL,
    ISSUE_DEEP_CALLBACK,
    ISSUE_PROMISE_CHAIN_HELL,
    CallbackHellAnalyzer,
)


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python tests ──────────────────────────────────────────────────


class TestPythonCallbackHell:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_no_callbacks(self) -> None:
        path = _write_tmp("x = 1\ny = 2\n", ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks == 0
        assert result.max_depth == 0
        assert len(result.issues) == 0

    def test_single_lambda_not_flagged(self) -> None:
        path = _write_tmp("list(map(lambda x: x + 1, [1, 2, 3]))\n", ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks >= 1
        assert len(result.issues) == 0

    def test_two_level_nesting_not_flagged(self) -> None:
        code = """\
def outer():
    nums = [1, 2, 3]
    result = map(lambda x: x + 1, nums)
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        # 2 levels of nesting (function + lambda) but lambda not in callback position
        deep_issues = [i for i in result.issues if i.issue_type == ISSUE_DEEP_CALLBACK]
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(deep_issues) == 0
        assert len(hell_issues) == 0

    def test_three_level_deep_callback(self) -> None:
        code = """\
def process():
    def step1():
        def step2():
            pass
        step2()
    step1()
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        deep_issues = [i for i in result.issues if i.issue_type == ISSUE_DEEP_CALLBACK]
        assert len(deep_issues) >= 1

    def test_four_level_callback_hell(self) -> None:
        code = """\
def run():
    def level1():
        def level2():
            def level3():
                pass
            level3()
        level2()
    level1()
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) >= 1
        assert hell_issues[0].depth >= 4

    def test_lambda_chain_three_levels(self) -> None:
        code = """\
result = (lambda a:
    lambda b:
        lambda c: a + b + c
)(1)(2)(3)
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks >= 3

    def test_nonexistent_file(self) -> None:
        result = self.analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_callbacks == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self) -> None:
        path = _write_tmp("some content", ".txt")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks == 0

    def test_result_to_dict(self) -> None:
        path = _write_tmp("x = 1\n", ".py")
        result = self.analyzer.analyze_file(path)
        d = result.to_dict()
        assert "total_callbacks" in d
        assert "max_depth" in d
        assert "issue_count" in d
        assert "issues" in d
        assert "file_path" in d

    def test_issue_to_dict(self) -> None:
        code = """\
def run():
    def level1():
        def level2():
            def level3():
                pass
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "line_number" in d
            assert "issue_type" in d
            assert "depth" in d
            assert "severity" in d
            assert "suggestion" in d


# ── JavaScript tests ──────────────────────────────────────────────


class TestJSCallbackHell:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_simple_js_no_issues(self) -> None:
        code = "const x = 1;\n"
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_two_level_js_not_flagged(self) -> None:
        code = """\
fetch(url).then(function(response) {
    return response.json();
});
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) == 0

    def test_three_level_deep_callback_js(self) -> None:
        code = """\
setTimeout(function() {
    setTimeout(function() {
        setTimeout(function() {
            console.log("done");
        }, 100);
    }, 100);
}, 100);
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        deep_issues = [i for i in result.issues if i.issue_type == ISSUE_DEEP_CALLBACK]
        assert len(deep_issues) >= 1

    def test_four_level_callback_hell_js(self) -> None:
        code = """\
setTimeout(function() {
    setTimeout(function() {
        setTimeout(function() {
            setTimeout(function() {
                console.log("done");
            }, 100);
        }, 100);
    }, 100);
}, 100);
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) >= 1

    def test_arrow_function_nesting(self) -> None:
        code = """\
Promise.resolve(1).then(() => {
    return Promise.resolve(2).then(() => {
        return Promise.resolve(3).then(() => {
            return Promise.resolve(4).then(() => {
                console.log("done");
            });
        });
    });
});
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_promise_chain_hell(self) -> None:
        code = """\
fetch(url)
  .then(r => r.json())
  .then(data => process(data))
  .then(result => save(result))
  .then(() => cleanup());
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        chain_issues = [i for i in result.issues if i.issue_type == ISSUE_PROMISE_CHAIN_HELL]
        assert len(chain_issues) >= 1
        assert chain_issues[0].depth >= 4

    def test_short_promise_chain_ok(self) -> None:
        code = """\
fetch(url)
  .then(r => r.json())
  .then(data => process(data));
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        chain_issues = [i for i in result.issues if i.issue_type == ISSUE_PROMISE_CHAIN_HELL]
        assert len(chain_issues) == 0


# ── TypeScript tests ──────────────────────────────────────────────


class TestTSCallbackHell:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_ts_arrow_callback_hell(self) -> None:
        code = """\
async function run() {
    setTimeout(() => {
        setTimeout(() => {
            setTimeout(() => {
                setTimeout(() => {
                    console.log("done");
                }, 100);
            }, 100);
        }, 100);
    }, 100);
}
"""
        path = _write_tmp(code, ".ts")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) >= 1

    def test_ts_no_issues_clean(self) -> None:
        code = """\
const greet = (name: string): string => `Hello ${name}`;
"""
        path = _write_tmp(code, ".ts")
        result = self.analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Java tests ────────────────────────────────────────────────────


class TestJavaCallbackHell:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_java_no_issues(self) -> None:
        code = """\
public class Main {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
"""
        path = _write_tmp(code, ".java")
        result = self.analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_java_nested_lambdas(self) -> None:
        code = """\
public class Main {
    public void run() {
        Runnable r1 = () -> {
            Runnable r2 = () -> {
                Runnable r3 = () -> {
                    System.out.println("deep");
                };
            };
        };
    }
}
"""
        path = _write_tmp(code, ".java")
        result = self.analyzer.analyze_file(path)
        deep_issues = [i for i in result.issues if i.issue_type == ISSUE_DEEP_CALLBACK]
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        total = len(deep_issues) + len(hell_issues)
        assert total >= 1


# ── Go tests ──────────────────────────────────────────────────────


class TestGoCallbackHell:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_go_no_issues(self) -> None:
        code = """\
package main

func main() {
    fmt.Println("hello")
}
"""
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_go_nested_func_literals(self) -> None:
        code = """\
package main

func main() {
    func() {
        func() {
            func() {
                func() {
                    println("deep")
                }()
            }()
        }()
    }()
}
"""
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) >= 1

    def test_go_two_level_ok(self) -> None:
        code = """\
package main

func main() {
    func() {
        func() {
            println("ok")
        }()
    }()
}
"""
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        hell_issues = [i for i in result.issues if i.issue_type == ISSUE_CALLBACK_HELL]
        assert len(hell_issues) == 0


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    def setup_method(self) -> None:
        self.analyzer = CallbackHellAnalyzer()

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks == 0
        assert len(result.issues) == 0

    def test_only_comments(self) -> None:
        code = "# This is a comment\n# Another comment\n"
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_callbacks == 0

    def test_issue_suggestion_not_empty(self) -> None:
        code = """\
def run():
    def level1():
        def level2():
            def level3():
                pass
"""
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        if result.issues:
            assert result.issues[0].suggestion != ""

    def test_severity_mapping(self) -> None:
        code = """\
setTimeout(function() {
    setTimeout(function() {
        setTimeout(function() {
            console.log("3 levels");
        });
    });
});
"""
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        for issue in result.issues:
            if issue.issue_type == ISSUE_CALLBACK_HELL:
                assert issue.severity == "critical"
            elif issue.issue_type == ISSUE_DEEP_CALLBACK:
                assert issue.severity == "warning"
            elif issue.issue_type == ISSUE_PROMISE_CHAIN_HELL:
                assert issue.severity == "critical"
