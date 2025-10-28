#!/usr/bin/env python3
"""
Demonstration script for SJIS encoding issue and fix.

This script shows how the encoding normalization fixes the Shift_JIS search issue.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

# Set up logging to see the normalization messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.fd_rg_utils import normalize_encoding_name


async def create_test_sjis_file() -> Path:
    """Create a test file with SJIS content."""
    # Create test content with Japanese characters
    test_content = """TESTSTRING
これはテストファイルです。
TESTSTRING が含まれています。
日本語のテキストファイルです。
TESTSTRING
"""
    
    # Create temporary file
    temp_file = Path(tempfile.mktemp(suffix=".log"))
    
    # Write content in Shift_JIS encoding
    with open(temp_file, 'w', encoding='shift_jis') as f:
        f.write(test_content)
    
    print(f"Created test file: {temp_file}")
    print(f"File content (first few lines):")
    with open(temp_file, 'r', encoding='shift_jis') as f:
        lines = f.readlines()[:3]
        for i, line in enumerate(lines, 1):
            print(f"  {i}: {line.strip()}")
    
    return temp_file


async def test_encoding_normalization():
    """Test the encoding normalization function."""
    print("\n" + "="*60)
    print("ENCODING NORMALIZATION TEST")
    print("="*60)
    
    test_cases = [
        "Shift_JIS",
        "shift_jis", 
        "SJIS",
        "cp932",
        "utf-8",
        "UTF-8",
        "latin1",
    ]
    
    for encoding in test_cases:
        normalized = normalize_encoding_name(encoding)
        print(f"'{encoding}' -> '{normalized}'")


async def test_search_with_different_encodings(test_file: Path):
    """Test search with different encoding specifications."""
    print("\n" + "="*60)
    print("SEARCH CONTENT TEST")
    print("="*60)
    
    # Initialize search tool
    search_tool = SearchContentTool(enable_cache=False)
    
    # Test cases: different ways to specify Shift_JIS
    encoding_variants = [
        "Shift_JIS",    # Original problematic case
        "shift_jis",    # Lowercase with underscore
        "shift-jis",    # Normalized form
        "sjis",         # Short form
        "cp932",        # Windows code page
        "utf-8",        # Wrong encoding for comparison
    ]
    
    query = "TESTSTRING"
    
    for encoding in encoding_variants:
        print(f"\nTesting with encoding: '{encoding}'")
        print("-" * 40)
        
        try:
            # Test with total_only for quick results
            result = await search_tool.execute({
                "files": [str(test_file)],
                "query": query,
                "total_only": True,
                "encoding": encoding
            })
            
            if isinstance(result, int):
                match_count = result
                print(f"✅ Found {match_count} matches")
            elif isinstance(result, dict) and result.get("success"):
                match_count = result.get("total_matches", 0)
                print(f"✅ Found {match_count} matches")
            else:
                print(f"❌ Search failed: {result}")
                
        except Exception as e:
            print(f"❌ Error: {e}")


async def test_detailed_search_results(test_file: Path):
    """Test detailed search results with correct encoding."""
    print("\n" + "="*60)
    print("DETAILED SEARCH RESULTS")
    print("="*60)
    
    search_tool = SearchContentTool(enable_cache=False)
    
    # Use the correct normalized encoding
    result = await search_tool.execute({
        "files": [str(test_file)],
        "query": "TESTSTRING",
        "encoding": "Shift_JIS",  # This will be normalized to "shift-jis"
        "context_before": 1,
        "context_after": 1,
    })
    
    if isinstance(result, dict) and result.get("success"):
        print(f"Total matches: {result.get('count', 0)}")
        print("\nMatch details:")
        for i, match in enumerate(result.get("results", [])[:3], 1):  # Show first 3 matches
            print(f"  Match {i}:")
            print(f"    File: {match.get('file', 'unknown')}")
            print(f"    Line: {match.get('line', '?')}")
            print(f"    Text: {match.get('text', '').strip()}")
    else:
        print(f"Search failed: {result}")


async def main():
    """Main demonstration function."""
    print("SJIS Encoding Issue Demonstration")
    print("=" * 60)
    print("This demo shows how the encoding normalization fixes")
    print("the Shift_JIS search issue in search_content tool.")
    
    # Test encoding normalization
    await test_encoding_normalization()
    
    # Create test file
    test_file = await create_test_sjis_file()
    
    try:
        # Test search with different encodings
        await test_search_with_different_encodings(test_file)
        
        # Test detailed results
        await test_detailed_search_results(test_file)
        
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()
            print(f"\nCleaned up test file: {test_file}")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("✅ The encoding normalization fix ensures that:")
    print("   - 'Shift_JIS' is normalized to 'shift-jis'")
    print("   - ripgrep can properly handle the file encoding")
    print("   - Search results are found correctly")
    print("   - Debug logging shows the normalization process")


if __name__ == "__main__":
    asyncio.run(main())