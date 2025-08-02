#!/usr/bin/env python3
"""
トークン消費量比較分析スクリプト
構造化データ（詳細・要約）の有無によるトークン消費量の違いを計算・比較します。
"""

import json
import re


def count_tokens_estimate(text):
    """
    厳密なトークナイザーの代わりに文字数でトークン数を概算する。
    一般的に、日本語は1文字=1トークン、英数字は4文字=1トークン程度として計算。
    """
    # 日本語文字（ひらがな、カタカナ、漢字）をカウント
    japanese_chars = len(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", text))

    # その他の文字（英数字、記号、スペースなど）をカウント
    other_chars = len(text) - japanese_chars

    # トークン数の概算：日本語1文字=1トークン、その他4文字=1トークン
    estimated_tokens = japanese_chars + (other_chars // 4)

    return estimated_tokens


def read_file_content(file_path):
    """ファイルの内容を読み込む"""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"ファイル読み込みエラー: {e}")
        return ""


def extract_method_lines(java_content, start_line, end_line):
    """指定された行範囲のコードを抽出"""
    lines = java_content.split("\n")
    # 1-based indexing to 0-based indexing
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)

    extracted_lines = lines[start_idx:end_idx]
    return "\n".join(extracted_lines)


def find_update_customer_name_method_detailed(json_content):
    """BigService.jsonからupdateCustomerNameメソッドの情報を取得（詳細版）"""
    try:
        # JSONコンテンツから実際のJSON部分を抽出
        json_start = json_content.find("{")
        if json_start == -1:
            return None

        json_data = json.loads(json_content[json_start:])

        # methodsセクションからupdateCustomerNameを探す
        for method in json_data.get("methods", []):
            if method.get("name") == "updateCustomerName":
                lines_str = method.get("lines", "")
                if "-" in lines_str:
                    start_line, end_line = map(int, lines_str.split("-"))
                    return {
                        "name": method.get("name"),
                        "start_line": start_line,
                        "end_line": end_line,
                        "lines": lines_str,
                        "visibility": method.get("visibility"),
                        "parameters": method.get("parameters"),
                        "complexity": method.get("complexity"),
                    }
        return None
    except Exception as e:
        print(f"詳細JSON解析エラー: {e}")
        return None


def find_update_customer_name_method_summary(summary_content):
    """BigService.summary.jsonからupdateCustomerNameメソッドの情報を取得（要約版）"""
    try:
        # JSONコンテンツから実際のJSON部分を抽出
        json_start = summary_content.find("{")
        if json_start == -1:
            return None

        json_data = json.loads(summary_content[json_start:])

        # summary_elementsセクションからupdateCustomerNameを探す
        for element in json_data.get("summary_elements", []):
            if (
                element.get("name") == "updateCustomerName"
                and element.get("type") == "method"
            ):
                lines_info = element.get("lines", {})
                start_line = lines_info.get("start")
                end_line = lines_info.get("end")

                if start_line and end_line:
                    return {
                        "name": element.get("name"),
                        "start_line": start_line,
                        "end_line": end_line,
                        "lines": f"{start_line}-{end_line}",
                        "type": element.get("type"),
                    }
        return None
    except Exception as e:
        print(f"要約JSON解析エラー: {e}")
        return None


