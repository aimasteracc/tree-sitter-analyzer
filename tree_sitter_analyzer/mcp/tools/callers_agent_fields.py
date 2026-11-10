"""Agent-native fields of ``nav action=callers`` (RFC-0044, dogfood §12.1/12.2/12.6).

Split out of ``callers_tool.py`` (which re-exports the public names). Every field
here makes a claim an agent will act on without re-checking, so each one may
claim **at most** what its evidence shows:

- ``absence``: ``proven`` only on a complete, fresh, zero-open-site answer; the one
  identification rule (console script) needs the manifest entry to name exactly
  the declaring module file and that file to define the function at module level.
  A shebang or a ``__main__.py`` file proves nothing about one function in it: a
  function those files really run is called from module-level code, so it has a
  ``<module>`` caller and no certificate is needed.
- ``expires_when``: reuse without re-asking is allowed only when the index
  generation is known (a new call in any *other* file invalidates the answer,
  and only the generation can witness that).
- ``answer_etag`` / ``previous_entries``: the fingerprint covers every count the
  answer reports, and a truncated list never produces a delta (``removed``
  cannot be told apart from "beyond the cap").
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

_SCRIPTS_ENTRY_LINE = re.compile(
    r"^\s*([\w.-]+)\s*=\s*[\"']([\w.]+):([\w.]+)", re.MULTILINE
)
_SCRIPT_SECTIONS = frozenset({"project.scripts", "tool.poetry.scripts"})
#: Source roots a console-script module may live under (flat and ``src/`` layouts).
_SOURCE_ROOTS = ("", "src/")

#: Open-site counts: any non-zero value means the empty list is not proven.
_OPEN_SITE_FIELDS = (
    "unresolved_inbound",
    "name_only_inbound",
    "unresolved_in_declaring_files",
    "unattributed_call_sites",
    "non_call_references",
)


def _relative_declaring_path(project_root: str, file_path: str) -> str:
    """``file_path`` relative to the project root, ``/``-separated, normalised."""
    path = file_path
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, project_root)
        except ValueError:  # different drive on Windows
            return ""
    normalized = os.path.normpath(path).replace("\\", "/")
    return "" if normalized.startswith("../") or normalized == ".." else normalized


def _module_candidates(module: str) -> set[str]:
    """Every file stem a console-script module can resolve to."""
    module_path = module.replace(".", "/")
    return {
        f"{root}{module_path}{suffix}"
        for root in _SOURCE_ROOTS
        for suffix in ("", "/__init__")
    }


def _defines_module_function(project_root: str, relative: str, name: str) -> bool:
    """The declaring file defines ``name`` as a module-level (column 0) function."""
    pattern = re.compile(rf"^(?:async[ \t]+)?def[ \t]+{re.escape(name)}[ \t]*\(", re.M)
    try:
        with open(
            os.path.join(project_root, relative), encoding="utf-8", errors="replace"
        ) as handle:
            return pattern.search(handle.read()) is not None
    except OSError:
        return False


def _console_script_evidence(
    project_root: str, function_name: str, *, file_path: str | None = None
) -> str | None:
    """The ``[project.scripts]`` / ``[tool.poetry.scripts]`` line that names it.

    Scanned line by line (``tomllib`` is 3.11+; the floor is 3.10). The entry must
    name the declaring module exactly — path-segment boundary, flat or ``src/``
    layout, ``pkg`` → ``pkg/__init__.py`` — and an undotted attribute equal to the
    function, which the declaring file must define at module level. Anything
    unreadable or ambiguous returns None: no proof, no certificate.
    """
    if not project_root or not file_path or not function_name:
        return None
    relative = _relative_declaring_path(project_root, file_path)
    if not relative:
        return None
    stem = os.path.splitext(relative)[0]
    try:
        with open(
            os.path.join(project_root, "pyproject.toml"),
            encoding="utf-8",
            errors="replace",
        ) as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]").strip()
            continue
        if section not in _SCRIPT_SECTIONS:
            continue
        match = _SCRIPTS_ENTRY_LINE.match(line)
        if match is None:
            continue
        script, module, attr = match.group(1), match.group(2), match.group(3)
        # ``pkg.cli:App.run`` names a method: a module-level ``run`` is not it.
        if attr != function_name or stem not in _module_candidates(module):
            continue
        if not _defines_module_function(project_root, relative, function_name):
            return None
        return f'[{section}] {script} = "{module}:{attr}"'
    return None


def _open_sites(result: dict[str, Any]) -> dict[str, int]:
    return {field: int(result.get(field) or 0) for field in _OPEN_SITE_FIELDS}


def _unproven_absence(result: dict[str, Any], open_sites: dict[str, int]) -> dict:
    """RFC-0044's honest downgrade: an empty list without proof is ``possible``."""
    reasons = list(result.get("completeness_reasons") or [])
    detail = (
        f"completeness={result.get('completeness')!r}; "
        f"unresolved={open_sites['unresolved_inbound']}, "
        f"name_only={open_sites['name_only_inbound']}, "
        f"declaring_file_sites={open_sites['unresolved_in_declaring_files']}, "
        f"module_level_sites={open_sites['unattributed_call_sites']}, "
        f"non_call_references={open_sites['non_call_references']}"
    )
    if result.get("stale"):
        detail += "; stale=True (source changed since indexing)"
    if reasons:
        detail += f"; reasons={', '.join(str(reason) for reason in reasons[:3])}"
    return {
        "kind": "unknown",
        "confidence": "possible",
        "evidence": [{"kind": "incomplete_call_graph", "detail": detail}],
        "next_step": (
            "The empty caller list is not proven: close the open sites above "
            "(resolve or rule out these inbound sites), then ask again."
        ),
    }


