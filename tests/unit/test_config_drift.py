"""Tests for Configuration Drift Detector.

TDD: Tests written first. Detect hardcoded configuration values
that should be externalized via environment variables.
"""
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.config_drift import (
    ConfigDriftAnalyzer,
    ConfigDriftIssue,
)


@pytest.fixture
def analyzer() -> ConfigDriftAnalyzer:
    return ConfigDriftAnalyzer()


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── Detection tests ──────────────────────────────────────────────


class TestPythonDetection:
    def test_detects_hardcoded_db_host(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST = "prod-db.internal"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "DB_HOST"
        assert result.issues[0].issue_type == "hardcoded_config"

    def test_detects_hardcoded_port(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = "PORT = 8080\n"
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "PORT"

    def test_detects_hardcoded_api_key(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'API_KEY = "sk-1234567890abcdef"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1

    def test_detects_hardcoded_timeout(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = "TIMEOUT = 30\n"
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1

    def test_detects_hardcoded_base_url(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'BASE_URL = "https://api.example.com/v2"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1

    def test_detects_hardcoded_secret_key(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'SECRET_KEY = "my-super-secret-key"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1

    def test_confidence_high_with_env_var_crossref(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'import os\nDB_HOST = "prod-db.internal"\nAPI_KEY = os.getenv("API_KEY")\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1
        assert result.issues[0].confidence == "high"

    def test_confidence_low_without_env_var(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST = "prod-db.internal"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1
        assert result.issues[0].confidence == "low"

    def test_detects_multiple_hardcoded_configs(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST = "prod"\nDB_PORT = 5432\nAPI_KEY = "sk-xxx"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 3


class TestJSDetection:
    def test_detects_hardcoded_const_url(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'const API_URL = "https://api.example.com";\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "API_URL"

    def test_detects_hardcoded_const_port(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = "const PORT = 3000;\n"
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert len(result.issues) == 1

    def test_confidence_high_with_process_env(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'const DB_HOST = "localhost";\nconst API_KEY = process.env.API_KEY;\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert len(result.issues) == 1
        assert result.issues[0].confidence == "high"

    def test_typescript_detection(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'const API_ENDPOINT: string = "https://api.example.com/v2";\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.ts", code))
        assert len(result.issues) == 1


class TestJavaDetection:
    def test_detects_hardcoded_static_final(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = (
            'public class Config {\n'
            '    private static final String DB_HOST = "prod-db.internal";\n'
            '}\n'
        )
        result = analyzer.analyze_file(_write(tmp_path, "Config.java", code))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "DB_HOST"

    def test_detects_hardcoded_port_int(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = (
            'public class Config {\n'
            '    private static final int PORT = 8080;\n'
            '}\n'
        )
        result = analyzer.analyze_file(_write(tmp_path, "Config.java", code))
        assert len(result.issues) == 1


class TestGoDetection:
    def test_detects_hardcoded_const(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'package main\n\nconst DBHost = "prod-db.internal"\n'
        result = analyzer.analyze_file(_write(tmp_path, "main.go", code))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "DBHost"

    def test_detects_hardcoded_port(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'package main\n\nconst Port = 8080\n'
        result = analyzer.analyze_file(_write(tmp_path, "main.go", code))
        assert len(result.issues) == 1


# ── Exclusion tests ──────────────────────────────────────────────


class TestExclusions:
    def test_ignores_env_var_assignment(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST = os.getenv("DB_HOST")\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_function_call_assignment(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'API_URL = get_config("api_url")\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_non_config_variable_name(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'GREETING = "hello world"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_local_variable_in_function(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'def foo():\n    port = 8080\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_imports(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'import os\nfrom config import DB_HOST\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_type_annotation_only(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST: str\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_ignores_augmented_assignment(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'TIMEOUT += 5\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0


# ── Structure/edge tests ────────────────────────────────────────


class TestStructure:
    def test_empty_file(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        result = analyzer.analyze_file(_write(tmp_path, "a.py", ""))
        assert result.issue_count == 0
        assert result.total_assignments == 0

    def test_nonexistent_file(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        result = analyzer.analyze_file(tmp_path / "nonexistent.py")
        assert result.issue_count == 0

    def test_unsupported_extension(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        result = analyzer.analyze_file(_write(tmp_path, "a.rs", 'const HOST = "x";\n'))
        assert result.issue_count == 0

    def test_result_to_dict(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'DB_HOST = "prod"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        d = result.to_dict()
        assert "issues" in d
        assert "total_assignments" in d
        assert "file_path" in d

    def test_issue_to_dict(self) -> None:
        issue = ConfigDriftIssue(
            line_number=1,
            issue_type="hardcoded_config",
            variable_name="DB_HOST",
            literal_value='"prod"',
            confidence="low",
            severity="info",
        )
        d = issue.to_dict()
        assert d["variable_name"] == "DB_HOST"
        assert d["confidence"] == "low"

    def test_counts_total_assignments(self, analyzer: ConfigDriftAnalyzer, tmp_path: Path) -> None:
        code = 'x = 1\ny = 2\nDB_HOST = "prod"\n'
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_assignments == 3
        assert result.issue_count == 1
