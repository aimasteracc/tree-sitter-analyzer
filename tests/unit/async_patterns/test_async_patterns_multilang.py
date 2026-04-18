"""
Tests for Async Pattern Analyzer - Multi-language support.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.async_patterns import (
    AsyncPatternAnalyzer,
    AsyncPatternType,
    PatternSeverity,
)


@pytest.fixture
def analyzer() -> AsyncPatternAnalyzer:
    return AsyncPatternAnalyzer()


def _write_tmp(content: str, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


# --- JavaScript / TypeScript ---


class TestJavaScriptAsyncPatterns:
    def test_async_function_without_await(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async function fetchData() {
    return 42;
}
"""
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_async_functions >= 1
        warnings = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(warnings) >= 1
        assert warnings[0].language == "javascript"

    def test_async_function_with_await_ok(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async function fetchData() {
    const result = await fetch('/api');
    return result.json();
}
"""
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        no_await = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(no_await) == 0

    def test_async_arrow_without_await(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
const handler = async (req, res) => {
    return res.json({ok: true});
};
"""
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_async_functions >= 1
        warnings = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(warnings) >= 1

    def test_unhandled_promise(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
function fetchData() {
    return new Promise((resolve) => {
        resolve(42);
    });
}
"""
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        unhandled = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.UNHANDLED_PROMISE
        ]
        assert len(unhandled) >= 1

    def test_promise_with_catch_ok(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
function fetchData() {
    return new Promise((resolve, reject) => {
        resolve(42);
    }).catch(err => console.error(err));
}
"""
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        unhandled = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.UNHANDLED_PROMISE
        ]
        assert len(unhandled) == 0

    def test_typescript_support(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async function fetchUser(id: string): Promise<User> {
    const resp = await fetch(`/api/users/${id}`);
    return resp.json();
}
"""
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert result.language == "typescript"
        no_await = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(no_await) == 0


# --- Java ---


class TestJavaAsyncPatterns:
    def test_async_void_method(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import org.springframework.scheduling.annotation.Async;

public class EmailService {
    @Async
    public void sendEmail(String to) {
        System.out.println("Sending email to " + to);
    }
}
"""
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert result.total_async_functions >= 1
        fire_forget = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.FIRE_AND_FORGET
        ]
        assert len(fire_forget) >= 1
        assert fire_forget[0].language == "java"

    def test_async_with_completablefuture(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import org.springframework.scheduling.annotation.Async;
import java.util.concurrent.CompletableFuture;

public class DataService {
    @Async
    public CompletableFuture<String> fetchData() {
        return CompletableFuture.completedFuture("data");
    }
}
"""
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        fire_forget = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.FIRE_AND_FORGET
        ]
        assert len(fire_forget) == 0

    def test_blocking_in_async(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import org.springframework.scheduling.annotation.Async;

public class BadService {
    @Async
    public void process() {
        try {
            Thread.sleep(5000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }
}
"""
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        blocking = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.BLOCKING_IN_ASYNC
        ]
        assert len(blocking) >= 1


# --- Go ---


class TestGoAsyncPatterns:
    def test_goroutine_detected(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """package main

import "fmt"

func main() {
    go func() {
        fmt.Println("hello from goroutine")
    }()
}
"""
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert result.total_goroutines >= 1
        fire_forget = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.FIRE_AND_FORGET
        ]
        assert len(fire_forget) >= 1

    def test_channel_without_select(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """package main

func process(ch chan int) {
    ch <- 42
}
"""
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        unchecked = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.UNCHECKED_CHANNEL
        ]
        assert len(unchecked) >= 1

    def test_channel_with_select_ok(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """package main

func process(ch chan int) {
    select {
    case val := <-ch:
        _ = val
    default:
    }
}
"""
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        unchecked = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.UNCHECKED_CHANNEL
        ]
        assert len(unchecked) == 0

    def test_empty_go_file(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """package main
"""
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert result.total_goroutines == 0
        assert len(result.patterns) == 0


# --- Cross-language ---


class TestCrossLanguage:
    def test_each_language_returns_correct_name(self, analyzer: AsyncPatternAnalyzer) -> None:
        for ext, expected in [(".py", "python"), (".js", "javascript"), (".ts", "typescript"),
                              (".tsx", "typescript"), (".jsx", "javascript"), (".java", "java"), (".go", "go")]:
            path = _write_tmp("", ext)
            result = analyzer.analyze_file(path)
            assert result.language == expected, f"Expected {expected} for {ext}, got {result.language}"

    def test_unsupported_extension(self, analyzer: AsyncPatternAnalyzer) -> None:
        path = _write_tmp("x = 1", ".rs")
        result = analyzer.analyze_file(path)
        assert result.language == "unknown"
        assert result.total_async_functions == 0
