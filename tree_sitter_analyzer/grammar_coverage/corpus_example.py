#!/usr/bin/env python3
"""Example usage of the Golden Corpus Generator.

演示如何使用语料库生成器为语法覆盖验证创建测试文件。
"""

from pathlib import Path

from .corpus_generator import (
    generate_and_save_corpus,
    generate_corpus_by_category,
    generate_minimal_code_for_node_type,
)


def example_generate_single_code_snippet() -> None:
    """示例 1: 生成单个节点类型的代码片段"""
    print("=== Example 1: Generate single code snippet ===\n")

    # Python function
    python_func = generate_minimal_code_for_node_type("python", "function_definition")
    print(f"Python function_definition:\n{python_func}")

    # JavaScript arrow function
    js_arrow = generate_minimal_code_for_node_type("javascript", "arrow_function")
    print(f"JavaScript arrow_function:\n{js_arrow}")

    # Java class
    java_class = generate_minimal_code_for_node_type("java", "class_declaration")
    print(f"Java class_declaration:\n{java_class}")


def example_generate_corpus_by_category() -> None:
    """示例 2: 按分类生成完整语料库"""
    print("\n=== Example 2: Generate corpus by category ===\n")

    # Generate Python corpus
    python_corpus = generate_corpus_by_category("python")
    print(f"Generated {len(python_corpus)} Python corpus files:")
    for relative_path in sorted(python_corpus.keys()):
        print(f"  - {relative_path}")

    # Show content of one file
    if "functions/basic_functions.py" in python_corpus:
        print("\nContent of functions/basic_functions.py:")
        print(python_corpus["functions/basic_functions.py"][:200] + "...")


def example_generate_and_save_all_languages() -> None:
    """示例 3: 生成并保存所有支持的语言的语料库"""
    print("\n=== Example 3: Generate and save corpus for all languages ===\n")

    output_dir = Path("corpus_output")
    languages = ["python", "javascript", "java"]

    for language in languages:
        print(f"\nGenerating corpus for {language}...")
        paths, success, failed = generate_and_save_corpus(
            language=language,
            base_dir=str(output_dir),
            validate=True,
        )

        print(f"  Saved {len(paths)} files")
        print(f"  Validation: {success} passed, {failed} failed")

        if paths:
            print("  Files saved to:")
            for path in sorted(paths)[:3]:  # Show first 3
                print(f"    - {path}")
            if len(paths) > 3:
                print(f"    ... and {len(paths) - 3} more")


def main() -> None:
    """运行所有示例"""
    example_generate_single_code_snippet()
    example_generate_corpus_by_category()
    example_generate_and_save_all_languages()

    print("\n=== All examples completed! ===")
    print("\nCheck the 'corpus_output/' directory for generated files.")


if __name__ == "__main__":
    main()
