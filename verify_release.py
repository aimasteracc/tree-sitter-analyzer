#!/usr/bin/env python3
"""
Release Verification Script
Verifies that the v0.6.0 release is working correctly
"""

import subprocess
import sys
import tempfile
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n🔍 {description}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"✅ Success: {description}")
        if result.stdout.strip():
            print(f"Output: {result.stdout.strip()[:200]}...")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {description}")
        print(f"Error: {e.stderr.strip()}")
        return False


def test_local_installation():
    """Test installation from local wheel file"""
    print("\n" + "="*60)
    print("🧪 TESTING LOCAL INSTALLATION")
    print("="*60)
    
    wheel_file = Path("dist/tree_sitter_analyzer-0.6.0-py3-none-any.whl")
    if not wheel_file.exists():
        print(f"❌ Wheel file not found: {wheel_file}")
        return False
    
    # Test installation in isolated environment
    success = run_command([
        "uv", "run", "--isolated", 
        "--with", str(wheel_file),
        "--with", "tree-sitter-java",
        "python", "-c", 
        """
import tree_sitter_analyzer
print(f'Package version: {tree_sitter_analyzer.__version__ if hasattr(tree_sitter_analyzer, "__version__") else "unknown"}')

# Test that CodeAnalyzer is NOT available (breaking change)
try:
    from tree_sitter_analyzer import CodeAnalyzer
    print('❌ ERROR: CodeAnalyzer should not be available!')
    exit(1)
except ImportError:
    print('✅ CodeAnalyzer correctly removed')

# Test new API
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
engine = get_analysis_engine()
print('✅ New analysis engine works')
        """
    ], "Test local wheel installation and API changes")
    
    return success


def test_cli_functionality():
    """Test CLI functionality"""
    print("\n" + "="*60)
    print("🧪 TESTING CLI FUNCTIONALITY")
    print("="*60)
    
    # Create a test Java file
    test_content = '''
public class TestClass {
    private String name;
    
    public TestClass(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
}
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
        f.write(test_content)
        test_file = f.name
    
    try:
        # Test CLI with local wheel
        success = run_command([
            "uv", "run", "--isolated",
            "--with", "dist/tree_sitter_analyzer-0.6.0-py3-none-any.whl",
            "--with", "tree-sitter-java",
            "tree-sitter-analyzer", test_file, "--advanced"
        ], "Test CLI functionality with local wheel")
        
        return success
    finally:
        Path(test_file).unlink(missing_ok=True)


def test_pypi_installation():
    """Test installation from PyPI (if available)"""
    print("\n" + "="*60)
    print("🧪 TESTING PYPI INSTALLATION")
    print("="*60)
    
    # Test if package is available on PyPI
    success = run_command([
        "uv", "run", "--isolated",
        "--with", "tree-sitter-analyzer==0.6.0",
        "python", "-c",
        """
import tree_sitter_analyzer
print('✅ Successfully installed from PyPI')

# Test that CodeAnalyzer is NOT available
try:
    from tree_sitter_analyzer import CodeAnalyzer
    print('❌ ERROR: CodeAnalyzer should not be available!')
    exit(1)
except ImportError:
    print('✅ CodeAnalyzer correctly removed from PyPI package')
        """
    ], "Test PyPI installation")
    
    return success


def main():
    """Main verification function"""
    print("🚀 Tree-sitter Analyzer v0.6.0 Release Verification")
    print("="*60)
    
    results = []
    
    # Test local installation
    results.append(("Local Installation", test_local_installation()))
    
    # Test CLI functionality
    results.append(("CLI Functionality", test_cli_functionality()))
    
    # Test PyPI installation (may fail if not yet published)
    results.append(("PyPI Installation", test_pypi_installation()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 VERIFICATION SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Release v0.6.0 is ready!")
    else:
        print("⚠️  Some tests failed. Please review the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
