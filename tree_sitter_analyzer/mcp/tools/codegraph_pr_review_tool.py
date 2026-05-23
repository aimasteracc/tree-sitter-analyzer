#!/usr/bin/env python3
"""
CodeGraph PR Review MCP Tool — AI-powered PR review via AST analysis.

Combines three existing capabilities into a single review-grade output:
  1. AST structural diff (difftastic-level change understanding)
  2. Semantic change classification (api_change, refactor, feature, etc.)
  3. Call graph blast radius (transitive caller/callee impact)

Unlike analyze_change_impact (which focuses on test discovery and
verification commands), this tool produces a reviewer-oriented summary:
risk verdict, semantic change categories per file, affected API surface,
and actionable review notes.

CodeGraph parity: CodeGraph lacks semantic classification; this goes beyond.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...ast_diff import ASTDiffer
from ...call_graph import CachedCallGraph, CallGraph
from ...pr_url import check_gh_available, fetch_pr_diff, parse_pr_url
from ...project_graph import _language_from_ext
from ...semantic_change_classifier import SemanticChangeClassifier
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_FILES = 30
_MAX_HUNKS_DISPLAY = 10


@dataclass
class FileReview:
    file_path: str
    language: str
    dominant_category: str
    risk_level: str
    change_summary: str
    category_counts: dict[str, int]
    hunk_count: int
    high_risk_hunks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.file_path,
            "language": self.language,
            "category": self.dominant_category,
            "risk": self.risk_level,
            "summary": self.change_summary,
            "hunk_count": self.hunk_count,
        }
        if self.category_counts:
            d["categories"] = self.category_counts
        if self.high_risk_hunks:
            d["high_risk_changes"] = self.high_risk_hunks[:5]
        return d


@dataclass
class PRReviewResult:
    files_reviewed: int
    files_skipped: int
    overall_risk: str
    overall_verdict: str
    file_reviews: list[FileReview]
    api_changes: list[str]
    affected_functions: list[dict[str, Any]]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_reviewed": self.files_reviewed,
            "files_skipped": self.files_skipped,
            "overall_risk": self.overall_risk,
            "verdict": self.overall_verdict,
            "file_reviews": [r.to_dict() for r in self.file_reviews],
            "api_changes": self.api_changes,
            "affected_functions": self.affected_functions[:20],
            "recommendations": self.recommendations,
        }


def _risk_to_score(risk: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(risk, 2)


def _score_to_risk(score: float) -> str:
    if score >= 3.0:
        return "critical"
    if score >= 2.0:
        return "high"
    if score >= 1.5:
        return "medium"
    return "low"


def _get_local_diff(mode: str, project_root: str | None) -> str:
    if not project_root:
        return ""
    cmd = {
        "diff": ["git", "diff"],
        "staged": ["git", "diff", "--cached"],
        "branch": ["git", "diff", "main...HEAD"],
    }.get(mode, ["git", "diff"])
    try:
        rc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=project_root
        )
        return rc.stdout if rc.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _parse_diff_files(diff_text: str) -> list[str]:
    files: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line.split("/", 1)[1] if "/" in line else line[4:]
            if path not in ("/dev/null",) and path not in files:
                files.append(path)
    return files


def _extract_file_diff(diff_text: str, file_path: str) -> tuple[str, str]:
    hunks: list[str] = []
    in_file = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if f" b/{file_path}" in line or line.endswith(f" {file_path}"):
                in_file = True
                continue
            in_file = False
            continue
        if in_file:
            hunks.append(line)
    return "\n".join(hunks), file_path


def _extract_old_new_from_diff(
    file_diff: str,
) -> tuple[list[str], list[str]]:
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in file_diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            new_lines.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            old_lines.append(line[1:])
        elif not line.startswith("\\"):
            old_lines.append(line[1:] if line.startswith(" ") else line)
            new_lines.append(line[1:] if line.startswith(" ") else line)
    return old_lines, new_lines


def _get_old_source(project_root: str, file_path: str) -> str:
    try:
        rc = subprocess.run(
            ["git", "show", f"HEAD:{file_path}"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root,
        )
        if rc.returncode == 0:
            return rc.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def _get_new_source(project_root: str, file_path: str) -> str:
    abs_path = Path(project_root) / file_path
    try:
        return abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class CodeGraphPRReviewTool(BaseMCPTool):
    """MCP Tool for AI-powered PR review via AST diff + semantic classify + call graph."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None

    def _try_get_cache(self) -> Any:
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            cache.close()
        except Exception:
            pass
        return None

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            cache = self._try_get_cache()
            if cache is not None:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
            else:
                self._call_graph = CallGraph(self.project_root)
        return self._call_graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_pr_review",
            "description": (
                "AI-powered PR review: AST diff + semantic classification + call graph "
                "blast radius. Produces per-file risk verdict, change categories "
                "(api_change, refactor, feature), affected API surface, and actionable "
                "review notes. Supports local diff modes and GitHub PR URLs. "
                "Unlike analyze_change_impact (test-focused), this produces "
                "reviewer-oriented structured analysis. "
                "No other built-in tool provides semantic PR review."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["diff", "staged", "branch", "pr"],
                    "default": "diff",
                    "description": "diff=unstaged, staged=staged, branch=vs main, pr=from GitHub PR URL",
                },
                "pr_url": {
                    "type": "string",
                    "default": "",
                    "description": "GitHub PR URL. Overrides local diff modes.",
                },
                "include_call_graph": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include call graph blast radius analysis",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "diff")
        if mode not in ("diff", "staged", "branch", "pr"):
            raise ValueError("mode must be diff|staged|branch|pr")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        pr_url = arguments.get("pr_url", "") or ""
        mode = "pr" if pr_url else arguments.get("mode", "diff")
        include_cg = arguments.get("include_call_graph", True)
        output_format = arguments.get("output_format", "toon")

        diff_text: str = ""
        changed_files: list[str] = []

        if mode == "pr" and pr_url:
            parsed = parse_pr_url(pr_url)
            if parsed is None:
                return self._format_response(
                    {
                        "success": False,
                        "error": f"Invalid GitHub PR URL: {pr_url}",
                    },
                    output_format,
                )
            if not check_gh_available():
                return self._format_response(
                    {
                        "success": False,
                        "error": "gh CLI not available or not authenticated",
                    },
                    output_format,
                )
            diff_text = fetch_pr_diff(parsed)
            changed_files = _parse_diff_files(diff_text)
        else:
            diff_text = _get_local_diff(mode, self.project_root)
            changed_files = _parse_diff_files(diff_text)

        if not changed_files:
            # pain #9: "CLEAN" wasn't in the canonical verdict set —
            # NOT_FOUND signals "no diff to review" so agents skip
            # downstream PR-review tools.
            return self._format_response(
                {
                    "success": True,
                    "verdict": "NOT_FOUND",
                    "overall_risk": "none",
                    "message": "No changed files found",
                    "files_reviewed": 0,
                },
                output_format,
            )

        changed_files = changed_files[:_MAX_FILES]
        differ = ASTDiffer()
        file_reviews: list[FileReview] = []
        api_changes: list[str] = []
        risk_scores: list[int] = []
        skipped = 0

        for fp in changed_files:
            lang = _language_from_ext(fp)
            if not lang:
                skipped += 1
                continue

            old_src = (
                _get_old_source(self.project_root or ".", fp)
                if self.project_root
                else ""
            )
            new_src = (
                _get_new_source(self.project_root or ".", fp)
                if self.project_root
                else ""
            )

            if not old_src and not new_src:
                skipped += 1
                continue

            diff_result = differ.diff_strings(
                old_src, new_src, lang, old_file=fp, new_file=fp
            )

            classifier = SemanticChangeClassifier(file_path=fp)
            classification = classifier.classify(diff_result)

            high_risk: list[dict[str, Any]] = []
            for ch in classification.classifications:
                if ch.category.value == "api_change":
                    api_changes.append(f"{fp}: {ch.reason}")
                    high_risk.append(ch.to_dict())

            review = FileReview(
                file_path=fp,
                language=lang,
                dominant_category=classification.dominant_category.value,
                risk_level=classification.risk_level,
                change_summary=classification.change_summary,
                category_counts=classification.category_counts,
                hunk_count=len(diff_result.hunks),
                high_risk_hunks=high_risk,
            )
            file_reviews.append(review)
            risk_scores.append(_risk_to_score(classification.risk_level))

        affected_functions: list[dict[str, Any]] = []
        if include_cg and self.project_root and file_reviews:
            affected_functions = self._analyze_call_graph_impact(
                [r.file_path for r in file_reviews]
            )

        overall_score = sum(risk_scores) / len(risk_scores) if risk_scores else 0
        overall_risk = _score_to_risk(overall_score)

        has_api = bool(api_changes)
        has_cg = len(affected_functions) > 5
        if has_api:
            overall_risk = "high"
        if has_api and has_cg:
            overall_risk = "critical"

        verdict = _compute_verdict(
            overall_risk, len(api_changes), len(affected_functions)
        )
        recommendations = _build_recommendations(
            file_reviews, api_changes, affected_functions
        )

        result = PRReviewResult(
            files_reviewed=len(file_reviews),
            files_skipped=skipped,
            overall_risk=overall_risk,
            overall_verdict=verdict,
            file_reviews=file_reviews,
            api_changes=api_changes,
            affected_functions=affected_functions,
            recommendations=recommendations,
        )

        response: dict[str, Any] = {"success": True, **result.to_dict()}
        if pr_url:
            response["pr_url"] = pr_url

        return self._format_response(response, output_format)

    def _analyze_call_graph_impact(
        self, changed_files: list[str]
    ) -> list[dict[str, Any]]:
        try:
            graph = self._get_call_graph()
            graph.build()
        except Exception:
            return []

        affected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for fp in changed_files:
            impact = graph.file_impact(fp)
            for func in impact.get("upstream", [])[:5]:
                key = f"{func.get('file', '')}:{func.get('name', '')}"
                if key not in seen:
                    seen.add(key)
                    affected.append(
                        {
                            "function": func.get("name", ""),
                            "file": func.get("file", ""),
                            "direction": "upstream",
                            "line": func.get("line", 0),
                        }
                    )
            for func in impact.get("downstream", [])[:5]:
                key = f"{func.get('file', '')}:{func.get('name', '')}"
                if key not in seen:
                    seen.add(key)
                    affected.append(
                        {
                            "function": func.get("name", ""),
                            "file": func.get("file", ""),
                            "direction": "downstream",
                            "line": func.get("line", 0),
                        }
                    )
        return affected

    def _format_response(
        self, response: dict[str, Any], output_format: str
    ) -> dict[str, Any]:
        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)


