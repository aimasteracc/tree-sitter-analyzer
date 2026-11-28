"""Evidence-carrying answers for the unreachable-code tool (#1955).

"Nothing unreachable" is only an answer when some function bodies were
actually checked. With 0 functions analyzed the tool says ``unknown``
(``success: false``, ``error_code: INSUFFICIENT_EVIDENCE``) and names the
exact command that would produce evidence, for the CLI and for MCP.
"""

from __future__ import annotations

from typing import Any

from ...unreachable_code import UnreachableCodeResult
from ...unreachable_code_scan import ProjectUnreachableScan

STATUS_FOUND = "unreachable_found"
STATUS_NONE_FOUND = "none_found"
STATUS_UNKNOWN = "unknown"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

#: Above this many findings the verdict escalates (same ladder as dead code).
_REVIEW_THRESHOLD = 20

_CLI = "tree-sitter-analyzer --unreachable-code"


def project_answer(scan: ProjectUnreachableScan, project_root: str) -> dict[str, Any]:
    """Build the project-mode response from a counted scan."""
    results = scan.results
    blocks = sum(len(r.unreachable_blocks) for r in results)
    failed = [r for r in results if r.errors]
    response: dict[str, Any] = {
        "success": not failed,
        "files_analyzed": scan.files_analyzed,
        "files_with_issues": sum(1 for r in results if r.unreachable_blocks),
        "total_functions_analyzed": scan.functions_analyzed,
        "total_unreachable_blocks": blocks,
        "skipped_test_files": scan.skipped_test_files,
        "truncated": scan.truncated,
        "results": [r.to_dict() for r in results],
    }
    if scan.functions_analyzed == 0:
        return _unknown(response, _project_unknown_reason(scan, project_root))
    _mark_known(response, blocks)
    response["next_step"] = _project_next_step(scan, project_root, blocks, failed)
    return response


def file_answer(result: UnreachableCodeResult) -> dict[str, Any]:
    """Build the file-mode response; 0 functions analyzed is ``unknown``."""
    response: dict[str, Any] = {"success": not result.errors, **result.to_dict()}
    if result.functions_analyzed == 0:
        outline = f'tree-sitter-analyzer --outline "{result.file_path}"'
        reason = (
            f"0 functions analyzed in {result.file_path} "
            f"(language: {result.language}). This check only covers function "
            "bodies, so it has no evidence either way. Confirm what the file "
            f"defines with `{outline}` (MCP: `structure action=outline "
            f'file_path="{result.file_path}"`).'
        )
        return _unknown(response, reason)
    blocks = len(result.unreachable_blocks)
    _mark_known(response, blocks)
    response["next_step"] = (
        "Review each unreachable block (start_line..end_line) before deleting it."
        if blocks
        else f"No unreachable statements in {result.functions_analyzed} function(s)."
    )
    return response


def _mark_known(response: dict[str, Any], blocks: int) -> None:
    response["status"] = STATUS_FOUND if blocks else STATUS_NONE_FOUND
    if not blocks:
        response["verdict"] = "INFO"
    else:
        response["verdict"] = "REVIEW" if blocks > _REVIEW_THRESHOLD else "CAUTION"


def _unknown(response: dict[str, Any], next_step: str) -> dict[str, Any]:
    response.update(
        {
            "success": False,
            "status": STATUS_UNKNOWN,
            # A failure may only carry ERROR / NOT_FOUND, and NOT_FOUND reads
            # as "nothing unreachable found" -- the exact misreading to avoid.
            "verdict": "ERROR",
            "error_code": INSUFFICIENT_EVIDENCE,
            "error": (
                f"{INSUFFICIENT_EVIDENCE}: 0 functions were analyzed, so this is "
                "not a 'nothing unreachable' answer."
            ),
            "next_step": next_step,
        }
    )
    return response


def _project_unknown_reason(scan: ProjectUnreachableScan, root: str) -> str:
    """Name why nothing was analyzed and the exact command that would help."""
    if scan.files_analyzed == 0 and scan.skipped_test_files:
        return (
            f"Only test files were found under {root} "
            f"({scan.skipped_test_files} skipped). Include them: "
            f"`{_CLI} --unreachable-code-mode project --unreachable-code-include-tests "
            f'--project-root "{root}"` (MCP: `health action=unreachable mode=project '
            "include_test_files=true`)."
        )
    if scan.files_analyzed == 0:
        return (
            f"No supported source files under {root}. Point the scan at the "
            f"source tree: `{_CLI} --unreachable-code-mode project --project-root "
            '"<source dir>"` (MCP: `set_project_path` to the source dir, then '
            "`health action=unreachable mode=project`)."
        )
    failed = [r.file_path for r in scan.results if r.errors]
    if failed:
        return (
            f"{len(failed)} of {scan.files_analyzed} file(s) failed to analyze and "
            "the rest define no function. See the parse failure: "
            f'`tree-sitter-analyzer --outline "{failed[0]}" --project-root "{root}"`.'
        )
    sample = scan.sample_file or root
    return (
        f"{scan.files_analyzed} file(s) analyzed but none defines a function, and "
        "this check only covers function bodies. Confirm with "
        f'`tree-sitter-analyzer --outline "{sample}" --project-root "{root}"` '
        f'(MCP: `structure action=outline file_path="{sample}"`).'
    )


def _project_next_step(
    scan: ProjectUnreachableScan,
    root: str,
    blocks: int,
    failed: list[UnreachableCodeResult],
) -> str:
    if blocks:
        step = (
            f"Review the {blocks} unreachable block(s) in results "
            "(start_line..end_line) before deleting them."
        )
    else:
        step = (
            f"No unreachable statements in {scan.functions_analyzed} function(s) "
            f"across {scan.files_analyzed} file(s)."
        )
    if failed:
        step += (
            f" {len(failed)} file(s) failed to analyze (errors > 0 in results); "
            "they are not covered by this answer."
        )
    if scan.truncated:
        step += (
            f" Scan stopped at max_files={scan.files_analyzed}; files beyond it were "
            f"not checked. Re-run: `{_CLI} --unreachable-code-mode project "
            f'--unreachable-code-max-files {scan.files_analyzed * 2} --project-root "{root}"` '
            f"(MCP: `health action=unreachable mode=project "
            f"max_files={scan.files_analyzed * 2}`)."
        )
    return step
