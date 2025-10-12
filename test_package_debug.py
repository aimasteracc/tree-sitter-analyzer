#!/usr/bin/env python3
"""Test package detection in Java"""

from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
import tree_sitter_java as tsjava
import tree_sitter

def test_package_detection():
    plugin = JavaPlugin()
    print("Java supported queries:", plugin.get_supported_queries())

    # Test package extraction directly
    parser = tree_sitter.Parser()
    parser.set_language(tsjava.language())

    with open("examples/Sample.java", "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = parser.parse(bytes(source_code, "utf8"))
    extractor = plugin.element_extractor
    packages = extractor.extract_packages(tree, source_code)
    print(f"Extracted packages: {len(packages)}")
    for pkg in packages:
        print(f"Package: {pkg.name}")

    # Also test HTML issue
    print("\n--- HTML Test ---")
    from tree_sitter_analyzer.languages.html_plugin import HTMLPlugin
    html_plugin = HTMLPlugin()
    print("HTML supported queries:", html_plugin.get_supported_queries())

if __name__ == "__main__":
    test_package_detection()