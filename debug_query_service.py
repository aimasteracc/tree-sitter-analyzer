#!/usr/bin/env python3

import asyncio
from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.query_loader import query_loader
from tree_sitter_analyzer.core.engine import AnalysisEngine

async def debug_query():
    print("=== Debugging QueryService ===")
    
    # Check query string
    query_string = query_loader.get_query('html', 'form_element')
    print(f'Query string: {query_string}')
    
    # Check if file exists and can be parsed
    engine = AnalysisEngine()
    
    try:
        result = engine.analyze_file('test_form_simple.html', 'html')
        print(f'Engine analysis result: {result}')
        
        elements_count = len(result.elements) if hasattr(result, 'elements') else 0
        print(f'Elements found: {elements_count}')
        
        if hasattr(result, 'elements') and result.elements:
            for i, elem in enumerate(result.elements[:3]):  # Show first 3
                print(f'Element {i}: {elem}')
                print(f'  - Type: {type(elem)}')
                print(f'  - Name: {getattr(elem, "name", "No name")}')
                print(f'  - Tag: {getattr(elem, "tag", "No tag")}')
    except Exception as e:
        print(f'Engine analysis failed: {e}')
        import traceback
        traceback.print_exc()
    
    # Now test QueryService
    print("\n=== Testing QueryService ===")
    try:
        service = QueryService()
        results = await service.execute_query(
            'test_form_simple.html',
            'html',
            query_key='form_element'
        )
        print(f'QueryService results: {results}')
        print(f'Results length: {len(results) if results else 0}')
    except Exception as e:
        print(f'QueryService failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_query())