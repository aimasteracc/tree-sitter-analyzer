#!/usr/bin/env python3
"""
Golden Master 更新スクリプト

修正後の出力を新しいゴールデンマスターとして保存し、
リグレッションテストに使用できるようにします。

使用方法:
    python update_baselines.py
"""

import subprocess  # nosec B404
import sys
from pathlib import Path


def run_command(cmd: list[str]) -> tuple[int, str]:
    """コマンドを実行して結果を返す"""
    try:
        result = subprocess.run(  # nosec B603
            cmd, capture_output=True, text=True, encoding="utf-8", check=False
        )
        return result.returncode, result.stdout
    except Exception as e:
        print(f"Error running command {' '.join(cmd)}: {e}", file=sys.stderr)
        return 1, ""


def update_golden_master(
    input_file: str, output_name: str, table_format: str = "full"
) -> bool:
    """ゴールデンマスターを更新"""
    golden_dir = Path("tests/golden_masters") / table_format
    golden_dir.mkdir(parents=True, exist_ok=True)

    output_file = golden_dir / f"{output_name}_{table_format}.md"

    print(f"Generating golden master: {output_file}")

    cmd = ["uv", "run", "tree-sitter-analyzer", input_file, "--table", table_format]

    returncode, output = run_command(cmd)

    if returncode != 0:
        print(f"  ❌ Failed to generate output for {input_file}", file=sys.stderr)
        return False

    # 出力を保存
    output_file.write_text(output, encoding="utf-8")
    print(f"  ✅ Updated: {output_file}")
    return True


def main():
    """メイン処理"""
    print("=" * 80)
    print("Golden Master Update Script")
    print("=" * 80)
    print()

    # 更新対象のテストケース
    # (入力ファイル, 出力名ベース - 言語_ファイル名の形式)
    test_cases = [
        # Java samples
        ("examples/Sample.java", "java_sample"),
        ("examples/BigService.java", "java_bigservice"),
        # Python samples
        ("examples/sample.py", "python_sample"),
        # TypeScript samples (from test_data)
        ("tests/test_data/test_enum.ts", "typescript_enum"),
        # JavaScript samples (from test_data)
        ("tests/test_data/test_class.js", "javascript_class"),
        # SQL samples
        ("examples/sample_database.sql", "sql_sample_database"),
    ]

    formats = ["full", "compact", "csv"]

    success_count = 0
    total_count = 0

    for input_file, output_name in test_cases:
        if not Path(input_file).exists():
            print(f"⚠️  Skipping {input_file} (not found)")
            continue

        for fmt in formats:
            total_count += 1
            if update_golden_master(input_file, output_name, fmt):
                success_count += 1

    print()
    print("=" * 80)
    print(f"Results: {success_count}/{total_count} golden masters updated")
    print("=" * 80)

    if success_count == total_count:
        print("✅ All golden masters updated successfully!")
        return 0
    else:
        print("⚠️  Some golden masters failed to update")
        return 1


if __name__ == "__main__":
    sys.exit(main())
