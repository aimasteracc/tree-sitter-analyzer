#!/usr/bin/env python3
"""
高速品質チェックツール

日常的な開発で使用する軽量で高速な品質チェックを実行します。
pyproject.tomlの設定に基づいて、必要最小限のチェックを行います。

使用方法:
    uv run tsa-fast-check
    または
    python -m tree_sitter_analyzer.dev.fast_check
"""

import subprocess
import sys
import time


def run_check(name: str, cmd: str) -> bool:
    """品質チェックを実行する"""
    print(f"🔍 {name}...")
    start_time = time.time()

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    duration = time.time() - start_time

    if result.returncode == 0:
        print(f"✅ {name} OK ({duration:.1f}s)")
        return True
    else:
        print(f"❌ {name} FAILED ({duration:.1f}s)")
        if result.stdout:
            print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return False


def main() -> None:
    """メイン処理"""
    print("🚀 Tree-sitter Analyzer 高速品質チェック")
    print("=" * 50)

    # 高速チェック項目（pyproject.tomlの設定に基づく）
    checks: list[tuple[str, str]] = [
        ("Black format check", "uv run black --check --line-length=88 ."),
        ("Ruff lint", "uv run ruff check ."),
        (
            "Import sorting",
            "uv run isort --check-only --profile black --line-length 88 .",
        ),
        (
            "Python syntax",
            "uv run python -m py_compile tree_sitter_analyzer/__init__.py",
        ),
    ]

    start_time = time.time()
    passed_checks = 0
    total_checks = len(checks)

    for name, cmd in checks:
        if run_check(name, cmd):
            passed_checks += 1

    total_duration = time.time() - start_time

    print("\n" + "=" * 50)
    print(f"📊 結果: {passed_checks}/{total_checks} チェック通過")
    print(f"⏱️  実行時間: {total_duration:.1f}秒")

    if passed_checks == total_checks:
        print("🎉 全ての高速チェックが通りました！")
        print("\n💡 次のステップ:")
        print("  - git commit でコミット（最適化されたpre-commit）")
        print("  - uv run tsa-full-check で完全チェック")
        sys.exit(0)
    else:
        print("💥 一部のチェックが失敗しました")
        print("\n🔧 修正方法:")
        print("  - uv run black . でフォーマット修正")
        print("  - uv run ruff check --fix . でlint修正")
        print("  - uv run isort . でimport修正")
        sys.exit(1)


if __name__ == "__main__":
    main()
