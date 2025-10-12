#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

def debug_html_element_data():
    """Debug actual HTML element data structure"""
    
    # Run the table command and capture the first few elements
    from tree_sitter_analyzer.cli.commands.table_command import TableCommand
    from tree_sitter_analyzer.language_detector import LanguageDetector
    
    detector = LanguageDetector()
    language = detector.detect_language("examples/comprehensive_html.html")
    print(f"Detected language: {language}")
    
    # Create TableCommand instance
    table_command = TableCommand()
    
    # Read file content
    with open("examples/comprehensive_html.html", 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        # Get analysis result
        result = table_command._analyze_file("examples/comprehensive_html.html", language, content)
        
        if 'elements' in result:
            elements = result['elements']
            print(f"Total elements: {len(elements)}")
            
            # Check first few elements in detail
            for i, element in enumerate(elements[:3]):
                print(f"\nElement {i+1}:")
                print(f"  Type: {type(element)}")
                print(f"  Class name: {element.__class__.__name__ if hasattr(element, '__class__') else 'N/A'}")
                
                if hasattr(element, '__dict__'):
                    print(f"  Attributes: {list(element.__dict__.keys())}")
                    for key, value in element.__dict__.items():
                        if key in ['name', 'element_type', 'type']:
                            print(f"    {key}: {value}")
                
                # Test get_element_type function
                from tree_sitter_analyzer.constants import get_element_type
                element_type = get_element_type(element)
                print(f"  get_element_type result: {element_type}")
                
                # Check if element has element_type attribute
                if hasattr(element, 'element_type'):
                    print(f"  element.element_type: {element.element_type}")
                else:
                    print(f"  element.element_type: NOT FOUND")
                    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_html_element_data()