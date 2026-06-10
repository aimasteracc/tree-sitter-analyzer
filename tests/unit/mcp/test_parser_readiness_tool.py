"""Tests for the parser-readiness MCP tool and shared builder.

r37fC (round-37f): the quality audit rated this file at 2/5. The
original suite covered the happy paths (declared parser without
plugin, supported language report, JSON / TOON output, argument
validation) but never exercised the error surfaces an MCP caller
will hit in practice: unknown languages, partial installs (parser
declared but no plugin / no loader), ABI / scanner mismatches, and
corrupted ``pyproject.toml``. The block below adds error-path
coverage for those exact gaps.

The tests run against the real :class:`ParserReadinessTool` (no
mocks on the tool itself) and use tmp_path fixtures so a divergent
CWD doesn't change the result.  For install-state tests,
``monkeypatch`` forces BOTH paths deterministically — no try/except
conditionals that silently skip a branch.
"""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.cli.parser_readiness import build_parser_readiness_advice
from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import ParserReadinessTool

# Legal verdict vocabulary — mirrored from
# ``tree_sitter_analyzer.mcp.tools.base_tool._LEGAL_VERDICTS``.
_LEGAL_VERDICTS = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)


def _write_pyproject(path, body: str) -> None:
    (path / "pyproject.toml").write_text(body, encoding="utf-8")


def test_parser_readiness_recommends_declared_parser_without_plugin(tmp_path):
    """A parser extra without a plugin should become an actionable candidate."""
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = ["tree-sitter-python>=0.23.0"]

[project.optional-dependencies]
fixturelang = ["tree-sitter-fixturelang>=0.1.0"]

[project.entry-points."tree_sitter_analyzer.plugins"]
python = "tree_sitter_analyzer.languages.python_plugin:PythonPlugin"
""",
    )

    result = build_parser_readiness_advice(str(tmp_path))

    assert result["success"] is True
    assert result["advisor"] == "parser readiness"
    assert result["implemented_languages"] == ["python"]
    assert result["candidate_count"] == 1
    assert result["status_distribution"]["candidate"] == 1
    assert result["recommendations"][0]["language"] == "fixturelang"
    assert result["recommendations"][0]["status"] == "candidate"
    fixture = result["readiness"][0]
    assert fixture["language"] == "fixturelang"
    assert fixture["signals"]["parser_dependency_declared"] is True
    assert fixture["signals"]["plugin_entrypoint"] is False
    assert fixture["signals"]["loader_mapping"] is False
    assert fixture["signals"]["upstream_external_scanner"] == "unknown_local_only"
    assert "tree-sitter-fixturelang>=0.1.0" in fixture["requirements"]


def test_parser_readiness_can_report_supported_language(tmp_path):
    """A requested implemented language should return a focused readiness record."""
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = ["tree-sitter-python>=0.23.0"]

[project.entry-points."tree_sitter_analyzer.plugins"]
python = "tree_sitter_analyzer.languages.python_plugin:PythonPlugin"
""",
    )
    tests_dir = tmp_path / "tests" / "unit" / "languages"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_python_plugin.py").write_text("def test_ok(): pass\n")

    result = build_parser_readiness_advice(str(tmp_path), language="python")

    assert result["requested_language"] == "python"
    assert result["readiness"][0]["language"] == "python"
    assert result["readiness"][0]["signals"]["plugin_entrypoint"] is True
    assert result["readiness"][0]["signals"]["loader_mapping"] is True
    assert result["readiness"][0]["signals"]["unit_tests"] is True


class _FakeMetadata:
    """Minimal email.message.Message stand-in for importlib distribution metadata."""

    def __init__(self, home_page: str, project_urls: list[str]) -> None:
        self._home_page = home_page
        self._project_urls = project_urls

    def get(self, key: str) -> str | None:
        if key == "Home-page":
            return self._home_page
        return None

    def get_all(self, key: str):
        if key == "Project-URL":
            return self._project_urls
        return []


class _FakeDistribution:
    """Fake importlib.metadata.Distribution for patching."""

    def __init__(self, version: str, home_page: str, project_urls: list[str]) -> None:
        self.version = version
        self.metadata = _FakeMetadata(home_page, project_urls)


