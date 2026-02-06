"""
Scenario 8: Multi-Language Support
TypeScript + Rust解析器 (基础支持)

Note: 完整实现需要tree-sitter bindings,这里提供简化版本
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional


class Language(Enum):
    """支持的语言"""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    JAVA = "java"


@dataclass
class CodeElement:
    """代码元素 (通用)"""
    name: str
    type: str  # function / class / interface / struct / trait
    language: Language
    file: str
    line_number: int


class TypeScriptParser:
    """TypeScript解析器 (简化版)"""
    
    def parse(self, content: str, file_path: str) -> List[CodeElement]:
        """解析TypeScript代码"""
        elements = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 简单的正则匹配
            import re
            
            # 函数: function name() 或 const name = () =>
            func_match = re.search(r'(?:function|const|let|var)\s+(\w+)\s*[=\(]', line)
            if func_match:
                elements.append(CodeElement(
                    name=func_match.group(1),
                    type="function",
                    language=Language.TYPESCRIPT,
                    file=file_path,
                    line_number=i
                ))
            
            # 类: class Name
            class_match = re.search(r'class\s+(\w+)', line)
            if class_match:
                elements.append(CodeElement(
                    name=class_match.group(1),
                    type="class",
                    language=Language.TYPESCRIPT,
                    file=file_path,
                    line_number=i
                ))
            
            # 接口: interface Name
            interface_match = re.search(r'interface\s+(\w+)', line)
            if interface_match:
                elements.append(CodeElement(
                    name=interface_match.group(1),
                    type="interface",
                    language=Language.TYPESCRIPT,
                    file=file_path,
                    line_number=i
                ))
        
        return elements


class RustParser:
    """Rust解析器 (简化版)"""
    
    def parse(self, content: str, file_path: str) -> List[CodeElement]:
        """解析Rust代码"""
        elements = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            import re
            
            # 函数: fn name()
            func_match = re.search(r'fn\s+(\w+)\s*[<\(]', line)
            if func_match:
                elements.append(CodeElement(
                    name=func_match.group(1),
                    type="function",
                    language=Language.RUST,
                    file=file_path,
                    line_number=i
                ))
            
            # 结构体: struct Name
            struct_match = re.search(r'struct\s+(\w+)', line)
            if struct_match:
                elements.append(CodeElement(
                    name=struct_match.group(1),
                    type="struct",
                    language=Language.RUST,
                    file=file_path,
                    line_number=i
                ))
            
            # Trait: trait Name
            trait_match = re.search(r'trait\s+(\w+)', line)
            if trait_match:
                elements.append(CodeElement(
                    name=trait_match.group(1),
                    type="trait",
                    language=Language.RUST,
                    file=file_path,
                    line_number=i
                ))
            
            # 实现: impl Name
            impl_match = re.search(r'impl\s+(\w+)', line)
            if impl_match:
                elements.append(CodeElement(
                    name=impl_match.group(1),
                    type="impl",
                    language=Language.RUST,
                    file=file_path,
                    line_number=i
                ))
        
        return elements


class MultiLanguageAnalyzer:
    """
    多语言分析器
    
    支持:
    - Python (使用ast模块)
    - TypeScript (简化版正则)
    - Rust (简化版正则)
    - Java (已有实现)
    """
    
    def __init__(self):
        self.typescript_parser = TypeScriptParser()
        self.rust_parser = RustParser()
    
    def detect_language(self, file_path: Path) -> Optional[Language]:
        """检测文件语言"""
        suffix = file_path.suffix.lower()
        
        if suffix == '.py':
            return Language.PYTHON
        elif suffix in ['.ts', '.tsx']:
            return Language.TYPESCRIPT
        elif suffix == '.rs':
            return Language.RUST
        elif suffix == '.java':
            return Language.JAVA
        else:
            return None
    
    def analyze_file(self, file_path: Path) -> List[CodeElement]:
        """分析文件"""
        language = self.detect_language(file_path)
        
        if not language:
            return []
        
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return []
        
        if language == Language.TYPESCRIPT:
            return self.typescript_parser.parse(content, str(file_path))
        elif language == Language.RUST:
            return self.rust_parser.parse(content, str(file_path))
        elif language == Language.PYTHON:
            return self._parse_python(content, file_path)
        else:
            return []
    
    def _parse_python(self, content: str, file_path: Path) -> List[CodeElement]:
        """解析Python代码"""
        import ast
        
        elements = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    elements.append(CodeElement(
                        name=node.name,
                        type="function",
                        language=Language.PYTHON,
                        file=str(file_path),
                        line_number=node.lineno
                    ))
                elif isinstance(node, ast.ClassDef):
                    elements.append(CodeElement(
                        name=node.name,
                        type="class",
                        language=Language.PYTHON,
                        file=str(file_path),
                        line_number=node.lineno
                    ))
        except Exception:
            pass
        
        return elements
    
    def analyze_directory(
        self,
        directory: Path,
        languages: Optional[List[Language]] = None
    ) -> dict:
        """分析整个目录"""
        if languages is None:
            languages = [Language.PYTHON, Language.TYPESCRIPT, Language.RUST]
        
        # 文件扩展名映射
        ext_map = {
            Language.PYTHON: ['*.py'],
            Language.TYPESCRIPT: ['*.ts', '*.tsx'],
            Language.RUST: ['*.rs'],
        }
        
        all_elements = []
        
        for language in languages:
            patterns = ext_map.get(language, [])
            for pattern in patterns:
                for file_path in directory.glob(f"**/{pattern}"):
                    if file_path.is_file():
                        elements = self.analyze_file(file_path)
                        all_elements.extend(elements)
        
        # 按语言分组
        by_language = {}
        for elem in all_elements:
            lang = elem.language.value
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(elem)
        
        return {
            "total_elements": len(all_elements),
            "by_language": {
                lang: len(elems) for lang, elems in by_language.items()
            },
            "elements": [
                {
                    "name": e.name,
                    "type": e.type,
                    "language": e.language.value,
                    "file": e.file,
                    "line": e.line_number
                }
                for e in all_elements
            ]
        }


def analyze_multilang(project_root: Path) -> dict:
    """
    分析多语言项目
    
    Args:
        project_root: 项目根目录
    
    Returns:
        分析结果
    """
    analyzer = MultiLanguageAnalyzer()
    return analyzer.analyze_directory(project_root)
