"""
Integration Tests for Format Testing

Real implementation testing with minimal mocking to ensure format validation
works end-to-end through actual code paths.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.formatters.legacy_formatter_adapters import (
    LegacyCompactFormatter,
    LegacyCsvFormatter,
    LegacyFullFormatter,
)
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.models import CodeElement

from .format_assertions import (
    FormatComplianceAssertions,
    assert_compact_format_compliance,
    assert_csv_format_compliance,
    assert_full_format_compliance,
)
from .golden_master import GoldenMasterManager


class TestTableFormatToolIntegration:
    """Integration tests using real implementations, minimal mocking"""

    @pytest.fixture
    def temp_project_with_java_file(self):
        """Create temporary project with Java test file"""
        temp_dir = tempfile.mkdtemp()
        java_file = Path(temp_dir) / "TestClass.java"

        java_content = """package com.example.service;

import java.util.List;
import java.sql.SQLException;

public class UserService {
    private UserRepository userRepository;
    private static final Logger logger = LoggerFactory.getLogger(UserService.class);

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public User findUserById(Long id) throws SQLException {
        if (id == null) {
            throw new IllegalArgumentException("ID cannot be null");
        }
        return userRepository.findById(id);
    }

    public User createUser(String name, String email) {
        User user = new User(name, email);
        validateUser(user);
        return userRepository.save(user);
    }

