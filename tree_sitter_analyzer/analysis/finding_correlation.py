"""Cross-Analyzer Finding Correlation Engine.

Groups findings from multiple analyzers by code location to identify
compound hotspots: locations flagged by several independent analyzers.

No existing analyzers are modified. Findings are normalized via duck-typing
to a unified schema, then correlated by (file_path, line_range).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class Severity(Enum):
    """Normalized severity levels across all analyzers."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class HotspotPattern(Enum):
    """Common finding cluster patterns."""

    COMPLEXITY_CLUSTER = "complexity_cluster"
    DEAD_CODE_CLUSTER = "dead_code_cluster"
    RISK_CLUSTER = "risk_cluster"
    MIXED = "mixed"


# Maps raw severity strings to normalized Severity enum.
# Covers all known severity vocabularies across 95+ analyzers.
_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
    "warning": Severity.HIGH,
    "error": Severity.CRITICAL,
    "ok": Severity.INFO,
}


def _normalize_severity(raw: str) -> Severity:
    """Convert any analyzer severity string to normalized Severity."""
    return _SEVERITY_MAP.get(raw.lower(), Severity.INFO)


@dataclass(frozen=True)
class UnifiedFinding:
    """A finding normalized from any analyzer's result type."""

    file_path: str
    line: int
    end_line: int
    element_name: str
    severity: Severity
    analyzer_name: str
    finding_type: str
    message: str

    @property
    def location_key(self) -> tuple[str, int]:
        return (self.file_path, self.line)


@dataclass
class Hotspot:
    """A code location flagged by multiple analyzers."""

    file_path: str
    line: int
    end_line: int
    findings: list[UnifiedFinding] = field(default_factory=list)

    @property
    def analyzer_count(self) -> int:
        return len({f.analyzer_name for f in self.findings})

    @property
    def analyzer_names(self) -> list[str]:
        return sorted({f.analyzer_name for f in self.findings})

    @property
    def max_severity(self) -> Severity:
        if not self.findings:
            return Severity.INFO
        return max(self.findings, key=lambda f: _SEVERITY_ORDER[f.severity]).severity

    @property
    def finding_types(self) -> list[str]:
        return sorted({f.finding_type for f in self.findings})

    @property
    def priority_score(self) -> int:
        """Numeric priority: higher = fix first."""
        severity_weight = _SEVERITY_ORDER[self.max_severity]
        density_bonus = len(self.findings) - self.analyzer_count
        return self.analyzer_count * severity_weight + max(0, density_bonus)

    @property
    def pattern(self) -> HotspotPattern:
        """Categorize the cluster by dominant finding type."""
        names = {f.analyzer_name for f in self.findings}
        complexity = names & _COMPLEXITY_ANALYZERS
        dead_code = names & _DEAD_CODE_ANALYZERS
        risk = names & _RISK_ANALYZERS

        scores = [
            (len(complexity), HotspotPattern.COMPLEXITY_CLUSTER),
            (len(dead_code), HotspotPattern.DEAD_CODE_CLUSTER),
            (len(risk), HotspotPattern.RISK_CLUSTER),
        ]
        scores.sort(key=lambda s: s[0], reverse=True)

        if scores[0][0] >= 2 and scores[0][0] > scores[1][0]:
            return scores[0][1]
        return HotspotPattern.MIXED


@dataclass
class FileSummary:
    """Aggregated hotspot info for a single file."""

    file_path: str
    hotspot_count: int
    max_priority_score: int
    top_pattern: HotspotPattern

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "hotspot_count": self.hotspot_count,
            "max_priority_score": self.max_priority_score,
            "top_pattern": self.top_pattern.value,
        }


