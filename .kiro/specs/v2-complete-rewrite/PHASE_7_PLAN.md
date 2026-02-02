# Phase 7: 优化与完善 - 实施计划

**日期**: 2026-02-01
**目标**: 增强 v2 功能至 v1 水平，添加缺失的 MCP 工具

---

## 分析结果：v1 vs v2 差异

### Python 语言支持对比

**v1 有但 v2 缺失的功能**:
1. ✅ Decorators extraction (装饰器提取)
2. ✅ Class attributes extraction (类属性提取)
3. ✅ Async function detection (异步函数检测)
4. ✅ If `__name__ == "__main__"` block detection
5. ✅ Framework detection (Django, Flask, FastAPI)
6. ✅ Context manager detection
7. ✅ Complexity scoring (复杂度评分)
8. ✅ Enhanced docstring extraction

**v2 已有的功能**:
- ✅ Functions (name, parameters, return type, docstring)
- ✅ Classes (name, methods, base classes, docstring)
- ✅ Imports (module, names, aliases)
- ✅ Basic metadata

---

### Java 语言支持对比

**需要验证的功能**:
- Annotations (@Override, @Deprecated 等)
- Modifiers (public, private, static, etc.)
- Generic types
- Enum support
- Interface vs Class distinction

**v2 当前状态**: 基本功能已实现，需要测试覆盖率检查

---

### TypeScript 语言支持对比

**需要验证的功能**:
- Interfaces
- Type aliases
- Generics
- Decorators
- Enums
- Namespaces

**v2 当前状态**: 基本功能已实现，需要测试覆盖率检查

---

### MCP 工具对比

**v1 有的工具**:
1. analyze_code_structure ✅ (v2 已实现)
2. analyze_scale (check_code_scale) ❌ (v2 缺失)
3. find_and_grep ❌ (v2 缺失，只有分开的 find_files + search_content)
4. list_files ✅ (v2 有 find_files)
5. query_code ✅ (v2 已实现)
6. read_partial (extract_code_section) ❌ (v2 缺失)
7. search_content ✅ (v2 已实现)
8. universal_analyze ❓ (需要研究是否必要)

**v2 缺失的关键工具**:
1. **check_code_scale**: 代码规模和复杂度分析
   - 文件行数、字符数
   - 元素计数（classes, functions, etc.）
   - 复杂度指标

2. **find_and_grep**: 两阶段搜索
   - 先用 fd 找文件
   - 再用 ripgrep 搜索内容
   - 结果按文件分组

3. **extract_code_section**: 部分文件读取
   - 指定行范围读取
   - 性能优化（大文件）
   - 上下文行支持

---

## 实施优先级

### 优先级 1: 增强 Python 语言支持 (T7.1)

**目标**: 将 v2 的 Python parser 提升至 v1 水平

**任务**:
1. 添加装饰器提取 (decorators)
2. 添加类属性提取 (class attributes)
3. 添加异步函数检测 (async/await)
4. 添加 `if __name__ == "__main__"` 检测
5. 优化 docstring 提取

**预计时间**: 3-4 小时
**测试要求**: TDD 方式，先写测试，>=80% 覆盖率

---

### 优先级 2: 实现 check_code_scale 工具 (T7.2)

**目标**: 添加代码规模分析 MCP 工具

**功能**:
- 文件指标: 行数、字符数、大小
- 元素统计: classes, functions, imports 计数
- 复杂度评估: 嵌套层级、圈复杂度
- 多种输出格式: TOON, Markdown

**预计时间**: 2-3 小时
**依赖**: T7.1 完成后进行

---

### 优先级 3: 实现 find_and_grep 工具 (T7.3)

**目标**: 两阶段综合搜索工具

**功能**:
- Stage 1: fd 文件搜索
- Stage 2: ripgrep 内容搜索
- 结果按文件分组
- 支持结果限制

**预计时间**: 2 小时
**依赖**: 无

---

### 优先级 4: 实现 extract_code_section 工具 (T7.4)

**目标**: 部分文件读取工具

**功能**:
- 按行范围读取 (start_line, end_line)
- 上下文行支持 (context_lines)
- 大文件性能优化
- 语法高亮支持（可选）

**预计时间**: 1-2 小时
**依赖**: 无

---

### 优先级 5: 优化 Java 和 TypeScript (T7.5)

**目标**: 验证和增强现有功能

**任务**:
1. 检查测试覆盖率
2. 添加缺失的边缘情况测试
3. 验证与 v1 的功能对等性

**预计时间**: 2-3 小时
**依赖**: 无

---

## 实施顺序

```
Day 1 (6-8h):
  T7.1: Python 增强 (4h)
  T7.2: check_code_scale (3h)

Day 2 (4-6h):
  T7.3: find_and_grep (2h)
  T7.4: extract_code_section (2h)
  T7.5: Java/TS 优化 (2h)
```

---

## TDD 开发流程

每个任务遵循：
1. **RED**: 写失败的测试
2. **GREEN**: 实现最小功能使测试通过
3. **REFACTOR**: 重构优化代码质量

---

## 验收标准

- [ ] Python parser 支持装饰器、类属性、async
- [ ] check_code_scale 工具完整实现并测试
- [ ] find_and_grep 工具完整实现并测试
- [ ] extract_code_section 工具完整实现并测试
- [ ] 所有测试通过 (>=400 tests)
- [ ] 代码覆盖率 >= 85%
- [ ] 性能指标达标

---

**开始实施**: T7.1 - Python 语言增强
