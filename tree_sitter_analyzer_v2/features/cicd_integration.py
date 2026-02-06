"""
Scenario 4: CI/CD Integration
JSON报告 + 配置文件 + 返回码规范
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExitCode(Enum):
    """标准返回码"""
    SUCCESS = 0  # 无问题
    WARNINGS = 1  # 有警告
    ERRORS = 2  # 有错误
    CRITICAL = 3  # 严重错误 (阻断构建)


@dataclass
class Issue:
    """问题"""
    file: str
    line: int
    column: int
    severity: str  # error / warning / info
    message: str
    rule: str


@dataclass
class CICDReport:
    """CI/CD报告"""
    project: str
    timestamp: str
    total_files: int
    total_lines: int
    issues: List[Issue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    exit_code: int = 0
    
    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps({
            "project": self.project,
            "timestamp": self.timestamp,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "column": i.column,
                    "severity": i.severity,
                    "message": i.message,
                    "rule": i.rule
                }
                for i in self.issues
            ],
            "metrics": self.metrics,
            "summary": {
                "errors": len([i for i in self.issues if i.severity == "error"]),
                "warnings": len([i for i in self.issues if i.severity == "warning"]),
                "info": len([i for i in self.issues if i.severity == "info"])
            },
            "exit_code": self.exit_code
        }, indent=2)


@dataclass
class CICDConfig:
    """CI/CD配置"""
    max_complexity: int = 10
    max_line_length: int = 120
    fail_on_error: bool = True
    fail_on_warning: bool = False
    
    @classmethod
    def load(cls, config_file: Path) -> "CICDConfig":
        """从配置文件加载"""
        if not config_file.exists():
            return cls()
        
        try:
            data = json.loads(config_file.read_text())
            return cls(
                max_complexity=data.get("max_complexity", 10),
                max_line_length=data.get("max_line_length", 120),
                fail_on_error=data.get("fail_on_error", True),
                fail_on_warning=data.get("fail_on_warning", False)
            )
        except Exception:
            return cls()


def generate_cicd_report(
    project_root: Path,
    config: Optional[CICDConfig] = None
) -> CICDReport:
    """
    生成CI/CD报告
    
    Args:
        project_root: 项目根目录
        config: CI/CD配置
    
    Returns:
        CICDReport
    """
    from datetime import datetime
    
    if config is None:
        config_file = project_root / ".tree-sitter-ci.json"
        config = CICDConfig.load(config_file)
    
    report = CICDReport(
        project=project_root.name,
        timestamp=datetime.now().isoformat(),
        total_files=0,
        total_lines=0
    )
    
    # 扫描Python文件
    issues = []
    files = list(project_root.glob("**/*.py"))
    report.total_files = len(files)
    
    total_lines = 0
    for file_path in files:
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            total_lines += len(lines)
            
            # 简单检查: 行长度
            for i, line in enumerate(lines, 1):
                if len(line) > config.max_line_length:
                    issues.append(Issue(
                        file=str(file_path.relative_to(project_root)),
                        line=i,
                        column=config.max_line_length + 1,
                        severity="warning",
                        message=f"Line too long ({len(line)} > {config.max_line_length})",
                        rule="E501"
                    ))
        except Exception:
            pass
    
    report.total_lines = total_lines
    report.issues = issues
    
    # 计算返回码
    error_count = len([i for i in issues if i.severity == "error"])
    warning_count = len([i for i in issues if i.severity == "warning"])
    
    if error_count > 0 and config.fail_on_error:
        report.exit_code = ExitCode.ERRORS.value
    elif warning_count > 0 and config.fail_on_warning:
        report.exit_code = ExitCode.WARNINGS.value
    else:
        report.exit_code = ExitCode.SUCCESS.value
    
    report.metrics = {
        "files": report.total_files,
        "lines": report.total_lines,
        "errors": error_count,
        "warnings": warning_count
    }
    
    return report