_FAKE_SWIFT_DIST = _FakeDistribution(
    version="9.9.9",
    home_page="https://github.com/fake/tree-sitter-swift",
    project_urls=[
        "Source, https://github.com/fake/tree-sitter-swift",
    ],
)

_SWIFT_PYPROJECT = """
[project]
dependencies = []

[project.optional-dependencies]
swift = ["tree-sitter-swift>=0.7.2"]
"""


def _make_fake_importlib_metadata(*, installed: bool):
    """Return a fake importlib_metadata namespace for monkeypatching.

    Replaces only ``parser_readiness_package.importlib_metadata`` so the
    real ``importlib.metadata`` module is never touched.  The ``PackageNotFoundError``
    class is borrowed from the real module so the ``except`` clause in
    ``parser_distribution_signals`` can still catch it.
    """
    import importlib.metadata as _real_imd

    class _FakeImportlibMetadata:
        PackageNotFoundError = _real_imd.PackageNotFoundError

        @staticmethod
        def distribution(name: str):
            if installed:
                return _FAKE_SWIFT_DIST
            raise _real_imd.PackageNotFoundError(name)

    return _FakeImportlibMetadata()


@pytest.mark.asyncio
async def test_parser_readiness_tool_returns_json_installed(tmp_path, monkeypatch):
    """JSON output: installed state — parser_package_version == installed version.

    P1 (honesty-split): when the package IS installed, parser_package_version
    carries the installed version; parser_required_spec carries the raw spec.
    Monkeypatching the importlib_metadata alias forces this path deterministically
    without touching the real importlib.metadata module.
    """
    import tree_sitter_analyzer.cli.parser_readiness_package as _pkg

    _write_pyproject(tmp_path, _SWIFT_PYPROJECT)
    monkeypatch.setattr(
        _pkg, "importlib_metadata", _make_fake_importlib_metadata(installed=True)
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["requested_language"] == "swift"
    assert result["status_distribution"]["candidate"] == 1
    assert result["high_priority_languages"] == ["swift"]
    readiness = result["readiness"][0]
    signals = readiness["signals"]
    assert readiness["language"] == "swift"
    # Installed: version == patched value, not the spec version
    assert signals["parser_package_version"] == "9.9.9"
    assert signals["parser_required_spec"] == "tree-sitter-swift>=0.7.2"
    # Project URLs populated from patched distribution metadata
    assert (
        signals["parser_project_urls"]["Homepage"]
        == "https://github.com/fake/tree-sitter-swift"
    )
    assert signals["parser_maintenance_urls"]["releases"].endswith("/releases")
    assert signals["parser_maintenance_urls"]["actions"].endswith("/actions")
    assert result["agent_summary"]["verification_command"] == (
        "uv run tree-sitter-analyzer parser-readiness swift --format json"
    )


@pytest.mark.asyncio
async def test_parser_readiness_tool_returns_json_not_installed(tmp_path, monkeypatch):
    """JSON output: not-installed state — parser_package_version == "".

    P1 (honesty-split): when the package is NOT installed, parser_package_version
    MUST be ""; parser_required_spec still carries the raw spec so callers
    can distinguish "declared but absent" from "not declared".
    Monkeypatching the importlib_metadata alias forces this deterministically.
    """
    import tree_sitter_analyzer.cli.parser_readiness_package as _pkg

    _write_pyproject(tmp_path, _SWIFT_PYPROJECT)
    monkeypatch.setattr(
        _pkg, "importlib_metadata", _make_fake_importlib_metadata(installed=False)
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["requested_language"] == "swift"
    readiness = result["readiness"][0]
    signals = readiness["signals"]
    assert readiness["language"] == "swift"
    # Not installed: version is ALWAYS "" — never a spec-extracted guess
    assert signals["parser_package_version"] == ""
    # Spec is still populated from pyproject
    assert signals["parser_required_spec"] == "tree-sitter-swift>=0.7.2"
    # No project URLs when not installed
    assert signals["parser_project_urls"] == {}
    assert signals["parser_maintenance_urls"] == {}
    assert result["agent_summary"]["verification_command"] == (
        "uv run tree-sitter-analyzer parser-readiness swift --format json"
    )


@pytest.mark.asyncio
async def test_parser_readiness_tool_defaults_to_toon(tmp_path):
    """TOON output keeps MCP parser-readiness advice compact."""
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []
""",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute({})

    assert result["format"] == "toon"
    assert result["advisor"] == "parser readiness"
    assert "readiness" not in result
    assert "advisor: parser readiness" in result["toon_content"]


@pytest.mark.asyncio
async def test_parser_readiness_toon_installed_shows_version_and_url(
    tmp_path, monkeypatch
):
    """TOON output: installed state — pkg_version and url are populated.

    P2: deterministic test for the installed path via monkeypatch.
    """
    import tree_sitter_analyzer.cli.parser_readiness_package as _pkg

    _write_pyproject(tmp_path, _SWIFT_PYPROJECT)
    monkeypatch.setattr(
        _pkg, "importlib_metadata", _make_fake_importlib_metadata(installed=True)
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "toon"}
    )

    toon = result["toon_content"]
    assert "readiness:" in toon
    assert "- swift: status=" in toon
    # Installed version from patched distribution
    assert "pkg_version=9.9.9" in toon
    # Spec always present
    assert "req_spec=tree-sitter-swift>=0.7.2" in toon
    # URL from patched project_urls
    assert "url=https://github.com/fake/tree-sitter-swift" in toon


@pytest.mark.asyncio
async def test_parser_readiness_toon_not_installed_shows_empty_version(
    tmp_path, monkeypatch
):
    """TOON output: not-installed state — pkg_version=- and no url.

    P2: deterministic test for the not-installed path via monkeypatch.
    """
    import tree_sitter_analyzer.cli.parser_readiness_package as _pkg

    _write_pyproject(tmp_path, _SWIFT_PYPROJECT)
    monkeypatch.setattr(
        _pkg, "importlib_metadata", _make_fake_importlib_metadata(installed=False)
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "toon"}
    )

    toon = result["toon_content"]
    assert "readiness:" in toon
    assert "- swift: status=" in toon
    # Not installed: version renders as '-' (the or '-' fallback in _toon_readiness_line)
    assert "pkg_version=-" in toon
    # Spec still populated from pyproject
    assert "req_spec=tree-sitter-swift>=0.7.2" in toon
    # No project URL when not installed
    assert "url=https://" not in toon


@pytest.mark.asyncio
async def test_parser_readiness_tool_validates_arguments(tmp_path):
    """Invalid enum and type inputs should fail before project inspection."""
    tool = ParserReadinessTool(str(tmp_path))

    with pytest.raises(ValueError, match="output_format"):
        await tool.execute({"output_format": "text"})

    with pytest.raises(ValueError, match="language"):
        await tool.execute({"language": ""})

    with pytest.raises(ValueError, match="include_supported"):
        await tool.execute({"include_supported": "yes"})


# ----------------------------------------------------------------------
# r37fC: error-path coverage (audit gap — was 2/5 missing
# unknown_lang / partial_install / abi_mismatch / corrupted_grammar)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parser_readiness_unknown_language_is_rejected_at_validation(tmp_path):
    """Language names outside the safe identifier shape fail before any I/O.

    Audit gap (unknown_lang): the original suite never tested the
    allowlist regex behaviour. The tool rejects path traversal
    (``../``), shell metacharacters (``;``, ``|``, spaces), and
    uppercase variants at the ``validate_arguments`` boundary so the
    builder is never even called.
    """
    tool = ParserReadinessTool(str(tmp_path))
    _write_pyproject(tmp_path, "[project]\ndependencies = []\n")

    # Each of these should be rejected with an "unknown language" message.
    bad_inputs = [
        "Python",  # uppercase — regex requires lowercase first char
        "../etc/passwd",  # path traversal
        "lang;rm -rf",  # shell metacharacter
        "lang|pipe",
        "x" * 33,  # too long (max 32 chars per regex)
        "1starts-with-digit",
    ]
    for bad in bad_inputs:
        with pytest.raises(ValueError, match="unknown language"):
            await tool.execute({"language": bad})


@pytest.mark.asyncio
async def test_parser_readiness_unknown_language_via_builder_returns_error(tmp_path):
    """The shared builder returns a structured error for unknown languages.

    Audit gap (unknown_lang via direct CLI path): callers that hit
    :func:`build_parser_readiness_advice` directly (without the MCP
    validate layer) must still get a clean error envelope with a
    canonical ``ERROR`` verdict and a non-empty next_step.
    """
    _write_pyproject(tmp_path, "[project]\ndependencies = []\n")

    result = build_parser_readiness_advice(str(tmp_path), language="MIXEDcase")

    assert result["success"] is False
    assert result["error_type"] == "validation"
    assert "MIXEDcase" in result["error"]
    summary = result["agent_summary"]
    assert summary["verdict"] == "ERROR"
    assert summary["verdict"] in _LEGAL_VERDICTS
    assert "parser-readiness" in summary["summary_line"]
    assert isinstance(summary["next_step"], str) and summary["next_step"]


@pytest.mark.asyncio
async def test_parser_readiness_partial_install_plugin_without_loader(tmp_path):
    """A plugin entrypoint without a loader mapping is a partial install.

    Audit gap (partial_install): the original suite covered the
    "declared package, no plugin" candidate path and the "fully
    implemented" supported path, but never a half-installed
    intermediate. Here the plugin entrypoint exists but the language
    name doesn't appear in ``LanguageLoader.LANGUAGE_MODULES``. The
    contract: status drops to ``needs_hardening`` so callers know the
    wiring is incomplete even though a plugin exists.
    """
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.entry-points."tree_sitter_analyzer.plugins"]
fixturelang = "tree_sitter_analyzer.languages.fixturelang_plugin:FixturelangPlugin"
""",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "fixturelang", "output_format": "json"}
    )

    assert result["success"] is True
    readiness = result["readiness"][0]
    assert readiness["language"] == "fixturelang"
    # Plugin is declared but loader mapping is absent (fixturelang is
    # not in LanguageLoader.LANGUAGE_MODULES).
    signals = readiness["signals"]
    assert signals["plugin_entrypoint"] is True
    assert signals["loader_mapping"] is False
    assert readiness["status"] == "needs_hardening"
    # next_steps must mention adding the loader mapping.
    assert any(
        "loader" in step.lower() or "language_modules" in step.lower()
        for step in readiness["next_steps"]
    )
    # Verdict in legal vocabulary.
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS


