"""Unit tests for project overview agent guidance."""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
    ProjectOverviewTool,
    _add_file_to_scan,
    _add_path_to_scan,
    _build_agent_summary,
    _build_base_result,
    _build_health_alert,
    _build_result,
    _build_smart_hint,
    _build_tool_routing,
    _count_lines,
    _health_opt_in_hint,
    _increment,
    _new_scan,
    _overview_next_step,
    _overview_risk,
    _scan_project,
    _suggest_refactor_action,
    _top_language,
)


def _run(coro):
    return asyncio.run(coro)


def _write(tmp_path, rel, content, encoding="utf-8"):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return p


class TestProjectOverviewExecute:
    def test_execute_basic_json(self, tmp_path) -> None:
        _write(tmp_path, "src/app.py", "def main():\n    return 1\n")
        _write(tmp_path, "notes.txt", "not source\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(
            tool.execute(
                {"include_health": False, "max_depth": 5, "output_format": "json"}
            )
        )

        assert result["success"] is True
        assert result["summary"]["source_files"] == 1
        assert result["summary"]["non_source_files"] == 1
        assert result["agent_summary"]["top_language"] == "python"
        assert "project_health" in result["tool_routing"]

    def test_execute_toon_format(self, tmp_path) -> None:
        _write(tmp_path, "app.py", "x = 1\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(
            tool.execute(
                {"include_health": False, "max_depth": 5, "output_format": "toon"}
            )
        )

        assert "toon_content" in result

    def test_execute_no_project_root_raises(self) -> None:
        tool = ProjectOverviewTool()
        with pytest.raises(ValueError, match="Project root not set"):
            _run(tool.execute({"max_depth": 5}))

    def test_execute_invalid_root_raises(self, tmp_path) -> None:
        tool = ProjectOverviewTool(project_root=str(tmp_path / "nonexistent"))
        with pytest.raises(ValueError, match="not a directory"):
            _run(tool.execute({"max_depth": 5}))

    def test_execute_empty_project(self, tmp_path) -> None:
        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(tool.execute({"output_format": "json", "max_depth": 5}))

        assert result["success"] is True
        assert result["summary"]["source_files"] == 0
        assert result["summary"]["total_files"] == 0
        assert result["agent_summary"]["top_language"] == ""
        assert result["agent_summary"]["largest_file"] == ""

    def test_execute_multi_language_project(self, tmp_path) -> None:
        _write(tmp_path, "app.py", "x = 1\n")
        _write(tmp_path, "main.java", "class Main {}\n")
        _write(tmp_path, "index.ts", "const x = 1;\n")
        _write(tmp_path, "style.css", "body {}\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(tool.execute({"output_format": "json", "max_depth": 5}))

        assert result["summary"]["languages_count"] == 4
        assert "python" in result["language_distribution"]
        assert "java" in result["language_distribution"]
        assert "typescript" in result["language_distribution"]
        assert "css" in result["language_distribution"]


class TestValidateArguments:
    def test_validate_default_max_depth(self) -> None:
        tool = ProjectOverviewTool()
        assert tool.validate_arguments({}) is True

    def test_validate_valid_max_depth(self) -> None:
        tool = ProjectOverviewTool()
        assert tool.validate_arguments({"max_depth": 10}) is True

    def test_validate_max_depth_zero_raises(self) -> None:
        tool = ProjectOverviewTool()
        with pytest.raises(ValueError, match="between 1 and 20"):
            tool.validate_arguments({"max_depth": 0})

    def test_validate_max_depth_too_large_raises(self) -> None:
        tool = ProjectOverviewTool()
        with pytest.raises(ValueError, match="between 1 and 20"):
            tool.validate_arguments({"max_depth": 21})

    def test_validate_max_depth_string_raises(self) -> None:
        tool = ProjectOverviewTool()
        with pytest.raises(ValueError, match="between 1 and 20"):
            tool.validate_arguments({"max_depth": "five"})


class TestToolDefinition:
    def test_get_tool_definition(self) -> None:
        tool = ProjectOverviewTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "get_project_overview"
        assert "inputSchema" in defn
        assert "include_health" in defn["inputSchema"]["properties"]

    def test_get_tool_schema(self) -> None:
        tool = ProjectOverviewTool()
        schema = tool.get_tool_schema()
        assert schema["type"] == "object"
        assert "max_depth" in schema["properties"]


class TestScanProject:
    def test_scan_excludes_node_modules(self, tmp_path) -> None:
        _write(tmp_path, "src/visible.py", "print('hi')\n")
        _write(tmp_path, "node_modules/hidden.py", "print('hidden')\n")

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["lang_dist"] == {"python": 1}

    def test_scan_excludes_git(self, tmp_path) -> None:
        _write(tmp_path, "app.py", "x = 1\n")
        _write(tmp_path, ".git/config", "stuff\n")

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["lang_dist"] == {"python": 1}
        assert ".git" not in scan["dir_tree"]

    def test_scan_excludes_pytest_cache(self, tmp_path) -> None:
        _write(tmp_path, "test.py", "def test_x(): pass\n")
        _write(tmp_path, ".pytest_cache/v/cache/stepid", "x\n")

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["lang_dist"] == {"python": 1}

    def test_scan_respects_max_depth(self, tmp_path) -> None:
        _write(tmp_path, "a.py", "x = 1\n")
        _write(tmp_path, "d1/d2/d3/d4/d5/d6/deep.py", "x = 1\n")

        scan = _scan_project(tmp_path, max_depth=3)

        assert scan["lang_dist"] == {"python": 1}

    def test_scan_sorts_source_files_by_lines(self, tmp_path) -> None:
        _write(tmp_path, "small.py", "x = 1\n")
        _write(tmp_path, "big.py", "\n".join(f"line{i}" for i in range(100)))

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["source_files"][0]["path"] == "big.py"
        assert scan["source_files"][1]["path"] == "small.py"

    def test_scan_records_directory_tree(self, tmp_path) -> None:
        _write(tmp_path, "src/app.py", "x = 1\n")
        _write(tmp_path, "src/lib/util.py", "y = 2\n")

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["dir_tree"].get("src", 0) >= 1

    def test_scan_extension_distribution(self, tmp_path) -> None:
        _write(tmp_path, "app.py", "x = 1\n")
        _write(tmp_path, "data.json", '{"a": 1}\n')

        scan = _scan_project(tmp_path, max_depth=5)

        assert scan["ext_dist"][".py"] == 1
        assert scan["ext_dist"][".json"] == 1


class TestAddPathToScan:
    def test_skips_excluded_dirs(self, tmp_path) -> None:
        scan = _new_scan()
        excluded = tmp_path / ".venv" / "lib.py"
        excluded.parent.mkdir()
        excluded.write_text("x = 1\n")

        _add_path_to_scan(scan, tmp_path, excluded, max_depth=5)

        assert scan["lang_dist"] == {}

    def test_skips_deep_paths(self, tmp_path) -> None:
        scan = _new_scan()
        deep = tmp_path / "a" / "b" / "c" / "d" / "deep.py"
        deep.parent.mkdir(parents=True)
        deep.write_text("x = 1\n")

        _add_path_to_scan(scan, tmp_path, deep, max_depth=2)

        assert scan["lang_dist"] == {}

    def test_increments_dir_tree_for_directories(self, tmp_path) -> None:
        scan = _new_scan()
        d = tmp_path / "src"
        d.mkdir()

        _add_path_to_scan(scan, tmp_path, d, max_depth=5)

        assert scan["dir_tree"]["src"] == 1


class TestAddFileToScan:
    def test_adds_source_file(self, tmp_path) -> None:
        scan = _new_scan()
        f = _write(tmp_path, "app.py", "x = 1\n")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["lang_dist"]["python"] == 1
        assert len(scan["source_files"]) == 1
        entry = scan["source_files"][0]
        assert entry["language"] == "python"
        assert entry["path"] == "app.py"
        assert entry["lines"] == 1
        assert entry["size_bytes"] > 0

    def test_skips_unsupported_extension(self, tmp_path) -> None:
        scan = _new_scan()
        f = _write(tmp_path, "data.dat", "binary data")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["lang_dist"] == {}
        assert len(scan["source_files"]) == 0

    def test_records_extension_even_for_unsupported(self, tmp_path) -> None:
        scan = _new_scan()
        f = _write(tmp_path, "data.dat", "stuff")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["ext_dist"][".dat"] == 1

    def test_handles_binary_file_gracefully(self, tmp_path) -> None:
        scan = _new_scan()
        f = tmp_path / "app.py"
        f.write_bytes(b"\x00\x01\x02\x03")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["lang_dist"]["python"] == 1

    def test_java_extension_mapped(self, tmp_path) -> None:
        scan = _new_scan()
        f = _write(tmp_path, "Main.java", "class Main {}\n")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["lang_dist"]["java"] == 1

    def test_header_mapped_to_c(self, tmp_path) -> None:
        scan = _new_scan()
        f = _write(tmp_path, "util.h", "int add(int a, int b);\n")

        _add_file_to_scan(scan, tmp_path, f)

        assert scan["lang_dist"]["c"] == 1

    def test_yaml_extensions_mapped(self, tmp_path) -> None:
        scan = _new_scan()
        _write(tmp_path, "a.yaml", "key: value\n")
        _write(tmp_path, "b.yml", "key: value\n")

        for name in ("a.yaml", "b.yml"):
            _add_file_to_scan(scan, tmp_path, tmp_path / name)

        assert scan["lang_dist"]["yaml"] == 2


class TestIncrement:
    def test_new_key(self) -> None:
        d: dict[str, int] = {}
        _increment(d, "test")
        assert d["test"] == 1

    def test_existing_key(self) -> None:
        d: dict[str, int] = {"test": 5}
        _increment(d, "test")
        assert d["test"] == 6


class TestBuildResult:
    def test_without_health(self, tmp_path) -> None:
        scan = _new_scan()
        scan["lang_dist"] = {"python": 2}
        scan["ext_dist"] = {".py": 2, ".txt": 1}
        scan["source_files"] = [
            {"path": "a.py", "language": "python", "lines": 10, "size_bytes": 50},
            {"path": "b.py", "language": "python", "lines": 5, "size_bytes": 30},
        ]

        result = _build_result(tmp_path, scan, include_health=False)

        assert result["success"] is True
        assert result["summary"]["total_files"] == 3
        assert result["summary"]["source_files"] == 2
        assert result["summary"]["non_source_files"] == 1
        assert result["summary"]["total_lines"] == 15
        # F11: ``risk`` is now inferred from observable signals instead of
        # ``"unknown"``. A 2-file project with sub-50-line files trips no
        # severity heuristic, so the fallback verdict is ``"low"``.
        assert result["agent_summary"]["risk"] == "low"
        assert "tool_routing" in result

    def test_with_health_includes_smart_hint(self, tmp_path) -> None:
        scan = _new_scan()
        scan["lang_dist"] = {"python": 1}
        scan["ext_dist"] = {".py": 1}
        scan["source_files"] = [
            {"path": "app.py", "language": "python", "lines": 5, "size_bytes": 20}
        ]
        scan["dir_tree"] = {}

        result = _build_result(tmp_path, scan, include_health=True)

        assert "smart_workflow_hint" in result
        assert result["agent_summary"]["health_checked"] is True


class TestBuildBaseResult:
    def test_languages_sorted_by_count(self, tmp_path) -> None:
        scan = {
            "lang_dist": {"python": 5, "java": 10, "go": 2},
            "ext_dist": {".py": 5, ".java": 10, ".go": 2},
            "source_files": [],
            "dir_tree": {},
        }

        result = _build_base_result(tmp_path, scan)

        langs = list(result["language_distribution"].keys())
        assert langs[0] == "java"
        assert langs[1] == "python"
        assert langs[2] == "go"

    def test_largest_source_files_capped_at_15(self, tmp_path) -> None:
        scan = {
            "lang_dist": {"python": 20},
            "ext_dist": {".py": 20},
            "source_files": [
                {
                    "path": f"f{i}.py",
                    "language": "python",
                    "lines": 20 - i,
                    "size_bytes": 10,
                }
                for i in range(20)
            ],
            "dir_tree": {},
        }

        result = _build_base_result(tmp_path, scan)

        assert len(result["largest_source_files"]) == 15


class TestBuildHealthAlert:
    def test_builds_alert(self) -> None:
        unhealthy = [
            {"file": "a.py", "grade": "D", "score": 30},
            {"file": "b.py", "grade": "F", "score": 10},
        ]
        alert = _build_health_alert(unhealthy)
        assert "2 file(s)" in alert
        assert "a.py" in alert
        assert "b.py" in alert

    def test_caps_at_5_files(self) -> None:
        unhealthy = [{"file": f"f{i}.py", "grade": "F", "score": 10} for i in range(8)]
        alert = _build_health_alert(unhealthy)
        assert "8 file(s)" in alert


class TestHealthOptInHint:
    def test_hint_text(self) -> None:
        hint = _health_opt_in_hint()
        assert "include_health=true" in hint


class TestOverviewRisk:
    def test_high_when_health_alert(self) -> None:
        assert _overview_risk({"health_alert": "bad"}, True) == "high"

    def test_fallback_when_no_signals(self) -> None:
        # F11: a bare empty result with no signals must NOT report
        # ``"unknown"`` — the fallback is ``"low"`` so the agent always
        # receives a comparable risk grade.
        assert _overview_risk({}, False) == "low"

    def test_low_when_health_ok(self) -> None:
        assert _overview_risk({}, True) == "low"


class TestOverviewNextStep:
    def test_with_health_alert(self) -> None:
        step = _overview_next_step({"health_alert": "bad"}, True)
        assert "project-health" in step

    def test_without_health(self) -> None:
        step = _overview_next_step({}, False)
        assert "include_health=true" in step

    def test_healthy_project(self) -> None:
        step = _overview_next_step({}, True)
        # DF-10: next_step must point at the response's own tool_routing map
        # (a real field this tool returns) with concrete examples — not a
        # bare tool-name the CLI surface doesn't have.
        assert step == (
            "Pick the next query from the tool_routing map in this response "
            "(e.g. health for grades, structure for outlines)."
        )


class TestTopLanguage:
    def test_empty(self) -> None:
        assert _top_language({}) == ""

    def test_returns_max(self) -> None:
        assert _top_language({"python": 5, "java": 10}) == "java"


class TestBuildToolRouting:
    def test_contains_all_expected_tools(self) -> None:
        routing = _build_tool_routing()
        assert "project_health" in routing
        assert "file_health" in routing
        assert "edit_risk" in routing
        assert "refactor_plan" in routing
        assert "change_impact" in routing
        assert "file_scale" in routing
        assert "structure_table" in routing
        assert "read_lines" in routing
        assert "find_symbol" in routing
        assert "search_text" in routing
        assert "find_files" in routing


class TestCountLines:
    def test_counts_correctly(self, tmp_path) -> None:
        f = _write(tmp_path, "test.py", "a\nb\nc\n")
        assert _count_lines(f) == 3

    def test_empty_file(self, tmp_path) -> None:
        f = _write(tmp_path, "empty.py", "")
        assert _count_lines(f) == 0

    def test_nonexistent_returns_zero(self, tmp_path) -> None:
        assert _count_lines(tmp_path / "missing.py") == 0


class TestSuggestRefactorAction:
    def test_large_prod_file(self) -> None:
        result = _suggest_refactor_action(
            "src/big.py", 600, type("H", (), {"grade": "D", "total": 30})
        )
        assert result is not None
        assert "check_file_health" in result

    def test_test_file(self) -> None:
        result = _suggest_refactor_action(
            "tests/test_foo.py", 400, type("H", (), {"grade": "D", "total": 30})
        )
        assert result is not None
        assert "Split" in result

    def test_markdown_file(self) -> None:
        result = _suggest_refactor_action(
            "docs/README.md", 200, type("H", (), {"grade": "D", "total": 30})
        )
        assert result is not None
        assert "Archive" in result

    def test_small_prod_file(self) -> None:
        result = _suggest_refactor_action(
            "src/small.py", 50, type("H", (), {"grade": "C", "total": 60})
        )
        assert result is None


class TestBuildSmartHint:
    def test_all_healthy_hint(self) -> None:
        result = {
            "health_summary": [{"file": "a.py", "grade": "A", "score": 90}],
            "language_distribution": {"python": 5},
            "largest_source_files": [{"path": "a.py", "lines": 100}],
        }
        hint = _build_smart_hint(result)
        assert "health is good" in hint

    def test_unhealthy_hint(self) -> None:
        result = {
            "health_summary": [
                {"file": "a.py", "grade": "F", "score": 10, "suggestion": "refactor"}
            ],
            "language_distribution": {"python": 5},
            "largest_source_files": [{"path": "a.py", "lines": 100}],
        }
        hint = _build_smart_hint(result)
        assert "REFACTOR" in hint

    def test_empty_project(self) -> None:
        result = {
            "health_summary": [],
            "language_distribution": {},
            "largest_source_files": [],
        }
        hint = _build_smart_hint(result)
        assert "health is good" in hint

    def test_language_to_extension_mapping(self) -> None:
        # DF-11: verify language names map to correct file extensions in hints
        result = {
            "health_summary": [{"file": "a.py", "grade": "A", "score": 90}],
            "language_distribution": {"python": 5},
            "largest_source_files": [{"path": "a.py", "lines": 100}],
        }
        hint = _build_smart_hint(result)
        assert ".py file" in hint

    def test_language_to_extension_mapping_java(self) -> None:
        # DF-11: verify Java maps to .java
        result = {
            "health_summary": [{"file": "App.java", "grade": "A", "score": 90}],
            "language_distribution": {"java": 10},
            "largest_source_files": [{"path": "App.java", "lines": 100}],
        }
        hint = _build_smart_hint(result)
        assert ".java file" in hint


class TestBuildAgentSummary:
    def test_summary_fields(self) -> None:
        result = {
            "summary": {"source_files": 3, "languages_count": 2},
            "language_distribution": {"python": 2, "java": 1},
            "largest_source_files": [{"path": "big.py"}],
        }
        summary = _build_agent_summary(result, include_health=False)

        assert summary["source_files"] == 3
        assert summary["languages_count"] == 2
        assert summary["top_language"] == "python"
        assert summary["largest_file"] == "big.py"
        assert summary["health_checked"] is False
        assert "verification_command" in summary

    def test_health_checked_flag(self) -> None:
        result = {
            "summary": {"source_files": 1, "languages_count": 1},
            "language_distribution": {"python": 1},
            "largest_source_files": [{"path": "a.py"}],
        }
        summary = _build_agent_summary(result, include_health=True)
        assert summary["health_checked"] is True


class TestEdgeCases:
    def test_max_depth_1(self, tmp_path) -> None:
        _write(tmp_path, "root.py", "x = 1\n")
        _write(tmp_path, "sub/deep.py", "y = 2\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(tool.execute({"max_depth": 1, "output_format": "json"}))

        assert result["summary"]["source_files"] == 1

    def test_unicode_filename(self, tmp_path) -> None:
        _write(tmp_path, "rückmeldung.py", "x = 1\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(tool.execute({"max_depth": 5, "output_format": "json"}))

        assert result["summary"]["source_files"] == 1

    def test_all_supported_extensions(self, tmp_path) -> None:
        ext_lang = {
            ".py": "python",
            ".java": "java",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".kt": "kotlin",
            ".swift": "swift",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".cpp": "cpp",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".yaml": "yaml",
        }
        for ext, lang in ext_lang.items():
            _write(tmp_path, f"file{ext}", f"{lang} content\n")

        tool = ProjectOverviewTool(project_root=str(tmp_path))
        result = _run(tool.execute({"max_depth": 5, "output_format": "json"}))

        assert result["summary"]["languages_count"] == len(ext_lang)
