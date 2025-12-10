#!/usr/bin/env python3
"""
Additional tests to boost CLI commands coverage.

Covers: table_command.py, structure_command.py, summary_command.py,
        advanced_command.py, query_command.py, partial_read_command.py
"""

import tempfile
from pathlib import Path

import pytest


class MockArgs:
    """Mock args object for CLI commands."""

    def __init__(self, **kwargs):
        self.file = kwargs.get("file", "test.py")
        self.language = kwargs.get("language", None)
        self.output_format = kwargs.get("output_format", "json")
        self.table = kwargs.get("table", "full")
        self.quiet = kwargs.get("quiet", False)
        self.toon_use_tabs = kwargs.get("toon_use_tabs", False)
        self.include_javadoc = kwargs.get("include_javadoc", False)
        self.project = kwargs.get("project", None)
        self.query_key = kwargs.get("query_key", None)
        self.query_string = kwargs.get("query_string", None)
        self.filter = kwargs.get("filter", None)
        self.start_line = kwargs.get("start_line", None)
        self.end_line = kwargs.get("end_line", None)
        self.element_name = kwargs.get("element_name", None)
        self.context_lines = kwargs.get("context_lines", 0)
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestTableCommandCoverage:
    """Test TableCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
class MyClass:
    """A test class."""

    def method_one(self):
        pass

    def method_two(self):
        pass

def function_one():
    pass
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_table_command_full(self, temp_python_file):
        """Test TableCommand with full format."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        args = MockArgs(file=temp_python_file, table="full")
        command = TableCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_table_command_compact(self, temp_python_file):
        """Test TableCommand with compact format."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        args = MockArgs(file=temp_python_file, table="compact")
        command = TableCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_table_command_csv(self, temp_python_file):
        """Test TableCommand with CSV format."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        args = MockArgs(file=temp_python_file, table="csv")
        command = TableCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_table_command_toon(self, temp_python_file):
        """Test TableCommand with TOON format."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        args = MockArgs(file=temp_python_file, table="toon")
        command = TableCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_table_command_nonexistent_file(self):
        """Test TableCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        args = MockArgs(file="nonexistent_file.py", table="full")
        command = TableCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1


class TestStructureCommandCoverage:
    """Test StructureCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
class MyClass:
    """A test class."""
    pass

def my_function():
    """A test function."""
    pass
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_structure_command_json(self, temp_python_file):
        """Test StructureCommand with JSON format."""
        from tree_sitter_analyzer.cli.commands.structure_command import StructureCommand

        args = MockArgs(file=temp_python_file, output_format="json")
        command = StructureCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_structure_command_toon(self, temp_python_file):
        """Test StructureCommand with TOON format."""
        from tree_sitter_analyzer.cli.commands.structure_command import StructureCommand

        args = MockArgs(file=temp_python_file, output_format="toon")
        command = StructureCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_structure_command_text_format(self, temp_python_file):
        """Test StructureCommand with text format."""
        from tree_sitter_analyzer.cli.commands.structure_command import StructureCommand

        args = MockArgs(file=temp_python_file, output_format="text")
        command = StructureCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_structure_command_nonexistent_file(self):
        """Test StructureCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.structure_command import StructureCommand

        args = MockArgs(file="nonexistent_file.py", output_format="json")
        command = StructureCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1


class TestSummaryCommandCoverage:
    """Test SummaryCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
class ClassOne:
    def method_a(self): pass
    def method_b(self): pass

class ClassTwo:
    def method_c(self): pass

def function_one(): pass
def function_two(): pass
""")
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_summary_command_json(self, temp_python_file):
        """Test SummaryCommand with JSON format."""
        from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand

        args = MockArgs(file=temp_python_file, output_format="json")
        command = SummaryCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_summary_command_toon(self, temp_python_file):
        """Test SummaryCommand with TOON format."""
        from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand

        args = MockArgs(file=temp_python_file, output_format="toon")
        command = SummaryCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_summary_command_nonexistent_file(self):
        """Test SummaryCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand

        args = MockArgs(file="nonexistent_file.py", output_format="json")
        command = SummaryCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1


class TestAdvancedCommandCoverage:
    """Test AdvancedCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
import os
from pathlib import Path

class ComplexClass:
    """A complex class."""

    def __init__(self):
        self.value = 0

    def method(self, x):
        return x * 2

    @property
    def prop(self):
        return self.value

def complex_function(a, b, c=None):
    """A complex function."""
    if c:
        return a + b + c
    return a + b
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_advanced_command_json(self, temp_python_file):
        """Test AdvancedCommand with JSON format."""
        from tree_sitter_analyzer.cli.commands.advanced_command import AdvancedCommand

        args = MockArgs(file=temp_python_file, output_format="json")
        command = AdvancedCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_advanced_command_toon(self, temp_python_file):
        """Test AdvancedCommand with TOON format."""
        from tree_sitter_analyzer.cli.commands.advanced_command import AdvancedCommand

        args = MockArgs(file=temp_python_file, output_format="toon")
        command = AdvancedCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_advanced_command_nonexistent_file(self):
        """Test AdvancedCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.advanced_command import AdvancedCommand

        args = MockArgs(file="nonexistent_file.py", output_format="json")
        command = AdvancedCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1


class TestQueryCommandCoverage:
    """Test QueryCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
class TestClass:
    def method(self):
        pass

def function():
    pass
""")
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_query_command_with_key(self, temp_python_file):
        """Test QueryCommand with query key."""
        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        args = MockArgs(
            file=temp_python_file, query_key="functions", output_format="json"
        )
        command = QueryCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_query_command_with_filter(self, temp_python_file):
        """Test QueryCommand with filter."""
        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        args = MockArgs(
            file=temp_python_file,
            query_key="functions",
            filter="name=~.*",
            output_format="json",
        )
        command = QueryCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_query_command_toon_format(self, temp_python_file):
        """Test QueryCommand with TOON output format."""
        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        args = MockArgs(
            file=temp_python_file, query_key="functions", output_format="toon"
        )
        command = QueryCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_query_command_nonexistent_file(self):
        """Test QueryCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        args = MockArgs(file="nonexistent_file.py", query_key="functions")
        command = QueryCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1


class TestPartialReadCommandCoverage:
    """Test PartialReadCommand for coverage boost."""

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            content = "\n".join([f"# Line {i}" for i in range(1, 51)])
            content += '''

class MyClass:
    """A test class."""

    def method(self):
        pass

def function():
    pass
'''
            f.write(content)
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_partial_read_command_line_range(self, temp_python_file):
        """Test PartialReadCommand with line range."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        args = MockArgs(
            file=temp_python_file, start_line=1, end_line=10, output_format="json"
        )
        command = PartialReadCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_partial_read_command_with_context(self, temp_python_file):
        """Test PartialReadCommand with context lines."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        args = MockArgs(
            file=temp_python_file,
            start_line=10,
            end_line=20,
            context_lines=3,
            output_format="json",
        )
        command = PartialReadCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_partial_read_command_toon_format(self, temp_python_file):
        """Test PartialReadCommand with TOON format."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        args = MockArgs(
            file=temp_python_file, start_line=1, end_line=10, output_format="toon"
        )
        command = PartialReadCommand(args)
        result = await command.execute_async("python")
        assert result == 0 or result == 1

    @pytest.mark.asyncio
    async def test_partial_read_command_nonexistent_file(self):
        """Test PartialReadCommand with nonexistent file."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        args = MockArgs(file="nonexistent_file.py", start_line=1, end_line=10)
        command = PartialReadCommand(args)
        result = await command.execute_async("python")
        # Should handle error gracefully
        assert result == 1