def _compute_verdict(overall_risk: str, api_changes: int, affected_funcs: int) -> str:
    """Map PR risk to the project's canonical verdict vocabulary.

    pain #9 (dogfood pass 2): this previously emitted CLEAN / NEEDS_REVIEW /
    LOOKS_GOOD, which are NOT in the canonical set
    (SAFE/CAUTION/REVIEW/UNSAFE/INFO/WARN/ERROR/NOT_FOUND). Agents
    branching on verdict were never matching these strings and silently
    falling through to default-INFO behavior.

    Mapping:
      critical/high risk  -> CAUTION   (block-worthy, needs human review)
      medium risk OR
        any API changes OR
        >3 affected funcs -> REVIEW    (proceed but verify downstream)
      low risk            -> INFO      (safe to merge)
      else                -> REVIEW    (fail-safe: prefer scrutiny)
    """
    if overall_risk in ("critical", "high"):
        return "CAUTION"
    if overall_risk == "medium" or api_changes > 0 or affected_funcs > 3:
        return "REVIEW"
    if overall_risk == "low":
        return "INFO"
    return "REVIEW"


def _build_recommendations(
    file_reviews: list[FileReview],
    api_changes: list[str],
    affected_functions: list[dict[str, Any]],
) -> list[str]:
    recs: list[str] = []

    if api_changes:
        recs.append(
            f"API breaking changes detected in {len(api_changes)} file(s). "
            "Review backward compatibility before merging."
        )

    high_risk_files = [r for r in file_reviews if r.risk_level in ("high", "critical")]
    if high_risk_files:
        names = [r.file_path for r in high_risk_files[:5]]
        recs.append(
            f"High-risk changes in: {', '.join(names)}. Ensure tests cover these files."
        )

    upstream_funcs = [f for f in affected_functions if f.get("direction") == "upstream"]
    if len(upstream_funcs) > 5:
        recs.append(
            f"Large blast radius: {len(upstream_funcs)} upstream callers affected. "
            "Consider breaking into smaller changes."
        )

    refactor_files = [r for r in file_reviews if r.dominant_category == "refactor"]
    if refactor_files:
        recs.append(
            f"Refactoring in {len(refactor_files)} file(s). "
            "Verify behavior is preserved with integration tests."
        )

    if not recs:
        recs.append("Low-risk change. Standard review recommended.")

    return recs
