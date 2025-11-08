# Design: Language-Specific Formatter Isolation

## 终极目标:完全解耦

每种语言拥有**完全独立**的格式化系统,互不影响。

---

## 当前问题:耦合层次分析

### Level 1: 命令层耦合 (当前提案已解决)
```python
# 问题:命令层决定用哪个格式化器
if create_language_formatter(lang):
    use_new()
else:
    use_old()
```
✅ **解决方案**: FormatterSelector + 显式配置

### Level 2: 数据转换耦合 (更深层问题)
```python
# table_command.py
def _convert_to_structure_format(self, analysis_result, language):
    # 所有语言共用同一个转换逻辑!
    package_name = "unknown"  # ← 对 JS/TS 不适用
    classes = []
    methods = []
    # 统一的数据结构
```
**问题**: 不同语言被强制转换为同一种数据结构

### Level 3: 格式化器接口耦合
```python
# 所有格式化器必须实现相同接口
class BaseFormatter:
    def format_structure(self, data: dict) -> str:
        pass
```
**问题**: 不同语言的需求可能完全不同

---

## 终极解决方案:语言隔离架构

### 核心原则

```
每种语言 = 独立的黑盒
输入: AnalysisResult (统一)
输出: Formatted String (统一)
内部: 完全自由,互不影响
```

---

## 新架构设计

### 1. 语言处理器接口 (Language Processor)

```python
# formatters/language_processor.py (新增)

from abc import ABC, abstractmethod
from typing import Any

class LanguageProcessor(ABC):
    """
    语言处理器基类 - 每种语言的独立黑盒
    
    输入: AnalysisResult (统一接口)
    输出: 格式化字符串 (统一接口)
    内部: 完全自由实现
    """
    
    def __init__(self, format_type: str, **options: Any):
        """
        初始化处理器
        
        Args:
            format_type: 输出格式类型 (full, compact, csv, json)
            **options: 语言特定的选项
        """
        self.format_type = format_type
        self.options = options
    
    @abstractmethod
    def process(self, analysis_result: 'AnalysisResult') -> str:
        """
        处理分析结果并返回格式化字符串
        
        Args:
            analysis_result: 语言分析器的原始输出
            
        Returns:
            格式化后的字符串
        """
        pass
    
    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """
        返回支持的格式类型
        
        Returns:
            支持的格式列表,如 ["full", "compact", "csv"]
        """
        pass
    
    def validate_format(self, format_type: str) -> bool:
        """
        验证是否支持指定格式
        
        Args:
            format_type: 格式类型
            
        Returns:
            是否支持
        """
        return format_type in self.get_supported_formats()
```

---

### 2. Java 处理器 (完全独立)

```python
# formatters/java_processor.py (新增)

class JavaProcessor(LanguageProcessor):
    """Java 语言处理器 - 完全独立实现"""
    
    def get_supported_formats(self) -> list[str]:
        return ["full", "compact", "csv", "json"]
    
    def process(self, analysis_result: 'AnalysisResult') -> str:
        """
        Java 特定的处理逻辑
        """
        # 1. 提取 Java 特定信息
        java_data = self._extract_java_data(analysis_result)
        
        # 2. 使用 Java 特定格式化器
        if self.format_type == "full":
            return self._format_full(java_data)
        elif self.format_type == "compact":
            return self._format_compact(java_data)
        # ...
    
    def _extract_java_data(self, result: 'AnalysisResult') -> dict:
        """
        Java 特定的数据提取
        
        - 包名处理: 有包概念,默认 "unknown"
        - 类型系统: interface, class, enum, annotation
        - 可见性: public, private, protected, package
        """
        package_name = "unknown"  # Java 需要包
        
        for element in result.elements:
            if element.type == "package":
                package_name = element.name
                break
        
        return {
            "package": package_name,
            "classes": self._extract_classes(result),
            "methods": self._extract_methods(result),
            # Java 特定字段
        }
    
    def _format_full(self, data: dict) -> str:
        """Java Full 格式"""
        lines = []
        
        # Java 标题格式: package.ClassName
        if len(data["classes"]) == 1:
            title = f"{data['package']}.{data['classes'][0]['name']}"
        else:
            title = data.get("filename", "Unknown")
        
        lines.append(f"# {title}")
        # ... Java 特定格式化
        
        return "\n".join(lines)
```

