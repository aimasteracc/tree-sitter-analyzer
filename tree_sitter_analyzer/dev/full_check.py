#!/usr/bin/env python3
"""
完全品質チェックツール

CI/CD環境相当の包括的な品質チェックを実行します。
pyproject.tomlの設定に基づいて、全ての品質基準をチェックします。

使用方法:
    uv run tsa-full-check
    または
    python -m tree_sitter_analyzer.dev.full_check
"""

import subprocess
import sys
import time


def run_check(name: str, cmd: str, fix_mode: bool = False) -> bool:
    """品質チェックを実行する"""
    action = "修正中" if fix_mode else "チェック中"
    print(f"🔍 {action}: {name}...")
    start_time = time.time()

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    duration = time.time() - start_time

    if result.returncode == 0:
        status = "修正完了" if fix_mode else "OK"
        print(f"✅ {name} {status} ({duration:.1f}s)")
        return True
    else:
        status = "修正失敗" if fix_mode else "FAILED"
        print(f"❌ {name} {status} ({duration:.1f}s)")
        if result.stdout:
            print(
                "STDOUT:",
                (
                    result.stdout[:500] + "..."
                    if len(result.stdout) > 500
                    else result.stdout
                ),
            )
        if result.stderr:
            print(
                "STDERR:",
                (
                    result.stderr[:500] + "..."
                    if len(result.stderr) > 500
                    else result.stderr
                ),
            )
        return False


def main() -> None:
    """メイン処理"""
    print("🔍 Tree-sitter Analyzer 完全品質チェック")
    print("=" * 50)

    # 修正可能な項目を先に実行
    fix_checks: list[tuple[str, str]] = [
        ("Black format", "uv run black --line-length=88 ."),
        ("Ruff lint & fix", "uv run ruff check --fix ."),
        ("Ruff format", "uv run ruff format ."),
        ("Import sorting", "uv run isort --profile black --line-length 88 ."),
        (
            "Python upgrade",
            "uv run pyupgrade --py310-plus tree_sitter_analyzer/**/*.py",
        ),
    ]

    # 検証のみの項目
    check_only: list[tuple[str, str]] = [
        (
            "Type checking",
            "uv run mypy tree_sitter_analyzer/ --ignore-missing-imports --no-error-summary --show-error-codes --explicit-package-bases",
        ),
        ("Security check", "uv run bandit -r tree_sitter_analyzer/ --format json"),
        (
            "Documentation check",
            "uv run pydocstyle tree_sitter_analyzer/ --convention=google --add-ignore=D100,D101,D102,D103,D104,D105,D107",
        ),
        (
            "Flake8 lint",
            "uv run flake8 tree_sitter_analyzer/ --max-line-length=88 --extend-ignore=E203,W503,E501",
        ),
        ("Tests", "uv run pytest tests/ -v --tb=short"),
    ]

    start_time = time.time()

    # 修正フェーズ
    print("🔧 修正フェーズ:")
    fix_passed = 0
    for name, cmd in fix_checks:
        if run_check(name, cmd, fix_mode=True):
            fix_passed += 1

    print(f"\n修正フェーズ完了: {fix_passed}/{len(fix_checks)} 項目")

    # 検証フェーズ
    print("\n🧪 検証フェーズ:")
    check_passed = 0
    for name, cmd in check_only:
        if run_check(name, cmd, fix_mode=False):
            check_passed += 1

    total_duration = time.time() - start_time
    total_passed = fix_passed + check_passed
    total_checks = len(fix_checks) + len(check_only)

    print("\n" + "=" * 50)
    print(f"📊 最終結果: {total_passed}/{total_checks} チェック通過")
    print(f"⏱️  総実行時間: {total_duration:.1f}秒")

    if total_passed == total_checks:
        print("🎉 全ての品質チェックが通りました！")
        print("\n🚀 プロダクション準備完了:")
        print("  - git commit でコミット")
        print("  - git push でプッシュ")
        print("  - CI/CDパイプラインで最終確認")
        sys.exit(0)
    else:
        failed_count = total_checks - total_passed
        print(f"💥 {failed_count} 項目で問題が検出されました")
        print("\n🔧 推奨アクション:")

        if fix_passed < len(fix_checks):
            print("  1. 修正フェーズの失敗項目を手動で修正")

        if check_passed < len(check_only):
            print("  2. 検証フェーズの失敗項目を確認・修正")
            print("     - MyPy: 型ヒントの追加・修正")
            print("     - Bandit: セキュリティ問題の修正")
            print("     - pydocstyle: docstringの追加・修正")
            print("     - Tests: テストの修正・追加")

        print("  3. uv run tsa-fast-check で再確認")
        sys.exit(1)


if __name__ == "__main__":
    main()
