#!/usr/bin/env python3
"""
PyPIアップロード用スクリプト
tree-sitter-analyzerをPyPIに安全にアップロードするためのスクリプト
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """必要なツールがインストールされているかチェック"""
    required_tools = ['twine', 'build']
    missing_tools = []
    
    for tool in required_tools:
        try:
            subprocess.check_call([sys.executable, "-m", tool, "--help"], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing_tools.append(tool)
    
    if missing_tools:
        print(f"Missing required tools: {', '.join(missing_tools)}")
        print("Installing missing tools...")
        for tool in missing_tools:
            subprocess.check_call([sys.executable, "-m", "pip", "install", tool])
        print("✓ All required tools installed")
    else:
        print("✓ All required tools are available")

def clean_dist():
    """distフォルダをクリーンアップ"""
    dist_path = Path("dist")
    if dist_path.exists():
        import shutil
        shutil.rmtree(dist_path)
        print("✓ Cleaned dist directory")

def build_package():
    """パッケージをビルド"""
    print("Building package...")
    try:
        subprocess.check_call([sys.executable, "-m", "build"])
        print("✓ Package built successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False

def check_package():
    """パッケージの整合性をチェック"""
    print("Checking package integrity...")
    try:
        subprocess.check_call([sys.executable, "-m", "twine", "check", "dist/*"])
        print("✓ Package integrity check passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Package check failed: {e}")
        return False

def upload_to_test_pypi():
    """TestPyPIにアップロード"""
    print("Uploading to TestPyPI...")
    print("Note: You need to have TestPyPI credentials configured")
    print("Visit: https://test.pypi.org/account/register/")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "twine", "upload",
            "--repository", "testpypi",
            "dist/*"
        ])
        print("✓ Successfully uploaded to TestPyPI")
        print("Test installation with:")
        print("  pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ TestPyPI upload failed: {e}")
        return False

def upload_to_pypi():
    """本番PyPIにアップロード"""
    print("Uploading to PyPI...")
    print("Note: You need to have PyPI credentials configured")
    print("Visit: https://pypi.org/account/register/")
    
    confirm = input("Are you sure you want to upload to production PyPI? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Upload cancelled")
        return False
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "twine", "upload",
            "dist/*"
        ])
        print("✓ Successfully uploaded to PyPI")
        print("Install with:")
        print("  pip install tree-sitter-analyzer")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ PyPI upload failed: {e}")
        return False

def main():
    """メイン処理"""
    print("=== PyPI Upload Tool for tree-sitter-analyzer ===")
    
    # 必要なツールをチェック
    check_requirements()
    
    # distフォルダをクリーンアップ
    clean_dist()
    
    # パッケージをビルド
    if not build_package():
        sys.exit(1)
    
    # パッケージの整合性をチェック
    if not check_package():
        sys.exit(1)
    
    print("\n=== Upload Options ===")
    print("1. Upload to TestPyPI (recommended first)")
    print("2. Upload to production PyPI")
    print("3. Exit")
    
    choice = input("Choose an option (1-3): ")
    
    if choice == "1":
        upload_to_test_pypi()
    elif choice == "2":
        upload_to_pypi()
    elif choice == "3":
        print("Exiting...")
    else:
        print("Invalid choice")
        sys.exit(1)

if __name__ == "__main__":
    main()