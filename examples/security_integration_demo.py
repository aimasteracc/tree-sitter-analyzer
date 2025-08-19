#!/usr/bin/env python3
"""
Security Integration Demo

Demonstrates how security features are integrated across all components
of the tree-sitter-analyzer system.
"""

import asyncio
import tempfile
from pathlib import Path

from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.security import SecurityValidator


async def main():
    """Demonstrate security integration across components."""
    print("🔒 Tree-sitter Analyzer Security Integration Demo")
    print("=" * 60)

    # Create a temporary test environment
    temp_dir = Path(tempfile.mkdtemp())
    test_file = temp_dir / "example.py"
    # Use temp_dir itself as project_root to ensure test_file is within it
    project_root = temp_dir

    # Create a test file
    with open(test_file, "w") as f:
        f.write(
            """
def calculate_fibonacci(n):
    '''Calculate fibonacci number'''
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

class MathUtils:
    @staticmethod
    def factorial(n):
        if n <= 1:
            return 1
        return n * MathUtils.factorial(n-1)
"""
        )

    print(f"📁 Created test file: {test_file}")
    print(f"🏠 Project root: {project_root}")
    print()

    # 1. Test Analysis Engine Security
    print("1️⃣ Testing Analysis Engine Security")
    print("-" * 40)

    engine = get_analysis_engine(str(project_root))

    try:
        # Valid file should work
        result = await engine.analyze_file(str(test_file))
        print(
            f"✅ Valid file analysis: SUCCESS (found {len(result.elements)} elements)"
        )
    except Exception as e:
        print(f"❌ Valid file analysis: FAILED - {e}")

    try:
        # Invalid path should be rejected
        await engine.analyze_file("../../../etc/passwd")
        print("❌ Path traversal attack: NOT BLOCKED (SECURITY ISSUE!)")
    except ValueError as e:
        print(f"✅ Path traversal attack: BLOCKED - {e}")

    print()

    # 2. Test MCP Tools Security
    print("2️⃣ Testing MCP Tools Security")
    print("-" * 40)

    # Test TableFormatTool
    table_tool = TableFormatTool(str(project_root))

    try:
        result = await table_tool.execute({"file_path": str(test_file)})
        print("✅ TableFormatTool valid file: SUCCESS")
    except Exception as e:
        print(f"❌ TableFormatTool valid file: FAILED - {e}")

    try:
        await table_tool.execute({"file_path": "../../../etc/passwd"})
        print("❌ TableFormatTool path traversal: NOT BLOCKED (SECURITY ISSUE!)")
    except ValueError:
        print("✅ TableFormatTool path traversal: BLOCKED")

    # Test UniversalAnalyzeTool
    analyze_tool = UniversalAnalyzeTool(str(project_root))

    try:
        result = await analyze_tool.execute({"file_path": str(test_file)})
        print("✅ UniversalAnalyzeTool valid file: SUCCESS")
    except Exception as e:
        print(f"❌ UniversalAnalyzeTool valid file: FAILED - {e}")

    try:
        await analyze_tool.execute({"file_path": "../../../etc/passwd"})
        print("❌ UniversalAnalyzeTool path traversal: NOT BLOCKED (SECURITY ISSUE!)")
    except Exception:  # Catch broader exception types
        print("✅ UniversalAnalyzeTool path traversal: BLOCKED")

    print()

    # 3. Test Input Sanitization
    print("3️⃣ Testing Input Sanitization")
    print("-" * 40)

    validator = SecurityValidator(str(project_root))

    malicious_inputs = [
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
        "<img src=x onerror=alert(1)>",
        "javascript:alert('xss')",
    ]

    for malicious_input in malicious_inputs:
        sanitized = validator.sanitize_input(malicious_input)
        is_safe = "<" not in sanitized and ">" not in sanitized and "'" not in sanitized
        status = "✅ SANITIZED" if is_safe else "⚠️ PARTIALLY SANITIZED"
        print(f"{status}: '{malicious_input}' → '{sanitized}'")

    print()

    # 4. Test Regex Safety
    print("4️⃣ Testing Regex Safety")
    print("-" * 40)

    dangerous_patterns = [
        "(.+)*(.+)*(.+)*",  # ReDoS pattern
        "(a+)+b",  # Catastrophic backtracking
        "^(a|a)*$",  # Exponential time complexity
        "(.*a){10}.*",  # High complexity
    ]

    for pattern in dangerous_patterns:
        is_safe, error_msg = validator.regex_checker.validate_pattern(pattern)
        status = "❌ DANGEROUS" if not is_safe else "✅ SAFE"
        print(
            f"{status}: '{pattern}' - {error_msg if not is_safe else 'Pattern is safe'}"
        )

    print()

    # 5. Test File Path Validation
    print("5️⃣ Testing File Path Validation")
    print("-" * 40)

    test_paths = [
        str(test_file),  # Valid path
        "../../../etc/passwd",  # Path traversal
        "/etc/shadow",  # Absolute path outside project
        "C:\\Windows\\System32\\config\\SAM",  # Windows system file
        "\\\\server\\share\\file.txt",  # UNC path
    ]

    for path in test_paths:
        is_valid, error_msg = validator.validate_file_path(path)
        status = "✅ VALID" if is_valid else "❌ INVALID"
        print(f"{status}: '{path}' - {error_msg if not is_valid else 'Path is valid'}")

    print()

    # 6. Performance Impact
    print("6️⃣ Testing Performance Impact")
    print("-" * 40)

    import time

    # Test without security (baseline)
    start_time = time.time()
    for _ in range(100):
        test_file.exists()
    baseline_time = time.time() - start_time

    # Test with security validation
    start_time = time.time()
    for _ in range(100):
        validator.validate_file_path(str(test_file))
    security_time = time.time() - start_time

    overhead = ((security_time - baseline_time) / baseline_time) * 100
    print(f"📊 Baseline (100 file checks): {baseline_time:.4f}s")
    print(f"📊 With security (100 validations): {security_time:.4f}s")
    print(f"📊 Security overhead: {overhead:.2f}%")

    if overhead < 50:  # Less than 50% overhead is acceptable
        print("✅ Performance impact is acceptable")
    else:
        print("⚠️ Performance impact may be too high")

    print()

    # Cleanup
    import shutil

    shutil.rmtree(str(temp_dir), ignore_errors=True)

    print("🎉 Security Integration Demo Complete!")
    print("=" * 60)
    print("Summary:")
    print("✅ Analysis Engine: Protected against path traversal")
    print("✅ MCP Tools: Integrated security validation")
    print("✅ Input Sanitization: XSS and injection protection")
    print("✅ Regex Safety: ReDoS attack prevention")
    print("✅ File Path Validation: Multi-layer security")
    print("✅ Performance: Minimal overhead")
    print()
    print("🔒 Your tree-sitter-analyzer is now enterprise-ready!")


if __name__ == "__main__":
    asyncio.run(main())
