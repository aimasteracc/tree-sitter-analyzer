#!/usr/bin/env python3
"""HTML パーサーの診断スクリプト"""

import sys
sys.path.insert(0, '.')

from tree_sitter_analyzer.language_detector import detect_language_from_file
from tree_sitter_analyzer.language_loader import load_language
import tree_sitter

def test_html_parser():
    print("=== HTML パーサー診断 ===")
    
    # 1. 言語検出テスト
    file_path = 'examples/comprehensive_html.html'
    detected = detect_language_from_file(file_path)
    print(f'1. Detected language: {detected}')
    
    # 2. HTMLパーサーの可用性テスト
    try:
        html_lang = load_language('html')
        print(f'2. HTML language loaded: {html_lang is not None}')
        
        if html_lang:
            parser = tree_sitter.Parser(html_lang)
            print('3. HTML parser created successfully')
            
            # 3. 簡単なHTMLをパース
            test_html = '<form><input type="text"></form>'
            tree = parser.parse(bytes(test_html, 'utf8'))
            print(f'4. Parse tree created: {tree.root_node is not None}')
            print(f'5. Root node type: {tree.root_node.type}')
            print(f'6. Child count: {tree.root_node.child_count}')
            
            # 4. 実際のHTMLファイルをパース
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            real_tree = parser.parse(bytes(content, 'utf8'))
            print(f'7. Real file parse tree created: {real_tree.root_node is not None}')
            print(f'8. Real file root node type: {real_tree.root_node.type}')
            print(f'9. Real file child count: {real_tree.root_node.child_count}')
            
        else:
            print('ERROR: Failed to load HTML language')
            
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_html_parser()