#!/usr/bin/env python3
"""Change-impact MCP tool bound to frozen source epochs."""

from typing import Any

from ...pr_url import (
    check_gh_available,
    fetch_pr_changed_files,
    fetch_pr_diff_stat,
    parse_pr_url,
)
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool, mirror_summary_line
from .change_impact_support import (
    _JOURNAL_VERDICT_RANK as _JOURNAL_VERDICT_RANK,
)
from .change_impact_support import (
    TOOL_SCHEMA,
    _canonicalize_change_impact_verdict,
    _enrich_with_journal_decisions,
    _pr_gh_unavailable_envelope,
    _pr_invalid_url_envelope,
    _scope_paths_invalid,
    _snapshot_records,
)
from .utils.change_impact_analysis import (
    ChangeImpactRequest,
    _build_change_impact_result,
)
from .utils.change_impact_git import (
    _get_changed_files,
    _get_diff_stat,
)
from .utils.change_impact_response import (
    apply_scope_validation,
    attach_queue_ledger,
    build_agent_summary_only_response,
    build_no_changes_result,
)


class ChangeImpactTool(BaseMCPTool):
    """Analyze the impact of code changes using git diff + dependency graph."""

    _capture_diff_snapshot_default: bool = False

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "analyze_change_impact",
            "description": (
                "Post-edit blast-radius scan: combines ``git diff`` (staged "
                "+ unstaged) with the project dependency graph to compute "
                "which files are affected, which test files must re-run, "
                "and a risk verdict (SAFE / REVIEW / WARN). Optionally "
                "accepts ``scope_paths`` to restrict the analysis to a "
                "subset of the diff. MUST be called after every non-trivial "
                "edit before declaring work done — the built-in tools have "
                "no view of dependency edges or test coverage.\n\n"
                "WHEN TO USE:\n"
                "- After ANY non-trivial edit before declaring 'done'\n"
                "- To pick which tests are worth running (vs the full suite)\n"
                "- To detect changes to high-fan-in files needing extra review\n"
                "- For PR risk summaries (diff against base branch)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Before editing — use safe_to_edit instead\n"
                "- For symbol-level rename — use modification_guard\n"
                "- To see WHO calls a symbol — use trace_impact\n"
                "\n"
                "VERDICT INTEGRITY: agent_summary.verdict is the blast-radius gate, "
                "not a tone signal. It is computed from the actual changed-file set, "
                "dependency edges, and impacted test count — not from the user's "
                "framing. If the user says 'just ship it' or 'is this safe to merge?' "
                "and this tool returns REVIEW / WARN / UNSAFE / ERROR, the calling "
                "agent MUST report that verdict verbatim and surface the impacted "
                "files. Do NOT rewrite a REVIEW/WARN as SAFE/INFO to keep the user "
                "moving. Legal vocabulary: SAFE / CAUTION / REVIEW / UNSAFE / INFO / "
                "WARN / ERROR / NOT_FOUND."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate mode + scope_mode arguments."""
        if "mode" in arguments and arguments["mode"] not in (
            "diff",
            "staged",
            "branch",
            "pr",
        ):
            raise ValueError("mode must be diff|staged|branch|pr")
        if "scope_mode" in arguments and arguments["scope_mode"] not in (
            "report",
            "strict",
        ):
            raise ValueError("scope_mode must be report|strict")
        if "resource_profile" in arguments and arguments["resource_profile"] not in (
            "default",
            "local_low_impact",
        ):
            raise ValueError("resource_profile must be default|local_low_impact")
        return True

    def _attach_diff_snapshot(
        self,
        result: dict[str, Any],
        mode: str,
        enabled: bool,
        assessed_scope_paths: list[str] | None = None,
        *,
        frozen: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        """Attach an artifact captured before analysis; never capture after it."""
        del mode, assessed_scope_paths
        if not enabled:
            return result
        if frozen is None or not frozen.get("success"):
            code = str((frozen or {}).get("error_code", "DIFF_SNAPSHOT_CAPTURE_ERROR"))
            return {
                "success": False,
                "verdict": "ERROR",
                "error_code": code,
                "error": code,
                "output_format": result.get("output_format", "toon"),
            }
        result.update({key: value for key, value in frozen.items() if key != "success"})
        return result

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Analyze git diff + dependency graph for change impact."""
        pr_url = arguments.get("pr_url", "") or ""
        mode = "pr" if pr_url else arguments.get("mode", "diff")
        include_tests = arguments.get("include_tests", True)
        output_format = arguments.get("output_format", "toon")
        scope_paths = arguments.get("scope_paths") or []
        scope_mode = arguments.get("scope_mode", "report")
        # MCP callers are always AI agents; default to low-impact so verification
        # commands don't stall the local machine. CLI uses its own default (#731).
        resource_profile = arguments.get("resource_profile", "local_low_impact")
        agent_summary_only = bool(arguments.get("agent_summary_only", False))
        compact_only = bool(arguments.get("compact_only", False))
        capture_diff_snapshot = bool(
            arguments.get(
                "capture_diff_snapshot",
                getattr(self, "_capture_diff_snapshot_default", False),
            )
        )
        frozen: dict[str, object] | None = None
        frozen_consumer: Any = None
        if capture_diff_snapshot:
            if mode not in ("diff", "staged"):
                code = "DIFF_SNAPSHOT_UNSUPPORTED_MODE"
                return {
                    "success": False,
                    "verdict": "ERROR",
                    "error_code": code,
                    "error": code,
                }
            from ...diff_snapshot_registry import REGISTRY
            from ...source_oracle import SourceOracleError, normalize_repo_path

            try:
                normalized_scope = [
                    normalize_repo_path(str(path)) for path in scope_paths
                ]
            except SourceOracleError as exc:
                code = str(exc)
                return {
                    "success": False,
                    "verdict": "ERROR",
                    "error_code": code,
                    "error": code,
                }
            frozen = REGISTRY.create(self.project_root, mode, normalized_scope)
            if not frozen.get("success"):
                code = str(frozen["error_code"])
                return {
                    "success": False,
                    "verdict": "ERROR",
                    "error_code": code,
                    "error": code,
                }
            frozen_consumer, error = REGISTRY.acquire(
                str(frozen["diff_snapshot_id"]), self.project_root
            )
            if error:
                REGISTRY.close_lease(
                    str(frozen["diff_snapshot_id"]), str(frozen["route_lease_id"])
                )
                return {
                    "success": False,
                    "verdict": "ERROR",
                    "error_code": error,
                    "error": error,
                }

        def finish_frozen(result: dict[str, Any]) -> dict[str, Any]:
            if frozen_consumer is None:
                return self._attach_diff_snapshot(
                    result, mode, capture_diff_snapshot, frozen=frozen
                )
            affected = result.get("affected_files") or []
            assert frozen is not None
            assessed = [str(record["path"]) for record in _snapshot_records(frozen)]
            assessed.extend(
                str(item.get("path", "") if isinstance(item, dict) else item)
                for item in affected
                if (item.get("path") if isinstance(item, dict) else item)
            )
            verify_error = REGISTRY.bind_assessed_scope(frozen_consumer, assessed)
            if verify_error is None:
                verify_error = REGISTRY.verify(frozen_consumer)
            frozen["assessed_scope_paths"] = list(
                frozen_consumer.snapshot.assessed_scope_paths
            )
            frozen_consumer.release()
            if verify_error:
                REGISTRY.close_lease(
                    str(frozen["diff_snapshot_id"]), str(frozen["route_lease_id"])
                )
                return {
                    "success": False,
                    "verdict": "ERROR",
                    "error_code": verify_error,
                    "error": verify_error,
                    "output_format": result.get("output_format", "toon"),
                }
            return self._attach_diff_snapshot(result, mode, True, frozen=frozen)

        # H8: validate scope paths against disk so a typo cannot silently
        # become "scope matched nothing". The analysis still runs on the
        # remaining valid scope (if any) — we only mark the invalid ones.
        if frozen is not None:
            frozen_paths = [str(record["path"]) for record in _snapshot_records(frozen)]
            scope_paths_invalid = [
                path
                for path in scope_paths
                if not any(
                    candidate == path.rstrip("/")
                    or candidate.startswith(path.rstrip("/") + "/")
                    for candidate in frozen_paths
                )
            ]
        else:
            scope_paths_invalid = _scope_paths_invalid(self.project_root, scope_paths)

        if mode == "pr" and pr_url:
            return self._execute_pr_analysis(
                pr_url,
                include_tests,
                output_format,
                scope_paths,
                agent_summary_only,
                scope_mode=scope_mode,
                resource_profile=resource_profile,
                compact_only=compact_only,
            )

        if frozen is not None:
            workspace_changed_files = [
                str(record["path"]) for record in _snapshot_records(frozen)
            ]
            changed_files = workspace_changed_files
            if scope_paths:
                changed_files = [
                    path
                    for path in workspace_changed_files
                    if any(
                        path == scope.rstrip("/")
                        or path.startswith(scope.rstrip("/") + "/")
                        for scope in scope_paths
                    )
                ]
        else:
            changed_files = _get_changed_files(mode, self.project_root, scope_paths)
            workspace_changed_files = (
                _get_changed_files(mode, self.project_root, []) if scope_paths else []
            )

        if not changed_files:
            result = build_no_changes_result(mode, scope_paths)
            result["scope_paths"] = scope_paths
            result["scope_filtered"] = bool(scope_paths)
            result = attach_queue_ledger(
                result,
                mode=mode,
                scope_paths=scope_paths,
                scoped_changed_files=changed_files,
                workspace_changed_files=workspace_changed_files,
                scope_mode=scope_mode,
            )
            result = apply_scope_validation(result, scope_paths_invalid)
            if agent_summary_only:
                result = build_agent_summary_only_response(result)
            result["output_format"] = output_format
            # F1 (round-37f7): defensive verdict canonicalization in
            # the no-changes path. ``apply_scope_validation`` already
            # stamps ``CHANGE_IMPACT_VERDICT_CLEAN`` (now ``"SAFE"``)
            # but a legacy import path or future helper could
            # re-introduce the old ``"CLEAN"`` literal — fold any
            # drift back to the canonical vocabulary so the no-changes
            # envelope can never ship a non-canonical verdict.
            _canonicalize_change_impact_verdict(result)
            # M5/M10: mirror summary_line + verdict between top-level and
            # agent_summary so direct callers (tests, hive-mind workers)
            # see the same envelope shape as MCP-routed callers.
            result = mirror_summary_line(result)
            result = finish_frozen(result)
            return apply_toon_format_to_response(
                result, output_format, compact_only=compact_only
            )

        diff_stat = (
            f"{len(changed_files)} frozen file(s) changed"
            if frozen is not None
            else _get_diff_stat(mode, self.project_root, scope_paths)
        )
        result = _build_change_impact_result(
            ChangeImpactRequest(
                mode=mode,
                changed_files=changed_files,
                diff_stat=diff_stat,
                project_root=self.project_root,
                include_tests=include_tests,
                scope_paths=scope_paths,
                agent_summary_only=agent_summary_only,
                resource_profile=resource_profile,
                read_only=capture_diff_snapshot,
            )
        )
        # r37fG phase 3: surface related decision_journal entries and
        # upgrade the envelope verdict if any matched decision is more
        # severe than the change-impact builder's primary verdict. The
        # journal stays advisory — never downgrades, never raises.
        if not capture_diff_snapshot:
            _enrich_with_journal_decisions(result, self.project_root, changed_files)
        result = attach_queue_ledger(
            result,
            mode=mode,
            scope_paths=scope_paths,
            scoped_changed_files=changed_files,
            workspace_changed_files=workspace_changed_files,
            scope_mode=scope_mode,
        )
        result = apply_scope_validation(result, scope_paths_invalid)
        if agent_summary_only:
            result = build_agent_summary_only_response(result)
        result["output_format"] = output_format
        # F1 (round-37f7): same defensive canonicalization as the
        # no-changes path — guarantees the cross-tool envelope sees
        # only canonical verdict tokens regardless of which builder
        # helper populated them.
        _canonicalize_change_impact_verdict(result)
        # M5/M10: mirror summary_line + verdict between top-level and
        # agent_summary so direct callers see the same envelope shape as
        # MCP-routed callers.
        result = mirror_summary_line(result)
        result = finish_frozen(result)
        return apply_toon_format_to_response(
            result, output_format, compact_only=compact_only
        )

    def _execute_pr_analysis(
        self,
        pr_url: str,
        include_tests: bool,
        output_format: str,
        scope_paths: list[str],
        agent_summary_only: bool,
        *,
        scope_mode: str = "report",
        resource_profile: str = "default",
        compact_only: bool = False,
    ) -> dict[str, Any]:
        """Analyze a GitHub PR's diff via gh CLI.

        r37em (dogfood): 95→~25 lines. Pre-flight envelopes moved to
        ``_pr_invalid_url_envelope`` / ``_pr_gh_unavailable_envelope``;
        shared postprocessing (PR fields → queue ledger → scope validation
        → summary-only → mirror → TOON) collapsed into ``_finalize_pr_result``.
        """
        parsed = parse_pr_url(pr_url)
        if parsed is None:
            return _pr_invalid_url_envelope(pr_url, output_format)

        if not check_gh_available():
            return _pr_gh_unavailable_envelope(parsed, output_format)

        # H8: validate scope paths against disk (PR mode treats them as
        # path prefixes from the local checkout).
        scope_paths_invalid = _scope_paths_invalid(self.project_root, scope_paths)

        changed_files = fetch_pr_changed_files(parsed)
        if scope_paths:
            changed_files = [
                f
                for f in changed_files
                if any(f.startswith(s.rstrip("/")) for s in scope_paths)
            ]

        if not changed_files:
            return self._finalize_pr_result(
                build_no_changes_result("pr", scope_paths),
                parsed=parsed,
                scope_paths=scope_paths,
                scope_paths_invalid=scope_paths_invalid,
                changed_files=[],
                agent_summary_only=agent_summary_only,
                output_format=output_format,
                scope_mode=scope_mode,
                compact_only=compact_only,
            )

        diff_stat = fetch_pr_diff_stat(parsed)
        result = _build_change_impact_result(
            ChangeImpactRequest(
                mode="pr",
                changed_files=changed_files,
                diff_stat=diff_stat,
                project_root=self.project_root,
                include_tests=include_tests,
                scope_paths=scope_paths,
                agent_summary_only=agent_summary_only,
                resource_profile=resource_profile,
            )
        )
        return self._finalize_pr_result(
            result,
            parsed=parsed,
            scope_paths=scope_paths,
            scope_paths_invalid=scope_paths_invalid,
            changed_files=changed_files,
            agent_summary_only=agent_summary_only,
            output_format=output_format,
            scope_mode=scope_mode,
            compact_only=compact_only,
        )

    @staticmethod
    def _finalize_pr_result(
        result: dict[str, Any],
        *,
        parsed: Any,
        scope_paths: list[str],
        scope_paths_invalid: Any,
        changed_files: list[str],
        agent_summary_only: bool,
        output_format: str,
        scope_mode: str = "report",
        compact_only: bool = False,
    ) -> dict[str, Any]:
        """Attach PR metadata + queue ledger + scope validation, mirror, and TOON.

        Shared by both the no-changes and with-changes branches of
        ``_execute_pr_analysis``. ``changed_files`` doubles as both
        ``scoped_changed_files`` and ``workspace_changed_files`` because
        PR mode pulls them from the same gh-CLI source.

        M5/M10: ``mirror_summary_line`` syncs ``summary_line`` + ``verdict``
        between top-level and ``agent_summary`` so direct callers see the
        same envelope shape regardless of routing.
        """
        result["pr_url"] = parsed.url
        result["pr_number"] = parsed.pr_number
        result["repo"] = parsed.slug
        result = attach_queue_ledger(
            result,
            mode="pr",
            scope_paths=scope_paths,
            scoped_changed_files=changed_files,
            workspace_changed_files=changed_files,
            scope_mode=scope_mode,
        )
        result = apply_scope_validation(result, scope_paths_invalid)
        if agent_summary_only:
            result = build_agent_summary_only_response(result)
        result["output_format"] = output_format
        # F1 (round-37f7): defensive canonicalization for the PR-mode
        # path. Mirrors the same protection applied in the diff-mode
        # branches above — keeps the cross-tool envelope free of
        # non-canonical verdict tokens regardless of which mode the
        # caller used.
        _canonicalize_change_impact_verdict(result)
        result = mirror_summary_line(result)
        return apply_toon_format_to_response(
            result, output_format, compact_only=compact_only
        )