def _identification_absence(
    result: dict[str, Any], project_root: str, function_name: str, file_path: str | None
) -> dict[str, Any] | None:
    """Console-script identification on an incomplete answer (RFC-0044, 2026-11-10).

    It asserts "entered from outside the graph", not "no callers", so it does not
    need caller completeness. It does need the symbol: ``SYMBOL_NOT_DEFINED`` never
    gets a certificate, and the declaring file must define the function itself.
    """
    reasons = set(result.get("completeness_reasons") or [])
    if "SYMBOL_NOT_DEFINED" in reasons or not project_root:
        return None
    console = _console_script_evidence(project_root, function_name, file_path=file_path)
    if console is None:
        return None
    return {
        "kind": "entry_point",
        "confidence": "proven",
        "identification_only": True,
        "evidence": [
            {"kind": "console_script", "detail": console},
            {
                "kind": "symbol_defined",
                "detail": (
                    f"{file_path} defines {function_name!r} at module level; the "
                    "certificate claims an external entry, not an absence of callers"
                ),
            },
        ],
        "next_step": (
            "This is an entry point, not dead code: the console script invokes it."
        ),
        "detail": (
            "Caller completeness is not proven here, so this is an identification "
            "(the code is reachable from outside the graph), not an absence claim."
        ),
    }


