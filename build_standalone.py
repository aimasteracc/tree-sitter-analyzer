#!/usr/bin/env python3
"""
スタンドアロン実行ファイル作成用スクリプト
PyInstallerを使用してtree-sitter-analyzerの実行ファイルを作成します。
"""

import subprocess
import sys


def install_pyinstaller():
    """PyInstallerをインストール"""
    try:
        import importlib.util

        if importlib.util.find_spec("PyInstaller") is not None:
            print("PyInstaller is already installed")
        else:
            raise ImportError("PyInstaller not found")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def create_spec_file():
    """PyInstaller用の.specファイルを作成"""
    spec_content = """# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['tree_sitter_analyzer/cli_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('tree_sitter_analyzer/queries', 'tree_sitter_analyzer/queries'),
    ],
    hiddenimports=[
        'tree_sitter_analyzer',
        'tree_sitter_analyzer.cli',
        'tree_sitter_analyzer.core',
        'tree_sitter_analyzer.languages',
        'tree_sitter_analyzer.plugins',
        'tree_sitter_analyzer.formatters',
        'tree_sitter_analyzer.interfaces',
        'tree_sitter',
        'tree_sitter_java',
        'chardet',
        'cachetools',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='tree-sitter-analyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
"""

    with open("tree-sitter-analyzer.spec", "w", encoding="utf-8") as f:
        f.write(spec_content)
    print("Created tree-sitter-analyzer.spec")


def build_executable():
    """実行ファイルをビルド"""
    print("Building standalone executable...")
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "tree-sitter-analyzer.spec",
            ]
        )
        print("Build completed successfully!")
        print("Executable location: dist/tree-sitter-analyzer.exe")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return False
    return True


def main():
    """メイン処理"""
    print("=== Tree-sitter Analyzer Standalone Builder ===")

    # 必要な依存関係をインストール
    install_pyinstaller()

    # .specファイルを作成
    create_spec_file()

    # 実行ファイルをビルド
    if build_executable():
        print("\n=== Build Summary ===")
        print("✓ Standalone executable created successfully")
        print("✓ Location: dist/tree-sitter-analyzer.exe")
        print("✓ This executable can run without Python installation")
        print("\nUsage:")
        print("  ./dist/tree-sitter-analyzer.exe examples/Sample.java --advanced")
    else:
        print("\n❌ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
