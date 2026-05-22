"""Parser readiness advisor for language plugin roadmap decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cli.parser_readiness_records import build_language_records
from tree_sitter_analyzer.cli.parser_readiness_sources import (
    WIKI_READINESS_SIGNALS,
    collect_readiness_inputs,
    normalize_language,
    parser_package_requirements,
    select_report_languages,
)


def build_parser_readiness_advice(
    project_root: str,
    *,
    language: str | None = None,
    include_supported: bool = False,
) -> dict[str, Any]:
    """Build a local parser-readiness report for language plugin planning."""
    root = Path(project_root).expanduser().resolve()
    inputs = collect_readiness_inputs(root)
    requested_language = normalize_language(language) if language else None
    report_languages = select_report_languages(
        inputs["parser_packages"],
        inputs["plugin_entrypoints"],
        requested_language=requested_language,
        include_supported=include_supported,
    )
    records = build_language_records(root, report_languages, inputs)
    recommendations = _build_recommendations(records)
    verdict = _parser_readiness_verdict(records, requested_language)
    agent_summary = _build_agent_summary(
        records, recommendations, requested_language, verdict
    )
    return _build_result(
        root,
        inputs,
        requested_language,
        records,
        recommendations,
        agent_summary,
        verdict,
    )


def _build_result(
    root: Path,
    inputs: dict[str, Any],
    requested_language: str | None,
    records: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    agent_summary: dict[str, Any],
    verdict: str,
) -> dict[str, Any]:
    """Assemble the final parser-readiness response."""
    result = _base_result(root, requested_language)
    result["verdict"] = verdict
    result.update(_metadata_summary(inputs, records))
    result.update(
        {
            "readiness": records,
            "recommendations": recommendations,
            "status_distribution": _status_distribution(records),
            "high_priority_languages": _high_priority_languages(recommendations),
            "agent_summary": agent_summary,
        }
    )
    result["toon_content"] = _build_toon_content(result)
    return result


def _parser_readiness_verdict(
    records: list[dict[str, Any]],
    requested_language: str | None,
) -> str:
    """Map readiness state to canonical verdict vocabulary.

    Anti-bias: when in doubt, err toward higher severity.

    - All requested languages supported (or no candidates) → INFO
    - Has a parser dependency declared but plugin/loader missing → REVIEW
    - Missing parser package entirely → CAUTION
    """
    # Focus on the requested language when provided; otherwise look across all.
    relevant = records
    if requested_language:
        relevant = [
            r for r in records if r["language"] == requested_language
        ] or records
    statuses = {r["status"] for r in relevant}
    if "missing_parser_package" in statuses:
        return "CAUTION"
    if statuses & {"needs_hardening", "candidate"}:
        return "REVIEW"
    return "INFO"


def _base_result(root: Path, requested_language: str | None) -> dict[str, Any]:
    """Return result fields that do not depend on parser inventory size."""
    return {
        "success": True,
        "advisor": "parser readiness",
        "project_root": str(root),
        "source": "local pyproject, plugin registry, loader mapping, tests, golden masters",
        "wiki_inspired_signals": WIKI_READINESS_SIGNALS,
        "requested_language": requested_language,
    }


def _metadata_summary(
    inputs: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return compact inventory counts and package display fields."""
    parser_packages = inputs["parser_packages"]
    plugin_entrypoints = inputs["plugin_entrypoints"]
    return {
        "implemented_language_count": len(plugin_entrypoints),
        "declared_parser_package_count": len(parser_packages),
        "candidate_count": _candidate_count(records),
        "implemented_languages": sorted(plugin_entrypoints),
        "parser_packages": parser_package_requirements(parser_packages),
    }


def _status_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    """Return a compact status histogram for workflow-aware prioritization."""
    distribution: dict[str, int] = {}
    for record in records:
        status = record["status"]
        distribution[status] = distribution.get(status, 0) + 1
    return distribution


def _high_priority_languages(recommendations: list[dict[str, Any]]) -> list[str]:
    """Expose top language names by score for quick CLI triage."""
    return [item["language"] for item in recommendations[:3]]


