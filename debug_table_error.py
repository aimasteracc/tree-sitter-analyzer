#!/usr/bin/env python3

import sys
import traceback
from tree_sitter_analyzer.cli.commands.table_command import TableCommand
from tree_sitter_analyzer.core.engine import AnalysisEngine
from tree_sitter_analyzer.language_detector import LanguageDetector

def debug_table_error():
    """Debug the table generation error"""
    try:
        # Create analysis engine
        engine = AnalysisEngine()
        
        # Analyze the file
        file_path = "test_form_simple.html"
        print(f"Analyzing {file_path}...")
        
        # Detect language
        detector = LanguageDetector()
        language = detector.detect_language(file_path)
        print(f"Detected language: {language}")
        
        # Perform analysis
        result = engine.analyze_file(file_path, language)
        print(f"Analysis result type: {type(result)}")
        print(f"Analysis result elements: {len(getattr(result, 'elements', []))}")
        
        # Check elements
        elements = getattr(result, 'elements', [])
        for i, element in enumerate(elements[:3]):  # Check first 3 elements
            print(f"Element {i}: type={type(element)}, value={element}")
            if hasattr(element, '__dict__'):
                print(f"  Attributes: {list(element.__dict__.keys())}")
        
        # Try table command
        class MockArgs:
            def __init__(self):
                self.format = "full"
                self.include_javadoc = False
                self.query_key = None
        
        args = MockArgs()
        table_cmd = TableCommand(args)
        
        print("Attempting table generation...")
        table_result = table_cmd._convert_to_structure_format(result, language)
        print("Table generation successful!")
        print(f"Table result keys: {table_result.keys()}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        print("Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    debug_table_error()