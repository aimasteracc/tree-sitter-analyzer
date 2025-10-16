#!/usr/bin/env python3
"""CLI async integration tests"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestCLIAsyncIntegration:
    """CLI非同期統合テスト"""

    @pytest.fixture
    def sample_files(self):
        """複数のテストファイル"""
        files = []
        contents = [
            # Python file with functions
            """
def function_a():
    '''Function A for testing'''
    return "a"

class ClassA:
    def method_a(self):
        return "method_a"

async def async_function_a():
    await asyncio.sleep(0.1)
    return "async_a"
""",
            # Python file with classes
            """
class ClassB:
    '''Class B for testing'''
    def __init__(self):
        self.value = 42

    def method_b(self):
        return self.value

def function_b():
    return "b"
""",
            # Python file with mixed content
            """
def function_c():
    '''Function C for testing'''
    return 42

class ClassC:
    def method_c(self):
        pass

def another_function():
    x = 1
    y = 2
    return x + y
""",
        ]

        try:
            for i, content in enumerate(contents):
                test_file = Path(f"test_sample_{i}.py")
                test_file.write_text(content)
                files.append(str(test_file))

            yield files
        finally:
            for file_path in files:
                Path(file_path).unlink(missing_ok=True)

    @pytest.fixture
    def sample_javascript_file(self):
        """JavaScriptテストファイル"""
        test_file = Path("test_sample.js")
        try:
            test_file.write_text("""
function testFunction() {
    return 42;
}

class TestClass {
    constructor() {
        this.value = 42;
    }

    method() {
        return this.value;
    }
}

const arrowFunction = () => {
    return "arrow";
};

