#!/usr/bin/env python3

from tree_sitter_analyzer.api import analyze_file

# Test HTML element type extraction
result = analyze_file("test_form_simple.html")

print("=== Element Type Debug ===")
print(f"Result type: {type(result)}")
print(f"Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

elements = result.get('elements', []) if isinstance(result, dict) else []
print(f"Found {len(elements)} elements")

for i, element in enumerate(elements[:5]):  # First 5 elements
    print(f"\nElement {i+1}:")
    print(f"  Type: {type(element)}")
    print(f"  Dir: {[attr for attr in dir(element) if not attr.startswith('_')]}")
    
    if hasattr(element, 'element_type'):
        print(f"  element_type attribute: {element.element_type}")
    else:
        print(f"  NO element_type attribute")
    
    if hasattr(element, 'name'):
        print(f"  name: {element.name}")
    
    # Check if it's a dict-like object
    if hasattr(element, 'get'):
        print(f"  element_type (dict): {element.get('element_type', 'NOT_FOUND')}")
        print(f"  type (dict): {element.get('type', 'NOT_FOUND')}")
        print(f"  name (dict): {element.get('name', 'NOT_FOUND')}")