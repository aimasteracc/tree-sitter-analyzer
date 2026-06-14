"""Parser readiness advisor for language plugin roadmap decisions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cli.parser_readiness_records import build_language_records
from tree_sitter_analyzer.cli.parser_readiness_sources import (
    WIKI_READINESS_SIGNALS,
    collect_readiness_inputs,
    detect_parser_package_warnings,
    normalize_language,
    parser_package_requirements,
)

# Strict allowlist pattern: must be a safe language identifier token.
# Rejects path traversal ('../'), shell metacharacters (';', '|', '&', ' '),
# and any other string that cannot be a valid language name.
_LANG_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def build_parser_readiness_advice(
    project_root: str,
    *,
    language: str | None = None,
    include_supported: bool = False,
) -> dict[str, Any]:
    """Build a local parser-readiness report for language plugin planning."""
    if language is not None:
        raw = language.strip()
        if not raw or not _LANG_NAME_RE.match(raw):
            return {
                "success": False,
                "error": (
                    f"unknown language {language!r}; "
                    "language names must match ^[a-z][a-z0-9_-]{{0,31}}$ — "
                    "see implemented_languages list"
                ),
                "error_type": "validation",
                "agent_summary": {
                    "summary_line": "parser-readiness: invalid language name",
                    "next_step": (
                        "Provide a valid language name such as 'python', 'javascript', "
                        "or 'typescript'. Run without --parser-readiness-language to "
                        "see implemented_languages."
                    ),
                    "verdict": "ERROR",
                },
            }
    root = Path(project_root).expanduser().resolve()
    try:
        inputs = collect_readiness_inputs(root)
    except ValueError as exc:
        return {
            "success": False,
            "error_type": "validation",
            "error": str(exc),
            "agent_summary": {"verdict": "ERROR", "next_step": str(exc)},
        }
    requested_language = normalize_language(language) if language else None
    records = _build_report_records(
        root,
        inputs,
        requested_language=requested_language,
        include_supported=include_supported,
    )
    recommendations = _build_recommendations(records)
    agent_summary = _build_agent_summary(records, recommendations, requested_language)
    return _build_result(
        root,
        inputs,
        requested_language,
        records,
        recommendations,
        agent_summary,
    )


def _build_report_records(
    root: Path,
    inputs: dict[str, Any],
    *,
    requested_language: str | None,
    include_supported: bool,
) -> list[dict[str, Any]]:
    """Build readiness records without hiding hardening gaps.

    The old selection logic only compared parser packages against plugin
    entrypoints. That let languages with a plugin but no golden-master or
    missing parser wiring disappear from the default roadmap. Build records
    first, then filter out only languages that are genuinely supported.
    """
    if requested_language:
        report_languages = [requested_language]
    else:
        report_languages = sorted(
            set(inputs["parser_packages"]) | set(inputs["plugin_entrypoints"])
        )
    records = build_language_records(root, report_languages, inputs)
    if include_supported or requested_language:
        return records
    return [record for record in records if record["status"] != "supported"]


def _build_result(
    root: Path,
    inputs: dict[str, Any],
    requested_language: str | None,
    records: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    agent_summary: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the final parser-readiness response."""
    result = _base_result(root, requested_language)
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
    _ensure_no_gap_consistency(result)
    # G7: build a one-line top-level summary so callers reading
    # ``response["summary_line"]`` get a non-None value. The agent_summary
    # mirror is set in the same step so both stay in sync.
    summary_line = _build_summary_line(result, recommendations)
    agent_summary["summary_line"] = summary_line
    result["summary_line"] = summary_line
    # N4: mirror ``verdict`` to the top-level envelope so direct CLI
    # callers see the same shape as MCP-routed dispatch (which already
    # symmetrises top/agent via ``mirror_summary_line`` /
    # ``ensure_canonical_success_envelope``). The agent_summary surface
    # is the source of truth.
    verdict = agent_summary.get("verdict")
    if isinstance(verdict, str) and verdict:
        result["verdict"] = verdict
    result["toon_content"] = _build_toon_content(result)
    return result


def _build_summary_line(
    result: dict[str, Any],
    recommendations: list[dict[str, Any]],
) -> str:
    """Build the canonical one-line headline for parser-readiness output."""
    implemented = result.get("implemented_language_count", 0)
    candidates = len(recommendations)
    risk = result.get("agent_summary", {}).get("risk", "low")
    top = recommendations[0]["language"] if recommendations else ""
    line = (
        f"parser_readiness implemented={implemented} "
        f"candidates={candidates} risk={risk}"
    )
    if top:
        line += f" top={top}"
    return line


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
        # r37o (dogfood): surface pyproject hygiene warnings — when the
        # same parser package is declared in multiple locations with
        # different version constraints, agents reading
        # ``parser_packages.<lang>`` cannot tell which one is binding.
        # Diagnostic only; does not change install behaviour or escalate
        # the readiness verdict (those are about parser wiring, not
        # manifest tidiness).
        "parser_package_warnings": detect_parser_package_warnings(parser_packages),
    }


def _status_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    """Return a compact status histogram for workflow-aware prioritization."""
    distribution: dict[str, int] = {}
    for record in records:
        status = record["status"]
        distribution[status] = distribution.get(status, 0) + 1
    return distribution


def _ensure_no_gap_consistency(result: dict[str, Any]) -> None:
    """When no gaps are reported, populate empty fields with explicit
    "all-ready" markers so callers don't read ``reported_language_count=0
    implemented_language_count=19`` as a contradiction.

    Mutates ``result`` in place; safe to call after the main assembly.
    """
    if result.get("readiness"):
        result["reported_language_count"] = len(result["readiness"])
        return
    if result.get("reported_language_count", 0) > 0:
        return
    implemented_count = result.get("implemented_language_count", 0)
    if implemented_count <= 0:
        return
    # Mirror the implemented inventory into the reported fields so the
    # summary line "X languages ready" works without special-casing.
    result["reported_language_count"] = implemented_count
    distribution = result.get("status_distribution") or {}
    if not distribution:
        result["status_distribution"] = {"ready": implemented_count}
    agent_summary = result.get("agent_summary")
    if isinstance(agent_summary, dict):
        if agent_summary.get("reported_language_count", 0) <= 0:
            agent_summary["reported_language_count"] = implemented_count


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
) -> dict[str, Any]:
    """Build the agent_summary block for parser-readiness output.

    N4 (round-29 dogfood): the success path used to omit ``verdict``
    even though :data:`_N_VERDICT_VOCABULARY` (envelope contract) requires
    it on every tool. We derive ``verdict`` from the existing ``risk``
    field — kept for backward compatibility — using the canonical
    informational-tool mapping:

    - 0 missing parsers (``risk=low``) → ``INFO``
    - 1-2 missing parsers (``risk=caution``) → ``CAUTION``
    - 3+ missing parsers → ``REVIEW`` and ``risk=high``
      (escalates the existing ``caution`` because a fleet of missing
      parsers is a real roadmap gap the caller should look at).
    """
    first = recommendations[0] if recommendations else None
    candidate_count = len(recommendations)
    if candidate_count >= 3:
        risk = "high"
        verdict = "REVIEW"
    elif first:
        risk = "caution"
        verdict = "CAUTION"
    else:
        risk = "low"
        verdict = "INFO"
    return {
        "risk": risk,
        "verdict": verdict,
        "requested_language": requested_language,
        "candidate_count": candidate_count,
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
        f"req_spec={signals.get('parser_required_spec') or '-'}",
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
