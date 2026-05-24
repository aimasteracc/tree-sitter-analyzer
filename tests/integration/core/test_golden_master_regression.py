#!/usr/bin/env python3
"""
Golden Master Regression Test

既存のゴールデンマスターと現在の出力を比較して、
意図しない変更がないことを確認します。

使用方法:
    pytest tests/test_golden_master_regression.py -v
"""

import subprocess
from pathlib import Path

import pytest

from tests.integration.core._golden_master_regression_helpers import (
    build_golden_master_diff,
    normalize_analyzer_output,
)
from tests.integration.core._golden_master_regression_helpers import (
    normalize_toon_output as normalize_toon_output_content,
)


def run_analyzer(input_file: str, table_format: str = "full") -> str:
    """アナライザーを実行して出力を取得"""
    import sys

    # Use the Python interpreter from the current environment
    python_exe = sys.executable

    cmd = [
        python_exe,
        "-m",
        "tree_sitter_analyzer",
        input_file,
        "--table",
        table_format,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=True
    )

    return result.stdout


def normalize_output(content: str) -> str:
    """
    出力を正規化して、バージョン情報や日時などの
    可変部分を除去します
    """
    return normalize_analyzer_output(content)


def compare_with_golden_master(
    input_file: str, golden_name: str, table_format: str = "full"
) -> tuple[bool, str]:
    """
    現在の出力とゴールデンマスターを比較

    Returns:
        (一致するか, 差分メッセージ)
    """
    extension = "csv" if table_format == "csv" else "md"
    golden_path = (
        Path("tests/golden_masters")
        / table_format
        / f"{golden_name}_{table_format}.{extension}"
    )

    if not golden_path.exists():
        return False, f"Golden master not found: {golden_path}"

    # ゴールデンマスターを読み込み
    golden_content = golden_path.read_text(encoding="utf-8")

    # 現在の出力を取得
    try:
        current_content = run_analyzer(input_file, table_format)
    except subprocess.CalledProcessError as e:
        return False, f"Failed to run analyzer: {e}"

    # 正規化して比較
    golden_normalized = normalize_output(golden_content)
    current_normalized = normalize_output(current_content)

    if golden_normalized == current_normalized:
        return True, "Output matches golden master"

    return False, build_golden_master_diff(golden_normalized, current_normalized)


