#!/usr/bin/env python3
"""
Total-Only to Count-Only Cross-Format Optimization Demo

This demo showcases the intelligent optimization where:
1. First search gets total count only (like your example)
2. Second search requests detailed file counts but gets them from cached data
3. No second ripgrep execution needed!

This solves the exact scenario you described:
- User gets total: 1250 matches
- User thinks "too many, let me see file distribution"
- System serves file counts from cache instead of re-searching
"""

import asyncio
import time
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import (
    clear_cache,
    configure_cache,
    get_default_cache,
)


async def demo_total_only_optimization():
    print("🎯 Total-Only → Count-Only Cross-Format Optimization Demo")
    print("=" * 70)

    # Use the project's examples directory for testing
    script_dir = Path(__file__).parent
    test_directory = str(script_dir)

    if not Path(test_directory).exists():
        print(f"❌ Test directory not found: {test_directory}")
        return

    print(f"📁 Using test directory: {test_directory}")
    print()

    # Configure cache
    configure_cache(max_size=100, ttl_seconds=300)
    clear_cache()  # Ensure clean slate

    # Initialize tool with caching enabled
    tool = SearchContentTool(project_root=test_directory, enable_cache=True)

    print("🔍 Your Use Case Scenario:")
    print("   Step 1: Get total matches only (like your example)")
    print("   {")
    print('     "roots": ["."],')
    print('     "query": "class",')
    print('     "case": "insensitive",')
    print('     "include_globs": ["*.py"],')
    print('     "total_only": true')
    print("   }")
    print()

    # Step 1: Get total count only (your exact use case)
    print("📊 Step 1: Getting total matches only...")
    start_time = time.time()

    total_result = await tool.execute(
        {
            "roots": ["."],
            "query": "class",
            "case": "insensitive",
            "include_globs": ["*.py"],
            "total_only": True,
        }
    )

    step1_time = time.time() - start_time
    print(f"   ⏱️  Time: {step1_time:.3f}s")
    print(f"   📈 Total matches: {total_result}")
    print(f"   💭 User thinks: 'Hmm, {total_result} matches might be too many...'")
    print("   💭 User wants: 'Let me see the file distribution'")

    # Show cache stats
    cache_stats = get_default_cache().get_stats()
    print(
        f"   🎯 Cache stats: {cache_stats['hits']} hits, {cache_stats['misses']} misses"
    )
    print()

    # Step 2: Get detailed file counts (user's follow-up query)
    print("📋 Step 2: Getting detailed file counts (user's follow-up)...")
    start_time = time.time()

    count_result = await tool.execute(
        {
            "roots": ["."],
            "query": "class",
            "case": "insensitive",
            "include_globs": ["*.py"],
            "count_only_matches": True,
        }
    )

    step2_time = time.time() - start_time
    print(f"   ⏱️  Time: {step2_time:.3f}s")

    # Check if result was derived from total_only cache
    if isinstance(count_result, dict):
        if count_result.get("derived_from_total_only"):
            print("   🎉 SUCCESS: File counts derived from cached total_only data!")
            print("   🚀 No second ripgrep execution needed!")
            speedup = step1_time / step2_time if step2_time > 0 else float("inf")
            print(f"   📈 Speedup: {speedup:.1f}x faster than re-searching")
        elif count_result.get("cache_hit"):
            print("   ✅ Direct cache hit (result was already cached)")
        else:
            print("   ⚠️  New search executed (optimization not available)")

        print(f"   📁 Files with matches: {len(count_result.get('file_counts', {}))}")
        print(f"   📊 Total matches: {count_result.get('total_matches', 0)}")

        # Show some file details if available
        file_counts = count_result.get("file_counts", {})
    else:
        # count_result is likely an integer (direct total)
        print("   ⚠️  Received direct total instead of detailed count structure")
        print(f"   📊 Total matches: {count_result}")
        file_counts = {}
    if file_counts:
        print("   📄 File distribution:")
        for _i, (file_path, count) in enumerate(sorted(file_counts.items())[:5]):
            print(f"      • {file_path}: {count} matches")
        if len(file_counts) > 5:
            print(f"      ... and {len(file_counts) - 5} more files")

    # Show final cache stats
    final_stats = get_default_cache().get_stats()
    print(
        f"   🎯 Final cache stats: {final_stats['hits']} hits, {final_stats['misses']} misses"
    )
    print()

    # Performance comparison
    print("📊 Performance Comparison:")
    print(
        f"   Without optimization: {step1_time:.3f}s + {step1_time:.3f}s = {step1_time * 2:.3f}s"
    )
    print(
        f"   With smart caching: {step1_time:.3f}s + {step2_time:.3f}s = {step1_time + step2_time:.3f}s"
    )

    if step2_time < step1_time * 0.1:  # If derivation is much faster
        savings = step1_time - step2_time
        savings_percent = (savings / step1_time) * 100
        print(f"   💰 Time saved: {savings:.3f}s ({savings_percent:.1f}% improvement)")

    print()
    print("🎯 Key Benefits:")
    print("   • total_only search preserves file-level data internally")
    print("   • count_only_matches queries served from total_only cache")
    print("   • Perfect for 'total → details' user workflow")
    print("   • Zero duplicate ripgrep executions")
    print("   • Optimal for large codebases with many matches")


if __name__ == "__main__":
    asyncio.run(demo_total_only_optimization())