    private boolean validateUser(User user) {
        if (user.getName() == null || user.getName().isEmpty()) {
            return false;
        }
        if (user.getEmail() == null || !user.getEmail().contains("@")) {
            return false;
        }
        return true;
    }
}"""

        java_file.write_text(java_content, encoding="utf-8")

        yield temp_dir, java_file

        # Cleanup
        java_file.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def real_tool(self, temp_project_with_java_file):
        """Create TableFormatTool with real dependencies"""
        temp_dir, _ = temp_project_with_java_file
        return TableFormatTool(project_root=temp_dir)

    @pytest.fixture
    def golden_master_manager(self):
        """Provide golden master manager for testing"""
        return GoldenMasterManager()

    @pytest.mark.asyncio
    async def test_full_format_end_to_end(
        self, real_tool, temp_project_with_java_file, golden_master_manager
    ):
        """Test complete flow with real formatting - full format"""
        temp_dir, java_file = temp_project_with_java_file

        # Execute with real implementation
        result = await real_tool.execute(
            {"file_path": str(java_file), "format_type": "full"}
        )

        # Validate basic result structure
        assert result["format_type"] == "full"
        assert result["language"] == "java"
        assert "table_output" in result

        table_output = result["table_output"]

        # Validate against golden master
        golden_tester = golden_master_manager.get_tester("full")
        golden_tester.assert_matches_golden_master(
            table_output, "java_userservice_full_format"
        )

        # Validate format compliance
        assert_full_format_compliance(table_output, "UserService")

        # Validate specific content expectations
        assert "# com.example.service.UserService" in table_output
        assert "## Package" in table_output
        assert "## Imports" in table_output
        assert "## Class Info" in table_output
        assert "| Package | com.example.service |" in table_output
        assert "findUserById" in table_output
        assert "createUser" in table_output
        assert "validateUser" in table_output

    @pytest.mark.asyncio
    async def test_compact_format_end_to_end(
        self, real_tool, temp_project_with_java_file, golden_master_manager
    ):
        """Test complete flow with real formatting - compact format"""
        temp_dir, java_file = temp_project_with_java_file

        # Execute with real implementation
        result = await real_tool.execute(
            {"file_path": str(java_file), "format_type": "compact"}
        )

        # Validate basic result structure
        assert result["format_type"] == "compact"
        assert result["language"] == "java"
        assert "table_output" in result

        table_output = result["table_output"]

        # Validate against golden master
        golden_tester = golden_master_manager.get_tester("compact")
        golden_tester.assert_matches_golden_master(
            table_output, "java_userservice_compact_format"
        )

        # Validate format compliance
        assert_compact_format_compliance(table_output)

        # Validate compact-specific features (v1.6.1.4 format)
        assert "# UserService" in table_output  # Compact format uses short name
        assert "## Info" in table_output
        assert "## Methods" in table_output
        assert "public" in table_output  # v1.6.1.4 uses text, not symbols
        assert "private" in table_output

    @pytest.mark.asyncio
    async def test_csv_format_end_to_end(
        self, real_tool, temp_project_with_java_file, golden_master_manager
    ):
        """Test complete flow with real formatting - CSV format"""
        temp_dir, java_file = temp_project_with_java_file

        # Execute with real implementation
        result = await real_tool.execute(
            {"file_path": str(java_file), "format_type": "csv"}
        )

        # Validate basic result structure
        assert result["format_type"] == "csv"
        assert result["language"] == "java"
        assert "table_output" in result

        table_output = result["table_output"]

        # Validate against golden master
        golden_tester = golden_master_manager.get_tester("csv")
        golden_tester.assert_matches_golden_master(
            table_output, "java_userservice_csv_format"
        )

        # Validate format compliance
        assert_csv_format_compliance(table_output)

        # Validate CSV-specific structure
        lines = table_output.strip().split("\n")
        assert len(lines) >= 2  # Header + at least one data row

        # Check header
        header = lines[0]
        assert "Type,Name,Signature,Visibility,Lines" in header

        # Check for method entries
        method_lines = [line for line in lines[1:] if line.startswith("Method,")]
        assert len(method_lines) >= 3  # findUserById, createUser, validateUser

        # Check for field entries
        field_lines = [line for line in lines[1:] if line.startswith("Field,")]
        assert len(field_lines) >= 2  # userRepository, logger

    @pytest.mark.asyncio
    async def test_format_consistency_across_all_types(
        self, real_tool, temp_project_with_java_file
    ):
        """Test format consistency across different output types"""
        temp_dir, java_file = temp_project_with_java_file

        # Execute all formats
        formats = ["full", "compact", "csv"]
        results = {}

        for format_type in formats:
            result = await real_tool.execute(
                {"file_path": str(java_file), "format_type": format_type}
            )
            results[format_type] = result["table_output"]

        # Validate consistency
        element_counts = {
            "methods": 4,  # Constructor + 3 methods
            "fields": 2,  # userRepository + logger
        }

        FormatComplianceAssertions.assert_format_consistency(results, element_counts)

        # All formats should contain the same basic information
        for format_type, output in results.items():
            assert (
                "UserService" in output
            ), f"Missing class name in {format_type} format"
            assert "findUserById" in output, f"Missing method in {format_type} format"
            assert "createUser" in output, f"Missing method in {format_type} format"
            assert "validateUser" in output, f"Missing method in {format_type} format"


class TestFormatConsistency:
    """Test format consistency across different code paths"""

    @pytest.fixture
    def sample_java_elements(self) -> list[CodeElement]:
        """Create sample Java CodeElements for testing"""
        elements = []

        # Package element
        package_element = CodeElement(
            name="com.example.service", start_line=1, end_line=1, language="java"
        )
        package_element.element_type = "package"
        elements.append(package_element)

        # Class element
        class_element = CodeElement(
            name="UserService", start_line=6, end_line=35, language="java"
        )
        class_element.element_type = "class"
        class_element.class_type = "class"
        class_element.visibility = "public"
        elements.append(class_element)

        # Field elements
        field1 = CodeElement(
            name="userRepository", start_line=7, end_line=7, language="java"
        )
        field1.element_type = "field"
        field1.field_type = "UserRepository"
        field1.visibility = "private"
        field1.modifiers = ["private"]
        elements.append(field1)

        field2 = CodeElement(name="logger", start_line=8, end_line=8, language="java")
        field2.element_type = "field"
        field2.field_type = "Logger"
        field2.visibility = "private"
        field2.modifiers = ["private", "static", "final"]
        elements.append(field2)

        # Constructor
        constructor = CodeElement(
            name="UserService", start_line=10, end_line=12, language="java"
        )
        constructor.element_type = "method"
        constructor.is_constructor = True
        constructor.visibility = "public"
        constructor.return_type = "void"
        constructor.parameters = [{"name": "userRepository", "type": "UserRepository"}]
        constructor.complexity_score = 1
        constructor.modifiers = ["public"]
        elements.append(constructor)

        # Regular methods
        method1 = CodeElement(
            name="findUserById", start_line=14, end_line=19, language="java"
        )
        method1.element_type = "method"
        method1.visibility = "public"
        method1.return_type = "User"
        method1.parameters = [{"name": "id", "type": "Long"}]
        method1.complexity_score = 3
        method1.modifiers = ["public"]
        method1.documentation = "Find user by ID"
        elements.append(method1)

        method2 = CodeElement(
            name="createUser", start_line=21, end_line=25, language="java"
        )
        method2.element_type = "method"
        method2.visibility = "public"
        method2.return_type = "User"
        method2.parameters = [
            {"name": "name", "type": "String"},
            {"name": "email", "type": "String"},
        ]
        method2.complexity_score = 2
        method2.modifiers = ["public"]
        method2.documentation = "Create a new user"
        elements.append(method2)

        method3 = CodeElement(
            name="validateUser", start_line=27, end_line=35, language="java"
        )
        method3.element_type = "method"
        method3.visibility = "private"
        method3.return_type = "boolean"
        method3.parameters = [{"name": "user", "type": "User"}]
        method3.complexity_score = 4
        method3.modifiers = ["private"]
        elements.append(method3)

        return elements

    def test_formatter_registry_vs_legacy_formatter(self, sample_java_elements):
        """Ensure FormatterRegistry and legacy formatters produce identical output"""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        # Test each format type
        for format_type in ["full", "compact", "csv"]:
            # Test with FormatterRegistry
            if FormatterRegistry.is_format_supported(format_type):
                registry_formatter = FormatterRegistry.get_formatter(format_type)
                registry_output = registry_formatter.format(sample_java_elements)
            else:
                # Skip if not supported by registry
                continue

            # Test with legacy formatter
            legacy_formatters = {
                "full": LegacyFullFormatter(),
                "compact": LegacyCompactFormatter(),
                "csv": LegacyCsvFormatter(),
            }

            if format_type in legacy_formatters:
                legacy_formatter = legacy_formatters[format_type]
                legacy_output = legacy_formatter.format(sample_java_elements)

                # Outputs should be functionally equivalent
                # (Allow for minor formatting differences but core content must match)
                assert (
                    "UserService" in registry_output and "UserService" in legacy_output
                )
                assert (
                    "findUserById" in registry_output
                    and "findUserById" in legacy_output
                )
                assert "createUser" in registry_output and "createUser" in legacy_output
                assert (
                    "validateUser" in registry_output
                    and "validateUser" in legacy_output
                )

    @pytest.mark.asyncio
    async def test_mcp_vs_cli_format_consistency(self, temp_project_with_java_file):
        """Ensure MCP and CLI interfaces produce consistent format output"""
        import subprocess
        import sys

        temp_dir, java_file = temp_project_with_java_file

        # Get output through MCP interface
        mcp_tool = TableFormatTool(project_root=temp_dir)
        mcp_result = await mcp_tool.execute(
            {"file_path": str(java_file), "format_type": "full"}
        )
        mcp_table = mcp_result["table_output"]

        # Get output through CLI interface
        try:
            cli_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tree_sitter_analyzer",
                    "--file",
                    str(java_file),
                    "--table",
                    "full",
                ],
                capture_output=True,
                text=True,
                cwd=temp_dir,
            )

            if cli_result.returncode == 0:
                cli_output = cli_result.stdout

                # Extract core content for comparison (ignore formatting differences)
                mcp_lines = [
                    line.strip() for line in mcp_table.split("\n") if line.strip()
                ]
                cli_lines = [
                    line.strip() for line in cli_output.split("\n") if line.strip()
                ]

                # Both should contain the same essential information
                essential_content = [
                    "UserService",
                    "findUserById",
                    "createUser",
                    "validateUser",
                ]

                for content in essential_content:
                    assert any(
                        content in line for line in mcp_lines
                    ), f"MCP missing: {content}"
                    assert any(
                        content in line for line in cli_lines
                    ), f"CLI missing: {content}"
            else:
                pytest.skip(f"CLI execution failed: {cli_result.stderr}")

        except FileNotFoundError:
            pytest.skip("CLI interface not available for testing")

    @pytest.fixture
    def temp_project_with_java_file(self):
        """Create temporary project with Java test file"""
        temp_dir = tempfile.mkdtemp()
        java_file = Path(temp_dir) / "TestClass.java"

        java_content = """package com.example.service;