class TestGoldenMasterRegression:
    """ゴールデンマスターリグレッションテスト"""

    @pytest.mark.parametrize(
        "input_file,golden_name,table_format",
        [
            # YAML tests
            ("examples/sample_config.yaml", "yaml_sample_config", "full"),
            ("examples/sample_config.yaml", "yaml_sample_config", "compact"),
            ("examples/sample_config.yaml", "yaml_sample_config", "csv"),
            # HTML tests
            ("examples/comprehensive_sample.html", "html_comprehensive_sample", "full"),
            (
                "examples/comprehensive_sample.html",
                "html_comprehensive_sample",
                "compact",
            ),
            ("examples/comprehensive_sample.html", "html_comprehensive_sample", "csv"),
            # CSS tests
            ("examples/comprehensive_sample.css", "css_comprehensive_sample", "full"),
            (
                "examples/comprehensive_sample.css",
                "css_comprehensive_sample",
                "compact",
            ),
            ("examples/comprehensive_sample.css", "css_comprehensive_sample", "csv"),
            # Markdown tests
            ("examples/test_markdown.md", "markdown_test", "full"),
            ("examples/test_markdown.md", "markdown_test", "compact"),
            ("examples/test_markdown.md", "markdown_test", "csv"),
            # Java tests
            ("examples/Sample.java", "java_sample", "full"),
            ("examples/Sample.java", "java_sample", "compact"),
            ("examples/Sample.java", "java_sample", "csv"),
            ("examples/BigService.java", "java_bigservice", "full"),
            ("examples/BigService.java", "java_bigservice", "compact"),
            ("examples/BigService.java", "java_bigservice", "csv"),
            # Python tests
            ("examples/sample.py", "python_sample", "full"),
            ("examples/sample.py", "python_sample", "compact"),
            ("examples/sample.py", "python_sample", "csv"),
            # TypeScript tests
            ("tests/test_data/test_enum.ts", "typescript_enum", "full"),
            ("tests/test_data/test_enum.ts", "typescript_enum", "compact"),
            ("tests/test_data/test_enum.ts", "typescript_enum", "csv"),
            # JavaScript tests
            ("tests/test_data/test_class.js", "javascript_class", "full"),
            ("tests/test_data/test_class.js", "javascript_class", "compact"),
            ("tests/test_data/test_class.js", "javascript_class", "csv"),
            # SQL tests
            ("examples/sample_database.sql", "sql_sample_database", "full"),
            ("examples/sample_database.sql", "sql_sample_database", "compact"),
            ("examples/sample_database.sql", "sql_sample_database", "csv"),
            # C# tests
            ("examples/Sample.cs", "csharp_sample", "full"),
            ("examples/Sample.cs", "csharp_sample", "compact"),
            ("examples/Sample.cs", "csharp_sample", "csv"),
            # PHP tests
            ("examples/Sample.php", "php_sample", "full"),
            ("examples/Sample.php", "php_sample", "compact"),
            ("examples/Sample.php", "php_sample", "csv"),
            # Ruby tests
            ("examples/Sample.rb", "ruby_sample", "full"),
            ("examples/Sample.rb", "ruby_sample", "compact"),
            ("examples/Sample.rb", "ruby_sample", "csv"),
            # Rust tests
            ("examples/sample.rs", "rust_sample", "full"),
            ("examples/sample.rs", "rust_sample", "compact"),
            # Kotlin tests
            ("examples/Sample.kt", "kotlin_sample", "full"),
            ("examples/Sample.kt", "kotlin_sample", "compact"),
            ("examples/Sample.kt", "kotlin_sample", "csv"),
            ("examples/sample.rs", "rust_sample", "csv"),
            # Go tests
            ("examples/sample.go", "go_sample", "full"),
            ("examples/sample.go", "go_sample", "compact"),
            ("examples/sample.go", "go_sample", "csv"),
            # C tests
            ("examples/sample.c", "c_sample", "full"),
            ("examples/sample.c", "c_sample", "compact"),
            ("examples/sample.c", "c_sample", "csv"),
            # C++ tests
            ("examples/sample.cpp", "cpp_sample", "full"),
            ("examples/sample.cpp", "cpp_sample", "compact"),
            ("examples/sample.cpp", "cpp_sample", "csv"),
        ],
    )
    def test_golden_master_comparison(
        self, input_file: str, golden_name: str, table_format: str
    ):
        """ゴールデンマスターとの比較テスト"""
        input_path = Path(input_file)

        if not input_path.exists():
            pytest.skip(f"Input file not found: {input_file}")

        matches, message = compare_with_golden_master(
            input_file, golden_name, table_format
        )

        assert matches, message

    def test_enum_members_extracted(self):
        """Enumのメンバーが正しく抽出されることを確認"""
        output = run_analyzer("examples/Sample.java", "full")

        # TestEnumのセクションが存在することを確認
        assert "## TestEnum" in output

        # Constructorが抽出されていることを確認
        assert "TestEnum |" in output and "description:String" in output

        # getDescription メソッドが抽出されていることを確認
        assert "getDescription" in output

        # descriptionフィールドが抽出されていることを確認
        assert "description | String" in output

    def test_interface_type_correct(self):
        """Interfaceのtypeが正しく認識されることを確認"""
        output = run_analyzer("examples/Sample.java", "full")

        # TestInterface と AnotherInterface が interface として認識
        assert "| TestInterface | interface |" in output
        assert "| AnotherInterface | interface |" in output

    def test_enum_type_correct(self):
        """Enumのtypeが正しく認識されることを確認"""
        output = run_analyzer("examples/Sample.java", "full")

        # TestEnum が enum として認識
        assert "| TestEnum | enum |" in output

    def test_visibility_correct(self):
        """Visibilityが正しく認識されることを確認"""
        output = run_analyzer("examples/Sample.java", "full")

        # package-private クラス
        assert "| AbstractParentClass | class | package |" in output
        assert "| ParentClass | class | package |" in output

        # public クラス
        assert "| Test | class | public |" in output


