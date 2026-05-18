"""Tests for the parser-readiness MCP tool and shared builder."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cli.parser_readiness import build_parser_readiness_advice
from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import ParserReadinessTool


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


@pytest.mark.asyncio
async def test_parser_readiness_tool_returns_json(tmp_path):
    """MCP JSON output should expose the shared parser-readiness shape."""
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.optional-dependencies]
swift = ["tree-sitter-swift>=0.7.2"]
""",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["requested_language"] == "swift"
    readiness = result["readiness"][0]
    signals = readiness["signals"]
    assert readiness["language"] == "swift"
    assert signals["parser_package_version"] == "0.7.2"
    assert signals["parser_project_urls"]["Homepage"].startswith("https://")
    assert signals["parser_maintenance_urls"]["releases"].endswith("/releases")
    assert signals["parser_maintenance_urls"]["actions"].endswith("/actions")
    assert signals["upstream_parser_abi"].startswith("local_binding_abi_")
    assert signals["parser_semantic_version"]
    assert signals["upstream_grammar_json"] in {"not_packaged", "packaged:grammar.json"}
    assert signals["upstream_external_scanner"] != "unknown_local_only"
    assert not any("ABI" in step for step in readiness["next_steps"])
    assert any("grammar.json" in step for step in readiness["next_steps"])
    assert any("scanner" in step for step in readiness["next_steps"])
    assert any(
        signals["parser_maintenance_urls"]["releases"] in step
        for step in readiness["next_steps"]
    )
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
async def test_parser_readiness_toon_includes_readiness_decision_surface(tmp_path):
    """TOON output should keep requested-language parser facts visible."""
    _write_pyproject(
        tmp_path,
        """
[project]
dependencies = []

[project.optional-dependencies]
swift = ["tree-sitter-swift>=0.7.2"]
""",
    )

    result = await ParserReadinessTool(str(tmp_path)).execute(
        {"language": "swift", "output_format": "toon"}
    )

    toon = result["toon_content"]
    assert "readiness:" in toon
    assert "- swift: status=" in toon
    assert "pkg_version=0.7.2" in toon
    assert "url=https://" in toon
    assert "/releases" in toon


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