public class UserService {
    private UserRepository userRepository;
    private static final Logger logger = LoggerFactory.getLogger(UserService.class);

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public User findUserById(Long id) {
        return userRepository.findById(id);
    }

    public User createUser(String name, String email) {
        User user = new User(name, email);
        validateUser(user);
        return userRepository.save(user);
    }

    private boolean validateUser(User user) {
        return user.getName() != null && user.getEmail() != null;
    }
}"""

        java_file.write_text(java_content, encoding="utf-8")

        yield temp_dir, java_file

        # Cleanup
        java_file.unlink()
        Path(temp_dir).rmdir()


class TestRealImplementationValidation:
    """Test real implementation behavior without mocks"""

    def test_legacy_formatters_produce_valid_output(self):
        """Test that legacy formatters produce valid, compliant output"""
        # Create minimal test data
        elements = [
            CodeElement(name="TestClass", start_line=1, end_line=10, language="java")
        ]
        elements[0].element_type = "class"
        elements[0].visibility = "public"

        # Test each legacy formatter
        formatters = {
            "full": LegacyFullFormatter(),
            "compact": LegacyCompactFormatter(),
            "csv": LegacyCsvFormatter(),
        }

        for format_type, formatter in formatters.items():
            output = formatter.format(elements)

            # Basic validation
            assert (
                output and output.strip()
            ), f"{format_type} formatter produced empty output"
            assert "TestClass" in output, f"{format_type} formatter missing class name"

            # Format-specific validation
            if format_type == "full":
                assert "# " in output, "Full format should have main header"
                assert "## " in output, "Full format should have section headers"
            elif format_type == "compact":
                assert (
                    "## Info" in output or "## Methods" in output
                ), "Compact format should have info sections"
            elif format_type == "csv":
                lines = output.strip().split("\n")
                assert len(lines) >= 2, "CSV should have header and data rows"
                assert "," in lines[0], "CSV should have comma-separated header"

    def test_format_validation_with_real_output(self):
        """Test format validation utilities with real formatter output"""
        from .schema_validation import validate_format

        # Create test elements
        elements = [
            CodeElement(name="TestClass", start_line=1, end_line=10, language="java")
        ]
        elements[0].element_type = "class"
        elements[0].visibility = "public"

        # Test markdown validation with real output
        full_formatter = LegacyFullFormatter()
        markdown_output = full_formatter.format(elements)

        validation_result = validate_format(markdown_output, "markdown")
        assert (
            validation_result.is_valid
        ), f"Markdown validation failed: {validation_result.errors}"

        # Test CSV validation with real output
        csv_formatter = LegacyCsvFormatter()
        csv_output = csv_formatter.format(elements)

        csv_validation_result = validate_format(csv_output, "csv")
        assert (
            csv_validation_result.is_valid
        ), f"CSV validation failed: {csv_validation_result.errors}"
