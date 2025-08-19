#!/usr/bin/env python3
"""
Project Root Detection Demo

Demonstrates the intelligent project root detection and configuration
across CLI and MCP interfaces.
"""

import asyncio
import tempfile
from pathlib import Path

from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.project_detector import (
    ProjectRootDetector,
    detect_project_root,
)


async def main():
    """Demonstrate project root detection and usage."""
    print("🔍 Tree-sitter Analyzer Project Root Detection Demo")
    print("=" * 70)

    # Create a mock project structure
    temp_dir = Path(tempfile.mkdtemp())
    project_root = temp_dir / "demo_project"

    # Create project structure
    project_root.mkdir()
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()

    # Create project markers
    with open(project_root / "pyproject.toml", "w") as f:
        f.write(
            """
[tool.poetry]
name = "demo-project"
version = "0.1.0"
description = "Demo project for tree-sitter-analyzer"

[tool.poetry.dependencies]
python = "^3.8"
"""
        )

    with open(project_root / "README.md", "w") as f:
        f.write(
            "# Demo Project\n\nThis is a demo project for testing project root detection."
        )

    # Create source files
    src_file = project_root / "src" / "main.py"
    with open(src_file, "w") as f:
        f.write(
            """
def fibonacci(n):
    '''Calculate fibonacci number'''
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class Calculator:
    def __init__(self):
        self.history = []

    def add(self, a, b):
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result

    def multiply(self, a, b):
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result
"""
        )

    test_file = project_root / "tests" / "test_main.py"
    with open(test_file, "w") as f:
        f.write(
            """
import unittest
from src.main import Calculator, fibonacci

class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_add(self):
        self.assertEqual(self.calc.add(2, 3), 5)

    def test_multiply(self):
        self.assertEqual(self.calc.multiply(4, 5), 20)

class TestFibonacci(unittest.TestCase):
    def test_fibonacci(self):
        self.assertEqual(fibonacci(0), 0)
        self.assertEqual(fibonacci(1), 1)
        self.assertEqual(fibonacci(5), 5)
"""
        )

    print(f"📁 Created demo project at: {project_root}")
    print(f"📄 Source file: {src_file}")
    print(f"🧪 Test file: {test_file}")
    print()

    # 1. Test Project Root Detection
    print("1️⃣ Testing Project Root Detection")
    print("-" * 50)

    detector = ProjectRootDetector()

    # Test detection from source file
    detected_from_src = detector.detect_from_file(str(src_file))
    print(f"✅ Detection from src file: {detected_from_src}")
    print(f"   Expected: {project_root}")
    print(
        f"   Match: {'✅ YES' if detected_from_src == str(project_root) else '❌ NO'}"
    )

    # Test detection from test file
    detected_from_test = detector.detect_from_file(str(test_file))
    print(f"✅ Detection from test file: {detected_from_test}")
    print(
        f"   Match: {'✅ YES' if detected_from_test == str(project_root) else '❌ NO'}"
    )

    print()

    # 2. Test Unified Detection Function
    print("2️⃣ Testing Unified Detection Function")
    print("-" * 50)

    # Test with file path only
    unified_result1 = detect_project_root(str(src_file))
    print(f"📍 Auto-detection from file: {unified_result1}")

    # Test with explicit root
    explicit_root = temp_dir / "custom_root"
    explicit_root.mkdir()
    unified_result2 = detect_project_root(str(src_file), str(explicit_root))
    print(f"📍 With explicit root: {unified_result2}")
    print(
        f"   Uses explicit: {'✅ YES' if unified_result2 == str(explicit_root.resolve()) else '❌ NO'}"
    )

    print()

    # 3. Test Analysis Engine Integration
    print("3️⃣ Testing Analysis Engine Integration")
    print("-" * 50)

    # Test with auto-detected project root
    engine1 = get_analysis_engine(detected_from_src)
    engine1_root = getattr(engine1, "_project_root", "None")
    print(f"🔧 Engine with auto-detected root: {engine1_root}")

    # Test with explicit project root
    engine2 = get_analysis_engine(str(explicit_root))
    engine2_root = getattr(engine2, "_project_root", "None")
    print(f"🔧 Engine with explicit root: {engine2_root}")

    # Verify they are different instances (due to different project roots)
    print(f"🔧 Different instances: {'✅ YES' if engine1 is not engine2 else '❌ NO'}")

    print()

    # 4. Test MCP Tool Integration
    print("4️⃣ Testing MCP Tool Integration")
    print("-" * 50)

    # Test MCP tool with auto-detected project root
    mcp_tool1 = TableFormatTool(detected_from_src)
    tool1_root = (
        mcp_tool1.security_validator.boundary_manager.project_root
        if mcp_tool1.security_validator.boundary_manager
        else "None"
    )
    print(f"🛠️ MCP tool with auto-detected root: {tool1_root}")

    # Test MCP tool with explicit project root
    mcp_tool2 = TableFormatTool(str(explicit_root))
    tool2_root = (
        mcp_tool2.security_validator.boundary_manager.project_root
        if mcp_tool2.security_validator.boundary_manager
        else "None"
    )
    print(f"🛠️ MCP tool with explicit root: {tool2_root}")

    # Test actual analysis
    try:
        result = await mcp_tool1.execute({"file_path": str(src_file)})
        print(
            f"✅ Analysis successful: Found {len(result.get('elements', []))} elements"
        )
    except Exception as e:
        print(f"❌ Analysis failed: {e}")

    print()

    # 5. Test Security Validation
    print("5️⃣ Testing Security Validation")
    print("-" * 50)

    # Test file within project
    is_valid1, msg1 = mcp_tool1.security_validator.validate_file_path(str(src_file))
    print(
        f"🔒 File within project: {'✅ VALID' if is_valid1 else '❌ INVALID'} - {msg1}"
    )

    # Test file outside project
    outside_file = temp_dir / "outside.py"
    with open(outside_file, "w") as f:
        f.write("print('outside')")

    is_valid2, msg2 = mcp_tool1.security_validator.validate_file_path(str(outside_file))
    print(
        f"🔒 File outside project: {'✅ VALID' if is_valid2 else '❌ INVALID'} - {msg2}"
    )

    # Test malicious path
    is_valid3, msg3 = mcp_tool1.security_validator.validate_file_path(
        "../../../etc/passwd"
    )
    print(
        f"🔒 Malicious path: {'✅ BLOCKED' if not is_valid3 else '❌ ALLOWED'} - {msg3}"
    )

    print()

    # 6. Test CLI Integration Simulation
    print("6️⃣ CLI Integration Examples")
    print("-" * 50)

    print("📝 CLI Usage Examples:")
    print("   # Auto-detect project root:")
    print(f"   tree-sitter-analyzer {src_file} --table=full")
    print()
    print("   # Explicit project root:")
    print(
        f"   tree-sitter-analyzer {src_file} --project-root {project_root} --table=full"
    )
    print()

    # 7. Test MCP Server Integration Simulation
    print("7️⃣ MCP Server Integration Examples")
    print("-" * 50)

    print("📝 MCP Server Configuration Examples:")
    print("   # Auto-detect project root:")
    print('   "command": "python", "args": ["-m", "tree_sitter_analyzer.mcp.server"]')
    print()
    print("   # Explicit project root:")
    print(
        f'   "command": "python", "args": ["-m", "tree_sitter_analyzer.mcp.server", "--project-root", "{project_root}"]'
    )
    print()
    print("   # Environment variable:")
    print(f'   "env": {{"TREE_SITTER_PROJECT_ROOT": "{project_root}"}}')
    print()

    # Cleanup
    import shutil

    shutil.rmtree(str(temp_dir), ignore_errors=True)

    print("🎉 Project Root Detection Demo Complete!")
    print("=" * 70)
    print("Summary:")
    print("✅ Intelligent project root detection from common markers")
    print("✅ Priority-based configuration (explicit > auto-detect > fallback)")
    print("✅ CLI support with --project-root parameter")
    print("✅ MCP server support with command line arguments")
    print("✅ Environment variable support (TREE_SITTER_PROJECT_ROOT)")
    print("✅ Security validation with project boundaries")
    print("✅ Multiple project root support (different instances)")
    print()
    print("🚀 Your tree-sitter-analyzer now has intelligent project management!")


if __name__ == "__main__":
    asyncio.run(main())
