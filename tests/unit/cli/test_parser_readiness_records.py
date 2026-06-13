#!/usr/bin/env python3
"""Tests for cli/parser_readiness_records.py"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.parser_readiness_records import (
    LOADER_ALIASES,
    SCORE_WEIGHTS,
    _artifact_signals,
    _build_language_record,
    _count_matching_files,
    _first_project_url,
    _has_loader_mapping,
    _is_supported,
    _language_record_actions,
    _language_record_metadata,
    _loader_keys,
    _maintenance_check_url,
    _metadata_signals,
    _module_is_installed,
    _module_name_for_language,
    _next_steps,
    _packaged_file_signal,
    _path_matches_language,
    _readiness_score,
    _readiness_status,
    _relative_display,
    _scanner_signal,
    _semantic_version_text,
    _unknown_upstream_signals,
    _upstream_next_steps,
    _verification_commands,
    build_language_records,
)


@pytest.fixture
def tmp_project(tmp_path):
    (tmp_project := tmp_path / "proj").mkdir()
    (tmp_project / "tests" / "unit" / "languages").mkdir(parents=True)
    (tmp_project / "tests" / "golden_masters").mkdir(parents=True)
    return tmp_project


def _make_inputs(
    parser_packages=None,
    plugin_entrypoints=None,
    loader_modules=None,
):
    return {
        "parser_packages": parser_packages or {},
        "plugin_entrypoints": plugin_entrypoints or {},
        "loader_modules": loader_modules or {},
    }


class TestLoaderAliases:
    def test_csharp_aliases(self):
        assert LOADER_ALIASES["csharp"] == ("csharp", "cs")

    def test_typescript_aliases(self):
        assert LOADER_ALIASES["typescript"] == ("typescript", "tsx")

    def test_yaml_aliases(self):
        assert LOADER_ALIASES["yaml"] == ("yaml", "yml")


class TestScoreWeights:
    def test_total_is_100(self):
        assert sum(SCORE_WEIGHTS.values()) == 100

    def test_parser_dependency_declared_highest(self):
        assert SCORE_WEIGHTS["parser_dependency_declared"] == 25


class TestLoaderKeys:
    def test_known_alias(self):
        assert _loader_keys("csharp") == ("csharp", "cs")

    def test_unknown_returns_self(self):
        assert _loader_keys("python") == ("python",)


class TestModuleIsInstalled:
    def test_os_installed(self):
        assert _module_is_installed("os") is True

    def test_empty_string(self):
        assert _module_is_installed("") is False

    def test_nonexistent_module(self):
        assert _module_is_installed("totally_fake_module_xyz_123") is False


class TestModuleNameForLanguage:
    def test_from_loader_modules(self):
        result = _module_name_for_language(
            "python", {}, {"python": "tree_sitter_python"}
        )
        assert result == "tree_sitter_python"

    def test_csharp_uses_alias(self):
        result = _module_name_for_language("csharp", {}, {"cs": "tree_sitter_csharp"})
        assert result == "tree_sitter_csharp"

    def test_from_parser_package(self):
        result = _module_name_for_language(
            "python", {"package": "tree-sitter-python"}, {}
        )
        assert result == "tree_sitter_python"

    def test_empty_when_nothing(self):
        result = _module_name_for_language("python", {}, {})
        assert result == ""


class TestHasLoaderMapping:
    def test_present(self):
        assert _has_loader_mapping("python", {"python": "tree_sitter_python"}) is True

    def test_alias_present(self):
        assert _has_loader_mapping("csharp", {"cs": "tree_sitter_csharp"}) is True

    def test_absent(self):
        assert _has_loader_mapping("python", {}) is False


class TestPathMatchesLanguage:
    def test_exact_match(self):
        assert _path_matches_language(Path("test_python_foo.py"), "python") is True

    def test_no_match(self):
        assert _path_matches_language(Path("test_java_foo.py"), "python") is False

    def test_underscore_split(self):
        assert _path_matches_language(Path("test_csharp_helper.py"), "csharp") is True


class TestCountMatchingFiles:
    def test_count_in_directory(self, tmp_path):
        (tmp_path / "test_python_plugin.py").touch()
        (tmp_path / "test_java_plugin.py").touch()
        (tmp_path / "python_helpers.py").touch()
        assert _count_matching_files(tmp_path, "python") == 2

    def test_empty_directory(self, tmp_path):
        assert _count_matching_files(tmp_path, "python") == 0

    def test_nonexistent_directory(self, tmp_path):
        assert _count_matching_files(tmp_path / "nope", "python") == 0


class TestArtifactSignals:
    def test_returns_dict(self, tmp_path):
        signals = _artifact_signals(tmp_path, "python")
        assert isinstance(signals, dict)
        assert "unit_tests" in signals
        assert "golden_masters" in signals
        assert "unit_test_count" in signals
        assert "golden_master_count" in signals

    def test_no_tests(self, tmp_path):
        signals = _artifact_signals(tmp_path, "python")
        assert signals["unit_tests"] is False
        assert signals["unit_test_count"] == 0

    def test_with_tests(self, tmp_project):
        langs = tmp_project / "tests" / "unit" / "languages"
        (langs / "test_python_plugin.py").touch()
        signals = _artifact_signals(tmp_project, "python")
        assert signals["unit_tests"] is True
        assert signals["unit_test_count"] == 1


class TestMetadataSignals:
    def test_all_missing(self):
        signals = _metadata_signals("python", {}, {}, {})
        assert signals["parser_dependency_declared"] is False
        assert signals["plugin_entrypoint"] is False
        assert signals["loader_mapping"] is False

    def test_all_present(self):
        signals = _metadata_signals(
            "python",
            {"python": {"package": "tree-sitter-python"}},
            {"python": "tree_sitter_python"},
            {"python": "tree_sitter_python"},
        )
        assert signals["parser_dependency_declared"] is True
        assert signals["plugin_entrypoint"] is True
        assert signals["loader_mapping"] is True


class TestReadinessScore:
    def test_all_true(self):
        signals = {
            "parser_dependency_declared": True,
            "loader_mapping": True,
            "plugin_entrypoint": True,
            "parser_installed": True,
            "unit_tests": True,
            "golden_masters": True,
        }
        assert _readiness_score(signals) == 100

    def test_all_false(self):
        signals = {
            "parser_dependency_declared": False,
            "loader_mapping": False,
            "plugin_entrypoint": False,
            "parser_installed": False,
            "unit_tests": False,
            "golden_masters": False,
        }
        assert _readiness_score(signals) == 0

    def test_partial(self):
        signals = {
            "parser_dependency_declared": True,
            "loader_mapping": True,
            "plugin_entrypoint": False,
            "parser_installed": False,
            "unit_tests": False,
            "golden_masters": False,
        }
        assert _readiness_score(signals) == 25 + 20


class TestIsSupported:
    def test_supported(self):
        assert (
            _is_supported(
                {
                    "plugin_entrypoint": True,
                    "loader_mapping": True,
                    "unit_tests": True,
                }
            )
            is True
        )

    def test_missing_unit_tests(self):
        assert (
            _is_supported(
                {
                    "plugin_entrypoint": True,
                    "loader_mapping": True,
                    "unit_tests": False,
                }
            )
            is False
        )

    def test_missing_loader(self):
        assert (
            _is_supported(
                {
                    "plugin_entrypoint": True,
                    "loader_mapping": False,
                    "unit_tests": True,
                }
            )
            is False
        )


class TestReadinessStatus:
    def test_supported(self):
        signals = {
            "plugin_entrypoint": True,
            "loader_mapping": True,
            "unit_tests": True,
            "parser_dependency_declared": True,
        }
        assert _readiness_status(signals) == "supported"

    def test_needs_hardening(self):
        signals = {
            "plugin_entrypoint": True,
            "loader_mapping": False,
            "unit_tests": False,
            "parser_dependency_declared": True,
        }
        assert _readiness_status(signals) == "needs_hardening"

    def test_candidate(self):
        signals = {
            "plugin_entrypoint": False,
            "loader_mapping": False,
            "unit_tests": False,
            "parser_dependency_declared": True,
        }
        assert _readiness_status(signals) == "candidate"

    def test_missing_parser_package(self):
        signals = {
            "plugin_entrypoint": False,
            "loader_mapping": False,
            "unit_tests": False,
            "parser_dependency_declared": False,
        }
        assert _readiness_status(signals) == "missing_parser_package"


class TestUnknownUpstreamSignals:
    def test_returns_dict(self):
        signals = _unknown_upstream_signals()
        assert isinstance(signals, dict)
        assert "parser_module_origin" in signals
        assert signals["parser_module_origin"] == ""
        assert signals["upstream_parser_abi"] == "unknown_local_only"


class TestSemanticVersionText:
    def test_none(self):
        assert _semantic_version_text(None) == ""

    def test_tuple(self):
        assert _semantic_version_text((1, 2, 3)) == "1.2.3"

    def test_single(self):
        assert _semantic_version_text((0,)) == "0"


class TestPackagedFileSignal:
    def test_none_root(self):
        assert _packaged_file_signal(None, "grammar.json") == "unknown_local_only"

    def test_nonexistent_root(self, tmp_path):
        assert (
            _packaged_file_signal(tmp_path / "nope", "grammar.json")
            == "unknown_local_only"
        )

    def test_file_found(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "grammar.json").touch()
        result = _packaged_file_signal(pkg, "grammar.json")
        assert result.startswith("packaged:")

    def test_file_not_found(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        assert _packaged_file_signal(pkg, "grammar.json") == "not_packaged"


class TestScannerSignal:
    def test_none_root(self):
        assert _scanner_signal(None) == "unknown_local_only"

    def test_scanner_c_found(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "scanner.c").touch()
        result = _scanner_signal(pkg)
        assert result.startswith("packaged:")

    def test_scanner_cc_found(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "scanner.cc").touch()
        result = _scanner_signal(pkg)
        assert result.startswith("packaged:")

    def test_no_scanner(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "parser.c").touch()
        assert _scanner_signal(pkg) == "not_packaged"


class TestRelativeDisplay:
    def test_relative(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert _relative_display(tmp_path, child) == "sub/file.txt"

    def test_outside_root(self, tmp_path):
        other = Path("/tmp/other/file.txt")
        result = _relative_display(tmp_path, other)
        assert result == "file.txt"


class TestLanguageRecordMetadata:
    def test_fields(self):
        result = _language_record_metadata(
            "python",
            {
                "package": "tree-sitter-python",
                "requirements": ["req1"],
                "sources": ["src1"],
            },
            {"python": "plugins.python_plugin"},
            "supported",
            85,
        )
        assert result["language"] == "python"
        assert result["status"] == "supported"
        assert result["score"] == 85
        assert result["parser_package"] == "tree-sitter-python"
        assert result["requirements"] == ["req1"]
        assert result["plugin_entrypoint_target"] == "plugins.python_plugin"

    def test_empty_parser_info(self):
        result = _language_record_metadata(
            "python", {}, {}, "missing_parser_package", 0
        )
        assert result["parser_package"] == ""
        assert result["requirements"] == []
        assert result["plugin_entrypoint_target"] == ""


class TestLanguageRecordActions:
    def test_has_signals_and_steps(self):
        signals = {
            "parser_dependency_declared": False,
            "loader_mapping": False,
            "plugin_entrypoint": False,
            "parser_installed": False,
            "unit_tests": False,
            "golden_masters": False,
            "upstream_parser_abi": "unknown_local_only",
            "upstream_grammar_json": "unknown_local_only",
            "upstream_external_scanner": "unknown_local_only",
            "upstream_maintenance": "unknown_local_only",
        }
        result = _language_record_actions("python", signals)
        assert "signals" in result
        assert "next_steps" in result
        assert "verification_commands" in result
        assert len(result["next_steps"]) == 8


class TestNextSteps:
    def test_all_false_gives_many_steps(self):
        signals = {
            "parser_dependency_declared": False,
            "loader_mapping": False,
            "plugin_entrypoint": False,
            "parser_installed": False,
            "unit_tests": False,
            "golden_masters": False,
            "upstream_parser_abi": "unknown_local_only",
            "upstream_grammar_json": "unknown_local_only",
            "upstream_external_scanner": "unknown_local_only",
            "upstream_maintenance": "unknown_local_only",
        }
        steps = _next_steps("python", signals)
        assert len(steps) == 8
        assert any("python" in s for s in steps)

    def test_all_true_few_steps(self):
        signals = {
            "parser_dependency_declared": True,
            "loader_mapping": True,
            "plugin_entrypoint": True,
            "parser_installed": True,
            "unit_tests": True,
            "golden_masters": True,
            "upstream_parser_abi": "local_binding_abi_14",
            "upstream_grammar_json": "packaged:grammar.json",
            "upstream_external_scanner": "not_packaged",
            "upstream_maintenance": "requires_online_check",
        }
        steps = _next_steps("python", signals)
        assert len(steps) == 2


class TestUpstreamNextSteps:
    def test_requires_online_check(self):
        signals = {
            "upstream_maintenance": "requires_online_check",
            "parser_maintenance_urls": {"releases": "https://example.com"},
            "upstream_parser_abi": "local_binding_abi_14",
            "upstream_grammar_json": "packaged:grammar.json",
            "upstream_external_scanner": "packaged:scanner.c",
        }
        steps = _upstream_next_steps(signals)
        assert any("maintenance" in s.lower() for s in steps)

    def test_unknown_abi_adds_step(self):
        signals = {
            "upstream_maintenance": "online",
            "upstream_parser_abi": "",
            "upstream_grammar_json": "packaged:grammar.json",
            "upstream_external_scanner": "packaged:scanner.c",
        }
        steps = _upstream_next_steps(signals)
        assert any("ABI" in s for s in steps)


class TestFirstProjectUrl:
    def test_empty(self):
        assert _first_project_url({}) == ""

    def test_returns_first(self):
        urls = {"homepage": "https://a.com", "repo": "https://b.com"}
        assert _first_project_url(urls) == "https://a.com"


class TestMaintenanceCheckUrl:
    def test_maintenance_urls_releases(self):
        signals = {"parser_maintenance_urls": {"releases": "https://r.com"}}
        assert _maintenance_check_url(signals) == "https://r.com"

    def test_maintenance_urls_fallback_repo(self):
        signals = {"parser_maintenance_urls": {"repository": "https://g.com"}}
        assert _maintenance_check_url(signals) == "https://g.com"

    def test_fallback_to_project_urls(self):
        signals = {
            "parser_maintenance_urls": {},
            "parser_project_urls": {"homepage": "https://h.com"},
        }
        assert _maintenance_check_url(signals) == "https://h.com"


class TestVerificationCommands:
    def test_returns_list(self):
        cmds = _verification_commands("python")
        assert isinstance(cmds, list)
        assert len(cmds) == 3

    def test_contains_pytest(self):
        cmds = _verification_commands("python")
        assert any("pytest" in c for c in cmds)

    def test_contains_parser_readiness(self):
        cmds = _verification_commands("python")
        assert any("parser-readiness" in c for c in cmds)


class TestBuildLanguageRecords:
    def test_single_language(self, tmp_path):
        inputs = _make_inputs(
            parser_packages={"python": {"package": "tree-sitter-python"}},
            plugin_entrypoints={"python": "plugins.python_plugin"},
            loader_modules={"python": "tree_sitter_python"},
        )
        records = build_language_records(tmp_path, ["python"], inputs)
        assert len(records) == 1
        assert records[0]["language"] == "python"

    def test_multiple_languages(self, tmp_path):
        inputs = _make_inputs(
            parser_packages={
                "python": {"package": "tree-sitter-python"},
                "java": {"package": "tree-sitter-java"},
            },
        )
        records = build_language_records(tmp_path, ["python", "java"], inputs)
        assert len(records) == 2

    def test_empty_languages(self, tmp_path):
        records = build_language_records(tmp_path, [], _make_inputs())
        assert records == []


class TestBuildLanguageRecord:
    def test_returns_complete_record(self, tmp_path):
        record = _build_language_record(
            tmp_path,
            "python",
            {"package": "tree-sitter-python", "requirements": [], "sources": []},
            {"python": "plugins.python_plugin"},
            {"python": "tree_sitter_python"},
        )
        assert "language" in record
        assert "status" in record
        assert "score" in record
        assert "signals" in record
        assert "next_steps" in record
        assert "verification_commands" in record

    def test_missing_language_has_low_score(self, tmp_path):
        record = _build_language_record(tmp_path, "fortran", {}, {}, {})
        assert record["score"] < 50
        assert record["status"] == "missing_parser_package"
