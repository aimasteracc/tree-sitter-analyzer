#!/usr/bin/env python3
"""
Test script for debug_utils functionality
"""

from tree_sitter_analyzer.debug_utils import execute_debug_code

def test_simple_debug():
    """Test simple debug code execution"""
    print("=== Testing Simple Debug Code ===")
    
    debug_code = '''
print("Hello from debug script!")
print("Testing UTF-8: 测试中文")
result = 2 + 3
print(f"Calculation result: {result}")
'''
    
    result = execute_debug_code(debug_code)
    print(f'Success: {result["success"]}')
    print(f'Return Code: {result["returncode"]}')
    if result['stdout']:
        print('STDOUT:')
        print(result['stdout'])
    if result['stderr']:
        print('STDERR:')
        print(result['stderr'])
    if result.get('error'):
        print(f'Error: {result["error"]}')

def test_complex_debug():
    """Test complex debug code with tree-sitter-analyzer"""
    print("\n=== Testing Complex Debug Code ===")
    
    debug_code = '''
from tree_sitter_analyzer.query_loader import query_loader
query_string = query_loader.get_query("html", "form_element")
print("Query contains [element syntax:", "[" in query_string if query_string else False)
print("Query contains input:", "input" in query_string if query_string else False)
print("Query string length:", len(query_string) if query_string else 0)
'''
    
    result = execute_debug_code(debug_code)
    print(f'Success: {result["success"]}')
    print(f'Return Code: {result["returncode"]}')
    if result['stdout']:
        print('STDOUT:')
        print(result['stdout'])
    if result['stderr']:
        print('STDERR:')
        print(result['stderr'])
    if result.get('error'):
        print(f'Error: {result["error"]}')

def test_chinese_characters():
    """Test debug code with Chinese characters"""
    print("\n=== Testing Chinese Characters ===")
    
    debug_code = '''
# 测试中文字符处理
print("测试中文输出")
data = {"名称": "测试", "值": 123}
print(f"数据: {data}")

# Test special characters
special_chars = '"Hello" & <World> | [Test]'
print(f"Special characters: {special_chars}")
'''
    
    result = execute_debug_code(debug_code)
    print(f'Success: {result["success"]}')
    print(f'Return Code: {result["returncode"]}')
    if result['stdout']:
        print('STDOUT:')
        print(result['stdout'])
    if result['stderr']:
        print('STDERR:')
        print(result['stderr'])
    if result.get('error'):
        print(f'Error: {result["error"]}')

if __name__ == "__main__":
    test_simple_debug()
    test_complex_debug()
    test_chinese_characters()
    
    # Cleanup
    from tree_sitter_analyzer.debug_utils import cleanup_debug_scripts
    cleaned = cleanup_debug_scripts()
    print(f"\n=== Cleanup ===")
    print(f"Cleaned up {cleaned} debug scripts")