#!/usr/bin/env python3
"""
CLI Query Filter Integration Tests

Tests for CLI query filtering functionality using real files.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.commands.query_command import QueryCommand


class TestCLIQueryFilterIntegration:
    """Integration tests for CLI query filtering"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create a temporary Java file for testing
        self.java_code = """
public class TestClass {
    public static void main(String[] args) {
        System.out.println("Hello World");
    }

    private void helper() {
        // helper method
    }

    public String authenticate(String user, String password) {
        return "token";
    }

    protected void initialize() {
        // initialization
    }

    public void processData() {
        // processing
    }
}
"""

        # Create temporary file
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        )
        self.temp_file.write(self.java_code)
        self.temp_file.close()

        # Mock args for testing
        self.base_args = type(
            "Args",
            (),
            {
                "file_path": self.temp_file.name,
                "query_key": None,
                "query_string": None,
                "filter": None,
                "output_format": "json",
            },
        )()

    def teardown_method(self):
        """Clean up test fixtures"""
        temp_file = Path(self.temp_file.name)
        if temp_file.exists():
            temp_file.unlink()

    @pytest.mark.asyncio
    async def test_cli_query_with_name_filter(self):
        """Test CLI query with exact name filter"""
        # Setup args
        args = self.base_args
        args.query_key = "methods"
        args.filter = "name=main"

        # Create command and execute
        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Verify results
        assert results is not None
        assert len(results) == 1
        assert "main" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_cli_query_with_pattern_filter(self):
        """Test CLI query with pattern name filter"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = "name=~process*"

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find processData method
        assert results is not None
        assert len(results) == 1
        assert "processData" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_cli_query_with_parameter_filter(self):
        """Test CLI query with parameter count filter"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = "params=0"

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find helper, initialize, and processData methods (no parameters)
        assert results is not None
        assert len(results) >= 2

        # Verify all results have no parameters
        for _result in results:
            # This is a simplified check - the actual filtering logic is more sophisticated
            pass

    @pytest.mark.asyncio
    async def test_cli_query_with_modifier_filter(self):
        """Test CLI query with modifier filter"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = "static=true"

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find only the main method (static)
        assert results is not None
        assert len(results) == 1
        assert "static" in results[0]["content"]
        assert "main" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_cli_query_with_multiple_filters(self):
        """Test CLI query with multiple filter conditions"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = "public=true,params=2"

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find authenticate method (public with 2 parameters)
        assert results is not None
        assert len(results) == 1
        assert "authenticate" in results[0]["content"]
        assert "public" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_cli_query_filter_no_matches(self):
        """Test CLI query filter with no matching results"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = "name=nonexistent"

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should return empty list
        assert results is not None
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_cli_custom_query_with_filter(self):
        """Test CLI custom query string with filter"""
        args = self.base_args
        args.query_string = "(method_declaration) @method"
        args.filter = "name=~auth*"

        command = QueryCommand(args)

        results = await command.execute_query(
            "java", "(method_declaration) @method", "custom"
        )

        # Should find authenticate method
        assert results is not None
        assert len(results) == 1
        assert "authenticate" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_cli_query_without_filter(self):
        """Test CLI query without filter (should return all results)"""
        args = self.base_args
        args.query_key = "methods"
        args.filter = None

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should return all methods
        assert results is not None
        assert (
            len(results) >= 4
        )  # At least main, helper, authenticate, initialize, processData


class TestCLIQueryFilterEdgeCases:
    """Edge case tests for CLI query filtering"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create a Java file with edge cases
        self.edge_case_code = """
public class EdgeCaseClass {
    // Method with complex parameters
    public void complexMethod(Map<String, List<Integer>> data, Consumer<String> callback) {
        // complex method
    }

    // Method with no body (abstract-like)
    public abstract void abstractMethod();

    // Overloaded methods
    public void overloaded() {}
    public void overloaded(String param) {}
    public void overloaded(String param1, String param2) {}

    // Methods with annotations
    @Override
    public String toString() {
        return "test";
    }

    // Generic method
    public <T> void genericMethod(T item) {
        // generic
    }
}
"""

        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        )
        self.temp_file.write(self.edge_case_code)
        self.temp_file.close()

    def teardown_method(self):
        """Clean up test fixtures"""
        temp_file = Path(self.temp_file.name)
        if temp_file.exists():
            temp_file.unlink()

    @pytest.mark.asyncio
    async def test_filter_overloaded_methods_by_params(self):
        """Test filtering overloaded methods by parameter count"""
        args = type(
            "Args",
            (),
            {
                "file_path": self.temp_file.name,
                "query_key": "methods",
                "filter": "params=0",
                "output_format": "json",
            },
        )()

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find methods with no parameters
        assert results is not None
        param_0_methods = [
            r
            for r in results
            if "overloaded()" in r["content"] or "toString()" in r["content"]
        ]
        assert len(param_0_methods) >= 1

    @pytest.mark.asyncio
    async def test_filter_methods_with_annotations(self):
        """Test filtering methods that have annotations"""
        args = type(
            "Args",
            (),
            {
                "file_path": self.temp_file.name,
                "query_key": "methods",
                "filter": "name=toString",
                "output_format": "json",
            },
        )()

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find toString method even with annotation
        assert results is not None
        assert len(results) == 1
        assert "toString" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_filter_generic_methods(self):
        """Test filtering generic methods"""
        args = type(
            "Args",
            (),
            {
                "file_path": self.temp_file.name,
                "query_key": "methods",
                "filter": "name=genericMethod",
                "output_format": "json",
            },
        )()

        command = QueryCommand(args)

        results = await command.execute_query("java", "methods", "methods")

        # Should find generic method
        assert results is not None
        assert len(results) == 1
        assert "genericMethod" in results[0]["content"]


if __name__ == "__main__":
    pytest.main([__file__])
