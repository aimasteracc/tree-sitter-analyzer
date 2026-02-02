# 编码检测与大文件优化 - 分析文档

**日期**: 2026-02-01
**任务**: 补充 v2 缺失的编码检测和大文件优化功能
**优先级**: HIGH（影响生产环境使用）

---

## 现状分析

### v1 已实现的功能

#### 1. 编码检测 (`encoding_utils.py`, 598 lines)

**核心功能**:
- ✅ 自动编码检测 (使用 chardet 库)
- ✅ 支持多种编码：
  - UTF-8, UTF-8-sig
  - UTF-16-LE, UTF-16-BE
  - CP1252, ISO-8859-1
  - **Shift_JIS (日语)**
  - **GBK (中文)**
- ✅ BOM (Byte Order Mark) 检测
- ✅ 编码缓存机制 (性能优化)
  - 线程安全的缓存
  - TTL: 3600 秒
  - 最大条目: 1000
- ✅ 快速 UTF-8 检测（优先尝试）
- ✅ 只分析前 32KB 样本（性能优化）

**编码检测流程**:
```python
1. 检查缓存 (文件路径 → 编码)
2. 尝试 UTF-8 解码（最快）
3. 检查 BOM 标记
4. 使用 chardet 分析前 32KB
5. 缓存结果
```

**关键类**:
- `EncodingManager`: 中央编码管理器
  - `detect_encoding()`: 检测编码
  - `safe_decode()`: 安全解码
  - `safe_encode()`: 安全编码
  - `read_file_safe()`: 安全读取文件
  
- `EncodingCache`: 线程安全缓存
  - LRU 驱逐策略
  - TTL 过期机制

#### 2. 大文件流式读取

**核心功能**:
- ✅ 流式读取（不加载整个文件到内存）
- ✅ 只读取 8KB 样本进行编码检测
- ✅ 行级迭代（按行处理）
- ✅ **性能优化**: 150x 加速（30s → <200ms）

**关键函数**:
```python
def read_file_safe_streaming(file_path: str | Path):
    """流式读取大文件，内存友好"""
    # 1. 读取 8KB 样本检测编码
    with open(file_path, "rb") as f:
        sample_data = f.read(8192)
    
    detected_encoding = detect_encoding(sample_data, str(file_path))
    
    # 2. 用检测到的编码打开文件（流式）
    with open(file_path, encoding=detected_encoding, errors="replace") as f:
        yield f  # 可以逐行读取
```

**使用场景**:
```python
# 大文件部分读取（extract_code_section）
with read_file_safe_streaming("huge_file.py") as f:
    for line_num, line in enumerate(f, 1):
        if start_line <= line_num <= end_line:
            process(line)  # 只处理需要的行
```

### v2 当前实现

#### 现有问题：

1. **无编码检测**:
   - ❌ 硬编码使用 `encoding='utf-8'`
   - ❌ 遇到非 UTF-8 文件会报错或乱码
   - ❌ 无法处理日语文件 (Shift_JIS, EUC-JP)
   - ❌ 无法处理中文文件 (GBK, GB2312)

2. **无大文件优化**:
   - ❌ 完整读取文件到内存 (`read_text()`)
   - ❌ 500MB+ 文件会占用大量内存
   - ❌ 可能导致 OOM (Out of Memory)

3. **无缓存机制**:
   - ❌ 每次都重新检测编码（浪费性能）

**影响的模块**:
```python
# find_and_grep.py (line 160)
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()  # 完整读取！
    
# scale.py (line 283)
content = file_path.read_text(encoding="utf-8")  # 硬编码！

# analyze.py (line 112)
content = file_path_obj.read_text(encoding="utf-8")  # 硬编码！
```

---

## 功能需求

### 必需功能 (MUST HAVE)

1. **编码自动检测**:
   - 支持 chardet 库（可选依赖）
   - 快速 UTF-8 检测
   - BOM 检测
   - 常见编码回退列表
   - 缓存机制

2. **大文件流式读取**:
   - 流式读取 API
   - 只读取样本检测编码
   - 行级迭代支持

3. **向后兼容**:
   - 如果 chardet 未安装，回退到 UTF-8 + errors='replace'
   - 不破坏现有 API

### 可选功能 (NICE TO HAVE)

1. 异步文件读取 (anyio)
2. 更多编码支持
3. 编码检测置信度报告

---

## 设计方案

### 1. 模块结构

