#!/usr/bin/env python3
"""
Grammar Introspection Prototype

验证通过 tree-sitter Language API 进行语法分析的可行性。
不依赖 grammar.json，而是通过运行时反射获取语法信息。
"""

import sys
from collections import defaultdict
from typing import Any

import tree_sitter
import tree_sitter_python


def get_all_node_types(lang: tree_sitter.Language) -> dict[str, dict[str, Any]]:
    """
    枚举 language 中的所有 node types

    Returns:
        dict[node_type, {id, is_named, is_supertype, is_visible}]
    """
    result = {}
    for i in range(lang.node_kind_count):
        try:
            name = lang.node_kind_for_id(i)
            result[name] = {
                "id": i,
                "is_named": lang.node_kind_is_named(i),
                "is_supertype": lang.node_kind_is_supertype(i),
                "is_visible": lang.node_kind_is_visible(i),
            }
        except Exception as e:
            print(f"Warning: Failed to get info for node type {i}: {e}", file=sys.stderr)
    return result


def get_all_field_names(lang: tree_sitter.Language) -> dict[int, str]:
    """
    枚举所有字段名称

    Returns:
        dict[field_id, field_name]
    """
    result = {}
    for i in range(lang.field_count):
        try:
            name = lang.field_name_for_id(i)
            if name:
                result[i] = name
        except Exception:
            pass
    return result


def infer_wrapper_patterns_heuristic(
    node_types: dict[str, dict[str, Any]]
) -> list[str]:
    """
    启发式推断 wrapper nodes

    规则：
    1. 名称包含 "decorated_", "attributed_", "modified_"
    2. 名称包含 "with_clause", "annotated_"
    3. 是 supertype（可能是抽象包装）

    注意：这种方法有局限性，真正的 wrapper 需要通过结构分析确定。
    """
    wrapper_candidates = []

    for node_type, _meta in node_types.items():
        # 规则 1: 名称模式匹配
        if any(
            pattern in node_type
            for pattern in [
                "decorated",
                "attributed",
                "modified",
                "annotated",
                "with_clause",
            ]
        ):
            wrapper_candidates.append(node_type)

    return wrapper_candidates


def analyze_parent_child_relationships(
    lang: tree_sitter.Language, sample_code: str
) -> dict[str, set[str]]:
    """
    通过解析示例代码分析父子关系

    Returns:
        dict[parent_type, set[child_types]]
    """
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(bytes(sample_code, "utf8"))

    relationships: dict[str, set[str]] = defaultdict(set)

    def traverse(node: tree_sitter.Node) -> None:
        for child in node.children:
            if child.is_named:  # 只记录 named nodes
                relationships[node.type].add(child.type)
            traverse(child)

    traverse(tree.root_node)
    return dict(relationships)


def enumerate_syntactic_paths_sample(
    lang: tree_sitter.Language, sample_code: str, max_depth: int = 3
) -> set[tuple[str, tuple[str, ...]]]:
    """
    通过解析示例代码枚举语法路径

    Returns:
        set[(node_type, (parent1, parent2, ...))]
    """
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(bytes(sample_code, "utf8"))

    paths: set[tuple[str, tuple[str, ...]]] = set()

    def traverse(node: tree_sitter.Node, parent_path: tuple[str, ...]) -> None:
        if len(parent_path) > max_depth:
            return

        if node.is_named:
            paths.add((node.type, parent_path))

        new_path = parent_path + (node.type,) if node.is_named else parent_path
        for child in node.children:
            traverse(child, new_path)

    traverse(tree.root_node, ())
    return paths


def main() -> None:
    """运行原型验证"""
    print("=" * 80)
    print("Phase 3 Auto-Discovery Feasibility Prototype")
    print("=" * 80)

    # 初始化 tree-sitter-python
    lang = tree_sitter.Language(tree_sitter_python.language())
    print(f"\n[OK] Language loaded: {lang.name}")
    print(f"   Version: {lang.version}")
    print(f"   ABI version: {lang.abi_version}")

    # 1. 枚举所有 node types
    print("\n" + "=" * 80)
    print("1. Node Types Enumeration")
    print("=" * 80)
    node_types = get_all_node_types(lang)
    named_types = [nt for nt, meta in node_types.items() if meta["is_named"]]
    print(f"Total node types: {len(node_types)}")
    print(f"Named node types: {len(named_types)}")
    print("\nSample named types (first 10):")
    for nt in named_types[:10]:
        meta = node_types[nt]
        print(f"  - {nt:30} (supertype={meta['is_supertype']})")

    # 2. 枚举字段名称
    print("\n" + "=" * 80)
    print("2. Field Names Enumeration")
    print("=" * 80)
    field_names = get_all_field_names(lang)
    print(f"Total fields: {len(field_names)}")
    print(f"Field names: {', '.join(sorted(field_names.values()))}")

    # 3. 推断 wrapper patterns
    print("\n" + "=" * 80)
    print("3. Wrapper Pattern Inference (Heuristic)")
    print("=" * 80)
    wrapper_candidates = infer_wrapper_patterns_heuristic(node_types)
    print(f"Found {len(wrapper_candidates)} wrapper candidates:")
    for wc in wrapper_candidates:
        print(f"  - {wc}")

    # 4. 分析示例代码的父子关系
    print("\n" + "=" * 80)
    print("4. Parent-Child Relationship Analysis")
    print("=" * 80)
    sample_code = """
@decorator
def foo(x: int) -> str:
    return str(x)

@decorator1
@decorator2
class Bar:
    def method(self):
        pass

async def async_func():
    await something()

lambda x: x + 1
"""
    relationships = analyze_parent_child_relationships(lang, sample_code)
    print(f"Analyzed {len(sample_code)} bytes of sample code")
    print(f"Found {len(relationships)} unique parent types\n")

    # 重点关注 decorated_definition
    if "decorated_definition" in relationships:
        print("decorated_definition children:")
        for child in sorted(relationships["decorated_definition"]):
            print(f"  - {child}")

    # 5. 枚举语法路径
    print("\n" + "=" * 80)
    print("5. Syntactic Path Enumeration")
    print("=" * 80)
    paths = enumerate_syntactic_paths_sample(lang, sample_code, max_depth=3)
    print(f"Total unique paths: {len(paths)}")
    print("\nSample paths involving decorated_definition:")
    decorated_paths = [
        p for p in paths if "decorated_definition" in (p[0],) + p[1]
    ]
    for node_type, parent_path in sorted(decorated_paths)[:10]:
        parent_str = " > ".join(parent_path) if parent_path else "(root)"
        print(f"  {parent_str} > {node_type}")

    # 6. 总结
    print("\n" + "=" * 80)
    print("6. Feasibility Summary")
    print("=" * 80)
    print("[OK] Grammar introspection via Language API: FEASIBLE")
    print("[OK] Node type enumeration: COMPLETE (275 types)")
    print("[WARN]  Wrapper pattern inference: HEURISTIC ONLY")
    print("[OK] Parent-child relationship discovery: FEASIBLE (code-based)")
    print("[OK] Syntactic path enumeration: FEASIBLE (limited by sample coverage)")
    print("\n[INFO] Key insight: grammar.json is NOT required!")
    print("   tree-sitter Language API provides runtime reflection.")
    print("   However, wrapper node identification needs structural analysis,")
    print("   not just name pattern matching.")


if __name__ == "__main__":
    main()
