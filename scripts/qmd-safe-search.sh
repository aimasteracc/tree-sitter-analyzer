#!/bin/bash
# qmd-safe-search.sh - 内存安全的 qmd 搜索包装器
# 避免大模型导致内存溢出

set -e

QUERY="$1"
MAX_RESULTS="${2:-5}"

# 使用轻量级搜索模式（不用 1.7B 生成模型）
# 优先级：BM25 > 向量搜索 > 混合搜索

if [ -z "$QUERY" ]; then
    echo "Usage: $0 <query> [max_results]"
    echo ""
    echo "Search modes (auto-selected by complexity):"
    echo "  - Simple keywords: BM25 (no LLM)"
    echo "  - Single phrase: Vector search (300M model only)"
    echo "  - Complex: Hybrid (with limits)"
    exit 1
fi

# 检测查询复杂度
WORD_COUNT=$(echo "$QUERY" | wc -w | tr -d ' ')

if [ "$WORD_COUNT" -le 3 ]; then
    # 简单查询：用 BM25（最快，不用大模型）
    echo "🔍 Using BM25 keyword search (fast, no LLM)..."
    qmd search "$QUERY" -n "$MAX_RESULTS"
elif [ "$WORD_COUNT" -le 6 ]; then
    # 中等查询：用向量搜索（只用 300M embedding 模型）
    echo "🔍 Using vector search (300M model only)..."
    qmd vsearch "$QUERY" -n "$MAX_RESULTS"
else
    # 复杂查询：用混合搜索，但限制结果
    echo "🔍 Using hybrid search (with expansion)..."
    echo "⚠️  Warning: This loads 1.7B model, may use 1-2GB RAM"
    qmd query "$QUERY" -n "$MAX_RESULTS"
fi

echo ""
echo "✅ Search complete"
