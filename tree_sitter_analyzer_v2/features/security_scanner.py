"""
Scenario 5: Security Vulnerability Scanner
SQL注入/XSS检测 + 规则引擎
"""

import ast
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional


class Severity(Enum):
    """漏洞严重程度"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Vulnerability:
    """安全漏洞"""
    file: str
    line: int
    severity: Severity
    rule_id: str
    rule_name: str
    description: str
    recommendation: str


class SecurityRule:
    """安全规则基类"""
    
    def __init__(self, rule_id: str, name: str, severity: Severity):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity
    
    def check(self, file_path: Path, content: str) -> List[Vulnerability]:
        """检查文件"""
        raise NotImplementedError


class SQLInjectionRule(SecurityRule):
    """SQL注入检测"""
    
    def __init__(self):
        super().__init__(
            rule_id="SEC001",
            name="SQL Injection",
            severity=Severity.HIGH
        )
    
    def check(self, file_path: Path, content: str) -> List[Vulnerability]:
        """检查SQL注入风险"""
        vulnerabilities = []
        lines = content.split('\n')
        
        # 检测模式: 字符串拼接构建SQL
        patterns = [
            r'execute\s*\(\s*["\'].*%s.*["\']',  # execute("SELECT * FROM users WHERE id=%s" % user_input)
            r'execute\s*\(\s*.*\+.*\)',  # execute("SELECT * FROM users WHERE id=" + user_input)
            r'f["\']SELECT.*\{.*\}',  # f"SELECT * FROM users WHERE id={user_input}"
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    vulnerabilities.append(Vulnerability(
                        file=str(file_path),
                        line=i,
                        severity=self.severity,
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        description="Potential SQL injection vulnerability: untrusted user input in SQL query",
                        recommendation="Use parameterized queries or ORM methods instead of string formatting"
                    ))
        
        return vulnerabilities


class XSSRule(SecurityRule):
    """XSS跨站脚本检测"""
    
    def __init__(self):
        super().__init__(
            rule_id="SEC002",
            name="Cross-Site Scripting (XSS)",
            severity=Severity.HIGH
        )
    
    def check(self, file_path: Path, content: str) -> List[Vulnerability]:
        """检查XSS风险"""
        vulnerabilities = []
        lines = content.split('\n')
        
        # 检测模式: 未转义的用户输入直接输出到HTML
        patterns = [
            r'render_template\s*\(.*\{.*\}',  # render_template("page.html", data={user_input})
            r'\.innerHTML\s*=',  # element.innerHTML = user_input
            r'document\.write\s*\(',  # document.write(user_input)
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    vulnerabilities.append(Vulnerability(
                        file=str(file_path),
                        line=i,
                        severity=self.severity,
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        description="Potential XSS vulnerability: unescaped user input in HTML output",
                        recommendation="Use template auto-escaping or sanitize user input before rendering"
                    ))
        
        return vulnerabilities


class HardcodedSecretRule(SecurityRule):
    """硬编码密钥检测"""
    
    def __init__(self):
        super().__init__(
            rule_id="SEC003",
            name="Hardcoded Secret",
            severity=Severity.CRITICAL
        )
    
    def check(self, file_path: Path, content: str) -> List[Vulnerability]:
        """检查硬编码密钥"""
        vulnerabilities = []
        lines = content.split('\n')
        
        # 检测模式: 密钥关键词
        patterns = [
            r'(?i)(password|passwd|pwd|secret|api[_-]?key|token)\s*=\s*["\'][^"\']{8,}["\']',
            r'(?i)aws[_-]?(access|secret)[_-]?key\s*=',
            r'(?i)private[_-]?key\s*=',
        ]
        
        for i, line in enumerate(lines, 1):
            # 跳过注释
            if line.strip().startswith('#'):
                continue
            
            for pattern in patterns:
                if re.search(pattern, line):
                    vulnerabilities.append(Vulnerability(
                        file=str(file_path),
                        line=i,
                        severity=self.severity,
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        description="Hardcoded secret detected: sensitive credentials in source code",
                        recommendation="Use environment variables or secret management systems"
                    ))
        
        return vulnerabilities


class SecurityScanner:
    """
    安全漏洞扫描器
    
    支持的检测:
    - SQL注入
    - XSS跨站脚本
    - 硬编码密钥
    """
    
    def __init__(self):
        self.rules: List[SecurityRule] = [
            SQLInjectionRule(),
            XSSRule(),
            HardcodedSecretRule(),
        ]
    
    def scan_file(self, file_path: Path) -> List[Vulnerability]:
        """扫描单个文件"""
        if not file_path.exists():
            return []
        
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return []
        
        vulnerabilities = []
        for rule in self.rules:
            vulns = rule.check(file_path, content)
            vulnerabilities.extend(vulns)
        
        return vulnerabilities
    
    def scan_directory(
        self,
        directory: Path,
        pattern: str = "**/*.py"
    ) -> List[Vulnerability]:
        """扫描整个目录"""
        all_vulnerabilities = []
        
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                vulns = self.scan_file(file_path)
                all_vulnerabilities.extend(vulns)
        
        return all_vulnerabilities
    
    def get_summary(self, vulnerabilities: List[Vulnerability]) -> dict:
        """获取扫描总结"""
        by_severity = {}
        for vuln in vulnerabilities:
            severity = vuln.severity.value
            if severity not in by_severity:
                by_severity[severity] = 0
            by_severity[severity] += 1
        
        return {
            "total": len(vulnerabilities),
            "by_severity": by_severity,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }


def scan_security(project_root: Path) -> dict:
    """
    扫描项目安全漏洞
    
    Args:
        project_root: 项目根目录
    
    Returns:
        扫描结果
    """
    scanner = SecurityScanner()
    vulnerabilities = scanner.scan_directory(project_root)
    summary = scanner.get_summary(vulnerabilities)
    
    return {
        "summary": summary,
        "vulnerabilities": [
            {
                "file": v.file,
                "line": v.line,
                "severity": v.severity.value,
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "description": v.description,
                "recommendation": v.recommendation,
            }
            for v in vulnerabilities
        ]
    }
