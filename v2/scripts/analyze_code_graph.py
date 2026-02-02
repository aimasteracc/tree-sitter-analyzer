#!/usr/bin/env python
"""
便捷的代码图谱分析脚本

用法:
    python scripts/analyze_code_graph.py <file.py>                    # Summary 模式
    python scripts/analyze_code_graph.py <file.py> --detailed         # Detailed 模式
    python scripts/analyze_code_graph.py <file.py> --find-callers <func_name>
    python scripts/analyze_code_graph.py <dir> --all                  # 分析整个目录
"""

import argparse
import sys
from pathlib import Path

import networkx as nx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer_v2.graph import (
    CodeGraphBuilder,
    export_for_llm,
    find_definition,
    get_callers,
)


def analyze_single_file(
    file_path: str, detail_level: str = "summary", include_private: bool = False
):
    """分析单个文件"""
    print(f"Analyzing: {file_path}")
    print("=" * 70)

    builder = CodeGraphBuilder()
    graph = builder.build_from_file(file_path)

    # 统计
    nodes = graph.number_of_nodes()
    edges = graph.number_of_edges()
    functions = len([n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"])
    classes = len([n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"])

    print("\nStatistics:")
    print(f"  Nodes: {nodes}")
    print(f"  Edges: {edges}")
    print(f"  Classes: {classes}")
    print(f"  Functions: {functions}")
    print()

    # TOON 输出
    output = export_for_llm(
        graph, max_tokens=4000, detail_level=detail_level, include_private=include_private
    )

    print(f"TOON Output ({detail_level} mode):")
    print("-" * 70)
    print(output)

    return graph


def analyze_directory(dir_path: str, detail_level: str = "summary"):
    """分析整个目录"""
    print(f"Analyzing directory: {dir_path}")
    print("=" * 70)

    builder = CodeGraphBuilder()
    combined_graph = nx.DiGraph()

    py_files = list(Path(dir_path).rglob("*.py"))
    print(f"Found {len(py_files)} Python files\n")

    for py_file in py_files:
        if py_file.name == "__init__.py":
            continue
        try:
            print(f"Processing: {py_file.relative_to(dir_path)}")
            graph = builder.build_from_file(str(py_file))
            combined_graph = nx.compose(combined_graph, graph)
        except Exception as e:
            print(f"  Error: {e}")

    print()
    print("Combined Graph Statistics:")
    print(f"  Total nodes: {combined_graph.number_of_nodes()}")
    print(f"  Total edges: {combined_graph.number_of_edges()}")
    print()

    # TOON 输出
    output = export_for_llm(
        combined_graph, max_tokens=8000, detail_level=detail_level, include_private=False
    )

    print(f"Combined TOON Output ({detail_level} mode):")
    print("-" * 70)
    print(output)

    return combined_graph


def find_callers_of(graph, function_name: str):
    """查找函数的调用者"""
    print(f"Finding callers of: {function_name}")
    print("=" * 70)

    # 查找函数定义
    defs = find_definition(graph, function_name)

    if not defs:
        print(f"Function '{function_name}' not found in graph")
        return

    for func_id in defs:
        print(f"\nFound: {func_id}")

        # 查找调用者
        callers = get_callers(graph, func_id)

        if not callers:
            print("  No callers found")
        else:
            print(f"  Called by {len(callers)} function(s):")
            for caller_id in callers:
                caller_name = graph.nodes[caller_id].get("name", caller_id)
                caller_type = graph.nodes[caller_id].get("type", "unknown")
                print(f"    - {caller_name} ({caller_type})")


def main():
    parser = argparse.ArgumentParser(description="Code Graph Analyzer")
    parser.add_argument("path", help="File or directory to analyze")
    parser.add_argument("--detailed", action="store_true", help="Use detailed mode")
    parser.add_argument("--all", action="store_true", help="Analyze entire directory")
    parser.add_argument("--include-private", action="store_true", help="Include private functions")
    parser.add_argument("--find-callers", metavar="FUNC", help="Find callers of a function")

    args = parser.parse_args()

    detail_level = "detailed" if args.detailed else "summary"

    if args.all:
        graph = analyze_directory(args.path, detail_level)
    else:
        graph = analyze_single_file(args.path, detail_level, args.include_private)

    # 查找调用者
    if args.find_callers:
        print("\n")
        find_callers_of(graph, args.find_callers)


if __name__ == "__main__":
    main()
