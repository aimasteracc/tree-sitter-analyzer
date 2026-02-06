"""
Feature: cross_file_call_chain
Scenario: refactoring_impact_analysis
Description: 重构函数前,分析影响的所有调用方

Success Criteria:
    - call_chain_depth: 10
    - cross_file_support: True
"""

from pathlib import Path
from typing import Any, Dict, List, Set, Optional
from dataclasses import dataclass, field
import re
import ast


@dataclass
class CallSite:
    """调用点信息"""
    file: Path
    function_name: str
    line_number: int
    context: str  # 调用上下文代码


@dataclass
class CallChain:
    """调用链"""
    target_function: str
    depth: int
    call_path: List[str] = field(default_factory=list)
    call_sites: List[CallSite] = field(default_factory=list)


class RefactoringAnalyzer:
    """
    重构影响分析器
    
    实现场景: 重构函数前,分析影响的所有调用方
    用户目标: 精确找到所有调用点,包括间接调用
    
    特性:
    - 跨文件分析
    - 调用链追踪 (支持10层深度)
    - 精确定位调用点
    - 影响范围评估
    """
    
    def __init__(self, max_depth: int = 10):
        """
        初始化分析器
        
        Args:
            max_depth: 最大调用链深度
        """
        self.max_depth = max_depth
        self.function_defs: Dict[str, List[Path]] = {}  # 函数定义位置
        self.function_calls: Dict[Path, Dict[str, List[CallSite]]] = {}  # 文件中的函数调用
    
    def analyze_directory(self, directory: Path, pattern: str = "**/*.py"):
        """
        分析整个目录,建立函数定义和调用索引
        
        Args:
            directory: 项目目录
            pattern: 文件匹配模式
        """
        self.function_defs.clear()
        self.function_calls.clear()
        
        # 扫描所有文件
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                self._index_file(file_path)
    
    def find_callers(
        self,
        function_name: str,
        max_depth: Optional[int] = None
    ) -> List[CallChain]:
        """
        查找指定函数的所有调用方 (支持间接调用)
        
        Args:
            function_name: 要分析的函数名
            max_depth: 最大深度 (None使用默认值)
        
        Returns:
            List[CallChain]: 调用链列表
        """
        max_depth = max_depth or self.max_depth
        call_chains: List[CallChain] = []
        visited: Set[str] = set()
        
        def search(target: str, current_depth: int, path: List[str]):
            """递归搜索调用链"""
            if current_depth > max_depth or target in visited:
                return
            
            visited.add(target)
            
            # 查找直接调用该函数的地方
            for file_path, calls_dict in self.function_calls.items():
                if target in calls_dict:
                    for call_site in calls_dict[target]:
                        chain = CallChain(
                            target_function=function_name,
                            depth=current_depth,
                            call_path=path + [call_site.function_name],
                            call_sites=[call_site]
                        )
                        call_chains.append(chain)
                        
                        # 继续向上追溯
                        search(call_site.function_name, current_depth + 1, chain.call_path)
            
            visited.remove(target)
        
        search(function_name, 1, [function_name])
        return call_chains
    
    def get_impact_summary(self, function_name: str) -> Dict[str, Any]:
        """
        获取重构影响总结
        
        Args:
            function_name: 函数名
        
        Returns:
            Dict: 影响总结
        """
        call_chains = self.find_callers(function_name)
        
        # 统计
        affected_files = set()
        affected_functions = set()
        max_chain_depth = 0
        
        for chain in call_chains:
            for call_site in chain.call_sites:
                affected_files.add(call_site.file)
                affected_functions.add(call_site.function_name)
            max_chain_depth = max(max_chain_depth, chain.depth)
        
        return {
            "function_name": function_name,
            "total_call_sites": len(call_chains),
            "affected_files": len(affected_files),
            "affected_functions": len(affected_functions),
            "max_call_depth": max_chain_depth,
            "call_chains": call_chains,
            "files_list": [str(f) for f in affected_files],
        }
    
    def _index_file(self, file_path: Path):
        """索引单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            
            # 解析 AST
            try:
                tree = ast.parse(content, filename=str(file_path))
                self._extract_functions_and_calls(tree, file_path, content)
            except SyntaxError:
                # 如果 AST 解析失败,使用简单的正则匹配
                self._extract_with_regex(content, file_path)
        except Exception as e:
            pass
    
    def _extract_functions_and_calls(self, tree: ast.AST, file_path: Path, content: str):
        """从 AST 提取函数定义和调用"""
        lines = content.split('\n')
        
        for node in ast.walk(tree):
            # 提取函数定义
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                if func_name not in self.function_defs:
                    self.function_defs[func_name] = []
                self.function_defs[func_name].append(file_path)
            
            # 提取函数调用
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_func = node.func.id
                    line_no = node.lineno
                    
                    # 找到包含这个调用的函数
                    caller_func = self._find_containing_function(tree, node)
                    
                    if file_path not in self.function_calls:
                        self.function_calls[file_path] = {}
                    
                    if called_func not in self.function_calls[file_path]:
                        self.function_calls[file_path][called_func] = []
                    
                    # 获取上下文
                    context = lines[line_no - 1] if line_no <= len(lines) else ""
                    
                    call_site = CallSite(
                        file=file_path,
                        function_name=caller_func or "<module>",
                        line_number=line_no,
                        context=context.strip()
                    )
                    self.function_calls[file_path][called_func].append(call_site)
    
    def _find_containing_function(self, tree: ast.AST, target_node: ast.AST) -> Optional[str]:
        """找到包含目标节点的函数名"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if target_node in ast.walk(node):
                    return node.name
        return None
    
    def _extract_with_regex(self, content: str, file_path: Path):
        """使用正则表达式提取(备选方案)"""
        lines = content.split('\n')
        
        # 提取函数定义
        for i, line in enumerate(lines):
            # def function_name(...):
            match = re.match(r'\s*def\s+(\w+)\s*\(', line)
            if match:
                func_name = match.group(1)
                if func_name not in self.function_defs:
                    self.function_defs[func_name] = []
                self.function_defs[func_name].append(file_path)
        
        # 提取函数调用 (简化版)
        for i, line in enumerate(lines):
            # 查找函数调用: function_name(...)
            matches = re.finditer(r'(\w+)\s*\(', line)
            for match in matches:
                called_func = match.group(1)
                
                # 跳过关键字
                if called_func in ['if', 'for', 'while', 'def', 'class', 'return']:
                    continue
                
                if file_path not in self.function_calls:
                    self.function_calls[file_path] = {}
                
                if called_func not in self.function_calls[file_path]:
                    self.function_calls[file_path][called_func] = []
                
                call_site = CallSite(
                    file=file_path,
                    function_name="<unknown>",
                    line_number=i + 1,
                    context=line.strip()
                )
                self.function_calls[file_path][called_func].append(call_site)


# 便捷函数
def analyze_refactoring_impact(
    directory: Path,
    function_name: str,
    max_depth: int = 10
) -> Dict[str, Any]:
    """
    分析重构影响
    
    Args:
        directory: 项目目录
        function_name: 要重构的函数名
        max_depth: 最大调用链深度
    
    Returns:
        Dict: 影响分析结果
    """
    analyzer = RefactoringAnalyzer(max_depth=max_depth)
    analyzer.analyze_directory(directory)
    return analyzer.get_impact_summary(function_name)
