#!/usr/bin/env python3

import tree_sitter
from tree_sitter_analyzer.encoding_utils import read_file_safe
from tree_sitter_analyzer.core.parser import Parser

def test_query_cursor():
    print("=== Testing QueryCursor API ===")
    
    # Parse a simple file
    content, _ = read_file_safe('test_form_simple.html')
    parser = Parser()
    parse_result = parser.parse_code(content, 'html', 'test_form_simple.html')

    if parse_result and parse_result.tree:
        language_obj = parse_result.tree.language
        query_string = '(element) @element'
        root_node = parse_result.tree.root_node
        
        try:
            # Create query and cursor
            ts_query = tree_sitter.Query(language_obj, query_string)
            cursor = tree_sitter.QueryCursor(ts_query)
            
            print('QueryCursor methods:', [method for method in dir(cursor) if not method.startswith('_')])
            
            # Execute query
            captures = cursor.captures(root_node)
            print(f'Captures result: {captures}')
            print(f'Captures type: {type(captures)}')
            
            # Try to iterate through captures
            capture_list = list(captures)
            print(f'Capture list length: {len(capture_list)}')
            
            if capture_list:
                print('First few captures:')
                for i, capture in enumerate(capture_list[:3]):
                    print(f'  Capture {i}: {capture}')
                    if isinstance(capture, tuple) and len(capture) >= 2:
                        node, capture_index = capture[0], capture[1]
                        print(f'    Node: {node}')
                        print(f'    Capture index: {capture_index}')
                        node_type = node.type if hasattr(node, 'type') else 'No type'
                        print(f'    Node type: {node_type}')
                        
                        if hasattr(node, 'text') and node.text:
                            node_text = node.text.decode() if isinstance(node.text, bytes) else str(node.text)
                            print(f'    Node text: {repr(node_text[:100])}')  # First 100 chars
                        else:
                            print('    Node text: No text')
            
            # Now test with form_element query
            print("\n=== Testing form_element query ===")
            from tree_sitter_analyzer.query_loader import query_loader
            form_query_string = query_loader.get_query('html', 'form_element')
            print(f'Form query: {repr(form_query_string)}')
            
            if form_query_string:
                form_query = tree_sitter.Query(language_obj, form_query_string)
                form_query_cursor = tree_sitter.QueryCursor(form_query)
                form_captures = form_query_cursor.captures(root_node)
                form_capture_list = list(form_captures)
                print(f'Form captures length: {len(form_capture_list)}')
                
                for i, capture in enumerate(form_capture_list):
                    print(f'  Form capture {i}: {capture}')
                    if isinstance(capture, tuple) and len(capture) >= 2:
                        node, capture_index = capture[0], capture[1]
                        node_type = node.type if hasattr(node, 'type') else 'No type'
                        print(f'    Node type: {node_type}')
                        
                        # Get capture name
                        capture_name = form_query.capture_name(capture_index)
                        print(f'    Capture name: {capture_name}')
            
        except Exception as e:
            print(f'Query execution failed: {e}')
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_query_cursor()