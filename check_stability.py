#!/usr/bin/env python3
"""多次运行检查输出稳定性"""

import subprocess  # nosec B404
import sys
from pathlib import Path


def run_analyzer(input_file: str, table_format: str) -> str:
    """运行分析器并返回输出"""
    cmd = [
        sys.executable,
        "-m",
        "tree_sitter_analyzer",
        input_file,
        "--table",
        table_format,
    ]

    result = subprocess.run(  # nosec B603
        cmd, capture_output=True, text=True, encoding="utf-8", check=True
    )

    return result.stdout


def check_stability(input_file: str, table_format: str, runs: int = 5):
    """检查输出稳定性"""
    outputs = []

    print(f"检查 {input_file} ({table_format}) 的稳定性...")

    for i in range(runs):
        output = run_analyzer(input_file, table_format)
        # 计算元素数量
        if "Total Elements" in output:
            import re

            match = re.search(r"Total Elements.*?(\d+)", output)
            if match:
                count = match.group(1)
                print(f"  Run {i + 1}: {count} elements")
                outputs.append((count, output))
        elif "| **Total**" in output:
            import re

            match = re.search(r"\|\s+\*\*Total\*\*.*?\|\s+\*\*(\d+)\*\*", output)
            if match:
                count = match.group(1)
                print(f"  Run {i + 1}: {count} elements")
                outputs.append((count, output))
        else:
            print(f"  Run {i + 1}: unable to parse count")
            outputs.append(("?", output))

    # 检查是否都一致
    counts = [o[0] for o in outputs]
    if len(set(counts)) == 1:
        print(f"  ✓ 稳定: 所有运行都返回 {counts[0]} 个元素\n")
        return outputs[0][1]  # 返回任意一个（都一样）
    else:
        print(f"  ✗ 不稳定: 元素数量在 {set(counts)} 之间变化\n")
        # 返回最常见的输出
        from collections import Counter

        most_common = Counter(counts).most_common(1)[0][0]
        for count, output in outputs:
            if count == most_common:
                return output
        return outputs[0][1]


def main():
    """检查并重新生成稳定的 Golden Master"""
    test_cases = [
        ("examples/test_markdown.md", "full"),
        ("examples/test_markdown.md", "compact"),
        ("examples/test_markdown.md", "csv"),
        ("examples/sample.cpp", "full"),
        ("examples/sample.cpp", "compact"),
    ]

    print("=" * 60)
    print("检查输出稳定性")
    print("=" * 60 + "\n")

    stable_outputs = {}

    for input_file, table_format in test_cases:
        stable_output = check_stability(input_file, table_format, runs=5)
        stable_outputs[(input_file, table_format)] = stable_output

    print("=" * 60)
    print("重新生成 Golden Master 文件")
    print("=" * 60 + "\n")

    # 重新生成文件
    mappings = {
        (
            "examples/test_markdown.md",
            "full",
        ): "tests/golden_masters/full/markdown_test_full.md",
        (
            "examples/test_markdown.md",
            "compact",
        ): "tests/golden_masters/compact/markdown_test_compact.md",
        (
            "examples/test_markdown.md",
            "csv",
        ): "tests/golden_masters/csv/markdown_test_csv.csv",
        ("examples/sample.cpp", "full"): "tests/golden_masters/full/cpp_sample_full.md",
        (
            "examples/sample.cpp",
            "compact",
        ): "tests/golden_masters/compact/cpp_sample_compact.md",
    }

    for key, output_path in mappings.items():
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(stable_outputs[key], encoding="utf-8")
        print(f"✓ 生成: {output_path}")

    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
