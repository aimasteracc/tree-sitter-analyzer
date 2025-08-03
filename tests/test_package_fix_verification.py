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

import asyncio
import subprocess
import sys
from pathlib import Path

from tree_sitter_analyzer.language_loader import get_loader
from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine, AnalysisRequest
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


def test_extractor_direct():
    """Test JavaElementExtractor directly."""
    print("=== Testing JavaElementExtractor directly ===")
    
    # Read BigService.java
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        print("❌ BigService.java not found")
        return False
    
    with open(bigservice_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # Parse
    loader = get_loader()
    parser = loader.create_parser_safely('java')
    tree = parser.parse(source_code.encode('utf-8'))

    # Test independent extract_classes call (this was the failing case)
    extractor = JavaElementExtractor()
    classes = extractor.extract_classes(tree, source_code)
    
    if len(classes) == 1 and classes[0].package_name == "com.example.service":
        print("✅ JavaElementExtractor: Package name correctly extracted")
        print(f"   Class: {classes[0].name}")
        print(f"   Package: {classes[0].package_name}")
        print(f"   Full name: {classes[0].full_qualified_name}")
        return True
    else:
        print("❌ JavaElementExtractor: Package name extraction failed")
        if classes:
            print(f"   Got package: {classes[0].package_name}")
        return False


async def test_analysis_engine():
    """Test UnifiedAnalysisEngine."""
    print("\n=== Testing UnifiedAnalysisEngine ===")
    
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        print("❌ BigService.java not found")
        return False
    
    engine = get_analysis_engine()
    request = AnalysisRequest(
        file_path=str(bigservice_path),
        language='java',
        include_complexity=True,
        include_details=True,
    )
    
    result = await engine.analyze(request)
    
    # Check for package elements
    package_elements = [e for e in result.elements if e.__class__.__name__ == 'Package']
    class_elements = [e for e in result.elements if e.__class__.__name__ == 'Class']
    
    if len(package_elements) == 1 and package_elements[0].name == "com.example.service":
        print("✅ UnifiedAnalysisEngine: Package element correctly extracted")
        print(f"   Package elements: {len(package_elements)}")
        print(f"   Package name: {package_elements[0].name}")
    else:
        print("❌ UnifiedAnalysisEngine: Package element extraction failed")
        print(f"   Package elements: {len(package_elements)}")
        return False
    
    if len(class_elements) == 1 and class_elements[0].package_name == "com.example.service":
        print("✅ UnifiedAnalysisEngine: Class package info correctly set")
        print(f"   Class: {class_elements[0].name}")
        print(f"   Class package: {class_elements[0].package_name}")
        return True
    else:
        print("❌ UnifiedAnalysisEngine: Class package info incorrect")
        if class_elements:
            print(f"   Got class package: {class_elements[0].package_name}")
        return False


def test_cli_command():
    """Test CLI command output."""
    print("\n=== Testing CLI Command ===")
    
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        print("❌ BigService.java not found")
        return False
    
    try:
        # Run CLI command
        result = subprocess.run([
            sys.executable, "-m", "tree_sitter_analyzer", 
            str(bigservice_path), "--table=full"
        ], capture_output=True, text=True, cwd=".")
        
        if result.returncode != 0:
            print("❌ CLI command failed")
            print(f"   Error: {result.stderr}")
            return False
        
        output = result.stdout
        
        # Check for correct package name in header and table
        if "# com.example.service.BigService" in output:
            print("✅ CLI: Header shows correct package name")
        else:
            print("❌ CLI: Header does not show correct package name")
            return False
        
        if "| Package | com.example.service |" in output:
            print("✅ CLI: Table shows correct package name")
        else:
            print("❌ CLI: Table does not show correct package name")
            return False
        
        # Check that old incorrect output is not present
        if "# unknown.BigService" in output or "| Package | unknown |" in output:
            print("❌ CLI: Still shows 'unknown' package")
            return False
        
        print("✅ CLI: All package name checks passed")
        return True
        
    except Exception as e:
        print(f"❌ CLI command test failed: {e}")
        return False


async def test_mcp_tool():
    """Test MCP tool output."""
    print("\n=== Testing MCP Tool ===")
    
    bigservice_path = Path("examples/BigService.java")
    if not bigservice_path.exists():
        print("❌ BigService.java not found")
        return False
    
    try:
        tool = TableFormatTool()
        result = await tool.execute({
            'file_path': str(bigservice_path),
            'format_type': 'full'
        })
        
        if not isinstance(result, dict) or 'table_output' not in result:
            print("❌ MCP tool execution failed")
            return False
        
        content = result['table_output']
        
        # Check for correct package name in header and table
        if "# com.example.service.BigService" in content:
            print("✅ MCP: Header shows correct package name")
        else:
            print("❌ MCP: Header does not show correct package name")
            return False
        
        if "| Package | com.example.service |" in content:
            print("✅ MCP: Table shows correct package name")
        else:
            print("❌ MCP: Table does not show correct package name")
            return False
        
        # Check that old incorrect output is not present
        if "# unknown.BigService" in content or "| Package | unknown |" in content:
            print("❌ MCP: Still shows 'unknown' package")
            return False
        
        print("✅ MCP: All package name checks passed")
        return True
        
    except Exception as e:
        print(f"❌ MCP tool test failed: {e}")
        return False


async def main():
    """Run all verification tests."""
    print("Package Name Fix Verification")
    print("=" * 50)
    
    tests = [
        ("JavaElementExtractor Direct", test_extractor_direct()),
        ("UnifiedAnalysisEngine", await test_analysis_engine()),
        ("CLI Command", test_cli_command()),
        ("MCP Tool", await test_mcp_tool()),
    ]
    
    all_passed = True
    
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    
    for test_name, result in tests:
        if isinstance(result, bool):
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name}: {status}")
            if not result:
                all_passed = False
        else:
            # Handle coroutine case
            print(f"{test_name}: ❌ FAIL (async issue)")
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Package name fix is working correctly!")
        print("\nThe issue has been successfully resolved:")
        print("- Package names are now correctly extracted and displayed")
        print("- Both CLI and MCP tools show 'com.example.service' instead of 'unknown'")
        print("- The fix handles independent method calls correctly")
    else:
        print("❌ SOME TESTS FAILED - Package name fix needs more work")
        print("\nPlease check the failed tests above and fix the issues.")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
