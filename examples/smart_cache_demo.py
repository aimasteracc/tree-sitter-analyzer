#!/usr/bin/env python3
"""
Smart Cache Demo - Cross-Format Optimization

This demo showcases the intelligent cross-format caching optimization where:
1. First search gets match counts (fast --count-matches)
2. Second search requests file list but gets it derived from cached count data
3. No second ripgrep execution needed!

Performance improvement: From 2 searches → 1 search + instant derivation
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


async def demo_smart_cache_optimization():
    print("🧠 Smart Cache Cross-Format Optimization Demo")
    print("=" * 60)

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

    print("🔍 Scenario: LLM workflow optimization")
    print("   Step 1: Get match count (for token efficiency)")
    print("   Step 2: Get file list (for detailed analysis)")
    print()

    # Step 1: Get match count (typical LLM workflow)
    print("📊 Step 1: Getting match count...")
    start_time = time.time()

    count_result = await tool.execute(
        {"query": "class", "roots": [test_directory], "count_only_matches": True}
    )

    step1_time = time.time() - start_time
    print(f"   ⏱️  Time: {step1_time:.3f}s")
    print(f"   📈 Total matches: {count_result.get('total_matches', 0)}")
    print(f"   📁 Files with matches: {len(count_result.get('file_counts', {}))}")

    # Show cache stats
    cache_stats = get_default_cache().get_stats()
    print(
        f"   🎯 Cache stats: {cache_stats['hits']} hits, {cache_stats['misses']} misses"
    )
    print()

    # Step 2: Get file summary (should derive from cached count data!)
    print("📋 Step 2: Getting file summary (watch for cache derivation)...")
    start_time = time.time()

    summary_result = await tool.execute(
        {"query": "class", "roots": [test_directory], "summary_only": True}
    )

    step2_time = time.time() - start_time
    print(f"   ⏱️  Time: {step2_time:.3f}s")

    # Check if result was derived from cache
    if summary_result.get("cache_derived"):
        print("   🎉 SUCCESS: File list derived from cached count data!")
        print("   🚀 No second ripgrep execution needed!")
        speedup = step1_time / step2_time if step2_time > 0 else float("inf")
        print(f"   📈 Speedup: {speedup:.1f}x faster than re-searching")
    elif summary_result.get("cache_hit"):
        print("   ✅ Direct cache hit (result was already cached)")
    else:
        print("   ⚠️  New search executed (cache derivation not available)")

    print(f"   📁 Files found: {summary_result.get('file_count', 0)}")

    # Show final cache stats
    final_stats = get_default_cache().get_stats()
    print(
        f"   🎯 Final cache stats: {final_stats['hits']} hits, {final_stats['misses']} misses"
    )
    print()

    # Step 3: Demonstrate traditional vs smart caching
    print("📊 Performance Comparison:")
    print(
        f"   Traditional approach: {step1_time:.3f}s + {step1_time:.3f}s = {step1_time * 2:.3f}s"
    )
    print(
        f"   Smart cache approach: {step1_time:.3f}s + {step2_time:.3f}s = {step1_time + step2_time:.3f}s"
    )

    if step2_time < step1_time * 0.1:  # If derivation is much faster
        savings = step1_time - step2_time
        savings_percent = (savings / step1_time) * 100
        print(f"   💰 Time saved: {savings:.3f}s ({savings_percent:.1f}% improvement)")

    print()
    print("🎯 Key Benefits:")
    print("   • Count search provides file list for free")
    print("   • No duplicate ripgrep executions")
    print("   • Optimal for LLM token-efficient workflows")
    print("   • Automatic cross-format result derivation")


if __name__ == "__main__":
    asyncio.run(demo_smart_cache_optimization())