@dataclass
class CorrelationResult:
    """Aggregated correlation result for a project or file set."""

    hotspots: list[Hotspot] = field(default_factory=list)
    total_findings: int = 0
    total_files: int = 0
    analyzers_used: list[str] = field(default_factory=list)

    @property
    def critical_hotspots(self) -> list[Hotspot]:
        """Hotspots with 3+ analyzers."""
        return [h for h in self.hotspots if h.analyzer_count >= 3]

    @property
    def warning_hotspots(self) -> list[Hotspot]:
        """Hotspots with exactly 2 analyzers."""
        return [h for h in self.hotspots if h.analyzer_count == 2]

    @property
    def file_summary(self) -> list[FileSummary]:
        """Aggregate hotspots by file, sorted by max priority desc."""
        by_file: dict[str, list[Hotspot]] = {}
        for h in self.hotspots:
            by_file.setdefault(h.file_path, []).append(h)

        summaries: list[FileSummary] = []
        for fpath, file_hotspots in by_file.items():
            summaries.append(
                FileSummary(
                    file_path=fpath,
                    hotspot_count=len(file_hotspots),
                    max_priority_score=max(h.priority_score for h in file_hotspots),
                    top_pattern=max(
                        file_hotspots, key=lambda h: h.priority_score
                    ).pattern,
                )
            )
        summaries.sort(key=lambda s: s.max_priority_score, reverse=True)
        return summaries

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": self.total_findings,
            "total_files": self.total_files,
            "analyzers_used": self.analyzers_used,
            "hotspot_count": len(self.hotspots),
            "critical_count": len(self.critical_hotspots),
            "warning_count": len(self.warning_hotspots),
            "file_summary": [s.to_dict() for s in self.file_summary],
            "hotspots": [
                {
                    "file_path": h.file_path,
                    "line": h.line,
                    "end_line": h.end_line,
                    "analyzer_count": h.analyzer_count,
                    "analyzer_names": h.analyzer_names,
                    "max_severity": h.max_severity.value,
                    "priority_score": h.priority_score,
                    "pattern": h.pattern.value,
                    "finding_count": len(h.findings),
                    "finding_types": h.finding_types,
                    "findings": [
                        {
                            "analyzer": f.analyzer_name,
                            "type": f.finding_type,
                            "severity": f.severity.value,
                            "message": f.message,
                        }
                        for f in h.findings
                    ],
                }
                for h in self.hotspots
            ],
        }


# Severity ordering for max() comparisons
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# Proximity window: findings within this many lines are grouped together.
_LINE_PROXIMITY = 5

# Analyzer categories for pattern detection.
_COMPLEXITY_ANALYZERS: frozenset[str] = frozenset({
    "cognitive_complexity", "boolean_complexity", "nesting_depth",
    "function_size", "loop_complexity",
})
_DEAD_CODE_ANALYZERS: frozenset[str] = frozenset({
    "dead_store", "dead_code_path", "unused_variable",
})
_RISK_ANALYZERS: frozenset[str] = frozenset({
    "error_handling", "security_scan", "error_propagation",
})


def normalize_findings(
    analyzer_name: str,
    result: Any,
    file_path: str,
) -> list[UnifiedFinding]:
    """Extract and normalize findings from any analyzer result.

    Uses duck-typing to handle 95+ different result dataclasses
    without modifying any analyzer.
    """
    findings: list[UnifiedFinding] = []

    # Get the collection of individual finding items from the result.
    items = _extract_items(result)
    if not items:
        return findings

    for item in items:
        try:
            line = _get_line(item)
            if line <= 0:
                continue

            end_line = _get_end_line(item, line)
            severity = _get_severity(item)
            element_name = _get_name(item)
            message = _get_message(item)
            finding_type = type(item).__name__

            findings.append(
                UnifiedFinding(
                    file_path=file_path,
                    line=line,
                    end_line=end_line,
                    element_name=element_name,
                    severity=severity,
                    analyzer_name=analyzer_name,
                    finding_type=finding_type,
                    message=message,
                )
            )
        except Exception:
            logger.debug(
                "Skipping unparseable finding from %s: %s",
                analyzer_name,
                type(item).__name__,
            )
            continue

    return findings


def _extract_items(result: Any) -> list[Any]:
    """Extract finding items from a result object via duck-typing."""
    # Most analyzers have an issues/findings/violations collection on the Result.
    for attr in ("issues", "findings", "violations", "hotspots", "items"):
        val = getattr(result, attr, None)
        if val is not None:
            return list(val)

    # Some results ARE the list (rare).
    if isinstance(result, (list, tuple)):
        return list(result)

    return []


def _get_line(item: Any) -> int:
    """Extract line number from a finding item."""
    for attr in ("line_number", "line", "start_line"):
        val = getattr(item, attr, None)
        if val is not None:
            return int(val)
    return 0


def _get_end_line(item: Any, start_line: int) -> int:
    """Extract end line, falling back to start line."""
    for attr in ("end_line",):
        val = getattr(item, attr, None)
        if val is not None:
            return int(val)
    return start_line


