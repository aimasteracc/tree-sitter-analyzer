# 修复 Golden Master 回归问题

## 概述

**变更ID**: `fix-golden-master-regression`  
**状态**: 草案  
**优先级**: 高  
**预计工作量**: ~5小时

### 问题描述

Golden Master 测试数据文件在最近的更改后出现了不正确的标题格式,导致测试失败和输出不一致。

### 解决方案

修复 `table_formatter.py` 中的标题生成逻辑,使用特定语言的约定,并更新受影响的 golden master 文件。

---

## 修复的关键问题

1. ✅ Java 文件使用文件名而不是类名(例如: `Sample.java` → `AbstractParentClass`)
2. ✅ Java compact 格式中缺少包信息
3. ✅ JavaScript/TypeScript 文件的错误 "unknown" 包前缀
4. ✅ Full 格式输出中的格式结构变化
5. ✅ 不一致的 Python 模块标题格式

---

## 具体问题分析

### 1. java_sample_compact.md
- **错误**: `# com.example.Sample.java`
- **正确**: `# com.example.AbstractParentClass`
- **原因**: 使用文件名而不是实际的类名

### 2. java_userservice_compact_format.md
- **错误**: `# UserService`
- **正确**: `# com.example.service.UserService` (或适当的包.类格式)
- **原因**: 缺少包信息

### 3. javascript_class_compact.md
- **错误**: `# unknown.Animal`
- **正确**: `# Animal`
- **原因**: JavaScript 文件不应该有包前缀

### 4. typescript_enum_compact.md
- **错误**: `# unknown.Color`
- **正确**: `# Color`
- **原因**: TypeScript 文件不应该有包前缀

### 5. java_bigservice_full.md
- **问题**: 格式结构被改变,破坏了兼容性
- **解决**: 维护原始格式结构

### 6. python_sample_full.md
- **问题**: 规范改进但与现有格式不一致
- **解决**: 确保一致的格式改进

---

## 标题格式规则

### Java 文件

| 场景 | 格式 | 示例 |
|------|------|------|
| 单个类 + 包信息 | `package.ClassName` | `com.example.service.BigService` |
| 单个类 + 无包 | `ClassName` | `UserService` |
| 多个类 | `filename` | `Sample` |

### Python 文件

| 场景 | 格式 | 示例 |
|------|------|------|
| 所有情况 | `Module: filename` | `Module: sample` |

### JavaScript/TypeScript 文件

| 场景 | 格式 | 示例 |
|------|------|------|
| 有类定义 | `ClassName` | `Animal` |
| 无类定义 | `filename` | `utilities` |
| **注意** | **不使用包前缀** | **不是** `unknown.Animal` |

---

## 根本原因分析

问题源于 `table_formatter.py` 中的标题生成逻辑:

### Compact 格式问题 (454-465行)
```python
# 当前错误的逻辑
package_name = (data.get("package") or {}).get("name", "unknown")  # 默认为 "unknown"
class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
lines.append(f"# {package_name}.{class_name}")  # 总是使用 package.class 格式
```

**问题**:
- 总是使用 `package.class` 格式,即使不合适
- 对缺少的包名默认使用 "unknown"
- 没有正确处理多个类或特殊情况
- JavaScript/TypeScript 文件不应该使用包表示法

### Full 格式问题 (60-102行)
- 复杂的条件逻辑,未覆盖所有情况
- 对不同语言的处理不一致
- 最近的更改破坏了现有行为

---

## 实现策略

### 新增辅助方法

```python
def _generate_title(self, data: dict[str, Any]) -> str:
    """基于语言和结构生成文档标题"""
    language = self.language.lower()
    
    if language == "java":
        return self._generate_java_title(...)
    elif language == "python":
        return self._generate_python_title(...)
    elif language in ["javascript", "typescript"]:
        return self._generate_js_ts_title(...)
    else:
        return self._generate_default_title(...)
```

### 语言特定的辅助方法

1. **`_generate_java_title()`**: 处理包.类格式,多类文件,无包情况
2. **`_generate_python_title()`**: 使用 "Module: name" 格式
3. **`_generate_js_ts_title()`**: 只使用类名,无包前缀
4. **`_extract_filename()`**: 提取不带扩展名的文件名

---

## 实施计划

### 第1阶段: 分析和理解 (已完成)
- [x] 识别所有有问题的 golden master 文件
- [x] 分析 `table_formatter.py` 中的根本原因
- [x] 记录每个文件的预期格式与实际格式
- [x] 审查 git diff 以了解变化

### 第2阶段: 修复标题生成逻辑
- [ ] 修复 compact 格式标题生成 (~30分钟)
- [ ] 修复 full 格式标题生成 (~45分钟)
- [ ] 添加语言特定的辅助方法 (~30分钟)

