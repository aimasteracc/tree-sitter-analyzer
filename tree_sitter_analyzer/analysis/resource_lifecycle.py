"""
Resource Lifecycle Analyzer.

Detects resource management issues in source code:
  - open() calls not wrapped in context managers (Python)
  - new FileInputStream/Reader without try-with-resources (Java)
  - fs.open()/createReadStream without proper cleanup (TypeScript/JS)
  - Resource acquisition without cleanup patterns

Risk levels:
  - HIGH: resource acquired with no cleanup mechanism
  - MEDIUM: resource acquired in try but no finally/catch cleanup
  - LOW: resource acquired with cleanup but could be safer
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

RISK_HIGH = "HIGH"
RISK_MEDIUM = "MEDIUM"
RISK_LOW = "LOW"

PATTERN_OPEN_PYTHON = re.compile(r"(\w+)\s*=\s*open\s*\(", re.MULTILINE)
PATTERN_WITH_PYTHON = re.compile(r"\bwith\s+open\s*\(", re.MULTILINE)
PATTERN_TRY_PYTHON = re.compile(r"\btry\s*:", re.MULTILINE)
PATTERN_FINALLY_PYTHON = re.compile(r"\bfinally\s*:", re.MULTILINE)

PATTERN_NEW_STREAM_JAVA = re.compile(
    r"new\s+(?:FileInputStream|FileOutputStream|FileReader|FileWriter"
    r"|BufferedReader|BufferedWriter|InputStream|OutputStream"
    r"|Connection|Statement|PreparedStatement|ResultSet)\s*\(",
    re.MULTILINE,
)
PATTERN_TRY_WITH_RESOURCES_JAVA = re.compile(r"\btry\s*\(", re.MULTILINE)

PATTERN_FS_OPEN_TS = re.compile(
    r"(?:fs|readline|child_process)\.(?:open|createReadStream|createWriteStream"
    r"|exec|spawn|fork)\s*\(",
    re.MULTILINE,
)
PATTERN_USING_TS = re.compile(r"\busing\s+.*=\s*(?:await\s+)?(?:fs|readline)", re.MULTILINE)
PATTERN_PROMISE_CSHARP = re.compile(
    r"new\s+(?:FileStream|StreamReader|StreamWriter|SqlConnection"
    r"|SqlCommand|HttpClient|WebResponse)\s*\(",
    re.MULTILINE,
)
PATTERN_USING_CSHARP = re.compile(r"\busing\s*(?:\(|\s+\w+\s*=)", re.MULTILINE)

@dataclass(frozen=True)
class ResourceIssue:
    file_path: str
    line: int
    resource_type: str
    risk: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "resource_type": self.resource_type,
            "risk": self.risk,
            "description": self.description,
        }

@dataclass(frozen=True)
class ResourceSafetyStats:
    total_acquisitions: int
    safe_acquisitions: int
    risky_acquisitions: int
    safety_percentage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_acquisitions": self.total_acquisitions,
            "safe_acquisitions": self.safe_acquisitions,
            "risky_acquisitions": self.risky_acquisitions,
            "safety_percentage": round(self.safety_percentage, 1),
        }

@dataclass(frozen=True)
class ResourceLifecycleResult:
    file_path: str
    issues: tuple[ResourceIssue, ...]
    stats: ResourceSafetyStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats.to_dict(),
        }

def _count_lines_before(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1

def _analyze_python(content: str, file_path: str) -> list[ResourceIssue]:
    issues: list[ResourceIssue] = []

    with_opens = set()
    for m in PATTERN_WITH_PYTHON.finditer(content):
        with_opens.add(_count_lines_before(content, m.start()))

    for m in PATTERN_OPEN_PYTHON.finditer(content):
        line = _count_lines_before(content, m.start())
        if line in with_opens:
            continue

        var = m.group(1)
        block_start = content.rfind("\n", 0, m.start())
        block_start = max(0, block_start)

        has_try = bool(PATTERN_TRY_PYTHON.search(content, block_start, block_start + 500))
        has_finally = bool(PATTERN_FINALLY_PYTHON.search(content, block_start, block_start + 500))

        if has_try and has_finally:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="file_open",
                risk=RISK_LOW,
                description=f"Variable '{var}' uses open() with try/finally (prefer 'with' statement)",
            ))
        elif has_try:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="file_open",
                risk=RISK_MEDIUM,
                description=f"Variable '{var}' uses open() in try block without finally cleanup",
            ))
        else:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="file_open",
                risk=RISK_HIGH,
                description=f"Variable '{var}' uses open() without context manager or cleanup",
            ))

    return issues

def _analyze_java(content: str, file_path: str) -> list[ResourceIssue]:
    issues: list[ResourceIssue] = []

    try_with_res = set()
    for m in PATTERN_TRY_WITH_RESOURCES_JAVA.finditer(content):
        try_with_res.add(_count_lines_before(content, m.start()))

    for m in PATTERN_NEW_STREAM_JAVA.finditer(content):
        line = _count_lines_before(content, m.start())

        nearby_try = any(
            abs(line - tl) < 5 for tl in try_with_res
        )

        if nearby_try:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="io_stream",
                risk=RISK_LOW,
                description="Resource created near try-with-resources (check wrapping)",
            ))
        else:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="io_stream",
                risk=RISK_HIGH,
                description="Resource created without try-with-resources or cleanup",
            ))

    return issues

def _analyze_typescript(content: str, file_path: str) -> list[ResourceIssue]:
    issues: list[ResourceIssue] = []

    for m in PATTERN_FS_OPEN_TS.finditer(content):
        line = _count_lines_before(content, m.start())
        issues.append(ResourceIssue(
            file_path=file_path,
            line=line,
            resource_type="fs_stream",
            risk=RISK_MEDIUM,
            description="File system resource opened (verify cleanup/error handling)",
        ))

    return issues

def _analyze_csharp(content: str, file_path: str) -> list[ResourceIssue]:
    issues: list[ResourceIssue] = []

    using_lines = set()
    for m in PATTERN_USING_CSHARP.finditer(content):
        using_lines.add(_count_lines_before(content, m.start()))

    for m in PATTERN_PROMISE_CSHARP.finditer(content):
        line = _count_lines_before(content, m.start())

        nearby_using = any(
            abs(line - ul) < 5 for ul in using_lines
        )

        if nearby_using:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="disposable",
                risk=RISK_LOW,
                description="Resource created near 'using' statement (check wrapping)",
            ))
        else:
            issues.append(ResourceIssue(
                file_path=file_path,
                line=line,
                resource_type="disposable",
                risk=RISK_HIGH,
                description="IDisposable resource created without 'using' statement",
            ))

    return issues

_EXT_TO_ANALYZER: dict[str, type] = {}  # populated below

class ResourceLifecycleAnalyzer(BaseAnalyzer):
    """Analyzes resource lifecycle management in source files."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".java", ".ts", ".tsx", ".js", ".jsx", ".cs"}

    def __init__(self) -> None:
        super().__init__()

    def analyze_file(self, file_path: str | Path) -> ResourceLifecycleResult:
        path = Path(file_path)
        if not path.is_file():
            return ResourceLifecycleResult(
                file_path=str(path),
                issues=(),
                stats=ResourceSafetyStats(0, 0, 0, 100.0),
            )

        ext = path.suffix.lower()
        analyzer_fn = _EXT_ANALYZER_MAP.get(ext)
        if analyzer_fn is None:
            return ResourceLifecycleResult(
                file_path=str(path),
                issues=(),
                stats=ResourceSafetyStats(0, 0, 0, 100.0),
            )

        content = path.read_text(errors="replace")
        issues = analyzer_fn(content, str(path))
        total = len(issues) + _count_safe_acquisitions(content, ext)
        risky = sum(1 for i in issues if i.risk in (RISK_HIGH, RISK_MEDIUM))
        safe = max(0, total - risky)
        pct = (safe / total * 100) if total > 0 else 100.0

        return ResourceLifecycleResult(
            file_path=str(path),
            issues=tuple(issues),
            stats=ResourceSafetyStats(
                total_acquisitions=total,
                safe_acquisitions=safe,
                risky_acquisitions=risky,
                safety_percentage=pct,
            ),
        )

    def analyze_project(self, project_root: str | Path) -> list[ResourceLifecycleResult]:
        root = Path(project_root)
        if not root.is_dir():
            return []

        results: list[ResourceLifecycleResult] = []
        for ext in _EXT_ANALYZER_MAP:
            for path in root.rglob(f"*{ext}"):
                result = self.analyze_file(path)
                if result.issues:
                    results.append(result)

        return results

_EXT_ANALYZER_MAP: dict[str, Any] = {
    ".py": _analyze_python,
    ".java": _analyze_java,
    ".ts": _analyze_typescript,
    ".tsx": _analyze_typescript,
    ".js": _analyze_typescript,
    ".jsx": _analyze_typescript,
    ".cs": _analyze_csharp,
}

def _count_safe_acquisitions(content: str, ext: str) -> int:
    if ext == ".py":
        return len(PATTERN_WITH_PYTHON.findall(content))
    if ext == ".java":
        return len(PATTERN_TRY_WITH_RESOURCES_JAVA.findall(content))
    if ext in (".cs",):
        return len(PATTERN_USING_CSHARP.findall(content))
    return 0
