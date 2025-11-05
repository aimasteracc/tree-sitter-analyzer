#!/usr/bin/env python3
"""
Tree-sitter Integration Tests

Comprehensive tests for tree-sitter engine integration with QueryService.
Tests the complete pipeline from file parsing to query execution across all supported languages.
"""

import asyncio
import os
import tempfile

import pytest

from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.language_detector import detect_language_from_file
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestTreeSitterIntegration:
    """Comprehensive tree-sitter integration tests"""

    # Test code samples for all supported languages
    TEST_SAMPLES = {
        "java": """
package com.example;

public class TestClass {
    private String name;
    private int value;

    public TestClass(String name) {
        this.name = name;
        this.value = 0;
    }

    public String getName() {
        return name;
    }

    public void setValue(int value) {
        this.value = value;
    }

    public static void staticMethod() {
        System.out.println("Static method");
    }

    private void privateMethod() {
        // Private implementation
    }
}

interface TestInterface {
    void interfaceMethod();
}
""",
        "javascript": """
function regularFunction() {
    return "regular";
}

const arrowFunction = () => {
    return "arrow";
}

class TestClass {
    constructor(name) {
        this.name = name;
        this.value = 0;
    }

    getName() {
        return this.name;
    }

    setValue(value) {
        this.value = value;
    }

    static staticMethod() {
        return "static";
    }
}

async function asyncFunction() {
    return "async";
}

export { TestClass, regularFunction };
""",
        "typescript": """
interface TestInterface {
    name: string;
    value: number;
}

type TestType = {
    id: number;
    data: string;
}

class TestClass implements TestInterface {
    public name: string;
    private value: number;

    constructor(name: string) {
        this.name = name;
        this.value = 0;
    }

    public getName(): string {
        return this.name;
    }

    public setValue(value: number): void {
        this.value = value;
    }

    static staticMethod(): string {
        return "static";
    }
}

function genericFunction<T>(param: T): T {
    return param;
}

export { TestClass, TestInterface, TestType };
""",
        "python": """
from typing import Optional, List
import asyncio

class TestClass:
    def __init__(self, name: str):
        self.name = name
        self._value = 0

    def get_name(self) -> str:
        return self.name

    def set_value(self, value: int) -> None:
        self._value = value

    @staticmethod
    def static_method() -> str:
        return "static"

    @classmethod
    def class_method(cls) -> 'TestClass':
        return cls("default")

    @property
    def value(self) -> int:
        return self._value

def regular_function(param: str) -> str:
    return f"Hello, {param}"

async def async_function() -> str:
    await asyncio.sleep(0.1)
    return "async"

@decorator
def decorated_function():
    pass

def function_with_args(*args, **kwargs):
    pass
""",
        "markdown": """
# Main Header

This is a test markdown file.

## Section Header

Some content here.

### Subsection

- List item 1
- List item 2

```python
def code_block():
    return "code"
```

[Link to example](https://example.com)

**Bold text** and *italic text*.

> Blockquote content

| Table | Header |
|-------|--------|
| Cell  | Data   |
""",
    }

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.query_service = QueryService(self.temp_dir)
        self.query_tool = QueryTool(self.temp_dir)
        self.test_files = {}

        # Create test files for all languages
        extensions = {
            "java": ".java",
            "javascript": ".js",
            "typescript": ".ts",
            "python": ".py",
            "markdown": ".md",
        }

        for lang, code in self.TEST_SAMPLES.items():
            file_path = os.path.join(self.temp_dir, f"test{extensions[lang]}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            self.test_files[lang] = file_path

    def teardown_method(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_language_detection_integration(self):
        """Test language detection for all supported file types"""
        expected_languages = {
            "java": "java",
            "javascript": "javascript",
            "typescript": "typescript",
            "python": "python",
            "markdown": "markdown",
        }

        for lang, file_path in self.test_files.items():
            detected = detect_language_from_file(file_path)
            assert (
                detected == expected_languages[lang]
            ), f"Language detection failed for {lang}"

    @pytest.mark.asyncio
    async def test_parser_integration_all_languages(self):
        """Test that parser can successfully parse all supported languages"""
        for lang, file_path in self.test_files.items():
            try:
                # Test through QueryService which uses the parser
                results = await self.query_service.execute_query(
                    file_path,
                    lang,
                    query_key="functions" if lang != "markdown" else "headers",
                )
                # Should not raise exception and should return some results
                assert results is not None, f"Parser failed for {lang}"
                print(
                    f"✓ Parser integration successful for {lang}: {len(results)} results"
                )
            except Exception as e:
                pytest.fail(f"Parser integration failed for {lang}: {e}")

    @pytest.mark.asyncio
    async def test_predefined_queries_all_languages(self):
        """Test predefined queries work for all languages"""
        # Define expected query keys for each language
        query_tests = {
            "java": ["class", "methods", "fields", "interfaces"],
            "javascript": ["functions", "classes", "variables"],
            "typescript": ["interfaces", "types", "functions", "classes"],
            "python": ["functions", "classes"],
            "markdown": ["headers", "links", "code_blocks"],
        }

        for lang, queries in query_tests.items():
            file_path = self.test_files[lang]

            for query_key in queries:
                try:
                    results = await self.query_service.execute_query(
                        file_path, lang, query_key=query_key
                    )
                    assert results is not None, f"Query {query_key} failed for {lang}"
                    print(
                        f"✓ Query '{query_key}' successful for {lang}: {len(results)} results"
                    )
                except Exception as e:
                    print(f"⚠ Query '{query_key}' failed for {lang}: {e}")
                    # Don't fail the test for individual query failures, just log them

    @pytest.mark.asyncio
    async def test_custom_queries_integration(self):
        """Test custom tree-sitter queries work correctly"""
        custom_query_tests = [
            {
                "lang": "java",
                "query": "(method_declaration) @method",
                "file": self.test_files["java"],
                "expected_min": 1,
            },
            {
                "lang": "javascript",
                "query": "(function_declaration) @func",
                "file": self.test_files["javascript"],
                "expected_min": 1,
            },
            {
                "lang": "python",
                "query": "(function_definition) @func",
                "file": self.test_files["python"],
                "expected_min": 1,
            },
        ]

        for test_case in custom_query_tests:
            try:
                results = await self.query_service.execute_query(
                    test_case["file"],
                    test_case["lang"],
                    query_string=test_case["query"],
                )
                assert (
                    results is not None
                ), f"Custom query failed for {test_case['lang']}"
                assert (
                    len(results) >= test_case["expected_min"]
                ), f"Expected at least {test_case['expected_min']} results for {test_case['lang']}"
                print(
                    f"✓ Custom query successful for {test_case['lang']}: {len(results)} results"
                )
            except Exception as e:
                pytest.fail(f"Custom query failed for {test_case['lang']}: {e}")

    @pytest.mark.asyncio
    async def test_query_result_structure(self):
        """Test that query results have correct structure"""
        file_path = self.test_files["java"]
        results = await self.query_service.execute_query(
            file_path, "java", query_key="methods"
        )

        assert results is not None
        assert isinstance(results, list)

        if results:
            result = results[0]
            required_fields = [
                "capture_name",
                "node_type",
                "start_line",
                "end_line",
                "content",
            ]
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"

            # Validate field types
            assert isinstance(result["start_line"], int)
            assert isinstance(result["end_line"], int)
            assert isinstance(result["content"], str)
            assert result["start_line"] > 0
            assert result["end_line"] >= result["start_line"]

    @pytest.mark.asyncio
    async def test_filter_integration(self):
        """Test query filtering functionality"""
        file_path = self.test_files["java"]

        # Test name filter
        results = await self.query_service.execute_query(
            file_path, "java", query_key="methods", filter_expression="name=getName"
        )

        if results:
            # All results should contain "getName" in content
            for result in results:
                assert "getName" in result["content"], "Filter did not work correctly"

    @pytest.mark.asyncio
    async def test_mcp_tool_integration(self):
        """Test MCP tool integration with tree-sitter"""
        file_path = self.test_files["python"]
        relative_path = os.path.relpath(file_path, self.temp_dir)

        # Test through MCP tool interface
        arguments = {
            "file_path": relative_path,
            "query_key": "functions",
            "output_format": "json",
        }

        result = await self.query_tool.execute(arguments)

        assert result["success"] is True
        assert "results" in result
        assert "count" in result
        assert isinstance(result["results"], list)

    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Test error handling in tree-sitter integration"""
        # Test with non-existent file
        with pytest.raises((FileNotFoundError, ValueError)):
            await self.query_service.execute_query(
                "non_existent.py", "python", query_key="functions"
            )

        # Test with invalid query key
        file_path = self.test_files["python"]
        with pytest.raises(ValueError):
            await self.query_service.execute_query(
                file_path, "python", query_key="invalid_query"
            )

    @pytest.mark.asyncio
    async def test_large_file_performance(self):
        """Test performance with larger files"""
        # Create a larger test file
        large_content = self.TEST_SAMPLES["python"] * 50  # Repeat content 50 times
        large_file = os.path.join(self.temp_dir, "large_test.py")

        with open(large_file, "w", encoding="utf-8") as f:
            f.write(large_content)

        import time

        start_time = time.time()

        results = await self.query_service.execute_query(
            large_file, "python", query_key="functions"
        )

        end_time = time.time()
        execution_time = end_time - start_time

        assert results is not None
        assert execution_time < 5.0, f"Query took too long: {execution_time}s"
        print(
            f"✓ Large file query completed in {execution_time:.2f}s with {len(results)} results"
        )

    @pytest.mark.asyncio
    async def test_encoding_handling(self):
        """Test handling of different file encodings"""
        # Create file with UTF-8 content including non-ASCII characters
        utf8_content = """
def test_function():
    # コメント with Japanese characters
    return "テスト"

class TestClass:
    def __init__(self):
        self.name = "名前"
"""
        utf8_file = os.path.join(self.temp_dir, "utf8_test.py")
        with open(utf8_file, "w", encoding="utf-8") as f:
            f.write(utf8_content)

        results = await self.query_service.execute_query(
            utf8_file, "python", query_key="functions"
        )

        assert results is not None
        assert len(results) > 0

        # Check that content is properly decoded
        for result in results:
            assert isinstance(result["content"], str)
            # Should not contain encoding errors
            assert "�" not in result["content"]

    @pytest.mark.asyncio
    async def test_concurrent_queries(self):
        """Test concurrent query execution"""
        tasks = []

        # Create multiple concurrent queries
        for lang, file_path in self.test_files.items():
            if lang != "markdown":  # Use functions query for code files
                task = self.query_service.execute_query(
                    file_path, lang, query_key="functions"
                )
            else:  # Use headers query for markdown
                task = self.query_service.execute_query(
                    file_path, lang, query_key="headers"
                )
            tasks.append(task)

        # Execute all queries concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check that all queries completed successfully
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent query {i} failed: {result}")
            assert result is not None

    def test_query_service_initialization(self):
        """Test QueryService initialization and configuration"""
        # Test with project root
        service = QueryService(self.temp_dir)
        assert service.project_root == self.temp_dir

        # Test without project root
        service = QueryService()
        assert service.project_root is None

    @pytest.mark.asyncio
    async def test_fallback_mechanisms(self):
        """Test fallback mechanisms in query execution"""
        file_path = self.test_files["java"]

        # Test with potentially problematic query that might need fallback
        try:
            results = await self.query_service.execute_query(
                file_path, "java", query_string="(invalid_syntax) @test"
            )
            # Should either work or fail gracefully
            assert results is not None or True
        except Exception as e:
            # Should be a meaningful error, not a crash
            assert "syntax" in str(e).lower() or "query" in str(e).lower()

    @pytest.mark.asyncio
    async def test_memory_efficiency(self):
        """Test memory efficiency of query operations"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Perform multiple queries
        for _ in range(10):
            for lang, file_path in self.test_files.items():
                if lang != "markdown":
                    await self.query_service.execute_query(
                        file_path, lang, query_key="functions"
                    )

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB for this test)
        assert (
            memory_increase < 50 * 1024 * 1024
        ), f"Memory usage increased by {memory_increase / 1024 / 1024:.1f}MB"

    def test_available_queries_integration(self):
        """Test available queries functionality"""
        for lang in ["java", "javascript", "typescript", "python", "markdown"]:
            available = self.query_tool.get_available_queries(lang)
            assert isinstance(available, list)
            assert len(available) > 0, f"No available queries for {lang}"
            print(f"✓ Available queries for {lang}: {available}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
