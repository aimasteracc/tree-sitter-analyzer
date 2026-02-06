"""
Scenario 6: Auto Documentation Generator  
Docstring提取 + Markdown生成
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class FunctionDoc:
    """函数文档"""
    name: str
    docstring: Optional[str]
    parameters: List[str] = field(default_factory=list)
    returns: Optional[str] = None
    line_number: int = 0


@dataclass
class ClassDoc:
    """类文档"""
    name: str
    docstring: Optional[str]
    methods: List[FunctionDoc] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ModuleDoc:
    """模块文档"""
    name: str
    file_path: str
    docstring: Optional[str]
    classes: List[ClassDoc] = field(default_factory=list)
    functions: List[FunctionDoc] = field(default_factory=list)


class DocumentationGenerator:
    """
    文档生成器
    
    功能:
    - 提取docstring
    - 生成Markdown文档
    - 支持交叉引用
    """
    
    def extract_from_file(self, file_path: Path) -> ModuleDoc:
        """从文件提取文档"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(content, filename=str(file_path))
        except Exception:
            return ModuleDoc(
                name=file_path.stem,
                file_path=str(file_path),
                docstring=None
            )
        
        module_doc = ModuleDoc(
            name=file_path.stem,
            file_path=str(file_path),
            docstring=ast.get_docstring(tree)
        )
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_doc = ClassDoc(
                    name=node.name,
                    docstring=ast.get_docstring(node),
                    line_number=node.lineno
                )
                
                # 提取方法
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_doc = self._extract_function(item)
                        class_doc.methods.append(method_doc)
                
                module_doc.classes.append(class_doc)
            
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 只提取模块级函数
                if self._is_module_level(tree, node):
                    func_doc = self._extract_function(node)
                    module_doc.functions.append(func_doc)
        
        return module_doc
    
    def _extract_function(self, node: ast.FunctionDef) -> FunctionDoc:
        """提取函数文档"""
        params = [arg.arg for arg in node.args.args]
        
        return FunctionDoc(
            name=node.name,
            docstring=ast.get_docstring(node),
            parameters=params,
            line_number=node.lineno
        )
    
    def _is_module_level(self, tree: ast.AST, node: ast.FunctionDef) -> bool:
        """判断是否为模块级函数"""
        for module_node in ast.walk(tree):
            if isinstance(module_node, ast.Module):
                return node in module_node.body
        return False
    
    def generate_markdown(self, module_doc: ModuleDoc) -> str:
        """生成Markdown文档"""
        lines = []
        
        # 模块标题
        lines.append(f"# {module_doc.name}")
        lines.append("")
        lines.append(f"**File**: `{module_doc.file_path}`")
        lines.append("")
        
        # 模块文档
        if module_doc.docstring:
            lines.append(module_doc.docstring)
            lines.append("")
        
        # 类文档
        if module_doc.classes:
            lines.append("## Classes")
            lines.append("")
            
            for class_doc in module_doc.classes:
                lines.append(f"### {class_doc.name}")
                lines.append("")
                
                if class_doc.docstring:
                    lines.append(class_doc.docstring)
                    lines.append("")
                
                if class_doc.methods:
                    lines.append("**Methods**:")
                    lines.append("")
                    
                    for method in class_doc.methods:
                        lines.append(f"#### `{method.name}({', '.join(method.parameters)})`")
                        lines.append("")
                        
                        if method.docstring:
                            lines.append(method.docstring)
                        else:
                            lines.append("*No documentation available.*")
                        lines.append("")
        
        # 函数文档
        if module_doc.functions:
            lines.append("## Functions")
            lines.append("")
            
            for func in module_doc.functions:
                lines.append(f"### `{func.name}({', '.join(func.parameters)})`")
                lines.append("")
                
                if func.docstring:
                    lines.append(func.docstring)
                else:
                    lines.append("*No documentation available.*")
                lines.append("")
        
        return "\n".join(lines)
    
    def generate_directory_docs(
        self,
        directory: Path,
        output_dir: Path,
        pattern: str = "**/*.py"
    ):
        """生成整个目录的文档"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                module_doc = self.extract_from_file(file_path)
                markdown = self.generate_markdown(module_doc)
                
                # 保存Markdown
                output_file = output_dir / f"{module_doc.name}.md"
                output_file.write_text(markdown, encoding='utf-8')


def generate_docs(
    source_path: Path,
    output_dir: Path
) -> dict:
    """
    生成文档
    
    Args:
        source_path: 源代码路径 (文件或目录)
        output_dir: 输出目录
    
    Returns:
        生成结果
    """
    generator = DocumentationGenerator()
    
    if source_path.is_file():
        module_doc = generator.extract_from_file(source_path)
        markdown = generator.generate_markdown(module_doc)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{module_doc.name}.md"
        output_file.write_text(markdown, encoding='utf-8')
        
        return {
            "success": True,
            "files_generated": 1,
            "output_file": str(output_file)
        }
    
    elif source_path.is_dir():
        generator.generate_directory_docs(source_path, output_dir)
        
        generated_files = list(output_dir.glob("*.md"))
        return {
            "success": True,
            "files_generated": len(generated_files),
            "output_dir": str(output_dir)
        }
    
    else:
        return {
            "success": False,
            "error": "Source path does not exist"
        }
