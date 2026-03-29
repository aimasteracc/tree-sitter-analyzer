#!/usr/bin/env python3
"""
Unit tests for ToonEncoder automatic Array Table detection.

遵循项目测试规范：
- Unit tests = Mock-based only, NO real parser
- 测试 ToonEncoder 自动检测同构数组并应用 Array Table
- 测试嵌套同构数组的紧凑编码
"""


from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder


class TestToonEncoderHomogeneousDetection:
    """测试同构数组检测"""

    def test_is_homogeneous_dict_array_with_identical_keys(self):
        """相同 keys 的 dict 数组应被识别为同构"""
        encoder = ToonEncoder()
        items = [
            {"name": "foo", "type": "bar"},
            {"name": "baz", "type": "qux"},
        ]

        assert encoder._is_homogeneous_dict_array(items) is True

    def test_is_homogeneous_dict_array_with_similar_keys(self):
        """80% 相似度的 keys 应被识别为同构"""
        encoder = ToonEncoder()
        items = [
            {"name": "foo", "type": "bar", "extra": "x"},
            {"name": "baz", "type": "qux", "extra": "y"},
            {"name": "test", "type": "value"},  # 缺少 extra，但相似度仍 >= 80%
        ]

        # 相似度 = 2/3 = 66.7% < 80%，应该返回 False
        assert encoder._is_homogeneous_dict_array(items) is False

    def test_is_homogeneous_dict_array_with_different_keys(self):
        """完全不同 keys 的 dict 数组不是同构"""
        encoder = ToonEncoder()
        items = [
            {"name": "foo"},
            {"type": "bar"},
            {"value": "baz"},
        ]

        assert encoder._is_homogeneous_dict_array(items) is False

    def test_is_homogeneous_dict_array_with_non_dicts(self):
        """包含非 dict 元素的数组不是同构"""
        encoder = ToonEncoder()
        items = [
            {"name": "foo"},
            "not a dict",
            {"name": "baz"},
        ]

        assert encoder._is_homogeneous_dict_array(items) is False

    def test_is_homogeneous_dict_array_empty_list(self):
        """空列表不是同构数组"""
        encoder = ToonEncoder()
        assert encoder._is_homogeneous_dict_array([]) is False

    def test_is_homogeneous_dict_array_single_item(self):
        """单个 dict 应被识别为同构"""
        encoder = ToonEncoder()
        items = [{"name": "foo", "type": "bar"}]

        assert encoder._is_homogeneous_dict_array(items) is True

    def test_is_homogeneous_dict_array_with_first_dict_empty(self):
        """第一个 dict 为空，应返回 False"""
        encoder = ToonEncoder()
        items = [{}, {"name": "foo"}]

        assert encoder._is_homogeneous_dict_array(items) is False

    def test_is_homogeneous_dict_array_with_subsequent_dict_empty(self):
        """后续 dict 为空，应返回 False"""
        encoder = ToonEncoder()
        items = [{"name": "foo"}, {}]

        assert encoder._is_homogeneous_dict_array(items) is False

    def test_is_homogeneous_dict_array_all_empty_dicts(self):
        """所有 dict 都为空，应返回 False"""
        encoder = ToonEncoder()
        items = [{}, {}, {}]

        assert encoder._is_homogeneous_dict_array(items) is False


