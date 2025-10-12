#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from tree_sitter_analyzer.encoding_utils import read_file_safe

def debug_simple():
    """Simple debug to check element types"""
    
    # Read file content
    content = read_file_safe("examples/comprehensive_html.html")
    print(f"File content length: {len(content)} characters")
    
    # Check if we can import the necessary modules
    try:
        from tree_sitter_analyzer.language_detector import LanguageDetector
        detector = LanguageDetector()
        language = detector.detect_language("examples/comprehensive_html.html")
        print(f"Detected language: {language}")
        
        # Try to import HTMLElementExtractor directly
        from tree_sitter_analyzer.languages.html_plugin import HTMLElementExtractor
        extractor = HTMLElementExtractor()
        print(f"HTMLElementExtractor loaded successfully")
        
        # Test element type classification
        test_elements = ['div', 'form', 'input', 'img', 'video', 'h1', 'p']
        for element in test_elements:
            element_type = extractor._get_html_element_type(element)
            print(f"  {element} -> {element_type}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_simple()