def _candidate_count(records: list[dict[str, Any]]) -> int:
    return sum(1 for record in records if record["status"] != "supported")


def _build_recommendations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [record for record in records if record["status"] != "supported"]
    candidates.sort(key=lambda item: (-item["score"], item["language"]))
    return [_recommendation(record) for record in candidates[:5]]


def _recommendation(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "language": record["language"],
        "status": record["status"],
        "score": record["score"],
        "next_step": record["next_steps"][0] if record["next_steps"] else "",
        "verification_command": record["verification_commands"][0],
    }


def _build_agent_summary(
    records: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    requested_language: str | None,
    verdict: str = "INFO",
) -> dict[str, Any]:
    first = recommendations[0] if recommendations else None
    return {
        "verdict": verdict,
        "risk": "caution" if first else "low",
        "requested_language": requested_language,
        "candidate_count": len(recommendations),
        "next_step": _summary_next_step(first),
        "verification_command": _summary_verification_command(first),
        "stop_condition": "Parser roadmap output names a next language, readiness gaps, and verification command.",
        "reported_language_count": len(records),
    }


def _summary_next_step(first: dict[str, Any] | None) -> str:
    if first:
        return first["next_step"]
    return "No local parser-roadmap gaps found. Inspect supported languages with include_supported=true."


def _summary_verification_command(first: dict[str, Any] | None) -> str:
    if first:
        return first["verification_command"]
    return "uv run tree-sitter-analyzer parser-readiness --format json"


def _build_toon_content(result: dict[str, Any]) -> str:
    summary = result["agent_summary"]
    status_distribution = result.get("status_distribution", {})
    lines = [
        "advisor: parser readiness",
        f"risk: {summary['risk']}",
        f"reported_language_count: {summary['reported_language_count']}",
        f"candidate_count: {summary['candidate_count']}",
        "status_distribution: "
        + ", ".join(
            f"{key}={status_distribution[key]}" for key in sorted(status_distribution)
        ),
        f"top_priority_languages: {', '.join(result.get('high_priority_languages', []))}",
        f"next_step: {summary['next_step']}",
        f"verification_command: {summary['verification_command']}",
        "readiness:",
    ]
    lines.extend(_toon_readiness_lines(result["readiness"]))
    lines.append("recommendations:")
    lines.extend(_toon_recommendation_lines(result["recommendations"]))
    return "\n".join(lines)


def _toon_readiness_lines(records: list[dict[str, Any]]) -> list[str]:
    return [_toon_readiness_line(record) for record in records[:5]]


def _toon_readiness_line(record: dict[str, Any]) -> str:
    signals = record["signals"]
    project_url = _readiness_url(signals)
    parts = [
        f"status={record['status']}",
        f"score={record['score']}",
        f"parser={record['parser_package'] or '-'}",
        f"pkg_version={signals.get('parser_package_version') or '-'}",
        f"abi={signals.get('upstream_parser_abi') or '-'}",
        f"grammar={signals.get('upstream_grammar_json') or '-'}",
        f"scanner={signals.get('upstream_external_scanner') or '-'}",
        f"maintenance={signals.get('upstream_maintenance') or '-'}",
    ]
    if project_url:
        parts.append(f"url={project_url}")
    return f"  - {record['language']}: " + " ".join(parts)


def _first_project_url(project_urls: dict[str, str]) -> str:
    if not project_urls:
        return ""
    return next(iter(project_urls.values()))


def _readiness_url(signals: dict[str, Any]) -> str:
    maintenance_urls = signals.get("parser_maintenance_urls", {})
    if maintenance_urls:
        return maintenance_urls.get("releases") or maintenance_urls.get(
            "repository", ""
        )
    return _first_project_url(signals.get("parser_project_urls", {}))


def _toon_recommendation_lines(recommendations: list[dict[str, Any]]) -> list[str]:
    return [
        f"  - {item['language']}: status={item['status']} score={item['score']} next={item['next_step']}"
        for item in recommendations
    ]
