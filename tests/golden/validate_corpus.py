#!/usr/bin/env python3
"""
Validate golden corpus files against expected.json

验证 golden corpus 文件是否与 expected.json 中的预期结果匹配
"""

import json
import sys
from collections import Counter
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser


def count_node_types(node: any) -> Counter:
    """递归统计所有命名节点类型的数量"""
    counts = Counter()
    if node.is_named:
        counts[node.type] += 1
    for child in node.children:
        counts.update(count_node_types(child))
    return counts


def validate_corpus(corpus_file: Path, expected_file: Path) -> bool:
    """验证 corpus 文件是否与 expected.json 匹配"""
    # 加载 expected.json
    with open(expected_file, encoding="utf-8") as f:
        expected = json.load(f)

    # 解析 corpus 文件
    language = expected["language"]
    if language == "python":
        lang = Language(tspython.language())
    else:
        print(f"Unsupported language: {language}")
        return False

    parser = Parser(lang)
    source_code = corpus_file.read_text(encoding="utf-8")
    tree = parser.parse(source_code.encode("utf-8"))

    # 统计实际的 node types
    actual_counts = count_node_types(tree.root_node)

    # 比较结果
    expected_counts = expected["node_types"]
    all_types = set(expected_counts.keys()) | set(actual_counts.keys())

    mismatches = []
    for node_type in sorted(all_types):
        expected_count = expected_counts.get(node_type, 0)
        actual_count = actual_counts.get(node_type, 0)
        if expected_count != actual_count:
            mismatches.append((node_type, expected_count, actual_count))

    if mismatches:
        print(f"FAIL: Validation FAILED for {corpus_file.name}")
        print("\nMismatches:")
        print(f"{'Node Type':40} {'Expected':10} {'Actual':10}")
        print("=" * 65)
        for node_type, expected_count, actual_count in mismatches:
            print(f"{node_type:40} {expected_count:10} {actual_count:10}")
        return False

    print(f"PASS: Validation PASSED for {corpus_file.name}")
    print(f"   Total node types: {len(actual_counts)}")
    print(f"   Total named nodes: {sum(actual_counts.values())}")

    # 验证关键 node types
    if "critical_node_types" in expected:
        print("\n   Critical node types:")
        for node_type, count in expected["critical_node_types"].items():
            actual_count = actual_counts.get(
                node_type if node_type != "dict_comprehension" else "dictionary_comprehension",
                0,
            )
            status = "OK" if actual_count == count else "FAIL"
            print(f"   {status} {node_type:30} {count}")

    return True


def main():
    """主函数"""
    golden_dir = Path(__file__).parent

    # 验证 Python corpus
    python_corpus = golden_dir / "corpus_python.py"
    python_expected = golden_dir / "corpus_python_expected.json"

    if not python_corpus.exists():
        print(f"FAIL: Corpus file not found: {python_corpus}")
        sys.exit(1)

    if not python_expected.exists():
        print(f"FAIL: Expected file not found: {python_expected}")
        sys.exit(1)

    success = validate_corpus(python_corpus, python_expected)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
