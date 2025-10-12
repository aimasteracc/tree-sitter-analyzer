#!/usr/bin/env python3
"""
Test script to verify debug_utils can be imported from the main package
"""

def test_direct_import():
    """Test importing debug utilities directly"""
    print("=== Testing Direct Import ===")
    try:
        from tree_sitter_analyzer.debug_utils import execute_debug_code
        print("✅ Direct import successful")
        return True
    except ImportError as e:
        print(f"❌ Direct import failed: {e}")
        return False

def test_package_import():
    """Test importing debug utilities from main package"""
    print("\n=== Testing Package Import ===")
    try:
        from tree_sitter_analyzer import execute_debug_code, DebugScriptManager
        print("✅ Package import successful")
        return True
    except ImportError as e:
        print(f"❌ Package import failed: {e}")
        return False

def test_functionality():
    """Test basic functionality"""
    print("\n=== Testing Functionality ===")
    try:
        from tree_sitter_analyzer import execute_debug_code
        
        test_code = '''
print("Hello from imported debug utils!")
print("Testing UTF-8: 测试中文")
result = 1 + 1
print(f"Math works: {result}")
'''
        
        result = execute_debug_code(test_code)
        if result['success']:
            print("✅ Functionality test successful")
            print("Output:")
            print(result['stdout'])
            return True
        else:
            print(f"❌ Functionality test failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Functionality test error: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Debug Utils Import and Functionality")
    print("=" * 50)
    
    tests = [
        test_direct_import,
        test_package_import,
        test_functionality
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests passed! Debug utils are ready to use.")
    else:
        print("⚠️ Some tests failed. Please check the implementation.")
    
    return all(results)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)