---

### 3. JavaScript/TypeScript 处理器 (完全独立)

```python
# formatters/javascript_processor.py (新增)

class JavaScriptProcessor(LanguageProcessor):
    """JavaScript/TypeScript 处理器 - 完全独立实现"""
    
    def get_supported_formats(self) -> list[str]:
        return ["full", "compact", "csv", "json"]
    
    def process(self, analysis_result: 'AnalysisResult') -> str:
        """JavaScript 特定的处理逻辑"""
        js_data = self._extract_js_data(analysis_result)
        
        if self.format_type == "full":
            return self._format_full(js_data)
        # ...
    
    def _extract_js_data(self, result: 'AnalysisResult') -> dict:
        """
        JavaScript 特定的数据提取
        
        - 包名处理: 无包概念,不使用 package
        - 类型系统: class, function, const
        - 可见性: export, default, private (#)
        """
        # JavaScript 不需要 package!
        return {
            "module": result.file_path,  # 使用模块路径
            "classes": self._extract_classes(result),
            "functions": self._extract_functions(result),
            "exports": self._extract_exports(result),
            # JavaScript 特定字段
        }
    
    def _format_full(self, data: dict) -> str:
        """JavaScript Full 格式"""
        lines = []
        
        # JavaScript 标题格式: ClassName (无包前缀!)
        if data["classes"]:
            title = data["classes"][0]["name"]
        else:
            title = data.get("filename", "Unknown")
        
        lines.append(f"# {title}")
        # ... JavaScript 特定格式化 (完全不同于 Java!)
        
        return "\n".join(lines)
```

---

### 4. Python 处理器 (完全独立)

```python
# formatters/python_processor.py (新增)

class PythonProcessor(LanguageProcessor):
    """Python 处理器 - 完全独立实现"""
    
    def get_supported_formats(self) -> list[str]:
        return ["full", "compact", "csv", "json"]
    
    def process(self, analysis_result: 'AnalysisResult') -> str:
        """Python 特定的处理逻辑"""
        python_data = self._extract_python_data(analysis_result)
        
        if self.format_type == "full":
            return self._format_full(python_data)
        # ...
    
    def _extract_python_data(self, result: 'AnalysisResult') -> dict:
        """
        Python 特定的数据提取
        
        - 包名处理: 使用模块概念,不是 package
        - 类型系统: class, def, async def
        - 可见性: _ (private), __ (name mangling)
        """
        module_name = result.file_path.stem  # 文件名即模块名
        
        return {
            "module": module_name,  # Python 用 module
            "classes": self._extract_classes(result),
            "functions": self._extract_functions(result),
            "decorators": self._extract_decorators(result),
            # Python 特定字段
        }
    
    def _format_full(self, data: dict) -> str:
        """Python Full 格式"""
        lines = []
        
        # Python 标题格式: Module: filename
        title = f"Module: {data['module']}"
        
        lines.append(f"# {title}")
        # ... Python 特定格式化 (包括 type hints, docstrings 等)
        
        return "\n".join(lines)
```

---

### 5. SQL 处理器 (完全独立)

```python
# formatters/sql_processor.py (新增)

class SQLProcessor(LanguageProcessor):
    """SQL 处理器 - 完全独立实现"""
    
    def get_supported_formats(self) -> list[str]:
        return ["full", "compact", "csv"]
    
    def process(self, analysis_result: 'AnalysisResult') -> str:
        """SQL 特定的处理逻辑"""
        sql_data = self._extract_sql_data(analysis_result)
        
        if self.format_type == "full":
            return self._format_full(sql_data)
        # ...
    
    def _extract_sql_data(self, result: 'AnalysisResult') -> dict:
        """
        SQL 特定的数据提取
        
        - 数据库对象: TABLE, VIEW, PROCEDURE, FUNCTION, TRIGGER
        - 关系: dependencies, foreign keys
        - 列信息: 数据类型, constraints
        """
        return {
            "database": self._get_database_name(result),
            "tables": self._extract_tables(result),
            "views": self._extract_views(result),
            "procedures": self._extract_procedures(result),
            "functions": self._extract_functions(result),
            # SQL 特定字段
        }
    
    def _format_full(self, data: dict) -> str:
        """SQL Full 格式 - 完全不同的结构!"""
        lines = []
        
        # SQL 标题格式: Database: name
        title = f"Database: {data['database']}"
        lines.append(f"# {title}")
        
        # SQL 特定章节
        if data["tables"]:
            lines.append("\n## Tables")
            for table in data["tables"]:
                lines.append(f"### {table['name']}")
                # 显示列信息
                lines.append("| Column | Type | Nullable | Default |")
                # ...
        
        # 与 Java/Python 完全不同的结构!
        
        return "\n".join(lines)
```

