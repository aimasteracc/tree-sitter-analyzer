# Fix Command-Formatter Coupling

## 概述

**变更ID**: `fix-command-formatter-coupling`  
**状态**: 草案  
**优先级**: 🔴 极高  
**复杂度**: 🟡 中等  
**风险**: 🟢 低  
**预计工作量**: ~7小时

---

## 问题本质 🎯

这才是 Golden Master 回归问题的**真正根源**!

### 错误的设计模式

```python
# table_command.py (第46-63行) - 罪魁祸首!
formatter = create_language_formatter(analysis_result.language)
if formatter:
    # 使用新格式化器
    ...
else:
    # 回退到旧格式化器
    ...
```

**问题**: 这是**隐式耦合** - "如果格式化器存在,就用它"

### 问题链

```
添加 SQL 支持
  ↓
在 LanguageFormatterFactory 注册 SQL
  ↓
table_command.py 检测到 formatter 存在
  ↓
自动切换到新的格式化路径
  ↓
新路径的标题生成逻辑不同
  ↓
Java/Python/JS/TS 输出格式改变
  ↓
Golden Master 测试全部失败 ❌
```

### 真相

之前我们误以为是 `table_formatter.py` 的标题生成逻辑问题,实际上是命令层的架构缺陷!

---

## 解决方案 💡

### 原则: 显式配置 > 隐式检测

```python
# 配置文件 (新增)
LANGUAGE_FORMATTER_CONFIG = {
    "java": {"table": "legacy"},      # 明确使用旧系统
    "python": {"table": "legacy"},
    "javascript": {"table": "legacy"},
    "typescript": {"table": "legacy"},
    "sql": {"table": "new"},          # 明确使用新系统
}

# table_command.py (修改后)
formatter = FormatterSelector.get_formatter(
    language=analysis_result.language,
    format_type=table_type
)
# 不再有 if/else - 配置决定一切!
```

---

## 修复的问题

### 1. 隐式耦合 → 显式配置
- ❌ 之前: "格式化器存在就用它"
- ✅ 现在: "配置说用哪个就用哪个"

### 2. 全局影响 → 完全隔离
- ❌ 之前: 添加SQL → 影响所有语言
- ✅ 现在: 添加SQL → 只影响SQL

### 3. 硬编码 "unknown" → 语言特定
- ❌ 之前: `package_name = "unknown"` (所有语言)
- ✅ 现在: Java用"unknown", JS/TS/Python用""

### 4. 死代码 → 清理
- ❌ 之前: 3个命令有未使用的 `_convert_to_formatter_format()`
- ✅ 现在: 删除所有死代码

---

## 核心组件

### 1. Formatter Configuration

**文件**: `formatters/formatter_config.py` (新增)

```python
LANGUAGE_FORMATTER_CONFIG = {
    "java": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
    },
    "sql": {
        "table": "new",
        "compact": "new",
        "full": "new",
    },
    # ... 其他语言
}
```

### 2. FormatterSelector Service

**文件**: `formatters/formatter_selector.py` (新增)

```python
class FormatterSelector:
    @staticmethod
    def get_formatter(language, format_type, **kwargs):
        """根据配置选择格式化器"""
        strategy = get_formatter_strategy(language, format_type)
        
        if strategy == "new":
            return create_language_formatter(language)
        else:
            return create_table_formatter(format_type, language, **kwargs)
```

### 3. Updated TableCommand

**文件**: `cli/commands/table_command.py` (修改)

```python
# 删除 46-63 行的 if formatter: else: 逻辑
# 替换为:
formatter = FormatterSelector.get_formatter(
    analysis_result.language,
    table_type,
    include_javadoc=getattr(self.args, "include_javadoc", False)
)
```

### 4. Fix Package Name Logic

**文件**: `cli/commands/table_command.py` (修改 132行)

```python
def _get_default_package_name(self, language: str) -> str:
    """语言特定的包名默认值"""
    if language in ["java", "kotlin", "scala"]:
        return "unknown"
    return ""  # JS/TS/Python 不需要包前缀
```

---

## 实施计划

### Phase 1: 分析 ✅ (已完成)
- [x] 识别问题根源
- [x] 分析影响范围
- [x] 设计解决方案

### Phase 2: FormatterSelector (~1.5小时)
- [ ] 创建 formatter_config.py
- [ ] 创建 formatter_selector.py  
- [ ] 编写单元测试

### Phase 3: 修复 table_command.py (~1小时)
- [ ] 替换隐式检查逻辑
- [ ] 修复包名硬编码
- [ ] 更新测试

### Phase 4: 清理其他命令 (~0.5小时)
- [ ] 删除 advanced_command.py 中的死代码
- [ ] 删除 structure_command.py 中的死代码
- [ ] 删除 summary_command.py 中的死代码

