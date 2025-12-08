#!/usr/bin/env python3
"""
YAML Golden Master Regression Test

YAMLファイルのゴールデンマスターと現在の出力を比較して、
意図しない変更がないことを確認します。

使用方法:
    pytest tests/test_yaml/test_yaml_golden_master.py -v
"""

import asyncio
from pathlib import Path

import pytest


def normalize_yaml_output(content: str) -> str:
    """
    YAML出力を正規化して、可変部分を除去します
    """
    # 改行コードを統一（CRLF -> LF）
    content = content.replace("\r\n", "\n")

    # 末尾の改行を統一
    content = content.rstrip("\n") + "\n"

    lines = content.split("\n")
    normalized = []

    for line in lines:
        # 行末の空白を削除
        line = line.rstrip()
        normalized.append(line)

    result = "\n".join(normalized)
    return result.rstrip("\n") + "\n"


async def run_yaml_analyzer(input_file: str, table_format: str = "full") -> str:
    """YAMLアナライザーを実行して出力を取得"""
    from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
    from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter
    from tree_sitter_analyzer.languages.yaml_plugin import YAMLPlugin

    plugin = YAMLPlugin()
    request = AnalysisRequest(file_path=input_file)
    result = await plugin.analyze_file(input_file, request)

    formatter = YAMLFormatter()
    data = formatter._convert_analysis_result_to_format(result)
    output = formatter.format_table(data, table_format)

    return output


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
        current_content = asyncio.run(run_yaml_analyzer(input_file, table_format))
    except Exception as e:
        return False, f"Failed to run analyzer: {e}"

    # 正規化して比較
    golden_normalized = normalize_yaml_output(golden_content)
    current_normalized = normalize_yaml_output(current_content)

    if golden_normalized == current_normalized:
        return True, "Output matches golden master"
    else:
        # 差分を生成
        diff_lines = []
        golden_lines = golden_normalized.split("\n")
        current_lines = current_normalized.split("\n")

        max_lines = max(len(golden_lines), len(current_lines))
        diff_count = 0

        for i in range(max_lines):
            if i >= len(golden_lines) or i >= len(current_lines):
                diff_count += 1
            elif golden_lines[i] != current_lines[i]:
                diff_count += 1

        diff_shown = 0
        for i in range(max_lines):
            if i >= len(golden_lines):
                if diff_shown < 20:
                    diff_lines.append(f"Line {i + 1}: + {current_lines[i]!r}")
                    diff_shown += 1
            elif i >= len(current_lines):
                if diff_shown < 20:
                    diff_lines.append(f"Line {i + 1}: - {golden_lines[i]!r}")
                    diff_shown += 1
            elif golden_lines[i] != current_lines[i]:
                if diff_shown < 20:
                    diff_lines.append(f"Line {i + 1}:")
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


class TestYAMLGoldenMasterRegression:
    """YAMLゴールデンマスターリグレッションテスト"""

    @pytest.mark.parametrize(
        "input_file,golden_name,table_format",
        [
            # YAML tests
            ("examples/sample_config.yaml", "yaml_sample_config", "full"),
        ],
    )
    def test_yaml_golden_master_comparison(
        self, input_file: str, golden_name: str, table_format: str
    ):
        """YAMLゴールデンマスターとの比較テスト"""
        input_path = Path(input_file)

        if not input_path.exists():
            pytest.skip(f"Input file not found: {input_file}")

        matches, message = compare_with_golden_master(
            input_file, golden_name, table_format
        )

        assert matches, message

    def test_yaml_elements_extracted(self):
        """YAML要素が正しく抽出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # Document Overviewセクションが存在することを確認
        assert "## Document Overview" in output

        # Mappingsセクションが存在することを確認
        assert "## Mappings" in output

        # Anchorsセクションが存在することを確認
        assert "## Anchors" in output
        assert "&db_creds" in output

        # Aliasesセクションが存在することを確認
        assert "## Aliases" in output
        assert "*db_creds" in output

        # Commentsセクションが存在することを確認
        assert "## Comments" in output

    def test_yaml_multi_document_detected(self):
        """マルチドキュメントが正しく検出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # 2つのドキュメントが検出されることを確認
        assert "| 0 |" in output
        assert "| 1 |" in output

    def test_yaml_value_types_correct(self):
        """値の型が正しく識別されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # 各種型が正しく識別されることを確認
        assert "| string |" in output
        assert "| number |" in output
        assert "| boolean |" in output
        assert "| null |" in output
        assert "| mapping |" in output
        assert "| sequence |" in output

    def test_yaml_merge_key_detected(self):
        """マージキー（<<: *anchor）が正しく検出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # マージキーが検出されることを確認
        assert "| << | alias |" in output

        # defaults アンカーが検出されることを確認
        assert "&defaults" in output

        # *defaults エイリアスが検出されることを確認（2回使用）
        assert "*defaults" in output

    def test_yaml_block_scalars_detected(self):
        """ブロックスカラー（| と >）が正しく検出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # description（リテラルブロックスカラー |）が検出されることを確認
        assert "| description | string |" in output

        # summary（フォールドブロックスカラー >）が検出されることを確認
        assert "| summary | string |" in output

    def test_yaml_flow_style_detected(self):
        """フロースタイル（{} と []）が正しく検出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # フローマッピングが検出されることを確認
        assert "| flow_mapping | mapping |" in output
        assert "| key1 | string |" in output
        assert "| key2 | string |" in output

        # フローシーケンスが検出されることを確認
        assert "| flow_sequence | sequence |" in output

    def test_yaml_deep_nesting_detected(self):
        """深いネスト構造が正しく検出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # 5レベルのネストが検出されることを確認
        assert "| deep_value | string | 5 |" in output

        # ネスト構造が検出されることを確認
        assert "| level1 | mapping | 2 |" in output
        assert "| level2 | mapping | 3 |" in output
        assert "| level3 | mapping | 4 |" in output

    def test_yaml_comments_extracted(self):
        """コメントが正しく抽出されることを確認"""
        output = asyncio.run(run_yaml_analyzer("examples/sample_config.yaml", "full"))

        # 各種コメントが検出されることを確認
        assert "Application configuration" in output
        assert "Merge key example" in output
        assert "Block scalar examples" in output
        assert "Flow style examples" in output
        assert "Nested structures" in output
        assert "Second document - metadata" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
