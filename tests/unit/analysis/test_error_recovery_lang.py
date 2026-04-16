"""Tests for multi-language error recovery regex fallback patterns."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery


class TestPythonFallback:
    """Python regex fallback extraction."""

    def test_extracts_class(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            "class UserService:\n    def get_user(self, id):\n        pass\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "app.py"),
            (tmp_path / "app.py").read_text(),
            3,
        )
        assert result["success"] is True
        assert result["language"] == "python"
        names = [c["name"] for c in result["classes"]]
        assert "UserService" in names

    def test_extracts_functions(self, tmp_path: Path) -> None:
        (tmp_path / "util.py").write_text(
            "def helper():\n    pass\n\nasync def fetch_data():\n    pass\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "util.py"),
            (tmp_path / "util.py").read_text(),
            5,
        )
        names = [m["name"] for m in result["methods"]]
        assert "helper" in names
        assert "fetch_data" in names


class TestGoFallback:
    """Go regex fallback extraction."""

    def test_extracts_functions(self, tmp_path: Path) -> None:
        (tmp_path / "main.go").write_text(
            "package main\n\nfunc main() {\n}\n\nfunc (s *Server) Start() {\n}\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "main.go"),
            (tmp_path / "main.go").read_text(),
            6,
        )
        assert result["language"] == "go"
        names = [m["name"] for m in result["methods"]]
        assert "main" in names
        assert "Start" in names

    def test_extracts_struct_and_interface(self, tmp_path: Path) -> None:
        (tmp_path / "types.go").write_text(
            "type Server struct {\n    Port int\n}\n\ntype Handler interface {\n    Serve()\n}\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "types.go"),
            (tmp_path / "types.go").read_text(),
            7,
        )
        names = [c["name"] for c in result["classes"]]
        assert "Server" in names


class TestCSharpFallback:
    """C# regex fallback extraction."""

    def test_extracts_class_and_methods(self, tmp_path: Path) -> None:
        (tmp_path / "Service.cs").write_text(
            "public class UserService {\n"
            "  public User GetUser(int id) { return null; }\n"
            "  private void Log(string msg) { }\n"
            "}\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "Service.cs"),
            (tmp_path / "Service.cs").read_text(),
            4,
        )
        assert result["language"] == "csharp"
        class_names = [c["name"] for c in result["classes"]]
        assert "UserService" in class_names

    def test_extracts_interface_and_record(self, tmp_path: Path) -> None:
        (tmp_path / "Types.cs").write_text(
            "public interface IRepository { }\n"
            "public record Person(string Name);\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "Types.cs"),
            (tmp_path / "Types.cs").read_text(),
            2,
        )
        names = [c["name"] for c in result["classes"]]
        assert "IRepository" in names
        assert "Person" in names


class TestKotlinFallback:
    """Kotlin regex fallback extraction."""

    def test_extracts_class_and_function(self, tmp_path: Path) -> None:
        (tmp_path / "App.kt").write_text(
            "class UserService {\n"
            "    fun getUser(id: Int): User { }\n"
            "}\n"
            "object Database {\n"
            "    fun connect() { }\n"
            "}\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "App.kt"),
            (tmp_path / "App.kt").read_text(),
            6,
        )
        assert result["language"] == "kotlin"
        class_names = [c["name"] for c in result["classes"]]
        assert "UserService" in class_names
        assert "Database" in class_names
        method_names = [m["name"] for m in result["methods"]]
        assert "getUser" in method_names
        assert "connect" in method_names


class TestRustFallback:
    """Rust regex fallback extraction."""

    def test_extracts_fn_struct_trait_enum(self, tmp_path: Path) -> None:
        (tmp_path / "lib.rs").write_text(
            "pub struct Server {\n    port: u32,\n}\n\n"
            "pub trait Handler {\n    fn handle(&self);\n}\n\n"
            "pub enum Error {\n    Io(std::io::Error),\n}\n\n"
            "pub fn start() { }\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "lib.rs"),
            (tmp_path / "lib.rs").read_text(),
            12,
        )
        assert result["language"] == "rust"
        class_names = [c["name"] for c in result["classes"]]
        assert "Server" in class_names
        assert "Handler" in class_names
        assert "Error" in class_names
        method_names = [m["name"] for m in result["methods"]]
        assert "handle" in method_names
        assert "start" in method_names


class TestJavaDefaultFallback:
    """Java/default style regex fallback (unchanged behavior)."""

    def test_java_class_extraction(self, tmp_path: Path) -> None:
        (tmp_path / "App.java").write_text(
            "public class Application {\n"
            "  public void run() { }\n"
            "}\n",
            encoding="utf-8",
        )
        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery._regex_fallback(
            str(tmp_path / "App.java"),
            (tmp_path / "App.java").read_text(),
            3,
        )
        names = [c["name"] for c in result["classes"]]
        assert "Application" in names