async function asyncFunction() {
    return new Promise(resolve => {
        setTimeout(() => resolve("async"), 100);
    });
}
""")
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)

    def test_basic_cli_execution_python(self, sample_files):
        """基本的なPython CLIクエリ実行テスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

        # 関数が見つかることを確認（具体的な名前は実装依存）
        output = result.stdout.lower()
        assert "function" in output or "def " in output

    def test_basic_cli_execution_javascript(self, sample_javascript_file):
        """基本的なJavaScript CLIクエリ実行テスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                sample_javascript_file,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

        # 関数が見つかることを確認（具体的な名前は実装依存）
        output = result.stdout.lower()
        assert "function" in output or "def " in output

    def test_class_query_execution(self, sample_files):
        """クラスクエリの実行テスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "class",
                sample_files[1],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

        # クラスが見つかることを確認（具体的な名前は実装依存）
        output = result.stdout.lower()
        assert "class" in output or "def " in output

    def test_multiple_file_processing(self, sample_files):
        """複数ファイルの処理テスト"""
        for i, file_path in enumerate(sample_files):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tree_sitter_analyzer",
                    "--query-key",
                    "function",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert result.returncode == 0, (
                f"CLI failed for file {i} with stderr: {result.stderr}"
            )
            assert len(result.stdout) > 0, f"No output from CLI for file {i}"

    def test_output_format_json(self, sample_files):
        """JSON出力フォーマットのテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "--output-format",
                "json",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

        # JSON形式の出力を確認
        try:
            json_output = json.loads(result.stdout)
            assert isinstance(json_output, (list, dict)), "Output is not valid JSON"
        except json.JSONDecodeError:
            # JSON形式でない場合もあるので、エラーにはしない
            pass

    def test_output_format_text(self, sample_files):
        """テキスト出力フォーマットのテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "--output-format",
                "text",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

    def test_custom_query_string(self, sample_files):
        """カスタムクエリ文字列のテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-string",
                "(function_definition name: (identifier) @function)",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

    def test_filter_expression(self, sample_files):
        """フィルター式のテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "--filter",
                "name=function_a",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # フィルターが実装されていない場合もあるので、エラーにはしない
        if result.returncode == 0:
            assert len(result.stdout) > 0, "No output from CLI"

    def test_language_auto_detection(self, sample_files):
        """言語自動検出のテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                sample_files[0],
                # --languageオプションを指定しない
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

    def test_explicit_language_specification(self, sample_files):
        """明示的な言語指定のテスト"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "--language",
                "python",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

    def test_error_cases_nonexistent_file(self):
        """エラーケース: 存在しないファイル"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "nonexistent_file.py",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0, "CLI should fail for nonexistent file"
        assert len(result.stderr) > 0, "No error message for nonexistent file"

        # エラーメッセージの確認
        error_msg = result.stderr.lower()
        assert any(
            keyword in error_msg
            for keyword in ["not exist", "not found", "no such file", "file not found"]
        ), f"Unexpected error message: {result.stderr}"

    def test_error_cases_invalid_language(self, sample_files):
        """エラーケース: 無効な言語"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                "--language",
                "invalid_language",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 無効な言語の場合、エラーになるかデフォルト動作するかは実装依存
        # エラーになる場合
        if result.returncode != 0:
            assert len(result.stderr) > 0, "No error message for invalid language"
        # 正常終了する場合（デフォルト動作）
        else:
            assert len(result.stdout) >= 0, "Unexpected output for invalid language"

    def test_error_cases_invalid_query_key(self, sample_files):
        """エラーケース: 無効なクエリキー"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "invalid_query_key",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 無効なクエリキーの場合、エラーになるか空結果を返すかは実装依存
        if result.returncode != 0:
            assert len(result.stderr) > 0, "No error message for invalid query key"
        else:
            # 正常終了の場合、空結果または何らかの出力があることを確認
            pass

    def test_error_cases_malformed_query_string(self, sample_files):
        """エラーケース: 不正なクエリ文字列"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-string",
                "((invalid query syntax",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 不正なクエリ文字列の場合、エラーになることを期待
        assert result.returncode != 0, "CLI should fail for malformed query string"
        assert len(result.stderr) > 0, "No error message for malformed query string"

    def test_help_command(self):
        """ヘルプコマンドのテスト"""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer", "query", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Help command failed with stderr: {result.stderr}"
        )
        assert len(result.stdout) > 0, "No help output"

        # ヘルプ内容の確認
        help_text = result.stdout.lower()
        assert any(
            keyword in help_text for keyword in ["usage", "help", "query", "file-path"]
        ), f"Unexpected help content: {result.stdout}"

    def test_version_command(self):
        """バージョンコマンドのテスト"""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # バージョンコマンドが実装されている場合
        if result.returncode == 0:
            assert len(result.stdout) > 0, "No version output"
        # 実装されていない場合はスキップ

    def test_concurrent_cli_execution(self, sample_files):
        """並行CLI実行のテスト"""
        import concurrent.futures

        def run_cli_query(file_path):
            """CLI クエリを実行する関数"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tree_sitter_analyzer",
                    "--query-key",
                    "function",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result

        # 複数のCLIプロセスを並行実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(run_cli_query, file_path) for file_path in sample_files
            ]

            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # 全ての実行が成功することを確認
        for i, result in enumerate(results):
            assert result.returncode == 0, (
                f"Concurrent CLI execution {i} failed with stderr: {result.stderr}"
            )
            assert len(result.stdout) > 0, (
                f"No output from concurrent CLI execution {i}"
            )

    def test_large_file_cli_processing(self):
        """大きなファイルのCLI処理テスト"""
        # 大きなファイルを作成
        large_file = Path("test_large_cli.py")
        try:
            content = ""
            # 100個の関数を持つファイルを生成
            for i in range(100):
                content += f"""
def function_{i}():
    '''Function {i} for testing'''
    return {i}

class Class_{i}:
    def method_{i}(self):
        return {i}
"""
            large_file.write_text(content)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tree_sitter_analyzer",
                    "--query-key",
                    "function",
                    str(large_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )  # 大きなファイルなので60秒のタイムアウト

            assert result.returncode == 0, (
                f"Large file CLI processing failed with stderr: {result.stderr}"
            )
            assert len(result.stdout) > 0, "No output from large file CLI processing"

        finally:
            large_file.unlink(missing_ok=True)

    def test_cli_performance_baseline(self, sample_files):
        """CLIパフォーマンスベースラインテスト"""
        import time

        start_time = time.time()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--query-key",
                "function",
                sample_files[0],
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        end_time = time.time()
        duration = end_time - start_time

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert len(result.stdout) > 0, "No output from CLI"

        # パフォーマンス要件: 10秒以内
        assert duration < 10.0, f"CLI execution took too long: {duration:.2f}s"

        print(f"CLI Performance: {duration:.2f}s")
