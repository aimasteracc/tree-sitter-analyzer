# Task A: 实现 --summary 快速模式

**痛点**: #4
**优先级**: 🔥 High
**预计时间**: 2h
**开始时间**: 2026-02-03

---

## 📋 需求

### 当前问题
用户想快速查看文件概览时，只有详细输出（--format markdown/toon），信息过载。

### 期望行为
```bash
uv run tsa analyze symbols.py --summary
```

**期望输出**:
```
File: symbols.py
Language: python
Lines: 357 (Code: 280, Comments: 50, Blank: 27)
Classes: 3 (SymbolEntry, SymbolTable, SymbolTableBuilder)
Functions: 0
Methods: 6 (across all classes)
Imports: 2
Complexity: Low (avg 2.5)
```

---

## 🎯 验收标准

- [ ] CLI 支持 `--summary` 参数
- [ ] 输出包含：文件名、语言、行数统计、类/函数/方法数、导入数、复杂度
- [ ] 输出简洁（< 10 行）
- [ ] 性能优于完整分析（> 2x faster，因为不需要格式化）
- [ ] 测试覆盖率 > 80%
- [ ] 所有现有测试继续通过

---

## 🔨 实施计划

### Step 1: TDD Red - 写失败的测试 (15min)
创建 `tests/integration/test_summary_mode.py`:
```python
def test_cli_summary_flag_exists():
    """Test that --summary flag is recognized."""

def test_summary_output_format():
    """Test summary output contains all required fields."""

def test_summary_is_faster_than_full():
    """Test summary mode is faster than full analysis."""
```

### Step 2: 设计 Summary Formatter (15min)
创建 `formatters/summary_formatter.py`:
```python
class SummaryFormatter(Formatter):
    def format(self, result: AnalysisResult) -> str:
        """Format as concise summary."""
```

### Step 3: 实现 CLI 参数 (15min)
修改 `cli/main.py`:
```python
parser.add_argument("--summary", action="store_true",
                   help="Show concise summary (faster)")
```

### Step 4: TDD Green - 实现功能 (45min)
- 实现 SummaryFormatter
- 注册到 FormatterRegistry
- CLI 集成
- 运行测试验证

### Step 5: 文档和提交 (30min)
- 更新 README
- 更新 PAINPOINTS_TRACKER
- Git commit

---

## 📊 技术设计

### Summary Formatter 输出格式
```python
def format(self, result: AnalysisResult) -> str:
    lines = [
        f"File: {result.file_path}",
        f"Language: {result.language}",
        f"Lines: {total} (Code: {code}, Comments: {comments}, Blank: {blank})",
        f"Classes: {len(classes)} ({class_names})",
        f"Functions: {len(functions)}",
        f"Methods: {total_methods} (across all classes)",
        f"Imports: {len(imports)}",
        f"Complexity: {complexity_level} (avg {avg})"
    ]
    return "\n".join(lines)
```

### 复杂度计算
```python
def calculate_complexity_level(avg_complexity: float) -> str:
    if avg_complexity < 3: return "Low"
    if avg_complexity < 7: return "Medium"
    return "High"
```

---

## 🧪 测试策略

### 单元测试
- `test_summary_formatter.py`: 测试 formatter 逻辑
- Mock AnalysisResult，验证输出格式

### 集成测试
- `test_summary_mode.py`: 端到端测试
- 实际文件分析，验证输出内容
- 性能对比测试

### 回归测试
- 确保所有现有测试继续通过
- 验证 --format 参数不受影响

---

## ⚠️ 边界情况

1. **空文件**: 显示 0 classes, 0 functions
2. **无类文件**: 只有函数，classes 显示为 0
3. **大文件**: 类名列表过长时截断 (显示前 3 个 + "...")
4. **无复杂度数据**: 显示 "N/A"

---

## 📝 进度追踪

- [ ] Step 1: 写测试 (15min)
- [ ] Step 2: 设计 Formatter (15min)
- [ ] Step 3: CLI 参数 (15min)
- [ ] Step 4: 实现功能 (45min)
- [ ] Step 5: 文档提交 (30min)

**总计**: 2h
