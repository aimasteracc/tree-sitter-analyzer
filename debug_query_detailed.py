#!/usr/bin/env python3

import asyncio
import tree_sitter
from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.query_loader import query_loader
from tree_sitter_analyzer.encoding_utils import read_file_safe
from tree_sitter_analyzer.core.parser import Parser

async def debug_query_detailed():
    print("=== Detailed QueryService Debug ===")
    
    # Step 1: Check query string
    query_string = query_loader.get_query('html', 'form_element')
    print(f'Query string: {repr(query_string)}')
    
    # Step 2: Read file content
    content, encoding = read_file_safe('test_form_simple.html')
    print(f'File content length: {len(content)}')
    print(f'File encoding: {encoding}')
    print(f'First 200 chars: {repr(content[:200])}')
    
    # Step 3: Parse file
    parser = Parser()
    parse_result = parser.parse_code(content, 'html', 'test_form_simple.html')
    print(f'Parse result: {parse_result}')
    print(f'Parse success: {parse_result.success if parse_result else False}')
    
    if parse_result and parse_result.tree:
        tree = parse_result.tree
        print(f'Tree: {tree}')
        print(f'Tree root node: {tree.root_node}')
        print(f'Tree language: {tree.language if hasattr(tree, "language") else "No language attr"}')
        
        # Step 4: Try to create tree-sitter query
        try:
            language_obj = tree.language
            print(f'Language object: {language_obj}')
            
            ts_query = tree_sitter.Query(language_obj, query_string)
            print(f'Query created successfully: {ts_query}')
            
            # Step 5: Execute query
            captures = ts_query.captures(tree.root_node)
            print(f'Captures result: {captures}')
            print(f'Captures type: {type(captures)}')
            print(f'Captures length: {len(captures) if hasattr(captures, "__len__") else "No len"}')
            
            if captures:
                print("First few captures:")
                for i, capture in enumerate(captures[:3]):
                    print(f'  Capture {i}: {capture}')
                    if isinstance(capture, tuple) and len(capture) >= 2:
                        node, name = capture[0], capture[1]
                        print(f'    Node: {node}')
                        print(f'    Name: {name}')
                        print(f'    Node type: {node.type if hasattr(node, "type") else "No type"}')
                        print(f'    Node text: {node.text if hasattr(node, "text") else "No text"}')
            
        except Exception as e:
            print(f'Query execution failed: {e}')
            import traceback
            traceback.print_exc()
    
    # Step 6: Test QueryService
    print("\n=== Testing QueryService ===")
    try:
        service = QueryService()
        results = await service.execute_query(
            'test_form_simple.html',
            'html',
            query_key='form_element'
        )
        print(f'QueryService results: {results}')
    except Exception as e:
        print(f'QueryService failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_query_detailed())