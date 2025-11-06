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


def run_analyzer(input_file: str, table_format: str = "full") -> str:
    """アナライザーを実行して出力を取得"""
    cmd = ["uv", "run", "tree-sitter-analyzer", input_file, "--table", table_format]

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=True
    )

    return result.stdout


def normalize_output(content: str) -> str:
    """
    出力を正規化して、バージョン情報や日時などの
    可変部分を除去します
    """
    # 改行コードを統一（CRLF -> LF）
    content = content.replace("\r\n", "\n")

    # 末尾の改行を統一（常に1つの改行で終わるようにする）
    content = content.rstrip("\n") + "\n"

    lines = content.split("\n")
    normalized = []

    for line in lines:
        # 行末の空白を削除（安定性向上）
        line = line.rstrip()

        # バージョン情報などをスキップ（必要に応じて追加）
        if "version" in line.lower() or "timestamp" in line.lower():
            continue

        # Python関数のパラメータ表記の正規化
        # 環境によって (i):Any と (Any):Any のように異なる場合がある
        # 単一文字のパラメータ名を Any に正規化
        import re

        line = re.sub(r"\| (\w+) \| \(([a-z])\):", r"| \1 | (Any):", line)

        normalized.append(line)

    # 再度末尾の改行を統一
    result = "\n".join(normalized)
    return result.rstrip("\n") + "\n"


def compare_with_golden_master(
    input_file: str, golden_name: str, table_format: str = "full"
) -> tuple[bool, str]:
    """
    現在の出力とゴールデンマスターを比較

    Returns:
        (一致するか, 差分メッセージ)
    """
    golden_path = (
        Path("tests/golden_masters") / table_format / f"{golden_name}_{table_format}.md"
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
    else:
        # 差分を生成
        diff_lines = []
        golden_lines = golden_normalized.split("\n")
        current_lines = current_normalized.split("\n")

        max_lines = max(len(golden_lines), len(current_lines))
        diff_count = 0

        # まず全体をスキャンして差分の総数をカウント
        for i in range(max_lines):
            if i >= len(golden_lines) or i >= len(current_lines):
                diff_count += 1
            elif golden_lines[i] != current_lines[i]:
                diff_count += 1

        # 最初の20行の差分を表示
        diff_shown = 0
        for i in range(max_lines):
            if i >= len(golden_lines):
                if diff_shown < 20:
                    diff_lines.append(f"Line {i+1}: + {current_lines[i]!r}")
                    diff_shown += 1
            elif i >= len(current_lines):
                if diff_shown < 20:
                    diff_lines.append(f"Line {i+1}: - {golden_lines[i]!r}")
                    diff_shown += 1
            elif golden_lines[i] != current_lines[i]:
                if diff_shown < 20:
                    diff_lines.append(f"Line {i+1}:")
                    diff_lines.append(f"  Golden: {golden_lines[i]!r}")
                    diff_lines.append(f"  Current: {current_lines[i]!r}")
                    diff_shown += 1

        if diff_count > 20:
            diff_lines.append(f"... ({diff_count - 20} more differences)")

        diff_message = (
            f"Output differs from golden master ({diff_count} differences):\n"
            f"Golden lines: {len(golden_lines)}, Current lines: {len(current_lines)}\n"
        )
        diff_message += "\n".join(diff_lines)

        return False, diff_message


class TestGoldenMasterRegression:
    """ゴールデンマスターリグレッションテスト"""

    @pytest.mark.parametrize(
        "input_file,golden_name,table_format",
        [
            # Java tests
            ("examples/Sample.java", "java_sample", "full"),
            ("examples/Sample.java", "java_sample", "compact"),
            ("examples/Sample.java", "java_sample", "csv"),
            ("examples/BigService.java", "java_bigservice", "full"),
            ("examples/BigService.java", "java_bigservice", "compact"),
            # Python tests
            ("examples/sample.py", "python_sample", "full"),
            ("examples/sample.py", "python_sample", "compact"),
            # TypeScript tests
            ("tests/test_data/test_enum.ts", "typescript_enum", "full"),
            # JavaScript tests
            ("tests/test_data/test_class.js", "javascript_class", "full"),
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
