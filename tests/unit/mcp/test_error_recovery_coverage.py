"""Cover the canonical error envelope built by error_recovery.py.

After the envelope standardization, every error response has 5 canonical keys
(``success`` / ``error`` / ``error_type`` / ``agent_summary`` / ``summary_line``)
plus the legacy ``error_category`` / ``recovery_hint`` / ``suggested_tool``
fields that older consumers may still read.

``error_type`` is now a machine-readable kind (``validation``,
``file_not_found``, ``subprocess``, ``internal``) — NOT the Python exception
class name. Tests below pin both the new contract and the preserved legacy
aliases.
"""

from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
    build_agent_friendly_error,
    ensure_canonical_error_envelope,
    ensure_canonical_success_envelope,
)


def _assert_canonical(result: dict) -> None:
    """Every error envelope must carry the 5 canonical keys."""
    for key in ("success", "error", "error_type", "agent_summary", "summary_line"):
        assert key in result, f"missing canonical key {key!r}"
    assert result["success"] is False
    assert isinstance(result["agent_summary"], dict)
    assert result["agent_summary"].get("verdict") == "ERROR"
    # Wave 1a (audit search-01/viz-01/project-02): the verdict MUST be mirrored
    # to the TOP LEVEL too, exactly as the success path does (search_envelope
    # normalize_envelope / _mirror_verdict). An agent reading ``result["verdict"]``
    # — the documented r37w contract — must get a value on errors, not KeyError.
    assert result.get("verdict") == "ERROR", (
        "error envelope must hoist verdict to the top level so agents can "
        "branch on result['verdict'] uniformly across success and error"
    )
    assert result["verdict"] == result["agent_summary"]["verdict"], (
        "top-level verdict must equal agent_summary.verdict (r37w mirror, "
        "now enforced on the error axis too)"
    )


