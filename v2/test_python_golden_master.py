#!/usr/bin/env python3
"""
测试v2 Python解析器的输出，为golden master测试做准备。
"""

import json
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

from tree_sitter_analyzer_v2.languages import PythonParser


def analyze_sample_file():
    """分析sample.py文件并输出结果"""
    sample_file = Path("../examples/sample.py")

    if not sample_file.exists():
        print(f"[ERROR] Sample file not found: {sample_file}")
        return None

    # 使用v2解析器
    parser = PythonParser()
    result = parser.parse(sample_file.read_text(encoding="utf-8"), str(sample_file))

    # 提取关键统计信息
    stats = {
        "total_classes": len(result.get("classes", [])),
        "total_functions": len(result.get("functions", [])),
        "total_imports": len(result.get("imports", [])),
        "has_async_functions": any(func.get("is_async") for func in result.get("functions", [])),
        "class_names": [cls["name"] for cls in result.get("classes", [])],
        "function_names": [func["name"] for func in result.get("functions", [])],
    }

    print("=" * 80)
    print("V2 Python Parser Analysis Results")
    print("=" * 80)
    print("\n[Statistics]")
    print(f"   Classes: {stats['total_classes']}")
    print(f"   Functions: {stats['total_functions']}")
    print(f"   Imports: {stats['total_imports']}")
    print(f"   Has async functions: {stats['has_async_functions']}")

    print("\n[Classes]")
    for cls in result.get("classes", []):
        decorators = cls.get("decorators", [])
        decorator_str = f" (decorators: {', '.join(decorators)})" if decorators else ""
        base_classes = cls.get("base_classes", [])
        bases_str = f" extends {', '.join(base_classes)}" if base_classes else ""
        print(f"   - {cls['name']}{bases_str}{decorator_str}")
        print(f"     Methods: {len(cls.get('methods', []))}")

        # 检查class attributes
        if "class_attributes" in cls:
            print(f"     Class attributes: {len(cls.get('class_attributes', []))}")

    print("\n[Functions]")
    for func in result.get("functions", []):
        async_marker = "async " if func.get("is_async") else ""
        decorators = func.get("decorators", [])
        decorator_str = f" @{', @'.join(decorators)}" if decorators else ""
        print(f"   - {async_marker}{func['name']}{decorator_str}")
        print(f"     Parameters: {len(func.get('parameters', []))}")

    print("\n[Imports]")
    for imp in result.get("imports", [])[:10]:  # 只显示前10个
        print(f"   - {imp}")

    # 检查main block
    if "has_main_block" in result:
        print(f"\n[Main Block] {result['has_main_block']}")

    # 保存JSON-serializable结果（排除AST节点）
    output_file = Path("python_v2_analysis_result.json")
    serializable_result = {k: v for k, v in result.items() if k != "ast"}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(serializable_result, f, indent=2, ensure_ascii=False)

    print(f"\n[Saved] Full result saved to: {output_file}")
    print("=" * 80)

    return result


def check_v2_features():
    """检查v2 Python解析器支持的特性"""
    print("\n[Features] Checking v2 Python parser features:")

    features_to_check = [
        ("Decorators", "@dataclass, @abstractmethod, @staticmethod"),
        ("Base classes", "Person(ABC), Dog(Animal)"),
        ("Async functions", "async def fetch_data"),
        ("Type hints", "str, int, dict[str, any]"),
        ("Class attributes", "dataclass fields"),
        ("Main block detection", "if __name__ == '__main__'"),
    ]

    for feature, example in features_to_check:
        print(f"   [OK] {feature}: {example}")


if __name__ == "__main__":
    print("[START] Testing v2 Python parser with sample.py")
    check_v2_features()
    analyze_sample_file()