def _get_severity(item: Any) -> Severity:
    """Extract and normalize severity from a finding item."""
    for attr in ("severity", "risk", "level"):
        val = getattr(item, attr, None)
        if val is not None:
            if isinstance(val, Enum):
                return _normalize_severity(val.value)
            return _normalize_severity(str(val))

    # Some analyzers use 'rating' instead of severity.
    rating = getattr(item, "rating", None)
    if rating is not None:
        rating_str = str(rating).lower()
        rating_map = {
            "critical": Severity.CRITICAL,
            "warning": Severity.HIGH,
            "good": Severity.INFO,
            "simple": Severity.INFO,
            "moderate": Severity.MEDIUM,
            "complex": Severity.HIGH,
            "very_complex": Severity.CRITICAL,
            "extreme": Severity.CRITICAL,
        }
        return rating_map.get(rating_str, Severity.INFO)

    return Severity.INFO


def _get_name(item: Any) -> str:
    """Extract element name from a finding item."""
    for attr in ("name", "element_name", "function_name", "variable_name",
                 "class_name", "method_name", "param_name", "parameter_name",
                 "variable"):
        val = getattr(item, attr, None)
        if val:
            return str(val)
    return ""


def _get_message(item: Any) -> str:
    """Extract human-readable message from a finding item."""
    for attr in ("message", "description", "text", "expression"):
        val = getattr(item, attr, None)
        if val:
            return str(val)

    # Build a message from available fields.
    name = _get_name(item)
    finding_type = type(item).__name__
    if name:
        return f"{finding_type}: {name}"
    return finding_type


class FindingCorrelator:
    """Correlates findings from multiple analyzers by code location.

    Usage:
        correlator = FindingCorrelator()
        correlator.add_findings("dead_store", findings_list, "file.py")
        correlator.add_findings("boolean_complexity", findings_list, "file.py")
        result = correlator.correlate()
    """

    def __init__(self, line_proximity: int = _LINE_PROXIMITY) -> None:
        self._all_findings: list[UnifiedFinding] = []
        self._analyzers: set[str] = set()
        self._files: set[str] = set()
        self._line_proximity = line_proximity

    def add_findings(
        self,
        analyzer_name: str,
        result: Any,
        file_path: str,
    ) -> None:
        """Normalize and collect findings from one analyzer for one file."""
        normalized = normalize_findings(analyzer_name, result, file_path)
        self._all_findings.extend(normalized)
        self._analyzers.add(analyzer_name)
        self._files.add(file_path)

    def add_unified(self, findings: list[UnifiedFinding]) -> None:
        """Add pre-normalized findings directly."""
        self._all_findings.extend(findings)
        for f in findings:
            self._analyzers.add(f.analyzer_name)
            self._files.add(f.file_path)

    def correlate(self) -> CorrelationResult:
        """Group findings by location and identify compound hotspots."""
        if not self._all_findings:
            return CorrelationResult(
                analyzers_used=sorted(self._analyzers),
                total_files=len(self._files),
            )

        # Group by (file_path, proximity-adjusted line).
        groups: dict[tuple[str, int], list[UnifiedFinding]] = {}
        for finding in self._all_findings:
            bucket = self._proximity_bucket(finding.file_path, finding.line)
            groups.setdefault(bucket, []).append(finding)

        # Build hotspots from groups with 2+ analyzers.
        hotspots: list[Hotspot] = []
        for (fpath, _base_line), group_findings in groups.items():
            analyzer_names = {f.analyzer_name for f in group_findings}
            if len(analyzer_names) < 2:
                continue

            lines = [f.line for f in group_findings]
            end_lines = [f.end_line for f in group_findings]

            hotspots.append(
                Hotspot(
                    file_path=fpath,
                    line=min(lines),
                    end_line=max(end_lines),
                    findings=group_findings,
                )
            )

        # Sort by priority_score desc.
        hotspots.sort(key=lambda h: h.priority_score, reverse=True)

        return CorrelationResult(
            hotspots=hotspots,
            total_findings=len(self._all_findings),
            total_files=len(self._files),
            analyzers_used=sorted(self._analyzers),
        )

    def _proximity_bucket(self, file_path: str, line: int) -> tuple[str, int]:
        """Map a line number to a proximity bucket for grouping."""
        bucket = (line // self._line_proximity) * self._line_proximity
        return (file_path, bucket)
