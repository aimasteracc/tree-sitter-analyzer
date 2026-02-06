"""
Scenario 7: Performance Hotspot Analyzer
复杂度计算 + 调用频率 + 热点检测
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class PerformanceHotspot:
    """性能热点"""
    file: str
    function: str
    complexity: int
    call_frequency_estimate: int
    hotspot_score: float
    line_number: int
    recommendation: str


class ComplexityCalculator:
    """复杂度计算器 (Cyclomatic Complexity)"""
    
    def calculate(self, node: ast.AST) -> int:
        """计算循环复杂度"""
        complexity = 1  # 基础复杂度
        
        for child in ast.walk(node):
            # 分支语句 +1
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            # 异常处理 +1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            # 布尔操作符 +1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            # 列表/字典/集合推导式 +1
            elif isinstance(child, (ast.ListComp, ast.DictComp, ast.SetComp)):
                complexity += 1
        
        return complexity


class PerformanceAnalyzer:
    """
    性能热点分析器
    
    功能:
    - 计算函数复杂度
    - 估算调用频率
    - 识别性能热点
    """
    
    def __init__(self):
        self.complexity_calculator = ComplexityCalculator()
    
    def analyze_file(self, file_path: Path) -> List[PerformanceHotspot]:
        """分析单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(content, filename=str(file_path))
        except Exception:
            return []
        
        hotspots = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 计算复杂度
                complexity = self.complexity_calculator.calculate(node)
                
                # 估算调用频率 (简化版: 基于函数名)
                call_frequency = self._estimate_call_frequency(node.name)
                
                # 计算热点分数
                hotspot_score = complexity * call_frequency
                
                # 生成建议
                recommendation = self._generate_recommendation(complexity, call_frequency)
                
                hotspot = PerformanceHotspot(
                    file=str(file_path),
                    function=node.name,
                    complexity=complexity,
                    call_frequency_estimate=call_frequency,
                    hotspot_score=hotspot_score,
                    line_number=node.lineno,
                    recommendation=recommendation
                )
                
                hotspots.append(hotspot)
        
        return hotspots
    
    def analyze_directory(
        self,
        directory: Path,
        pattern: str = "**/*.py"
    ) -> List[PerformanceHotspot]:
        """分析整个目录"""
        all_hotspots = []
        
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                hotspots = self.analyze_file(file_path)
                all_hotspots.extend(hotspots)
        
        return all_hotspots
    
    def get_top_hotspots(
        self,
        hotspots: List[PerformanceHotspot],
        top_n: int = 10
    ) -> List[PerformanceHotspot]:
        """获取Top N热点"""
        return sorted(hotspots, key=lambda h: h.hotspot_score, reverse=True)[:top_n]
    
    def _estimate_call_frequency(self, function_name: str) -> int:
        """
        估算调用频率 (简化版)
        
        基于函数名启发式估算:
        - 公共API: 10
        - 工具函数: 5
        - 内部函数: 2
        - 私有函数: 1
        """
        if function_name.startswith('_'):
            return 1  # 私有函数
        elif function_name in ['main', 'run', 'execute', 'process']:
            return 10  # 高频入口函数
        elif function_name.startswith('get_') or function_name.startswith('set_'):
            return 5  # 访问器
        else:
            return 2  # 普通函数
    
    def _generate_recommendation(self, complexity: int, call_frequency: int) -> str:
        """生成优化建议"""
        if complexity > 15 and call_frequency > 5:
            return "🔴 Critical: High complexity + High frequency. Refactor immediately!"
        elif complexity > 15:
            return "⚠️  Warning: High complexity. Consider splitting into smaller functions."
        elif call_frequency > 5:
            return "⚡ Optimize: High frequency call. Profile and optimize if needed."
        elif complexity > 10:
            return "💡 Suggestion: Moderate complexity. Monitor for future optimization."
        else:
            return "✅ OK: Low impact. No immediate action needed."


def analyze_performance(
    project_root: Path,
    top_n: int = 10
) -> dict:
    """
    分析性能热点
    
    Args:
        project_root: 项目根目录
        top_n: 返回Top N热点
    
    Returns:
        分析结果
    """
    analyzer = PerformanceAnalyzer()
    all_hotspots = analyzer.analyze_directory(project_root)
    top_hotspots = analyzer.get_top_hotspots(all_hotspots, top_n)
    
    return {
        "total_functions": len(all_hotspots),
        "top_hotspots": [
            {
                "file": h.file,
                "function": h.function,
                "complexity": h.complexity,
                "call_frequency": h.call_frequency_estimate,
                "hotspot_score": h.hotspot_score,
                "line_number": h.line_number,
                "recommendation": h.recommendation
            }
            for h in top_hotspots
        ],
        "summary": {
            "critical": len([h for h in all_hotspots if h.complexity > 15 and h.call_frequency_estimate > 5]),
            "warning": len([h for h in all_hotspots if h.complexity > 15]),
            "moderate": len([h for h in all_hotspots if h.complexity > 10]),
        }
    }