def main():
    print("=" * 80)
    print("トークン消費量の最終比較分析")
    print("=" * 80)

    # ファイル読み込み
    java_content = read_file_content("BigService.java")
    json_content = read_file_content("BigService.json")
    summary_content = read_file_content("BigService.summary.json")

    if not java_content or not json_content or not summary_content:
        print("ファイルの読み込みに失敗しました。")
        return

    # BigService.javaの基本情報
    java_lines = java_content.split("\n")
    total_java_lines = len(java_lines)

    print(f"BigService.java: {total_java_lines:,}行")

    # updateCustomerNameメソッドの情報を取得（詳細版と要約版）
    method_info_detailed = find_update_customer_name_method_detailed(json_content)
    method_info_summary = find_update_customer_name_method_summary(summary_content)

    if not method_info_detailed or not method_info_summary:
        print("updateCustomerNameメソッドの情報が見つかりませんでした。")
        return

    print(f"updateCustomerNameメソッド: {method_info_detailed['lines']}行")

    # シナリオ1: BigService.java全体のトークン数
    scenario1_tokens = count_tokens_estimate(java_content)

    # シナリオ2: BigService.json + updateCustomerNameメソッド部分のトークン数
    json_tokens = count_tokens_estimate(json_content)

    # updateCustomerNameメソッドの部分を抽出
    method_code = extract_method_lines(
        java_content,
        method_info_detailed["start_line"],
        method_info_detailed["end_line"],
    )
    method_tokens = count_tokens_estimate(method_code)
    method_lines_count = (
        method_info_detailed["end_line"] - method_info_detailed["start_line"] + 1
    )

    scenario2_tokens = json_tokens + method_tokens

    # シナリオ3: BigService.summary.json + updateCustomerNameメソッド部分のトークン数
    summary_tokens = count_tokens_estimate(summary_content)
    scenario3_tokens = summary_tokens + method_tokens

    # 削減量と削減率の計算
    scenario2_reduction = scenario1_tokens - scenario2_tokens
    scenario2_reduction_percentage = (
        (scenario2_reduction / scenario1_tokens) * 100 if scenario1_tokens > 0 else 0
    )

    scenario3_reduction_vs_scenario1 = scenario1_tokens - scenario3_tokens
    scenario3_reduction_percentage_vs_scenario1 = (
        (scenario3_reduction_vs_scenario1 / scenario1_tokens) * 100
        if scenario1_tokens > 0
        else 0
    )

    scenario3_reduction_vs_scenario2 = scenario2_tokens - scenario3_tokens
    scenario3_reduction_percentage_vs_scenario2 = (
        (scenario3_reduction_vs_scenario2 / scenario2_tokens) * 100
        if scenario2_tokens > 0
        else 0
    )

    # 結果の表示
    print("\n" + "=" * 80)
    print("【トークン消費量の最終比較】")
    print("=" * 80)

    print("\n■ シナリオ1：従来型（ファイル全体）")
    print(f"   - 対象: BigService.java ({total_java_lines:,}行)")
    print(f"   - トークン数: 約 {scenario1_tokens:,} トークン")

    print("\n■ シナリオ2：詳細データ活用")
    print(f"   - 対象: BigService.json + コード一部 ({method_lines_count}行)")
    print(
        f"   - トークン数: 約 {scenario2_tokens:,} トークン (JSON: {json_tokens:,} + コード: {method_tokens:,})"
    )
    print(f"   - 削減率 (vs シナリオ1): 約 {scenario2_reduction_percentage:.1f}%")

    print("\n■ シナリオ3：要約データ活用")
    print(f"   - 対象: BigService.summary.json + コード一部 ({method_lines_count}行)")
    print(
        f"   - トークン数: 約 {scenario3_tokens:,} トークン (JSON: {summary_tokens:,} + コード: {method_tokens:,})"
    )
    print(
        f"   - 削減率 (vs シナリオ1): 約 {scenario3_reduction_percentage_vs_scenario1:.1f}%"
    )
    print(
        f"   - 削減率 (vs シナリオ2): 約 {scenario3_reduction_percentage_vs_scenario2:.1f}%"
    )

    # 詳細情報
    print("\n" + "=" * 80)
    print("【詳細情報】")
    print("=" * 80)
    print("updateCustomerNameメソッド詳細:")
    print(f"  - 行範囲: {method_info_detailed['lines']}")
    print(f"  - 抽出行数: {method_lines_count}行")
    print(f"  - 可視性: {method_info_detailed.get('visibility', 'N/A')}")
    print(f"  - パラメータ数: {method_info_detailed.get('parameters', 'N/A')}")
    print(f"  - 複雑度: {method_info_detailed.get('complexity', 'N/A')}")

    print("\nファイルサイズ比較:")
    print(f"  - BigService.java: {len(java_content):,} 文字")
    print(f"  - BigService.json: {len(json_content):,} 文字")
    print(f"  - BigService.summary.json: {len(summary_content):,} 文字")
    print(f"  - 抽出コード部分: {len(method_code):,} 文字")

    print("\n注記: トークン数は文字数ベースの概算値です。")
    print("      日本語文字=1トークン、その他4文字=1トークンとして計算。")

    # 結論
    print("\n" + "=" * 80)
    print("【結論】")
    print("=" * 80)
    print("--summary機能の導入により、シナリオ2と比較して")
    print(
        f"さらに約 {scenario3_reduction_percentage_vs_scenario2:.1f}% のトークン削減が実現されました。"
    )
    print("\nこの改善により、LLMを活用した開発支援ツールの")
    print("実用性と経済性が大幅に向上し、より効率的な")
    print("コード解析とAI支援開発が可能になります。")


if __name__ == "__main__":
    main()