### Phase 5: 测试和验证 (~1小时)
- [ ] 单元测试
- [ ] 集成测试
- [ ] Golden master 测试
- [ ] 隔离测试(添加新语言不影响旧语言)

### Phase 6: 文档 (~1.5小时)
- [ ] 架构文档
- [ ] 迁移指南
- [ ] CHANGELOG

### Phase 7: 集成 (~1.5小时)
- [ ] 代码审查
- [ ] CI/CD 验证
- [ ] 合并到 develop

---

## 成功标准 ✅

- [ ] FormatterSelector 实现并测试通过
- [ ] table_command.py 使用显式选择
- [ ] 无 "unknown" 前缀(JS/TS/Python)
- [ ] 所有 Golden Master 测试通过
- [ ] 添加新语言不影响旧语言输出
- [ ] 死代码已删除
- [ ] 所有 3,370+ 测试通过
- [ ] CI/CD 在所有平台通过

---

## 与 fix-golden-master-regression 的关系

### fix-golden-master-regression
- **类型**: 症状修复
- **位置**: `table_formatter.py` 的标题生成逻辑
- **解决**: Golden Master 文件的标题格式错误

### fix-command-formatter-coupling (本提案)
- **类型**: 根本原因修复  
- **位置**: CLI 命令层的架构缺陷
- **解决**: 防止未来添加新语言时出现同样问题

### 建议

**两个都要做!**

1. **先做本提案** (fix-command-formatter-coupling)
   - 修复架构缺陷
   - 确保隔离性

2. **再做另一个** (fix-golden-master-regression)
   - 修正标题格式
   - 更新 Golden Master 文件

这样可以确保:
- ✅ 当前问题解决
- ✅ 未来不会再犯同样错误

---

## 优势 🎉

### 1. 完全隔离
```python
# 添加新语言
LANGUAGE_FORMATTER_CONFIG["newlang"] = {"table": "new"}
# Java/Python/JS/TS 配置不变 → 输出不变 ✅
```

### 2. 显式清晰
```python
# 一眼就能看出每种语言用什么
"java": {"table": "legacy"}   # 清楚!
"sql": {"table": "new"}        # 明确!
```

### 3. 易于测试
```python
def test_language_isolation():
    old_output = generate_output("java")
    add_new_language("rust")
    new_output = generate_output("java")
    assert old_output == new_output  # 通过!
```

### 4. 渐进迁移
```python
# 可以逐步迁移
"java": {
    "table": "new",      # 已迁移
    "compact": "legacy",  # 还没迁移
}
```

---

## 影响评估

### 优势
- ✅ 架构更清晰
- ✅ 隔离性更好
- ✅ 可测试性更强
- ✅ 可维护性更高
- ✅ 向后兼容

### 风险
- ⚠️ 需要更新多个文件
- ⚠️ 需要全面测试

### 缓解措施
- ✅ 渐进实施
- ✅ 充分测试
- ✅ 保持向后兼容

---

## 文件结构

```
fix-command-formatter-coupling/
├── README_zh.md           ← 你在这里
├── README.md              (英文版)
├── proposal.md            (详细提案)
├── tasks.md               (任务分解)
├── design.md              (设计文档)
└── specs/
    └── explicit-formatter-selection/
        └── spec.md        (需求规范)
```

---

## 快速开始

### 1. 理解问题
```bash
# 查看问题代码
cat tree_sitter_analyzer/cli/commands/table_command.py | grep -A 20 "create_language_formatter"
```

### 2. 查看设计
```bash
cat openspec/changes/fix-command-formatter-coupling/design.md
```

### 3. 开始实施
按照 `tasks.md` 中的阶段顺序执行

---

## 常见问题 ❓

### Q: 这个和 fix-golden-master-regression 有什么区别?
**A**: 那个修复症状(标题格式),这个修复根本原因(架构缺陷)

### Q: 为什么不直接修改 table_formatter.py?
**A**: 因为问题不在那里! 问题在命令层的隐式耦合

### Q: 会破坏现有功能吗?
**A**: 不会。设计完全向后兼容,有充分测试

### Q: 需要多长时间?
**A**: 约7小时完成所有阶段

### Q: 优先级有多高?
**A**: 极高! 这是架构层面的缺陷,必须修复

---

## 关键洞察 💡

### 问题本质

不是 `table_formatter.py` 的标题生成逻辑有问题,而是**命令层决定使用哪个格式化器的方式有问题**!

### 设计原则

```
隐式 "如果存在就用" → ❌ 脆弱,不可预测
显式 "配置说用就用" → ✅ 稳定,可预测
```

### 教训

添加新功能时,不应该影响现有功能。需要明确的隔离边界。

---

**最后更新**: 2025-11-08  
**变更负责人**: AI Agent / 开发团队  
**审查状态**: 待定