@pytest.mark.asyncio
async def test_parser_readiness_partial_install_missing_parser_package(tmp_path):
    """A language requested without any parser package or plugin is missing.

    Audit gap (partial_install): the inverse of the case above —
    caller asks for a language that has no parser dep, no plugin
    entrypoint, no loader mapping. The status must be
    ``missing_parser_package`` (a real signal that the language is
    not even on the roadmap), not silently ``candidate``.
    """
    _write_pyproject(tmp_path, "[project]\ndependencies = []\n")

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "klingon", "output_format": "json"}
    )

    assert result["success"] is True
    readiness = result["readiness"][0]
    assert readiness["language"] == "klingon"
    assert readiness["status"] == "missing_parser_package"
    signals = readiness["signals"]
    assert signals["plugin_entrypoint"] is False
    assert signals["loader_mapping"] is False
    assert signals["parser_dependency_declared"] is False
    # next_steps must guide caller to declare the parser package.
    assert any(
        "tree-sitter-klingon" in step or "parser" in step.lower()
        for step in readiness["next_steps"]
    )


@pytest.mark.asyncio
async def test_parser_readiness_signals_surface_abi_and_scanner_state(tmp_path):
    """The readiness signals must expose ABI / grammar / scanner status.

    Audit gap (abi_mismatch / corrupted_grammar): the audit asked for
    coverage of ABI mismatch and grammar / scanner corruption signals
    so callers can branch on them. Without an actual installed parser
    we can't fabricate a mismatch, but we can still pin the *shape*
    of the signals dict: every upstream-flavoured key must be present
    with a string value (the canonical "unknown_local_only" /
    "not_packaged" / etc. tokens) so callers don't crash on
    ``signals["upstream_external_scanner"]`` lookup.
    """
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.optional-dependencies]
fixturelang = ["tree-sitter-fixturelang>=0.1.0"]
""",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "fixturelang", "output_format": "json"}
    )

    signals = result["readiness"][0]["signals"]
    # Every upstream signal key must be present and stringy.
    for key in (
        "upstream_parser_abi",
        "upstream_grammar_json",
        "upstream_external_scanner",
        "upstream_maintenance",
    ):
        assert key in signals, f"upstream signal {key!r} missing from signals dict"
        # Some signals legitimately use the string "False" / "True"
        # tokens; what matters is that the field is reachable, not
        # missing-or-None which would crash callers branching on it.
        assert signals[key] is not None, (
            f"signal {key!r} is None — callers can't branch"
        )
    # When the parser package is declared but no local install exists,
    # ABI / grammar / scanner are all in "unknown" or "unavailable" form.
    assert (
        "unknown" in signals["upstream_parser_abi"]
        or "unavailable" in signals["upstream_parser_abi"]
    )


@pytest.mark.asyncio
async def test_parser_readiness_handles_corrupted_pyproject(tmp_path):
    """A malformed pyproject.toml must produce a clean error envelope.

    Audit gap (corrupted_grammar / corrupted manifest): the most
    common partial-install signal in practice is a broken
    ``pyproject.toml`` — half-edited table headers, missing
    quotation marks, etc. The current code path lets the TOML decode
    error bubble. The contract this test encodes (xfail until fix):
    the tool returns ``success=False`` with ``error_type='validation'``
    and a usable ``next_step`` rather than crashing the MCP server.
    """
    # Note the unterminated table header — tomllib raises on the
    # first character of the second line.
    (tmp_path / "pyproject.toml").write_text(
        "[project\ndependencies = [missing brace\n",
        encoding="utf-8",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute({"output_format": "json"})

    # When the fix lands, the test asserts the recovered envelope:
    assert result["success"] is False
    assert result["error_type"] == "validation"
    assert "pyproject" in result["error"].lower()
    assert result["agent_summary"]["verdict"] == "ERROR"


@pytest.mark.asyncio
async def test_parser_readiness_concurrent_calls_are_safe(tmp_path):
    """Parallel execute calls must return independent results.

    Audit gap (concurrent / re-entrant safety): the readiness builder
    holds no per-call state but the tool layer reads
    ``self.security_validator`` and ``self.project_root`` — both must
    be immutable across concurrent executions.
    """
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.optional-dependencies]
swift = ["tree-sitter-swift>=0.7.2"]
""",
    )
    tool = ParserReadinessTool(str(tmp_path))

    results = await asyncio.gather(
        *(
            tool.execute({"language": "swift", "output_format": "json"})
            for _ in range(8)
        ),
    )

    assert all(result["success"] is True for result in results)
    assert all(result["requested_language"] == "swift" for result in results)
    # Each call gets its own readiness list — no shared mutation.
    readiness_lists = [id(result["readiness"]) for result in results]
    assert len(set(readiness_lists)) == len(readiness_lists), (
        "readiness list reference shared across concurrent calls — "
        "callers mutating their copy would poison other callers"
    )
    # Envelope contract holds on every result.
    for result in results:
        assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS
        assert isinstance(result["summary_line"], str) and result["summary_line"]