---

### 6. 处理器注册中心

```python
# formatters/processor_registry.py (新增)

from typing import Type, Optional

class ProcessorRegistry:
    """
    语言处理器注册中心
    
    完全解耦的语言注册系统
    """
    
    _processors: dict[str, Type[LanguageProcessor]] = {}
    
    @classmethod
    def register(cls, language: str, processor_class: Type[LanguageProcessor]) -> None:
        """
        注册语言处理器
        
        Args:
            language: 语言名称
            processor_class: 处理器类
        """
        cls._processors[language.lower()] = processor_class
    
    @classmethod
    def get_processor(
        cls,
        language: str,
        format_type: str,
        **options: Any
    ) -> Optional[LanguageProcessor]:
        """
        获取语言处理器实例
        
        Args:
            language: 语言名称
            format_type: 格式类型
            **options: 选项
            
        Returns:
            处理器实例,如果语言不支持则返回 None
        """
        processor_class = cls._processors.get(language.lower())
        if processor_class is None:
            return None
        
        processor = processor_class(format_type, **options)
        
        # 验证格式支持
        if not processor.validate_format(format_type):
            raise ValueError(
                f"{language} processor does not support format type: {format_type}"
            )
        
        return processor
    
    @classmethod
    def is_supported(cls, language: str) -> bool:
        """检查语言是否支持"""
        return language.lower() in cls._processors
    
    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """获取支持的语言列表"""
        return list(cls._processors.keys())


# 自动注册所有语言
def _register_builtin_processors():
    """注册内置处理器"""
    ProcessorRegistry.register("java", JavaProcessor)
    ProcessorRegistry.register("javascript", JavaScriptProcessor)
    ProcessorRegistry.register("js", JavaScriptProcessor)  # 别名
    ProcessorRegistry.register("typescript", TypeScriptProcessor)
    ProcessorRegistry.register("ts", TypeScriptProcessor)
    ProcessorRegistry.register("python", PythonProcessor)
    ProcessorRegistry.register("py", PythonProcessor)
    ProcessorRegistry.register("sql", SQLProcessor)
    # ... 更多语言

_register_builtin_processors()
```

---

### 7. 简化的 TableCommand

```python
# cli/commands/table_command.py (大幅简化!)

from ...formatters.processor_registry import ProcessorRegistry

class TableCommand(BaseCommand):
    async def execute_async(self, language: str) -> int:
        # 1. 分析文件
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1
        
        # 2. 获取语言处理器
        table_type = getattr(self.args, "table", "full")
        processor = ProcessorRegistry.get_processor(
            language=analysis_result.language,
            format_type=table_type,
            include_javadoc=getattr(self.args, "include_javadoc", False)
        )
        
        if processor is None:
            output_error(f"Unsupported language: {analysis_result.language}")
            return 1
        
        # 3. 处理并输出 (完全语言独立!)
        formatted_output = processor.process(analysis_result)
        self._output_table(formatted_output)
        
        return 0
    
    # 不再需要 _convert_to_structure_format()!
    # 不再需要 _convert_class_element()!
    # 不再需要判断用哪个格式化器!
    # 所有逻辑都在各自的 Processor 中!
```

---

## 架构对比

### 之前:耦合架构

