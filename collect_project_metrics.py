#!/usr/bin/env python3
"""
tree-sitter-analyzerプロジェクト固有のメトリクス収集スクリプト
"""

from collections import defaultdict
from pathlib import Path


def is_project_file(filepath):
    """プロジェクト固有のファイルかどうかを判定"""
    path_str = str(filepath)
    # 除外するディレクトリ
    exclude_dirs = [
        ".venv",
        "__pycache__",
        ".git",
        ".pytest_cache",
        "node_modules",
        ".ruff_cache",
    ]

    for exclude_dir in exclude_dirs:
        if exclude_dir in path_str:
            return False
    return True


def count_lines_in_file(filepath):
    """ファイルの行数を数える"""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            total_lines = len(lines)
            empty_lines = sum(1 for line in lines if line.strip() == "")
            comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
            code_lines = total_lines - empty_lines - comment_lines
            return {
                "total": total_lines,
                "empty": empty_lines,
                "comment": comment_lines,
                "code": code_lines,
            }
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return {"total": 0, "empty": 0, "comment": 0, "code": 0}


def collect_file_metrics():
    """ファイルメトリクスを収集"""
    print("=== プロジェクトファイル統計 ===")

    # プロジェクト固有のPythonファイルの統計
    all_py_files = list(Path(".").rglob("*.py"))
    py_files = [f for f in all_py_files if is_project_file(f)]
    test_files = [
        f
        for f in py_files
        if "test_" in f.name or f.name.startswith("test_") or "tests/" in str(f)
    ]

    print(f"プロジェクト内Pythonファイル数: {len(py_files)}")
    print(f"テストファイル数: {len(test_files)}")
    print(f"プロダクションファイル数: {len(py_files) - len(test_files)}")

    # 言語別ファイル数（プロジェクト固有のみ）
    extensions = defaultdict(int)
    for file_path in Path(".").rglob("*"):
        if file_path.is_file() and is_project_file(file_path):
            ext = file_path.suffix.lower()
            if ext:
                extensions[ext] += 1

    print("\n=== 言語別ファイル数（プロジェクト固有）===")
    for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
        if count > 1:  # 2個以上のファイルがある拡張子のみ表示
            print(f"{ext}: {count}")

    return py_files, test_files


def collect_line_metrics(py_files, test_files):
    """行数メトリクスを収集"""
    print("\n=== 行数統計（プロジェクト固有）===")

    total_metrics = {"total": 0, "empty": 0, "comment": 0, "code": 0}
    test_metrics = {"total": 0, "empty": 0, "comment": 0, "code": 0}
    prod_metrics = {"total": 0, "empty": 0, "comment": 0, "code": 0}

    file_sizes = []

    for py_file in py_files:
        metrics = count_lines_in_file(py_file)
        file_sizes.append((py_file, metrics["total"]))

        # 総計に追加
        for key in total_metrics:
            total_metrics[key] += metrics[key]

        # テストファイルかプロダクションファイルかで分類
        if py_file in test_files:
            for key in test_metrics:
                test_metrics[key] += metrics[key]
        else:
            for key in prod_metrics:
                prod_metrics[key] += metrics[key]

    print("全体:")
    print(f"  総行数: {total_metrics['total']:,}")
    print(f"  実効コード行数: {total_metrics['code']:,}")
    print(f"  コメント行数: {total_metrics['comment']:,}")
    print(f"  空行数: {total_metrics['empty']:,}")

    print("\nプロダクションコード:")
    print(f"  総行数: {prod_metrics['total']:,}")
    print(f"  実効コード行数: {prod_metrics['code']:,}")

    print("\nテストコード:")
    print(f"  総行数: {test_metrics['total']:,}")
    print(f"  実効コード行数: {test_metrics['code']:,}")

    # 最大ファイルサイズ（プロジェクト固有のみ）
    file_sizes.sort(key=lambda x: x[1], reverse=True)
    print("\n=== 最大ファイル（上位10件）===")
    for i, (file_path, lines) in enumerate(file_sizes[:10]):
        print(f"{i + 1:2d}. {file_path} ({lines:,} 行)")

    return total_metrics, prod_metrics, test_metrics


def analyze_project_structure():
    """プロジェクト構造を分析"""
    print("\n=== プロジェクト構造分析 ===")

    # メインパッケージのディレクトリ構造
    main_package = Path("tree_sitter_analyzer")
    if main_package.exists():
        print(f"メインパッケージ: {main_package}")
        subdirs = [d for d in main_package.rglob("*") if d.is_dir()]
        print(f"サブディレクトリ数: {len(subdirs)}")

        # 主要なサブモジュール
        main_subdirs = [d for d in main_package.iterdir() if d.is_dir()]
        print("主要サブモジュール:")
        for subdir in sorted(main_subdirs):
            py_files_in_subdir = list(subdir.rglob("*.py"))
            print(f"  {subdir.name}: {len(py_files_in_subdir)} ファイル")


def check_dependencies():
    """依存関係を確認"""
    print("\n=== 依存関係確認 ===")

    # pyproject.tomlから依存関係を読み取り
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        print("pyproject.tomlから依存関係を確認:")
        try:
            with open(pyproject_path, encoding="utf-8") as f:
                content = f.read()
                if "[tool.poetry.dependencies]" in content:
                    lines = content.split("\n")
                    in_deps = False
                    for line in lines:
                        if "[tool.poetry.dependencies]" in line:
                            in_deps = True
                            continue
                        elif line.startswith("[") and in_deps:
                            break
                        elif in_deps and "=" in line:
                            print(f"  {line.strip()}")
        except Exception as e:
            print(f"pyproject.toml読み取りエラー: {e}")


def main():
    """メイン関数"""
    print("tree-sitter-analyzer プロジェクト固有メトリクス収集")
    print("=" * 60)

    # ファイルメトリクス収集
    py_files, test_files = collect_file_metrics()

    # 行数メトリクス収集
    total_metrics, prod_metrics, test_metrics = collect_line_metrics(
        py_files, test_files
    )

    # プロジェクト構造分析
    analyze_project_structure()

    # 依存関係確認
    check_dependencies()

    print("\n" + "=" * 60)
    print("プロジェクト固有メトリクス収集完了")

    # サマリー
    print("\n=== サマリー ===")
    print(f"プロジェクト規模: {len(py_files)} Pythonファイル")
    print(f"総コード行数: {total_metrics['code']:,} 行")
    print(f"テストカバレッジ対象: {len(test_files)} テストファイル")
    print(
        f"平均ファイルサイズ: {total_metrics['total'] // len(py_files) if py_files else 0} 行/ファイル"
    )


if __name__ == "__main__":
    main()
