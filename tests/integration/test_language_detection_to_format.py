"""Integration test: language detection -> plugin loading -> parsing -> formatting."""

import textwrap

from tree_sitter_analyzer.api import analyze_file

_PYTHON_SRC = textwrap.dedent("""\
    class Calculator:
        def add(self, a, b):
            return a + b

    def main():
        c = Calculator()
        print(c.add(1, 2))
""")

_JAVA_SRC = textwrap.dedent("""\
    public class HelloWorld {
        public static void main(String[] args) {
            System.out.println("Hello");
        }
    }
""")

_TS_SRC = textwrap.dedent("""\
    enum Color { Red = "RED", Green = "GREEN" }
    class User {
        constructor(public name: string) {}
        greet(): void { console.log(this.name); }
    }
""")


class TestLanguageDetectionToFormat:
    def test_python_file_full_pipeline(self, tmp_path):
        p = tmp_path / "calc.py"
        p.write_text(_PYTHON_SRC)
        result = analyze_file(str(p))
        assert result["success"] is True
        assert {item["name"] for item in result["elements"]} == {
            "Calculator",
            "add",
            "main",
        }

    def test_java_file_full_pipeline(self, tmp_path):
        p = tmp_path / "Hello.java"
        p.write_text(_JAVA_SRC)
        result = analyze_file(str(p))
        assert result["success"] is True
        assert {item["name"] for item in result["elements"]} == {
            "HelloWorld",
            "main",
        }

    def test_typescript_file_full_pipeline(self, tmp_path):
        p = tmp_path / "app.ts"
        p.write_text(_TS_SRC)
        result = analyze_file(str(p))
        assert result["success"] is True
        assert {item["name"] for item in result["elements"]} == {
            "Color",
            "User",
            "constructor",
            "greet",
        }

    def test_unknown_extension_raises(self, tmp_path):
        p = tmp_path / "data.xyz"
        p.write_text("hello")
        result = analyze_file(str(p))
        assert result["success"] is False
        assert result["error"] == "Unsupported language: unknown"
