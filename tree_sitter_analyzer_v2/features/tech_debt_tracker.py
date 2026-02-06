"""
Scenario 10: Tech Debt Tracker
债务量化 + 趋势分析
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List


class DebtType(Enum):
    """债务类型"""
    CODE_SMELL = "code_smell"  # 代码异味
    COMPLEXITY = "complexity"  # 高复杂度
    DUPLICATION = "duplication"  # 重复代码
    DEPRECATED = "deprecated"  # 过时代码
    TODO = "todo"  # 待办事项
    FIXME = "fixme"  # 需要修复
    HACK = "hack"  # 临时解决方案


@dataclass
class TechDebt:
    """技术债务"""
    file: str
    line_number: int
    debt_type: DebtType
    severity: str  # high / medium / low
    description: str
    estimated_fix_time: int  # 分钟


class TechDebtAnalyzer:
    """
    技术债务分析器
    
    功能:
    - 识别技术债务
    - 债务量化
    - 趋势分析
    """
    
    def __init__(self):
        # 债务修复时间估算 (分钟)
        self.fix_time_estimates = {
            DebtType.TODO: 30,
            DebtType.FIXME: 60,
            DebtType.HACK: 120,
            DebtType.CODE_SMELL: 45,
            DebtType.COMPLEXITY: 90,
            DebtType.DUPLICATION: 60,
            DebtType.DEPRECATED: 30,
        }
    
    def analyze_file(self, file_path: Path) -> List[TechDebt]:
        """分析单个文件的技术债务"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
        except Exception:
            return []
        
        debts = []
        
        for i, line in enumerate(lines, 1):
            # 检测TODO/FIXME/HACK注释
            if '# TODO' in line or '# todo' in line:
                debts.append(TechDebt(
                    file=str(file_path),
                    line_number=i,
                    debt_type=DebtType.TODO,
                    severity="low",
                    description=line.strip(),
                    estimated_fix_time=self.fix_time_estimates[DebtType.TODO]
                ))
            elif '# FIXME' in line or '# fixme' in line:
                debts.append(TechDebt(
                    file=str(file_path),
                    line_number=i,
                    debt_type=DebtType.FIXME,
                    severity="medium",
                    description=line.strip(),
                    estimated_fix_time=self.fix_time_estimates[DebtType.FIXME]
                ))
            elif '# HACK' in line or '# hack' in line:
                debts.append(TechDebt(
                    file=str(file_path),
                    line_number=i,
                    debt_type=DebtType.HACK,
                    severity="high",
                    description=line.strip(),
                    estimated_fix_time=self.fix_time_estimates[DebtType.HACK]
                ))
            
            # 检测过时API (简化版)
            if 'deprecated' in line.lower() and 'import' not in line.lower():
                debts.append(TechDebt(
                    file=str(file_path),
                    line_number=i,
                    debt_type=DebtType.DEPRECATED,
                    severity="medium",
                    description="使用过时API",
                    estimated_fix_time=self.fix_time_estimates[DebtType.DEPRECATED]
                ))
        
        return debts
    
    def analyze_directory(
        self,
        directory: Path,
        pattern: str = "**/*.py"
    ) -> List[TechDebt]:
        """分析整个目录"""
        all_debts = []
        
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                debts = self.analyze_file(file_path)
                all_debts.extend(debts)
        
        return all_debts
    
    def calculate_total_debt(self, debts: List[TechDebt]) -> dict:
        """计算总债务"""
        total_time = sum(d.estimated_fix_time for d in debts)
        
        # 按类型分组
        by_type = {}
        for debt in debts:
            debt_type = debt.debt_type.value
            if debt_type not in by_type:
                by_type[debt_type] = 0
            by_type[debt_type] += 1
        
        # 按严重程度分组
        by_severity = {}
        for debt in debts:
            severity = debt.severity
            if severity not in by_severity:
                by_severity[severity] = 0
            by_severity[severity] += 1
        
        return {
            "total_debts": len(debts),
            "total_fix_time_minutes": total_time,
            "total_fix_time_hours": round(total_time / 60, 1),
            "total_fix_time_days": round(total_time / (60 * 8), 1),  # 8小时工作日
            "by_type": by_type,
            "by_severity": by_severity
        }
    
    def generate_report(self, debts: List[TechDebt]) -> dict:
        """生成债务报告"""
        total_debt = self.calculate_total_debt(debts)
        
        # Top 10 最严重的债务
        top_debts = sorted(
            debts,
            key=lambda d: (
                {"high": 3, "medium": 2, "low": 1}.get(d.severity, 0),
                d.estimated_fix_time
            ),
            reverse=True
        )[:10]
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": total_debt,
            "top_debts": [
                {
                    "file": d.file,
                    "line": d.line_number,
                    "type": d.debt_type.value,
                    "severity": d.severity,
                    "description": d.description,
                    "estimated_fix_time": d.estimated_fix_time
                }
                for d in top_debts
            ],
            "recommendations": self._generate_recommendations(total_debt)
        }
    
    def _generate_recommendations(self, total_debt: dict) -> List[str]:
        """生成建议"""
        recommendations = []
        
        total_days = total_debt["total_fix_time_days"]
        
        if total_days > 30:
            recommendations.append("🔴 Critical: 技术债务超过30天,需要立即安排专项重构")
        elif total_days > 10:
            recommendations.append("⚠️  Warning: 技术债务较高,建议每周安排时间处理")
        elif total_days > 3:
            recommendations.append("💡 Moderate: 债务可控,保持定期清理")
        else:
            recommendations.append("✅ Good: 债务水平健康")
        
        # 按类型建议
        by_type = total_debt["by_type"]
        if by_type.get("hack", 0) > 5:
            recommendations.append("优先处理HACK标记的临时解决方案")
        if by_type.get("fixme", 0) > 10:
            recommendations.append("大量FIXME标记,需要系统性修复")
        
        return recommendations


def analyze_tech_debt(project_root: Path) -> dict:
    """
    分析技术债务
    
    Args:
        project_root: 项目根目录
    
    Returns:
        债务报告
    """
    analyzer = TechDebtAnalyzer()
    debts = analyzer.analyze_directory(project_root)
    return analyzer.generate_report(debts)