```
tree_sitter_analyzer_v2/
├── utils/
│   ├── __init__.py
│   └── encoding.py          # 新增：编码检测与流式读取
├── mcp/tools/
│   ├── find_and_grep.py     # 修改：使用编码检测
│   ├── scale.py             # 修改：使用编码检测
│   └── analyze.py           # 修改：使用编码检测
```

### 2. API 设计

#### EncodingDetector 类

```python
class EncodingDetector:
    """编码检测器（简化版，基于 v1）"""
    
    DEFAULT_ENCODING = "utf-8"
    FALLBACK_ENCODINGS = [
        "utf-8", 
        "cp1252",      # Windows
        "iso-8859-1",  # Latin-1
        "shift_jis",   # 日语
        "gbk",         # 中文
        "euc-jp",      # 日语
    ]
    
    @classmethod
    def detect_encoding(cls, data: bytes, file_path: str | None = None) -> str:
        """检测编码（带缓存）"""
        
    @classmethod
    def read_file_safe(cls, file_path: Path) -> tuple[str, str]:
        """安全读取文件，返回 (content, encoding)"""
        
    @classmethod
    def read_file_streaming(cls, file_path: Path):
        """流式读取文件（上下文管理器）"""
```

#### 编码缓存

```python
class EncodingCache:
    """简单的 LRU 缓存"""
    
    def __init__(self, max_size: int = 500):
        self._cache: dict[str, str] = {}  # path -> encoding
        self._max_size = max_size
    
    def get(self, file_path: str) -> str | None:
        """获取缓存的编码"""
        
    def set(self, file_path: str, encoding: str):
        """缓存编码"""
```

### 3. 检测流程

```
文件路径 → 检查缓存
         ↓ (miss)
         读取 8KB 样本
         ↓
         尝试 UTF-8 解码
         ↓ (失败)
         检查 BOM
         ↓ (无 BOM)
         使用 chardet (如果可用)
         ↓
         回退到 UTF-8 + errors='replace'
         ↓
         缓存结果
```

### 4. 依赖管理

```toml
[project.optional-dependencies]
encoding = ["chardet>=5.0.0"]
```

**策略**:
- chardet 作为可选依赖
- 如果未安装，使用简单回退策略

---

## 实施计划

### Phase 1: 创建编码检测模块 (TDD)

**测试** (`tests/unit/test_encoding.py`):
```python
def test_detect_utf8()
def test_detect_shift_jis()  # 日语
def test_detect_gbk()         # 中文
def test_detect_bom()
def test_encoding_cache()
def test_fallback_without_chardet()
def test_streaming_large_file()
```

**实现** (`tree_sitter_analyzer_v2/utils/encoding.py`):
- `EncodingDetector` 类
- `EncodingCache` 类
- 流式读取函数

### Phase 2: 集成到现有工具 (TDD)

**修改**:
1. `find_and_grep.py`:
   - 替换 `open(..., encoding='utf-8')` → `read_file_safe()`
   
2. `scale.py`:
   - 替换 `read_text(encoding="utf-8")` → `read_file_safe()`
   
3. `analyze.py`:
   - 替换 `read_text(encoding="utf-8")` → `read_file_safe()`

**测试**:
- 使用 Shift_JIS 编码的日语文件
- 使用 GBK 编码的中文文件
- 大文件 (100MB+) 性能测试

### Phase 3: 文档与示例

**文档**:
- 编码检测原理
- 大文件优化说明
- 可选依赖安装指南

---

## 性能目标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| UTF-8 检测速度 | < 1ms | 无 chardet 开销 |
| 缓存命中率 | > 90% | 重复访问文件 |
| 大文件内存占用 | O(1) | 流式读取，不加载全文件 |
| 100MB 文件处理 | < 500ms | 部分读取场景 |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| chardet 性能慢 | 检测延迟 | 只分析前 32KB + 缓存 |
| 编码误检测 | 乱码 | errors='replace' 回退 |
| 缓存过大 | 内存占用 | LRU 驱逐 + 最大 500 条目 |
| chardet 未安装 | 功能降级 | 使用回退策略，不报错 |

---

## 下一步

1. ✅ 分析完成
2. ⏳ 设计评审
3. ⏳ TDD 实施 (Phase 1)
4. ⏳ 集成 (Phase 2)
5. ⏳ 测试验证 (Phase 3)

---

**结论**:

v2 **严重缺失**编码检测和大文件优化功能，这在生产环境中会导致：
1. **无法处理非 UTF-8 文件**（日语、中文等）
2. **大文件内存溢出**（500MB+ 文件）
3. **性能问题**（无缓存，重复检测）

**必须立即补充这些功能！**