class TestToonGoldenMasterRegression:
    """TOON フォーマットゴールデンマスターリグレッションテスト"""

    @staticmethod
    def run_toon_analyzer(input_file: str) -> str:
        """TOON フォーマットでアナライザーを実行 (--table toon)"""
        import sys

        python_exe = sys.executable
        cmd = [
            python_exe,
            "-m",
            "tree_sitter_analyzer",
            input_file,
            "--table",
            "toon",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", check=True
        )
        return result.stdout

    @staticmethod
    def normalize_toon_output(content: str) -> str:
        """
        TOON 出力を正規化して、可変部分を除去
        """
        return normalize_toon_output_content(content)

    def compare_toon_golden_master(
        self, input_file: str, golden_name: str
    ) -> tuple[bool, str]:
        """TOON ゴールデンマスターとの比較"""
        golden_path = Path("tests/golden_masters/toon") / f"{golden_name}_toon.toon"

        if not golden_path.exists():
            return False, f"Golden master not found: {golden_path}"

        golden_content = golden_path.read_text(encoding="utf-8")

        try:
            current_content = self.run_toon_analyzer(input_file)
        except subprocess.CalledProcessError as e:
            return False, f"Failed to run analyzer: {e}"

        golden_normalized = self.normalize_toon_output(golden_content)
        current_normalized = self.normalize_toon_output(current_content)

        if golden_normalized == current_normalized:
            return True, "Output matches golden master"

        return False, build_golden_master_diff(
            golden_normalized, current_normalized, prefix="TOON output"
        )

    @pytest.mark.parametrize(
        "input_file,golden_name",
        [
            # Python tests
            ("examples/sample.py", "python_sample"),
            # Java tests
            ("examples/Sample.java", "java_sample"),
            ("examples/BigService.java", "java_bigservice"),
            # TypeScript tests
            ("tests/test_data/test_enum.ts", "typescript_enum"),
            # JavaScript tests
            ("tests/test_data/test_class.js", "javascript_class"),
            # Go tests
            ("examples/sample.go", "go_sample"),
            # Rust tests
            ("examples/sample.rs", "rust_sample"),
            # Kotlin tests
            ("examples/Sample.kt", "kotlin_sample"),
            # C# tests
            ("examples/Sample.cs", "csharp_sample"),
            # PHP tests
            ("examples/Sample.php", "php_sample"),
            # Ruby tests
            ("examples/Sample.rb", "ruby_sample"),
            # C tests
            ("examples/sample.c", "c_sample"),
            # C++ tests
            ("examples/sample.cpp", "cpp_sample"),
            # YAML tests
            ("examples/sample_config.yaml", "yaml_sample_config"),
            # HTML tests
            ("examples/comprehensive_sample.html", "html_comprehensive_sample"),
            # CSS tests
            ("examples/comprehensive_sample.css", "css_comprehensive_sample"),
            # Markdown tests
            ("examples/test_markdown.md", "markdown_test"),
            # SQL tests
            ("examples/sample_database.sql", "sql_sample_database"),
        ],
    )
    def test_toon_golden_master_comparison(self, input_file: str, golden_name: str):
        """TOON ゴールデンマスターとの比較テスト"""
        input_path = Path(input_file)

        if not input_path.exists():
            pytest.skip(f"Input file not found: {input_file}")

        matches, message = self.compare_toon_golden_master(input_file, golden_name)

        assert matches, message

    def test_toon_format_consistency(self):
        """TOON フォーマットの一貫性を確認"""
        output = self.run_toon_analyzer("examples/sample.py")

        # TOON フォーマットの特徴を確認
        assert "file_path:" in output, "Should have file_path key"
        assert "language:" in output, "Should have language key"
        assert "classes:" in output, "Should have classes section"
        assert "methods:" in output, "Should have methods section"
        assert "{name," in output, "Should use array table format with schema"
        assert "line_range(a,b)" in output, "Should have compact line_range format"

    def test_toon_token_reduction(self):
        """TOON フォーマットのトークン削減を確認"""

        # JSON 出力を取得
        import sys

        python_exe = sys.executable
        json_cmd = [
            python_exe,
            "-m",
            "tree_sitter_analyzer",
            "examples/sample.py",
            "--structure",
            "--format",
            "json",
        ]
        json_result = subprocess.run(
            json_cmd, capture_output=True, text=True, encoding="utf-8", check=True
        )
        json_output = json_result.stdout

        # TOON 出力を取得
        toon_output = self.run_toon_analyzer("examples/sample.py")

        # トークン削減率を計算（文字数ベース）
        json_chars = len(json_output)
        toon_chars = len(toon_output)

        reduction = (1 - toon_chars / json_chars) * 100 if json_chars else 0

        # 少なくとも 20% の削減があることを確認
        assert reduction > 20, f"Token reduction should be > 20%, got {reduction:.1f}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
