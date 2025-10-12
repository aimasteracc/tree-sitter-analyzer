#!/usr/bin/env python3
"""
Demonstration of debug_utils solving Windows command line issues
"""

from tree_sitter_analyzer.debug_utils import execute_debug_code

def demonstrate_problem_and_solution():
    """Demonstrate the Windows command line problem and our solution"""
    
    print("=== Windows Command Line Problem Demonstration ===")
    print()
    
    # This is the problematic code that fails with python -c on Windows
    problematic_code = '''
# This code contains special characters that cause issues with python -c
print("Testing quotes: 'single' and \\"double\\"")
print("Testing Chinese: 测试中文字符")
print("Testing special chars: & < > | [ ] ( )")

# Complex multi-line code
data = {
    "name": "测试项目",
    "description": "This contains 'quotes' and \\"more quotes\\"",
    "special": "& < > | symbols"
}

for key, value in data.items():
    print(f"{key}: {value}")

# Simulate tree-sitter-analyzer usage (without actual import to avoid dependency issues)
print("Simulating tree-sitter-analyzer query:")
query_result = "form_element query contains [element] syntax"
print(f"Query result: {query_result}")
print("Contains [element syntax:", "[" in query_result)
'''
    
    print("Problematic code that would fail with 'python -c':")
    print("=" * 50)
    print(problematic_code)
    print("=" * 50)
    print()
    
    print("Executing with debug_utils (file-based approach):")
    print("-" * 50)
    
    result = execute_debug_code(problematic_code)
    
    if result['success']:
        print("✅ SUCCESS! Code executed successfully")
        print()
        print("Output:")
        print(result['stdout'])
    else:
        print("❌ FAILED!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        if result.get('stderr'):
            print(f"Stderr: {result['stderr']}")
    
    print("-" * 50)
    print()
    
    # Show the benefits
    print("=== Benefits of File-Based Debug Execution ===")
    print("✅ Handles complex multi-line code")
    print("✅ Supports UTF-8 and Chinese characters")
    print("✅ No issues with quotes and special characters")
    print("✅ Proper error handling and logging")
    print("✅ Automatic cleanup of temporary files")
    print("✅ Works reliably on Windows 11")

if __name__ == "__main__":
    demonstrate_problem_and_solution()