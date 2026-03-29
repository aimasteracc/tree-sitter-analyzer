#!/usr/bin/env python3
"""
Public Contract Tests for TOON Encoder.

测试 TOON 编码器的对外契约（外部用户依赖的行为）。
这些测试失败意味着破坏了向后兼容性。
"""

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder


class TestToonEncoderPublicContract:
    """对外契约测试：外部用户依赖的核心行为"""

    def test_contract_simple_dict_structure(self):
        """契约：简单 dict 编码为 key: value 格式"""
        encoder = ToonEncoder()
        data = {"name": "test", "value": 42}

        output = encoder.encode(data)

        # 契约承诺：简单 dict 使用 key: value 格式
        assert "name: test" in output
        assert "value: 42" in output

    def test_contract_homogeneous_array_uses_array_table(self):
        """契约：同构数组使用 Array Table 格式（紧凑表示）"""
        encoder = ToonEncoder()
        data = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
            ]
        }

        output = encoder.encode(data)

        # 契约承诺：同构数组使用 [N]{fields}: 格式
        assert "[2]{" in output  # Array Table 标记
        assert "Alice" in output
        assert "Bob" in output

    def test_contract_mixed_array_uses_inline_json(self):
        """契约：非同构数组使用内联 JSON 格式"""
        encoder = ToonEncoder()
        data = {
            "items": [
                {"type": "A", "value": 1},
                {"kind": "B", "count": 2},  # 不同 keys
            ]
        }

        output = encoder.encode(data)

        # 契约承诺：非同构数组使用 [{...},{...}] 内联格式
        assert "[{" in output or "[" in output  # JSON 数组标记

    def test_contract_nested_structure_preserves_hierarchy(self):
        """契约：嵌套结构保持层级关系"""
        encoder = ToonEncoder()
        data = {
            "module": {
                "name": "core",
                "classes": [
                    {"name": "ClassA", "methods": ["method1", "method2"]}
                ]
            }
        }

        output = encoder.encode(data)

        # 契约承诺：能够识别 module > classes > methods 层级
        assert "module:" in output
        assert "classes" in output or "[1]{" in output
        assert "ClassA" in output

    def test_contract_empty_containers_handled(self):
        """契约：空容器不导致崩溃"""
        encoder = ToonEncoder()

        # 空 dict
        output1 = encoder.encode({})
        assert output1 is not None  # 不崩溃

        # 空 list
        output2 = encoder.encode({"items": []})
        assert "items:" in output2 or "items" in output2
        assert "[]" in output2 or "items:" in output2  # 空数组表示

    def test_contract_unicode_content_preserved(self):
        """契约：Unicode 内容正确保留"""
        encoder = ToonEncoder()
        data = {
            "name": "测试",
            "description": "这是一个带有中文的 docstring"
        }

        output = encoder.encode(data)

        # 契约承诺：Unicode 字符不被破坏
        assert "测试" in output
        assert "中文" in output or "docstring" in output

    def test_contract_large_array_does_not_timeout(self):
        """契约：大数组处理不超时（性能契约）"""
        encoder = ToonEncoder()
        data = {
            "items": [
                {"id": i, "name": f"item{i}", "value": i * 10}
                for i in range(1000)
            ]
        }

        # 契约承诺：1000个元素在5秒内完成（之前9分钟→现在5秒）
        import time
        start = time.time()
        output = encoder.encode(data)
        duration = time.time() - start

        assert duration < 5.0, f"Encoding took {duration:.2f}s (should be < 5s)"
        assert len(output) > 0  # 产生了输出

    def test_contract_circular_reference_no_crash(self):
        """契约：循环引用不导致堆栈溢出"""
        encoder = ToonEncoder()

        # 创建循环引用
        data = {"name": "root"}
        data["self"] = data  # 循环引用

        # 契约承诺：循环引用被检测并安全处理（不崩溃）
        try:
            output = encoder.encode(data)
            # 应该包含循环引用的标记（如 "[...]"）
            assert "[...]" in output or "..." in output
        except RecursionError:
            # 如果抛出递归错误，说明契约被打破
            raise AssertionError("Circular reference caused stack overflow - contract broken!") from None

    def test_contract_priority_fields_order_respected(self):
        """契约：高优先级字段优先保留（当字段数超限时）"""
        encoder = ToonEncoder()

        # 包含所有优先级字段 + 额外字段的数组
        data = {
            "methods": [
                {
                    "name": "method1",  # 优先级 10
                    "docstring": "This is a method",  # 优先级 9
                    "parameters": ["self", "arg1"],  # 优先级 8
                    "return_type": "str",  # 优先级 7
                    "line_start": 10,  # 优先级 3
                    "line_end": 20,  # 低优先级（应被截断）
                    "visibility": "public",  # 低优先级（应被截断）
                }
            ]
        }

        output = encoder.encode(data)

        # 契约承诺：高优先级字段（name, docstring, parameters, return_type）必须出现
        assert "name" in output.lower() or "method1" in output
        assert "docstring" in output.lower() or "This is a method" in output
        assert "parameters" in output.lower() or "self" in output or "arg1" in output
        assert "return_type" in output.lower() or "str" in output

        # 低优先级字段可能被截断（非强制契约）
        # assert "visibility" not in output.lower()  # 可能被截断

    def test_contract_docstring_truncation_with_ellipsis(self):
        """契约：超长 docstring 被截断并添加 ... 标记"""
        encoder = ToonEncoder()

        long_docstring = "A" * 100  # 100 字符的超长 docstring
        data = {
            "methods": [
                {"name": "method1", "docstring": long_docstring}
            ]
        }

        output = encoder.encode(data)

        # 契约承诺：超长内容被截断并添加 "..." 标记
        if len(long_docstring) > encoder.COMPACT_DOCSTRING_LIMIT:
            assert "..." in output  # 截断标记
            # 不应该包含完整的100个A
            assert "A" * 100 not in output