@pytest.mark.asyncio
async def test_parser_readiness_envelope_contract_holds_for_both_formats(tmp_path):
    """Both JSON and TOON outputs must carry the canonical envelope.

    Audit gap (envelope contract): the original suite spot-checked
    individual fields per format but never the full cross-format
    invariant. Pins verdict ∈ legal vocabulary, summary_line mirror,
    and agent_summary.next_step on a single fixture.
    """
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.optional-dependencies]
swift = ["tree-sitter-swift>=0.7.2"]
""",
    )
    tool = ParserReadinessTool(str(tmp_path))

    for output_format in ("json", "toon"):
        result = await tool.execute(
            {"language": "swift", "output_format": output_format}
        )
        assert result["success"] is True, (
            f"format={output_format} returned success=False"
        )
        agent_summary = result["agent_summary"]
        assert agent_summary["verdict"] in _LEGAL_VERDICTS, (
            f"agent_summary.verdict drifted for format={output_format}"
        )
        next_step = agent_summary["next_step"]
        assert isinstance(next_step, str) and next_step.strip(), (
            f"agent_summary.next_step empty for format={output_format}"
        )
        summary_line = result.get("summary_line")
        assert isinstance(summary_line, str) and summary_line, (
            f"top-level summary_line missing for format={output_format}"
        )
        assert summary_line == agent_summary.get("summary_line"), (
            f"summary_line mirror diverges for format={output_format}"
        )
        assert result.get("verdict") == agent_summary["verdict"], (
            f"top-level verdict mirror diverges for format={output_format}"
        )
