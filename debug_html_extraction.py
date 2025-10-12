#!/usr/bin/env python3
"""HTML 要素抽出の診断スクリプト"""

import sys
sys.path.insert(0, '.')

# Force module reload to pick up changes
import importlib
if 'tree_sitter_analyzer.languages.html_plugin' in sys.modules:
    importlib.reload(sys.modules['tree_sitter_analyzer.languages.html_plugin'])

from tree_sitter_analyzer.language_loader import load_language
from tree_sitter_analyzer.languages.html_plugin import HTMLElementExtractor
import tree_sitter

def test_html_extraction():
    print("=== HTML 要素抽出診断 ===")
    
    try:
        # HTMLパーサーの準備
        html_lang = load_language('html')
        parser = tree_sitter.Parser(html_lang)
        
        # 簡単なHTMLをテスト
        test_html = '''<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <form action="/submit" method="post">
        <input type="text" name="username">
        <button type="submit">Submit</button>
    </form>
</body>
</html>'''
        
        print("1. Parsing test HTML...")
        tree = parser.parse(bytes(test_html, 'utf8'))
        print(f"   Root node: {tree.root_node.type}")
        print(f"   Child count: {tree.root_node.child_count}")
        
        # HTMLElementExtractorを使用
        print("2. Creating HTML extractor...")
        extractor = HTMLElementExtractor()
        
        print("3. Extracting elements...")
        elements = extractor.extract_elements_from_html(tree, test_html)
        print(f"   Total elements extracted: {len(elements)}")
        
        # 抽出された要素の詳細
        print("4. Element details:")
        for i, element in enumerate(elements):
            print(f"   [{i}] Type: {element.get('type')}, Name: {element.get('name')}, Node: {element.get('node_type')}")
        
        # フォーム要素の確認
        form_elements = [e for e in elements if 'form' in e.get('name', '').lower()]
        print(f"5. Form-related elements: {len(form_elements)}")
        for element in form_elements:
            print(f"   - {element.get('name')} (type: {element.get('type')})")
        
        # 標準インターフェースのテスト
        print("6. Testing standard interface...")
        functions = extractor.extract_functions(tree, test_html)
        classes = extractor.extract_classes(tree, test_html)
        variables = extractor.extract_variables(tree, test_html)
        imports = extractor.extract_imports(tree, test_html)
        
        print(f"   Functions: {len(functions)}")
        print(f"   Classes: {len(classes)}")
        print(f"   Variables: {len(variables)}")
        print(f"   Imports: {len(imports)}")
        
        # Debug: Check what elements match each filter
        print("7. Debug filtering:")
        attribute_elements = [e for e in elements if e.get("node_type") == "attribute"]
        print(f"   Attribute elements: {len(attribute_elements)}")
        for attr in attribute_elements:
            print(f"     - {attr.get('name')} (node_type: {attr.get('node_type')})")
        
        text_elements = [e for e in elements if e.get("node_type") in ["comment", "text", "doctype"]]
        print(f"   Text/Comment/Doctype elements: {len(text_elements)}")
        for txt in text_elements:
            print(f"     - {txt.get('name')} (node_type: {txt.get('node_type')})")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_html_extraction()