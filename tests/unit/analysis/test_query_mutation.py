"""Tests for Query Method Mutation Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.query_mutation import (
    ISSUE_QUERY_MUTATION,
    QueryMutationAnalyzer,
)

ANALYZER = QueryMutationAnalyzer()


class TestPythonQueryMutation:
    def test_getter_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class User:\n"
            "    def __init__(self):\n"
            "        self._cache = None\n"
            "    def get_name(self):\n"
            "        self._cache = True\n"
            "        return self._name\n"
        )
        f = tmp_path / "user.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_is_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Config:\n"
            "    def is_valid(self):\n"
            "        self._checked = True\n"
            "        return self._valid\n"
        )
        f = tmp_path / "config.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_has_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Cache:\n"
            "    def has_item(self, key):\n"
            "        self._last_key = key\n"
            "        return key in self._data\n"
        )
        f = tmp_path / "cache.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_find_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Repository:\n"
            "    def find_by_id(self, id):\n"
            "        self._query_count += 1\n"
            "        return self._data.get(id)\n"
        )
        f = tmp_path / "repo.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_check_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Validator:\n"
            "    def check_rules(self, data):\n"
            "        self._last_data = data\n"
            "        return len(data) > 0\n"
        )
        f = tmp_path / "validator.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_can_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Perms:\n"
            "    def can_access(self, resource):\n"
            "        self._access_count += 1\n"
            "        return resource in self._allowed\n"
        )
        f = tmp_path / "perms.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_should_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Policy:\n"
            "    def should_retry(self, error):\n"
            "        self._retry_count += 1\n"
            "        return self._retry_count < 3\n"
        )
        f = tmp_path / "policy.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_validate_method_modifies_self(self, tmp_path: Path) -> None:
        code = (
            "class Form:\n"
            "    def validate_email(self, email):\n"
            "        self._last_email = email\n"
            "        return '@' in email\n"
        )
        f = tmp_path / "form.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_clean_getter_no_mutation(self, tmp_path: Path) -> None:
        code = (
            "class User:\n"
            "    def __init__(self, name):\n"
            "        self._name = name\n"
            "    def get_name(self):\n"
            "        return self._name\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_non_query_method_mutation_ok(self, tmp_path: Path) -> None:
        code = (
            "class User:\n"
            "    def __init__(self, name):\n"
            "        self._name = name\n"
            "    def set_name(self, name):\n"
            "        self._name = name\n"
        )
        f = tmp_path / "setter.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_standalone_function_no_self(self, tmp_path: Path) -> None:
        code = (
            "def get_value(data):\n"
            "    data['cached'] = True\n"
            "    return data.get('value')\n"
        )
        f = tmp_path / "standalone.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_augmented_assignment_on_self(self, tmp_path: Path) -> None:
        code = (
            "class Counter:\n"
            "    def get_count(self):\n"
            "        self._count += 1\n"
            "        return self._count\n"
        )
        f = tmp_path / "counter.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)


class TestJavaScriptQueryMutation:
    def test_getter_modifies_this(self, tmp_path: Path) -> None:
        code = (
            "class User {\n"
            "  getName() {\n"
            "    this._cached = true;\n"
            "    return this._name;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "user.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_is_method_modifies_this(self, tmp_path: Path) -> None:
        code = (
            "class Config {\n"
            "  isValid() {\n"
            "    this._checked = true;\n"
            "    return this._valid;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "config.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_clean_getter_no_mutation(self, tmp_path: Path) -> None:
        code = (
            "class User {\n"
            "  getName() {\n"
            "    return this._name;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "clean.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_arrow_function_not_checked(self, tmp_path: Path) -> None:
        code = "const getName = () => this._name;\n"
        f = tmp_path / "arrow.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestTypeScriptQueryMutation:
    def test_getter_modifies_this(self, tmp_path: Path) -> None:
        code = (
            "class Service {\n"
            "  getStatus(): string {\n"
            "    this._cache_hit = true;\n"
            "    return this._status;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "service.ts"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)


class TestJavaQueryMutation:
    def test_getter_modifies_this(self, tmp_path: Path) -> None:
        code = (
            "public class User {\n"
            "  private boolean cached;\n"
            "  public String getName() {\n"
            "    this.cached = true;\n"
            "    return this.name;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "User.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_is_method_modifies_field(self, tmp_path: Path) -> None:
        code = (
            "public class Config {\n"
            "  private boolean checked;\n"
            "  public boolean isValid() {\n"
            "    this.checked = true;\n"
            "    return this.valid;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Config.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_clean_getter(self, tmp_path: Path) -> None:
        code = (
            "public class User {\n"
            "  private String name;\n"
            "  public String getName() {\n"
            "    return this.name;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Clean.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestGoQueryMutation:
    def test_getter_modifies_receiver(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "\n"
            "type User struct {\n"
            "    name string\n"
            "    cached bool\n"
            "}\n"
            "\n"
            "func (u *User) GetName() string {\n"
            "    u.cached = true\n"
            "    return u.name\n"
            "}\n"
        )
        f = tmp_path / "user.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_is_method_modifies_receiver(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "\n"
            "type Config struct {\n"
            "    valid bool\n"
            "    checked bool\n"
            "}\n"
            "\n"
            "func (c *Config) IsValid() bool {\n"
            "    c.checked = true\n"
            "    return c.valid\n"
            "}\n"
        )
        f = tmp_path / "config.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_QUERY_MUTATION for i in result.issues)

    def test_clean_getter(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "\n"
            "type User struct {\n"
            "    name string\n"
            "}\n"
            "\n"
            "func (u *User) GetName() string {\n"
            "    return u.name\n"
            "}\n"
        )
        f = tmp_path / "clean.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_value_receiver_not_flagged(self, tmp_path: Path) -> None:
        code = (
            "package main\n"
            "\n"
            "type User struct {\n"
            "    name string\n"
            "}\n"
            "\n"
            "func (u User) GetName() string {\n"
            "    u.name = \"changed\"\n"
            "    return u.name\n"
            "}\n"
        )
        f = tmp_path / "value.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0