def absence_certificate(
    result: dict[str, Any],
    *,
    project_root: str = "",
    function_name: str = "",
    file_path: str | None = None,
) -> dict[str, Any] | None:
    """RFC-0044: certify absence only when it is proven, and say why.

    ``proven`` ``unreferenced`` needs: zero callers, ``completeness == "complete"``,
    a fresh (non-stale) answer and zero open sites of any kind. A console-script
    entry upgrades it to ``entry_point``. Otherwise: an identification certificate
    when the console-script rule holds, else ``unknown``/``possible``; a
    ``NOT_FOUND`` answer gets nothing (it may simply not be indexed).
    """
    if result.get("caller_count") != 0:
        return None
    open_sites = _open_sites(result)
    stale = bool(result.get("stale"))
    if result.get("completeness") != "complete" or any(open_sites.values()) or stale:
        identification = (
            None
            if stale
            else _identification_absence(result, project_root, function_name, file_path)
        )
        if identification is not None:
            return identification
        if result.get("verdict") == "NOT_FOUND":
            return None
        return _unproven_absence(result, open_sites)
    base_evidence = {
        "kind": "complete_call_graph",
        "detail": (
            "every required caller check ran; 0 resolved, 0 unresolved, "
            "0 name-only inbound sites"
        ),
    }
    script = _console_script_evidence(project_root, function_name, file_path=file_path)
    if script is not None:
        return {
            "kind": "entry_point",
            "confidence": "proven",
            "evidence": [base_evidence, {"kind": "console_script", "detail": script}],
            "next_step": (
                "This is an entry point, not dead code: it is invoked by the "
                "console script, not by a call edge."
            ),
        }
    return {
        "kind": "unreferenced",
        "confidence": "proven",
        "evidence": [base_evidence],
        "next_step": (
            "Treat the absence as a fact: no call edge in the project reaches "
            "this target."
        ),
    }


#: The reuse contract, stated where the agent reads the scope.
_REUSE_RULE_KNOWN = (
    "Reuse this answer without re-asking only while index_generation is unchanged "
    "AND none of files changed. A new call in any other file also invalidates it; "
    "a changed index_generation (or any doubt) means re-ask, cheaply with "
    "if_none_match=answer_etag."
)
_REUSE_RULE_UNKNOWN = (
    "index_generation is unknown, so a new call added in any other file would go "
    "unnoticed: do not reuse this answer without re-asking. Re-ask with "
    "if_none_match=answer_etag (a match returns {unchanged: true}). files lists "
    "the answer's own inputs, not its full invalidation scope."
)
_REUSE_RULE_STALE = (
    "The answer is stale (source changed since indexing): refresh the index and "
    "re-ask before relying on it."
)


def expires_when(result: dict[str, Any]) -> dict[str, Any]:
    """The answer's invalidation scope (§12.6) and whether it may be reused blind.

    ``files`` (declaring file + caller files) are the answer's inputs, but NOT its
    whole scope: a new call in any other file adds a caller. Only a known, unchanged
    index generation can witness that, so ``reusable_without_reask`` is true only
    when ``index_generation`` is known and the answer is fresh. The generation comes
    from the answer's own ``source_evidence`` (no filesystem probe on warm requests).
    """
    files: set[str] = set()
    declaring = result.get("file_path") or result.get("file")
    if isinstance(declaring, str) and declaring:
        files.add(declaring.replace("\\", "/"))
    for caller in result.get("callers") or []:
        if isinstance(caller, dict):
            path = caller.get("file") or caller.get("file_path")
            if isinstance(path, str) and path:
                files.add(path.replace("\\", "/"))
    evidence = result.get("source_evidence") or {}
    generation = (
        evidence.get("source_generation") if isinstance(evidence, dict) else None
    )
    index_generation = str(generation) if generation else None
    stale = bool(result.get("stale"))
    reusable = index_generation is not None and not stale
    if stale:
        rule = _REUSE_RULE_STALE
    elif reusable:
        rule = _REUSE_RULE_KNOWN
    else:
        rule = _REUSE_RULE_UNKNOWN
    return {
        "files": sorted(files),
        "index_generation": index_generation,
        "reusable_without_reask": reusable,
        "rule": rule,
    }


def _caller_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
    """A caller entry's identity: (file, line, call_site_line, name)."""
    return (
        entry.get("file"),
        entry.get("line"),
        entry.get("call_site_line"),
        entry.get("name"),
    )