```
┌─────────────────────────────────────┐
│       TableCommand                   │
│  ┌─────────────────────────────┐   │
│  │ _convert_to_structure       │   │
│  │ - package = "unknown"       │   │
│  │ - classes = []              │   │
│  │ - methods = []              │   │
│  │ (所有语言共用!)              │   │
│  └──────────┬──────────────────┘   │
└─────────────┼────────────────────────┘
              │
              ↓
      ┌───────┴────────┐
      │                │
  Java格式化器    Python格式化器
  (被迫接受统一结构)
```

**问题**:
- ❌ 统一的数据结构
- ❌ 硬编码的 "unknown"
- ❌ 命令层包含语言特定逻辑

---

### 现在:完全解耦架构

```
                ┌────────────────┐
                │ TableCommand   │
                │  (非常简单!)   │
                └────────┬───────┘
                         │
                         ↓
                ProcessorRegistry
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   JavaProcessor   JSProcessor    PythonProcessor
        │                │                │
   [独立黑盒]       [独立黑盒]      [独立黑盒]
        │                │                │
   输入: AnalysisResult (统一)
   输出: String (统一)
   内部: 完全自由!
```

**优势**:
- ✅ 每种语言完全独立
- ✅ 添加新语言零影响
- ✅ 命令层极简
- ✅ 易于测试和维护

---

## 完全隔离的保证

### 1. 数据结构隔离

```python
# Java
java_data = {
    "package": "com.example",  # Java 特有
    "interfaces": [...],       # Java 特有
}

# JavaScript
js_data = {
    "module": "./utils",       # JS 特有
    "exports": [...],          # JS 特有
}

# Python
python_data = {
    "module": "utils",         # Python 特有
    "decorators": [...],       # Python 特有
}

# 完全不同的数据结构!
```

### 2. 格式化逻辑隔离

```python
# Java: package.ClassName
title = f"{package}.{class_name}"

# JavaScript: ClassName (无包!)
title = f"{class_name}"

# Python: Module: name
title = f"Module: {module_name}"

# SQL: Database: name
title = f"Database: {database_name}"

# 每种语言完全不同!
```

### 3. 测试隔离

```python
# 测试 Java 处理器
def test_java_processor():
    processor = JavaProcessor("full")
    result = processor.process(java_analysis_result)
    assert "com.example.Class" in result

# 测试 JavaScript 处理器  
def test_js_processor():
    processor = JavaScriptProcessor("full")
    result = processor.process(js_analysis_result)
    assert "unknown" not in result  # 绝对不会有 "unknown"!

# 完全独立的测试!
```

---

## 添加新语言:零影响

```python
# 1. 创建处理器
class RustProcessor(LanguageProcessor):
    def process(self, analysis_result):
        # Rust 特定逻辑
        return rust_formatted_output

# 2. 注册
ProcessorRegistry.register("rust", RustProcessor)

# 完成!
# Java/Python/JS/TS 完全不受影响!
```

---

## 迁移路径

### Phase 1: 创建新架构 (不破坏现有)
- [ ] 创建 `LanguageProcessor` 基类
- [ ] 创建 `ProcessorRegistry`
- [ ] 添加测试

### Phase 2: 逐个语言迁移
- [ ] 创建 `JavaProcessor`
- [ ] 注册并测试
- [ ] 创建 `JavaScriptProcessor`
- [ ] 注册并测试
- [ ] ...逐个迁移

### Phase 3: 更新命令层
- [ ] TableCommand 使用 ProcessorRegistry
- [ ] 删除旧的转换逻辑
- [ ] 测试所有语言

### Phase 4: 清理
- [ ] 删除旧的格式化器系统 (可选)
- [ ] 统一测试
- [ ] 文档更新

---

## 总结

### 完全解耦的三个层次

1. **命令层解耦**: FormatterSelector (当前提案)
2. **数据转换解耦**: 每种语言自己的 `_extract_data()`
3. **格式化逻辑解耦**: 每种语言自己的 `_format_xxx()`

### 最终效果

```python
# 添加任何新语言
ProcessorRegistry.register("newlang", NewLangProcessor)

# 对现有语言:零影响!
# Java 输出: 不变
# Python 输出: 不变
# JavaScript 输出: 不变
# ...
```

---

**这才是真正的语言隔离!** 🎉