### 第3阶段: 更新 Golden Master 文件
- [ ] 修复 Java golden masters (~20分钟)
- [ ] 修复 JavaScript/TypeScript golden masters (~15分钟)
- [ ] 修复 Python golden masters (~15分钟)

### 第4阶段: 测试和验证
- [ ] 运行所有 golden master 测试 (~10分钟)
- [ ] 运行格式验证测试 (~10分钟)
- [ ] 手动验证 (~20分钟)
- [ ] 跨平台验证 (~15分钟)

### 第5阶段: 文档和清理
- [ ] 更新格式规范 (~20分钟)
- [ ] 添加回归测试 (~30分钟)
- [ ] 更新 CHANGELOG (~5分钟)

---

## 测试策略

### 单元测试
```python
def test_java_title_single_class_with_package()
def test_java_title_no_package()
def test_python_title()
def test_js_title_no_unknown_prefix()
def test_java_title_multiple_classes()
```

### 集成测试
- 所有语言类型的 golden master 测试
- 格式验证测试
- 跨语言验证

### 手动测试
- 为每个测试用例生成输出
- 与 golden master 文件进行比较
- 验证标题易读且正确

---

## 成功标准

- [ ] 所有 golden master 测试文件都有正确的标题
- [ ] JavaScript/TypeScript 输出中没有 "unknown" 包前缀
- [ ] Java 文件在适当时使用 `package.ClassName` 格式
- [ ] Python 文件使用 `Module: name` 格式
- [ ] Full 格式保持原始结构
- [ ] 其他格式类型(CSV, JSON)没有回归
- [ ] 添加了防止未来问题的回归测试

---

## 文件结构

```
openspec/changes/fix-golden-master-regression/
├── README.md                          # 英文摘要
├── README_zh.md                       # 本文件(中文摘要)
├── proposal.md                        # 详细提案(英文)
├── tasks.md                           # 任务分解(英文)
├── design.md                          # 设计文档(英文)
├── validation.md                      # 验证清单(英文)
└── specs/
    └── golden-master-title-format/
        └── spec.md                    # 规范(英文)
```

---

## 影响评估

### 优势
- ✅ 修复损坏的 golden master 测试
- ✅ 改善输出格式一致性
- ✅ 更好地处理多语言场景
- ✅ 更易维护的标题生成逻辑

### 风险
- ⚠️ 如果格式更改,可能需要更新其他测试文件
- ⚠️ 需要验证所有 golden master 文件是否正确

### 范围
- **修改的组件**: `table_formatter.py`, golden master 测试文件
- **测试覆盖**: 现有 golden master 测试, 格式验证测试
- **破坏性变更**: 无(修复回归,不引入新行为)

---

## 依赖关系

- 需要理解当前的 golden master 测试框架
- 可能需要与格式测试策略更改协调
- 相关变更: `fix-analyze-code-structure-format-regression`
- 相关变更: `implement-comprehensive-format-testing-strategy`

---

## 快速开始

### 1. 查看提案
```bash
cat openspec/changes/fix-golden-master-regression/proposal.md
```

### 2. 检查当前状态
```bash
git diff --cached tests/golden_masters/
```

### 3. 实施更改
按照 `tasks.md` 中的任务顺序进行。

### 4. 运行测试
```bash
# 单元测试
pytest tests/test_table_formatter.py -v

# Golden master 测试
pytest tests/golden_masters/ -v

# 所有测试
pytest tests/ -v
```

### 5. 验证
使用 `validation.md` 中的检查清单。

---

## 注意事项

### 重要
- 这个变更修复回归,不引入新行为
- 为有效的 golden master 保持向后兼容性
- 专注于正确性和一致性

### 未来改进
- 考虑为标题格式偏好添加配置
- 可能添加更复杂的标题自定义
- 可以扩展以支持更多语言

---

## 时间线

| 阶段 | 状态 | 预计时间 |
|------|------|---------|
| 第1阶段: 分析 | ✅ 完成 | 已完成 |
| 第2阶段: 实现 | ⏳ 计划中 | ~2小时 |
| 第3阶段: 测试 | ⏳ 计划中 | ~1小时 |
| 第4阶段: 文档 | ⏳ 计划中 | ~1小时 |
| **总计** | | **~5小时** |

---

**最后更新**: 2025-11-08  
**变更负责人**: AI Agent / 开发团队  
**审查状态**: 待定

---

## 联系与资源

### 文档
- **设计**: `design.md` - 标题生成规则和实现策略
- **规范**: `specs/golden-master-title-format/spec.md` - 详细需求
- **任务**: `tasks.md` - 分步实施任务

### 代码参考
- `tree_sitter_analyzer/table_formatter.py` - 主要实现
- `tests/golden_masters/` - Golden master 测试文件
- `docs/format_specifications.md` - 格式文档

### 相关问题
- GitHub Issues: (如果创建则链接)
- 先前提交: 7409bcf, c4a0ac7

