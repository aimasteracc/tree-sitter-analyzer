#!/usr/bin/env python3
"""
Package Name Fix Verification Script

This script verifies that the package name parsing fix is working correctly
by testing the exact scenarios that were failing before the fix.

Expected Results (after fix):
- CLI command should show: # com.example.service.BigService
- CLI command should show: | Package | com.example.service |
- MCP tool should show: # com.example.service.BigService
- MCP tool should show: | Package | com.example.service |

Before Fix (incorrect):
- CLI command showed: # unknown.BigService
- CLI command showed: | Package | unknown |
- MCP tool showed: # unknown.BigService
- MCP tool showed: | Package | unknown |
"""

import subprocess
import sys
from pathlib import Path
import pytest

from tree_sitter_analyzer.language_loader import get_loader
from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine, AnalysisRequest
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


def test_extractor_direct():
    """Test JavaElementExtractor directly."""
    # Read BigService.java
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        pytest.skip("BigService.java not found")

    with open(bigservice_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # Parse
    loader = get_loader()
    parser = loader.create_parser_safely('java')
    tree = parser.parse(source_code.encode('utf-8'))

    # Test independent extract_classes call (this was the failing case)
    extractor = JavaElementExtractor()
    classes = extractor.extract_classes(tree, source_code)

    # Assertions
    assert len(classes) == 1
    assert classes[0].package_name == "com.example.service"
    assert classes[0].name == "BigService"
    assert classes[0].full_qualified_name == "com.example.service.BigService"


@pytest.mark.asyncio
async def test_analysis_engine():
    """Test UnifiedAnalysisEngine."""
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        pytest.skip("BigService.java not found")

    engine = get_analysis_engine()
    request = AnalysisRequest(
        file_path=str(bigservice_path),
        language='java',
        include_complexity=True,
        include_details=True,
    )

    result = await engine.analyze(request)

    # Check for class elements (main focus of the fix)
    class_elements = [e for e in result.elements if e.__class__.__name__ == 'Class']

    # Assertions - focus on the main issue: class package names
    assert len(class_elements) == 1, f"Expected 1 class, got {len(class_elements)}"
    assert class_elements[0].name == "BigService", f"Expected BigService, got {class_elements[0].name}"
    assert class_elements[0].package_name == "com.example.service", f"Expected com.example.service, got {class_elements[0].package_name}"

    # Check for package elements (if available, but not required for the fix)
    package_elements = [e for e in result.elements if e.__class__.__name__ == 'Package']
    if package_elements:
        assert package_elements[0].name == "com.example.service"


def test_cli_command():
    """Test CLI command output."""
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        pytest.skip("BigService.java not found")

    # Run CLI command
    result = subprocess.run([
        sys.executable, "-m", "tree_sitter_analyzer",
        str(bigservice_path), "--table=full"
    ], capture_output=True, text=True, cwd=".")

    # Check command succeeded
    assert result.returncode == 0, f"CLI command failed: {result.stderr}"

    output = result.stdout

    # Check for correct package name in header and table
    assert "# com.example.service.BigService" in output, "Header does not show correct package name"
    assert "| Package | com.example.service |" in output, "Table does not show correct package name"

    # Check that old incorrect output is not present
    assert "# unknown.BigService" not in output, "Still shows 'unknown' in header"
    assert "| Package | unknown |" not in output, "Still shows 'unknown' in table"


@pytest.mark.asyncio
async def test_mcp_tool():
    """Test MCP tool output."""
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        pytest.skip("BigService.java not found")

    tool = TableFormatTool()
    result = await tool.execute({
        'file_path': str(bigservice_path),
        'format_type': 'full'
    })

    # Check tool execution succeeded
    assert isinstance(result, dict), "MCP tool execution failed"
    assert 'table_output' in result, "MCP tool result missing table_output"

    content = result['table_output']

    # Check for correct package name in header and table
    assert "# com.example.service.BigService" in content, "MCP header does not show correct package name"
    assert "| Package | com.example.service |" in content, "MCP table does not show correct package name"

    # Check that old incorrect output is not present
    assert "# unknown.BigService" not in content, "MCP still shows 'unknown' in header"
    assert "| Package | unknown |" not in content, "MCP still shows 'unknown' in table"


# This file contains pytest tests for package name fix verification.
# Run with: pytest tests/test_package_fix_verification.py -v