class TestBuildAgentFriendlyError:
    def test_file_not_found_pattern(self):
        err = FileNotFoundError("file not found at /tmp/missing.js")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "file_not_found"
        assert result["error_type"] == "file_not_found"
        assert result["suggested_tool"] == "project action=files"

    def test_unsupported_language_pattern(self):
        err = ValueError("unsupported language: .xyz")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "language_unsupported"
        assert "suggested_tool" not in result

    def test_project_root_pattern(self):
        err = RuntimeError("project root has not been configured")
        result = build_agent_friendly_error("analyze_dependencies", err)
        _assert_canonical(result)
        assert result["error_category"] == "project_not_set"
        assert result["suggested_tool"] == "set_project_path"

    def test_outside_boundary_pattern(self):
        err = PermissionError("outside project boundary detected")
        result = build_agent_friendly_error("read_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "security_violation"
        assert "suggested_tool" not in result

    def test_missing_parameter_pattern(self):
        # ``required`` message is now classified as ``validation`` — the
        # historical ``missing_parameter`` value collapsed into the broader
        # ``validation`` bucket so agents have one consistent name for any
        # input-shape failure.
        err = TypeError("file_path is required")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "validation"
        assert result["error_type"] == "validation"
        assert "suggested_tool" not in result

    def test_blast_radius_required_keeps_xref_guidance(self):
        # #668: the blast_radius "function_names is required ..." message also
        # contains "required", so the blast_radius-specific rule MUST win over
        # the generic "required" rule — otherwise the agent-facing recovery_hint
        # / next_step lose the file-level xref guidance and #668 isn't fixed on
        # the real MCP error path.
        err = ValueError(
            "function_names is required for blast_radius mode; "
            "for file-level dependents use nav action=xref mode=file"
        )
        result = build_agent_friendly_error("codegraph_impact", err)
        _assert_canonical(result)
        assert result["error_type"] == "validation"
        assert result["suggested_tool"] == "nav action=xref mode=file"
        assert "nav action=xref mode=file" in result["recovery_hint"]
        assert result["agent_summary"]["next_step"] == result["recovery_hint"]

    def test_validation_error_pattern(self):
        err = ValueError("format must be one of: full, compact")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "validation"
        assert result["error_type"] == "validation"

    def test_resource_exhausted_pattern(self):
        err = MemoryError("out of memory during analysis")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "resource_exhausted"
        assert "suppress_output" in result["recovery_hint"]

    def test_timeout_pattern(self):
        err = TimeoutError("operation timed out after 30s")
        result = build_agent_friendly_error("search_content", err)
        _assert_canonical(result)
        assert result["error_category"] == "timeout"
        assert "scope" in result["recovery_hint"]

    def test_unknown_error_category(self):
        # When no message rule fires, the exception class falls back through
        # the canonical-class table. ``RuntimeError`` → ``internal``.
        err = RuntimeError("something completely unexpected")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_category"] == "internal"
        assert result["error_type"] == "internal"
        assert "Review the error message" in result["recovery_hint"]
        assert "suggested_tool" not in result

    def test_error_message_preserved(self):
        # SEC-2: absolute paths are redacted to <external-path>, but the
        # rest of the message + the exception class name are preserved so
        # the agent can still reason about the failure.
        err = FileNotFoundError("file not found: /tmp/test.py")
        result = build_agent_friendly_error("analyze_file", err)
        assert "FileNotFoundError" in result["error"]
        assert "file not found" in result["error"]
        assert "/tmp/test.py" not in result["error"]
        assert "<external-path>" in result["error"]

    def test_error_type_canonical_for_memory_error(self):
        # ``MemoryError`` → matches the "memory" pattern hint, so the
        # error_type is the canonical ``resource_exhausted`` (not the Python
        # class name).
        err = MemoryError("out of memory")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert result["error_type"] == "resource_exhausted"

    def test_suggested_tool_with_file_not_found(self):
        err = FileNotFoundError("not found: missing.py")
        result = build_agent_friendly_error("analyze_file", err)
        _assert_canonical(result)
        assert "suggested_tool" in result
        assert result["suggested_tool"] == "project action=files"

    def test_identifier_mirrored_from_arguments(self):
        err = ValueError("File not found: missing.py")
        result = build_agent_friendly_error(
            "analyze_file",
            err,
            arguments={"file_path": "missing.py"},
        )
        _assert_canonical(result)
        assert result["file_path"] == "missing.py"
        assert "missing.py" in result["summary_line"]


class TestEnsureCanonicalErrorEnvelope:
    """Tools that already return ``{success: False, ...}`` get the canonical
    keys added without losing their tool-specific fields.
    """

    def test_adds_canonical_keys_to_minimal_dict(self):
        response = {"success": False, "error": "fd failed", "returncode": 1}
        result = ensure_canonical_error_envelope(
            "find_and_grep", response, arguments={"query": "foo"}
        )
        _assert_canonical(result)
        # Tool-specific field is preserved.
        assert result["returncode"] == 1
        # Identifier from arguments is mirrored.
        assert result.get("query") == "foo"

    def test_preserves_existing_canonical_fields(self):
        response = {
            "success": False,
            "error": "boom",
            "error_type": "subprocess",
            "summary_line": "custom: subprocess",
            "agent_summary": {
                "summary_line": "custom: subprocess",
                "next_step": "do thing",
                "verdict": "ERROR",
            },
        }
        result = ensure_canonical_error_envelope("find_and_grep", response)
        assert result["summary_line"] == "custom: subprocess"
        assert result["agent_summary"]["next_step"] == "do thing"
        assert result["error_type"] == "subprocess"

    def test_skips_success_responses(self):
        response = {"success": True, "count": 5}
        result = ensure_canonical_error_envelope("find_and_grep", response)
        # No envelope keys added when success is True.
        assert "agent_summary" not in result
        assert "summary_line" not in result

    def test_hoists_verdict_to_top_level(self):
        """Wave 1a: a tool that returns a bare {success: False} dict gets a
        top-level ``verdict`` mirrored from the canonical agent_summary."""
        response = {"success": False, "error": "boom", "error_type": "subprocess"}
        result = ensure_canonical_error_envelope("find_and_grep", response)
        assert result["verdict"] == "ERROR"
        assert result["verdict"] == result["agent_summary"]["verdict"]

    def test_preserves_tool_specific_top_level_verdict(self):
        """A tool that already set a more specific top-level verdict (e.g.
        NOT_FOUND) keeps it — the hoist must not clobber it with ERROR, and
        the agent_summary mirrors the same value."""
        response = {
            "success": False,
            "error": "no match",
            "error_type": "validation",
            "verdict": "NOT_FOUND",
        }
        result = ensure_canonical_error_envelope("query", response)
        assert result["verdict"] == "NOT_FOUND"
        assert result["agent_summary"]["verdict"] == "NOT_FOUND"

    def test_na_placeholder_treated_as_missing_verdict(self):
        """The ``n/a`` post-hook placeholder must NOT be promoted to a
        top-level verdict — it counts as missing, so the error envelope falls
        back to ERROR (consistent with _mirror_verdict's sentinel handling)."""
        response = {
            "success": False,
            "error": "boom",
            "error_type": "internal",
            "verdict": "n/a",
            "agent_summary": {"verdict": "n/a"},
        }
        result = ensure_canonical_error_envelope("query", response)
        assert result["verdict"] == "ERROR"
        assert result["agent_summary"]["verdict"] == "ERROR"


class TestSuccessEnvelopeNextStepMirror:
    """Wave 1b batch B (audit nav-03/04, search-05, project-03, viz-05, health-04):
    tools that set a rich TOP-LEVEL ``next_step`` left ``agent_summary.next_step``
    empty. The canonical success envelope must mirror the top-level value so an
    agent reading ``agent_summary.next_step`` (the documented place) gets the
    real guidance, not ``""``."""

    def test_top_level_next_step_mirrored_into_agent_summary(self):
        response = {
            "success": True,
            "verdict": "INFO",
            "next_step": "Answer from the inlined body — no Read needed.",
        }
        result = ensure_canonical_success_envelope("nav", response)
        assert (
            result["agent_summary"]["next_step"]
            == "Answer from the inlined body — no Read needed."
        )

    def test_existing_agent_summary_next_step_is_not_clobbered(self):
        response = {
            "success": True,
            "verdict": "INFO",
            "next_step": "top-level value",
            "agent_summary": {"next_step": "tool-specific value"},
        }
        result = ensure_canonical_success_envelope("nav", response)
        assert result["agent_summary"]["next_step"] == "tool-specific value"

    def test_no_next_step_anywhere_stays_empty_string(self):
        response = {"success": True, "verdict": "INFO"}
        result = ensure_canonical_success_envelope("nav", response)
        # Contract unchanged when there is nothing to mirror.
        assert result["agent_summary"]["next_step"] == ""