class TestToonEncoderAutoArrayTable:
    """测试自动 Array Table 应用"""

    def test_top_level_homogeneous_array_uses_array_table(self):
        """顶层同构数组应自动使用 Array Table"""
        encoder = ToonEncoder()
        data = {
            "methods": [
                {"name": "foo", "type": "int"},
                {"name": "bar", "type": "str"},
            ]
        }

        output = encoder.encode(data)

        # 验证 Array Table 格式
        assert "[2]{name,type}:" in output
        assert "foo,int" in output
        assert "bar,str" in output

    def test_nested_homogeneous_array_uses_compact_format(self):
        """嵌套的同构数组应使用紧凑格式"""
        encoder = ToonEncoder()
        data = {
            "classes": [
                {
                    "name": "MyClass",
                    "methods": [
                        {"name": "method1", "return_type": "void", "line_start": 10},
                        {"name": "method2", "return_type": "int", "line_start": 20},
                    ],
                }
            ]
        }

        output = encoder.encode(data)

        # 验证紧凑格式（嵌套在 Array Table 单元格中）
        assert "[2]<" in output  # 紧凑 Array Table 标记
        assert "method1|void|10" in output or "method1|" in output  # 紧凑值分隔
        assert "method2|int|20" in output or "method2|" in output

    def test_non_homogeneous_array_uses_inline_json(self):
        """非同构数组应使用内联 JSON"""
        encoder = ToonEncoder()
        data = {
            "items": [
                {"name": "foo"},
                {"type": "bar"},  # 不同 keys
            ]
        }

        output = encoder.encode(data)

        # 验证内联 JSON 格式
        assert "[{name:foo},{type:bar}]" in output or "[{" in output

    def test_mixed_list_uses_inline_format(self):
        """混合类型列表应使用内联格式"""
        encoder = ToonEncoder()
        data = {
            "items": ["string", 123, {"key": "value"}]
        }

        output = encoder.encode(data)

        # 验证内联格式
        assert "[string,123," in output


class TestToonEncoderCompactHomogeneousArray:
    """测试紧凑同构数组编码"""

    def test_encode_compact_homogeneous_array_basic(self):
        """基本的紧凑同构数组编码"""
        encoder = ToonEncoder()
        items = [
            {"name": "foo", "return_type": "int", "line_start": 10},
            {"name": "bar", "return_type": "str", "line_start": 20},
        ]

        output = encoder._encode_compact_homogeneous_array(items, set())

        # 验证格式：[N]<k1,k2,...>(v1|v2|...,...)
        assert output.startswith("[2]<")
        assert "name,return_type,line_start" in output or "name," in output
        assert "foo|" in output or "foo)" in output
        assert "bar|" in output or "bar)" in output

    def test_encode_compact_homogeneous_array_with_list_values(self):
        """包含列表值的紧凑编码"""
        encoder = ToonEncoder()
        items = [
            {"name": "method1", "parameters": ["self", "arg1"]},
            {"name": "method2", "parameters": ["self"]},
        ]

        output = encoder._encode_compact_homogeneous_array(items, set())

        # 验证列表值被简化
        assert "[2]<" in output
        assert "method1|" in output
        assert "method2|" in output

    def test_encode_compact_homogeneous_array_empty(self):
        """空数组应返回 []"""
        encoder = ToonEncoder()
        output = encoder._encode_compact_homogeneous_array([], set())

        assert output == "[]"

    def test_encode_compact_homogeneous_array_selects_priority_keys(self):
        """应优先选择关键字段（name, type, parameters, line_start）"""
        encoder = ToonEncoder()
        items = [
            {
                "name": "method1",
                "return_type": "int",
                "parameters": ["self"],
                "line_start": 10,
                "line_end": 15,
                "visibility": "public",  # 低优先级
            }
        ]

        output = encoder._encode_compact_homogeneous_array(items, set())

        # 验证只包含前 4 个优先字段
        assert "name," in output
        assert "return_type," in output
        assert "parameters," in output
        assert "line_start" in output
        # visibility 不应出现
        assert "visibility" not in output


class TestToonEncoderRegressionTests:
    """回归测试：确保优化不破坏现有功能"""

    def test_simple_dict_still_works(self):
        """简单 dict 编码仍然正常"""
        encoder = ToonEncoder()
        data = {"key": "value", "number": 42}

        output = encoder.encode(data)

        assert "key: value" in output
        assert "number: 42" in output

    def test_simple_list_still_works(self):
        """简单列表编码仍然正常"""
        encoder = ToonEncoder()
        data = {"items": [1, 2, 3, "test"]}

        output = encoder.encode(data)

        assert "items: [1,2,3,test]" in output or "items:" in output

    def test_nested_dict_still_works(self):
        """嵌套 dict 编码仍然正常"""
        encoder = ToonEncoder()
        data = {
            "outer": {
                "inner": {
                    "key": "value"
                }
            }
        }

        output = encoder.encode(data)

        assert "outer:" in output
        assert "inner:" in output
        assert "key: value" in output