def _callers_delta(previous: list[Any], current: list[dict[str, Any]]) -> dict:
    """Delta between two caller lists: added / removed / unchanged_count (§12.2)."""
    previous_set = {
        _caller_identity(entry) for entry in previous if isinstance(entry, dict)
    }
    current_set = {_caller_identity(entry) for entry in current}
    return {
        "added": [
            {key: entry.get(key) for key in ("name", "file", "line", "call_site_line")}
            for entry in current
            if _caller_identity(entry) in current_set - previous_set
        ],
        "removed": [
            entry
            for entry in previous
            if isinstance(entry, dict)
            and _caller_identity(entry) in previous_set - current_set
        ],
        "unchanged_count": len(previous_set & current_set),
    }


def _body_sha(entry: dict[str, Any]) -> str | None:
    body = entry.get("body")
    if not isinstance(body, str):
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def answer_etag(result: dict[str, Any]) -> str:
    """Stable fingerprint of the answer content (dogfood §12.1).

    Covers the question, every listed entry (with inlined body), every count the
    answer reports (including open-site counts, which can change while the
    completeness reasons do not) and the evidence state; excludes timings and
    absolute paths. Pure: no index read.
    """
    payload: dict[str, Any] = {
        "function": result.get("function"),
        "file_path": result.get("file_path"),
        "callers": [
            {
                **{
                    key: entry.get(key)
                    for key in ("name", "file", "line", "call_site_line")
                },
                "body_sha": _body_sha(entry),
            }
            for entry in (result.get("callers") or [])
            if isinstance(entry, dict)
        ],
        "truncated": bool(result.get("truncated", False)),
        "listed": result.get("callers_listed"),
        "caller_count": result.get("caller_count"),
        "completeness": result.get("completeness"),
        "completeness_reasons": result.get("completeness_reasons") or [],
        "freshness": (result.get("source_evidence") or {}).get("freshness"),
        "stale": bool(result.get("stale", False)),
        "absence": result.get("absence"),
    }
    payload.update({field: result.get(field) for field in _OPEN_SITE_FIELDS})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def callers_unchanged_response(
    result: dict[str, Any], requested_etag: str, func_name: str
) -> dict[str, Any] | None:
    """§12.1 If-None-Match: the minimal payload, or None to send the full answer.

    Only a fresh answer whose recomputed fingerprint equals the prior etag is
    reported unchanged; any stale state sends the full answer.
    """
    if (
        not requested_etag
        or requested_etag != result.get("answer_etag")
        or result.get("stale")
    ):
        return None
    return {
        "success": True,
        "verdict": "INFO",
        "unchanged": True,
        "answer_etag": requested_etag,
        "function": func_name,
        "caller_count": result.get("caller_count"),
        "agent_summary": {
            "summary_line": f"callers: {func_name!r} unchanged (etag match)",
            "verdict": "INFO",
            "next_step": (
                "Reuse the previous answer: no caller, completeness or "
                "source-freshness change since that etag."
            ),
        },
    }


def callers_delta_response(
    result: dict[str, Any], previous_entries: Any, func_name: str
) -> dict[str, Any] | None:
    """§12.2 stateless delta, or None to send the full answer.

    No delta for a stale answer, and none for a truncated one: a capped list cannot
    tell a removed caller from one that merely fell beyond the cap.
    """
    if (
        not isinstance(previous_entries, list)
        or not previous_entries
        or result.get("stale")
        or result.get("truncated")
    ):
        return None
    delta = _callers_delta(previous_entries, result.get("callers") or [])
    return {
        "success": True,
        "verdict": "INFO",
        "answer_etag": result.get("answer_etag"),
        "function": func_name,
        "caller_count": result.get("caller_count"),
        # The delta describes this answer: completeness evidence travels with it.
        "completeness": result.get("completeness"),
        "completeness_reasons": result.get("completeness_reasons") or [],
        "truncated": False,
        "delta": delta,
        "agent_summary": {
            "summary_line": (
                f"callers: {func_name!r} delta +{len(delta['added'])} "
                f"-{len(delta['removed'])} ={delta['unchanged_count']} unchanged"
            ),
            "verdict": "INFO",
            "next_step": (
                "Apply the added/removed callers; unchanged entries do not need "
                "to be re-read."
            ),
        },
    }
