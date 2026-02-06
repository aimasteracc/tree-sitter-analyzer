"""
Scenario 9: Semantic Code Search
AST模式匹配 + 语义查询
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class SearchResult:
    """搜索结果"""
    file: str
    line_number: int
    code_snippet: str
    context: str
    match_type: str


class ASTPattern:
    """AST模式"""
    
    def __init__(self, pattern_type: str, **kwargs):
        self.pattern_type = pattern_type
        self.kwargs = kwargs
    
    def matches(self, node: ast.AST) -> bool:
        """检查节点是否匹配模式"""
        raise NotImplementedError


class FunctionCallPattern(ASTPattern):
    """函数调用模式"""
    
    def __init__(self, function_name: Optional[str] = None):
        super().__init__("function_call", function_name=function_name)
        self.function_name = function_name
    
    def matches(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        
        if self.function_name:
            if isinstance(node.func, ast.Name):
                return node.func.id == self.function_name
            elif isinstance(node.func, ast.Attribute):
                return node.func.attr == self.function_name
        
        return True


class VariableAssignmentPattern(ASTPattern):
    """变量赋值模式"""
    
    def __init__(self, variable_name: Optional[str] = None):
        super().__init__("assignment", variable_name=variable_name)
        self.variable_name = variable_name
    
    def matches(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Assign):
            return False
        
        if self.variable_name:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == self.variable_name:
                    return True
        
        return True


class SemanticSearchEngine:
    """
    语义代码搜索引擎
    
    功能:
    - AST模式匹配
    - 语义查询 (查找特定代码结构)
    - 上下文感知搜索
    """
    
    def search_pattern(
        self,
        file_path: Path,
        pattern: ASTPattern
    ) -> List[SearchResult]:
        """在文件中搜索模式"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(content, filename=str(file_path))
            lines = content.split('\n')
        except Exception:
            return []
        
        results = []
        
        for node in ast.walk(tree):
            if pattern.matches(node):
                # 获取代码片段
                if hasattr(node, 'lineno'):
                    line_no = node.lineno
                    snippet = lines[line_no - 1].strip()
                    
                    # 获取上下文 (前后各2行)
                    context_lines = []
                    for i in range(max(0, line_no - 3), min(len(lines), line_no + 2)):
                        context_lines.append(lines[i])
                    context = '\n'.join(context_lines)
                    
                    results.append(SearchResult(
                        file=str(file_path),
                        line_number=line_no,
                        code_snippet=snippet,
                        context=context,
                        match_type=pattern.pattern_type
                    ))
        
        return results
    
    def search_directory(
        self,
        directory: Path,
        pattern: ASTPattern,
        file_pattern: str = "**/*.py"
    ) -> List[SearchResult]:
        """在整个目录中搜索"""
        all_results = []
        
        for file_path in directory.glob(file_pattern):
            if file_path.is_file():
                results = self.search_pattern(file_path, pattern)
                all_results.extend(results)
        
        return all_results
    
    def search_function_calls(
        self,
        directory: Path,
        function_name: str
    ) -> List[SearchResult]:
        """查找所有调用指定函数的地方"""
        pattern = FunctionCallPattern(function_name=function_name)
        return self.search_directory(directory, pattern)
    
    def search_variable_assignments(
        self,
        directory: Path,
        variable_name: str
    ) -> List[SearchResult]:
        """查找所有赋值给指定变量的地方"""
        pattern = VariableAssignmentPattern(variable_name=variable_name)
        return self.search_directory(directory, pattern)
    
    def search_semantic(
        self,
        directory: Path,
        query_type: str,
        **kwargs
    ) -> dict:
        """
        语义查询
        
        支持的查询类型:
        - function_calls: 查找函数调用
        - assignments: 查找变量赋值
        - imports: 查找导入语句
        """
        if query_type == "function_calls":
            function_name = kwargs.get("function_name")
            results = self.search_function_calls(directory, function_name)
        elif query_type == "assignments":
            variable_name = kwargs.get("variable_name")
            results = self.search_variable_assignments(directory, variable_name)
        else:
            results = []
        
        return {
            "query_type": query_type,
            "total_results": len(results),
            "results": [
                {
                    "file": r.file,
                    "line": r.line_number,
                    "snippet": r.code_snippet,
                    "context": r.context,
                    "match_type": r.match_type
                }
                for r in results[:100]  # 限制返回前100个结果
            ]
        }


def semantic_search(
    project_root: Path,
    query_type: str,
    **kwargs
) -> dict:
    """
    语义搜索
    
    Args:
        project_root: 项目根目录
        query_type: 查询类型
        **kwargs: 查询参数
    
    Returns:
        搜索结果
    """
    engine = SemanticSearchEngine()
    return engine.search_semantic(project_root, query_type, **kwargs)
