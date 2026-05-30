<!-- HISTORICAL RECORD — file paths in this document reflect early project planning. Some paths may no longer exist. -->
# 回归测试指南

本文档为tree-sitter-analyzer项目提供全面的回归测试指南，帮助开发者理解和使用Golden Master方法进行回归测试。

## 📋 目录

- [回归测试概述](#回归测试概述)
- [Golden Master方法](#golden-master方法)
- [回归测试添加流程](#回归测试添加流程)
- [回归测试维护指南](#回归测试维护指南)
- [常见问题解答](#常见问题解答)

---

## 回归测试概述

### 什么是回归测试？

回归测试是确保代码更改不会破坏现有功能的测试。它们验证：

- **API向后兼容性**: 旧API仍然工作
- **输出格式稳定性**: 输出格式保持一致
- **功能完整性**: 现有功能继续正常工作

### 为什么需要回归测试？

1. **防止破坏性变更**: 捕获意外破坏现有功能的更改
2. **确保向后兼容**: 验证新版本与旧版本兼容
3. **提高信心**: 在发布前确保代码质量
4. **自动化验证**: 通过CI/CD自动运行，节省时间

### 回归测试类型

| 类型 | 描述 | 示例 |
|------|------|------|
| **格式回归** | 输出格式保持一致 | Python分析输出格式不变 |
| **API回归** | API接口保持兼容 | 旧API调用仍然工作 |
| **兼容性回归** | 跨版本兼容 | v1.6配置文件在v1.7中工作 |

---

## Golden Master方法

### 什么是Golden Master？

Golden Master是已知正确的输出快照，用作回归测试的参考标准。它记录了系统在特定状态下的预期行为。

### Golden Master工作原理

```
1. 创建Golden Master
   ↓
2. 代码变更
   ↓
3. 运行回归测试
   ↓
4. 比较当前输出与Golden Master
   ↓
5. 如果匹配 → 测试通过
   如果不匹配 → 测试失败
```

### Golden Master文件结构

```
tests/golden_masters/
├── python_sample_full.txt          # Python完整格式输出
├── python_sample_compact.txt       # Python紧凑格式输出
├── java_sample_full.txt            # Java完整格式输出
├── javascript_sample_full.txt      # JavaScript完整格式输出
└── toon/                          # Toon格式输出
    ├── python_sample_toon.toon
    ├── java_sample_toon.toon
    └── javascript_sample_toon.toon
```

### 创建Golden Master

#### 方法1: 手动创建

```bash
# 1. 运行分析并保存输出
uv run python -m tree_sitter_analyzer analyze \
  examples/sample.py \
  --format full > output.txt

# 2. 验证输出正确性
cat output.txt

# 3. 复制到golden_masters目录
cp output.txt tests/golden_masters/python_sample_full.txt
```

#### 方法2: 自动创建

```bash
# 使用pytest的--update-golden-masters标志
uv run pytest tests/regression/test_format_regression.py \
  --update-golden-masters

# 这将自动更新所有Golden Master文件
```

#### 方法3: CI/CD自动更新

```yaml
# .github/workflows/regression-tests.yml
- name: Update Golden Masters
  if: inputs.update-golden-masters == true
  run: |
    uv run pytest tests/regression/test_format_regression.py \
      --update-golden-masters
```

### Golden Master最佳实践

1. **版本控制**: Golden Master文件应该提交到版本控制
2. **明确命名**: 使用描述性文件名（如`python_sample_full.txt`）
3. **文档化**: 在测试文件中记录Golden Master的用途
4. **定期审查**: 定期检查Golden Master是否仍然有效
5. **变更日志**: 记录Golden Master变更的原因

```python
# 测试文件中的文档
def test_python_format_stability():
    """测试Python格式输出的稳定性。

    Golden Master: tests/golden_masters/python_sample_full.txt
    创建日期: 2025-01-01
    最后更新: 2025-01-15
    更新原因: 添加了新的输出字段
    """
    # 测试代码
```

---

## 回归测试添加流程

### 步骤1: 识别需要回归测试的功能

考虑以下问题：

- [ ] 这个功能是否影响用户可见的输出？
- [ ] 这个功能是否影响API接口？
- [ ] 这个功能是否影响配置文件格式？
- [ ] 这个功能是否影响数据序列化？

如果答案是"是"，则需要回归测试。

### 步骤2: 创建测试用例

#### 格式回归测试示例

```python
"""测试格式输出回归。"""

import pytest
from pathlib import Path
from tree_sitter_analyzer.core import analyze_code_structure

class TestFormatRegression:
    """格式输出回归测试。"""

    @pytest.mark.regression
    def test_python_format_stability(self, sample_python_file):
        """测试Python格式输出的稳定性。

        验证Python代码的完整格式输出保持稳定。

        Golden Master: tests/golden_masters/python_sample_full.txt
        """
        # 执行分析
        result = analyze_code_structure(
            sample_python_file,
            format_type="full"
        )

        # 加载Golden Master
        golden_master_path = Path(
            "tests/golden_masters/python_sample_full.txt"
        )
        with open(golden_master_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()

        # 验证一致性
        assert result == expected_output, (
            f"Format output changed. "
            f"Expected:\n{expected_output}\n\n"
            f"Got:\n{result}"
        )

    @pytest.mark.regression
    def test_java_format_stability(self, sample_java_file):
        """测试Java格式输出的稳定性。"""
        result = analyze_code_structure(
            sample_java_file,
            format_type="full"
        )

        golden_master_path = Path(
            "tests/golden_masters/java_sample_full.txt"
        )
        with open(golden_master_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()

        assert result == expected_output

    @pytest.mark.regression
    def test_toon_format_stability(self, sample_python_file):
        """测试Toon格式输出的稳定性。"""
        result = analyze_code_structure(
            sample_python_file,
            format_type="toon"
        )

        golden_master_path = Path(
            "tests/golden_masters/toon/python_sample_toon.toon"
        )
        with open(golden_master_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()

        assert result == expected_output
```

#### API回归测试示例

```python
"""测试API回归。"""

import pytest
from tree_sitter_analyzer.core.request import AnalysisRequest

class TestAPIRegression:
    """API向后兼容性测试。"""

    @pytest.mark.regression
    def test_old_api_compatibility(self):
        """测试旧API创建方式仍然工作。"""
        # 旧方式（v1.0）
        request = AnalysisRequest(
            file_path=Path("test.py"),
            language="python",
            format_type="full"
        )

        # 验证所有字段都存在
        assert hasattr(request, 'file_path')
        assert hasattr(request, 'language')
        assert hasattr(request, 'format_type')
        assert hasattr(request, 'include_details')

    @pytest.mark.regression
    def test_new_api_parameters_accepted(self):
        """测试新参数被接受。"""
        # 新方式（v1.5+）
        request = AnalysisRequest(
            file_path=Path("test.py"),
            language="python",
            format_type="full",
            include_details=True,  # 新参数
            include_complexity=True,  # 新参数
            include_dependencies=True  # 新参数
        )

        # 验证新参数被接受
        assert request.include_details is True
        assert request.include_complexity is True
        assert request.include_dependencies is True
```

#### 兼容性回归测试示例

```python
"""测试跨版本兼容性。"""

import pytest
from pathlib import Path
import yaml

class TestCrossVersionCompatibility:
    """跨版本兼容性测试。"""

    @pytest.mark.regression
    def test_config_file_compatibility(self):
        """测试配置文件向后兼容性。"""
        # v1.6配置文件
        config_v1_6 = {
            "language": "python",
            "queries": [
                {"name": "classes", "query": "(class_definition) @class"}
            ]
        }

        # 应该仍然工作
        from tree_sitter_analyzer.core.config import load_config
        config = load_config(config_v1_6)

        assert config is not None
        assert config["language"] == "python"
        assert len(config["queries"]) == 1

    @pytest.mark.regression
    def test_missing_fields_handled(self):
        """测试缺失字段被正确处理。"""
        # 不完整的配置文件
        incomplete_config = {
            "language": "python"
            # 缺少"queries"字段
        }

        from tree_sitter_analyzer.core.config import load_config
        config = load_config(incomplete_config)

        # 应该使用默认值
        assert config is not None
        assert config["queries"] == []
```

### 步骤3: 添加测试标记

使用`@pytest.mark.regression`标记回归测试：

```python
@pytest.mark.regression
def test_regression_example():
    """这是一个回归测试。"""
    pass
```

### 步骤4: 运行回归测试

```bash
# 运行所有回归测试
uv run pytest tests/ -m regression

# 运行特定回归测试
uv run pytest tests/regression/test_format_regression.py

# 运行带详细输出的回归测试
uv run pytest tests/ -m regression -v

# 运行带覆盖率的回归测试
uv run pytest tests/ -m regression --cov=tree_sitter_analyzer
```

### 步骤5: 验证测试

确保测试：

1. **通过**: 在当前代码上运行并通过
2. **失败**: 在有问题的代码上运行并失败
3. **有意义**: 失败消息清晰且有帮助

---

## 回归测试维护指南

### 何时更新Golden Master

更新Golden Master的情况：

1. **有意更改**: 功能性更改需要新输出格式
2. **Bug修复**: 修复了导致错误输出的bug
3. **新功能**: 添加了新的输出字段
4. **重构**: 代码重构改变了输出顺序

**不更新Golden Master的情况**：

1. **代码清理**: 不影响输出的代码改进
2. **性能优化**: 不影响输出的性能改进
3. **文档更新**: 仅文档更改

### 更新Golden Master的流程

#### 本地更新

```bash
# 1. 更新Golden Master
uv run pytest tests/regression/test_format_regression.py \
  --update-golden-masters

# 2. 验证更改
git diff tests/golden_masters/

# 3. 提交更改
git add tests/golden_masters/
git commit -m "chore: update golden masters for new feature"

# 4. 推送到远程
git push
```

#### CI/CD更新

```yaml
# .github/workflows/regression-tests.yml
golden-master-update:
  name: Update Golden Masters
  runs-on: ubuntu-latest
  if: github.event_name == 'workflow_dispatch' &&
      inputs.update-golden-masters == true

  steps:
  - name: Checkout code
    uses: actions/checkout@v4

  - name: Update Golden Masters
    run: |
      uv run pytest tests/regression/test_format_regression.py \
        --update-golden-masters

  - name: Commit and push changes
    run: |
      git config --local user.email "github-actions[bot]@users.noreply.github.com"
      git config --local user.name "github-actions[bot]"
      git add tests/golden_masters/
      git commit -m "chore: update golden masters [skip ci]"
      git push
```

### Golden Master变更文档

每次更新Golden Master时，记录变更：

```markdown
## Golden Master变更日志

### 2025-01-15

**原因**: 添加了新的输出字段`complexity`和`dependencies`

**影响文件**:
- `tests/golden_masters/python_sample_full.txt`
- `tests/golden_masters/java_sample_full.txt`
- `tests/golden_masters/toon/python_sample_toon.toon`

**变更详情**:
- 在每个类元素后添加了`complexity`字段
- 在每个方法元素后添加了`dependencies`字段
- 格式保持不变，只是添加了新字段

**审查者**: @username
```

### 回归测试失败处理

当回归测试失败时：

1. **分析失败原因**:
   - 是有意更改吗？
   - 是意外bug吗？
   - 是格式问题吗？

2. **如果是无意更改**:
   - 修复导致失败的代码
   - 重新运行测试验证修复

3. **如果是有意更改**:
   - 更新Golden Master
   - 记录变更原因
   - 提交更新

4. **如果是格式问题**:
   - 检查代码格式化
   - 运行`uv run black .`
   - 重新运行测试

### 回归测试性能优化

如果回归测试运行缓慢：

1. **使用pytest缓存**:
   ```bash
   uv run pytest tests/ -m regression --cache-clear
   ```

2. **并行运行**:
   ```bash
   uv run pytest tests/ -m regression -n auto
   ```

3. **选择性运行**:
   ```bash
   # 只运行格式回归测试
   uv run pytest tests/regression/test_format_regression.py

   # 只运行API回归测试
   uv run pytest tests/regression/test_api_regression.py
   ```

---

## 常见问题解答

### Q1: Golden Master应该包含在版本控制中吗？

**A:** 是的。Golden Master文件应该提交到版本控制中，因为它们是测试的参考标准。

### Q2: 如何处理小的格式差异（如空格）？

**A:** 使用规范化比较：

```python
def test_with_normalization():
    """使用规范化比较的测试。"""
    result = analyze_code_structure(file_path, format_type="full")

    with open(golden_master_path, 'r') as f:
        expected_output = f.read()

    # 规范化比较（忽略空格和换行）
    assert result.strip() == expected_output.strip()
```

### Q3: 如何测试多个输出格式？

**A:** 为每个格式创建单独的测试：

```python
@pytest.mark.parametrize("format_type,golden_master", [
    ("full", "python_sample_full.txt"),
    ("compact", "python_sample_compact.txt"),
    ("csv", "python_sample.csv"),
])
def test_multiple_formats(self, format_type, golden_master):
    """测试多种输出格式。"""
    result = analyze_code_structure(file_path, format_type=format_type)

    with open(f"tests/golden_masters/{golden_master}", 'r') as f:
        expected_output = f.read()

    assert result == expected_output
```

### Q4: 如何处理动态输出（如时间戳）？

**A:** 在比较前替换动态值：

```python
def test_with_dynamic_values():
    """处理动态值的测试。"""
    result = analyze_code_structure(file_path)

    with open(golden_master_path, 'r') as f:
        expected_output = f.read()

    # 替换动态值
    import re
    result_normalized = re.sub(
        r'timestamp: \d+',
        'timestamp: <TIMESTAMP>',
        result
    )
    expected_normalized = re.sub(
        r'timestamp: \d+',
        'timestamp: <TIMESTAMP>',
        expected_output
    )

    assert result_normalized == expected_normalized
```

### Q5: 如何调试回归测试失败？

**A:** 使用详细的失败消息：

```python
def test_with_detailed_failure():
    """带有详细失败消息的测试。"""
    result = analyze_code_structure(file_path)

    with open(golden_master_path, 'r') as f:
        expected_output = f.read()

    if result != expected_output:
        # 找出差异
        import difflib
        diff = difflib.unified_diff(
            expected_output.splitlines(keepends=True),
            result.splitlines(keepends=True),
            fromfile='golden_master',
            tofile='actual'
        )

        # 提供详细的失败消息
        raise AssertionError(
            f"Output differs from Golden Master:\n"
            f"{''.join(diff)}\n\n"
            f"To update Golden Master, run:\n"
            f"uv run pytest tests/regression/test_format_regression.py "
            f"--update-golden-masters"
        )
```

### Q6: 回归测试应该运行多频繁？

**A:** 回归测试应该在每次代码更改时运行：

- **Pull Request**: 自动运行
- **Push to main**: 自动运行
- **Scheduled**: 每日运行（可选）
- **Manual**: 按需运行

### Q7: 如何处理大型Golden Master文件？

**A:** 对于大型Golden Master文件：

1. **使用压缩**: 考虑使用`.gz`压缩
2. **分割文件**: 将大型Golden Master分割为多个小文件
3. **使用哈希**: 比较文件哈希而不是内容

```python
def test_large_golden_master():
    """测试大型Golden Master。"""
    result = analyze_code_structure(file_path)

    # 计算哈希而不是比较内容
    import hashlib
    result_hash = hashlib.md5(result.encode()).hexdigest()

    with open(golden_master_path, 'rb') as f:
        expected_hash = hashlib.md5(f.read()).hexdigest()

    assert result_hash == expected_hash
```

---

## 参考资料

- [测试编写指南](./test-writing-guide.md)
- [项目测试规范](../TESTING.md)
- [pytest文档](https://docs.pytest.org/)
- [Golden Master模式](https://martinfowler.com/bliki/GoldenMaster)
