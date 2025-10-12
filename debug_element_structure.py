#!/usr/bin/env python3

from tree_sitter_analyzer.cli.commands.table_command import TableCommand
from tree_sitter_analyzer.language_detector import LanguageDetector
from tree_sitter_analyzer.file_handler import FileHandler

def debug_element_structure():
    """Debug element data structure to understand element_type handling"""
    
    # Initialize components
    detector = LanguageDetector()
    file_handler = FileHandler()
    
    # Analyze HTML file
    file_path = "examples/comprehensive_html.html"
    language = detector.detect_language(file_path)
    print(f"Detected language: {language}")
    
    # Get analysis result using TableCommand's internal logic
    table_command = TableCommand()
    
    # Read file content
    content = file_handler.read_file(file_path)
    print(f"File content length: {len(content)} characters")
    
    # Simulate TableCommand analysis
    try:
        result = table_command._analyze_file(file_path, language, content)
        print(f"Analysis result type: {type(result)}")
        print(f"Analysis result keys: {result.keys() if hasattr(result, 'keys') else 'Not a dict'}")
        
        if 'elements' in result:
            elements = result['elements']
            print(f"Total elements: {len(elements)}")
            
            # Check first few elements
            for i, element in enumerate(elements[:3]):
                print(f"\nElement {i+1}:")
                print(f"  Type: {type(element)}")
                if isinstance(element, dict):
                    print(f"  Keys: {list(element.keys())}")
                    print(f"  name: {element.get('name', 'N/A')}")
                    print(f"  type: {element.get('type', 'N/A')}")
                    print(f"  element_type: {element.get('element_type', 'N/A')}")
                    print(f"  start_line: {element.get('start_line', 'N/A')}")
                else:
                    print(f"  Value: {element}")
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_element_structure()