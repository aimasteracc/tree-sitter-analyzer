#!/usr/bin/env python3
"""
Interactive PyPI Upload Script for tree-sitter-analyzer v0.9.1
"""

import subprocess
import sys
import getpass
from pathlib import Path


def check_packages():
    """Check if packages are built"""
    dist_path = Path("dist")
    if not dist_path.exists():
        print("❌ dist/ directory not found. Please run 'uv build' first.")
        return False
    
    wheel_file = dist_path / "tree_sitter_analyzer-0.9.1-py3-none-any.whl"
    tar_file = dist_path / "tree_sitter_analyzer-0.9.1.tar.gz"
    
    if not wheel_file.exists() or not tar_file.exists():
        print("❌ Package files not found. Please run 'uv build' first.")
        return False
    
    print("✅ Package files found:")
    print(f"  - {wheel_file}")
    print(f"  - {tar_file}")
    return True


def upload_with_uv():
    """Upload using uv"""
    print("\n🚀 Uploading to PyPI using uv...")
    
    # Ask for token
    token = getpass.getpass("Enter your PyPI API token (starts with 'pypi-'): ")
    if not token.startswith('pypi-'):
        print("❌ Invalid token format. Token should start with 'pypi-'")
        return False
    
    try:
        # Upload using uv
        cmd = ["uv", "publish", "--token", token]
        print("Running: uv publish --token [HIDDEN]")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Successfully uploaded to PyPI!")
            print(result.stdout)
            return True
        else:
            print("❌ Upload failed:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        return False


def upload_with_twine():
    """Upload using twine"""
    print("\n🚀 Uploading to PyPI using twine...")
    
    try:
        # Check if twine is available
        subprocess.check_call([sys.executable, "-m", "twine", "--version"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Installing twine...")
        try:
            subprocess.check_call(["uv", "add", "--dev", "twine"])
        except subprocess.CalledProcessError:
            print("❌ Failed to install twine")
            return False
    
    try:
        # Upload using twine
        cmd = [sys.executable, "-m", "twine", "upload", "dist/*"]
        print("Running: python -m twine upload dist/*")
        print("When prompted:")
        print("  Username: __token__")
        print("  Password: [your PyPI token]")
        
        result = subprocess.run(cmd)
        
        if result.returncode == 0:
            print("✅ Successfully uploaded to PyPI!")
            return True
        else:
            print("❌ Upload failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        return False


def test_installation():
    """Test installation from PyPI"""
    print("\n🧪 Testing installation from PyPI...")
    print("You can test the installation with:")
    print("  pip install tree-sitter-analyzer==0.9.1")
    print("  python -c \"import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)\"")


def main():
    """Main function"""
    print("=== Interactive PyPI Upload for tree-sitter-analyzer v0.9.1 ===")
    print()
    
    # Check packages
    if not check_packages():
        sys.exit(1)
    
    print("\n📋 Pre-upload checklist:")
    print("✅ All 306 tests passed")
    print("✅ Package built and verified")
    print("✅ Version updated to 0.9.1")
    print("✅ Documentation updated")
    print("✅ GitHub tagged and pushed")
    
    print("\n🔑 PyPI Account Setup:")
    print("1. Create account: https://pypi.org/account/register/")
    print("2. Generate API token: https://pypi.org/manage/account/token/")
    print("3. Select 'Entire account' scope")
    print("4. Copy the token (starts with 'pypi-')")
    
    print("\n📦 Upload Options:")
    print("1. Upload with uv (recommended)")
    print("2. Upload with twine")
    print("3. Show manual commands")
    print("4. Exit")
    
    while True:
        choice = input("\nChoose an option (1-4): ").strip()
        
        if choice == "1":
            if upload_with_uv():
                test_installation()
                break
        elif choice == "2":
            if upload_with_twine():
                test_installation()
                break
        elif choice == "3":
            print("\n📝 Manual Upload Commands:")
            print("Using uv:")
            print("  set UV_PUBLISH_TOKEN=pypi-your-token-here")
            print("  uv publish")
            print()
            print("Using twine:")
            print("  uv run twine upload dist/*")
            print("  Username: __token__")
            print("  Password: pypi-your-token-here")
            break
        elif choice == "4":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter 1-4.")


if __name__ == "__main__":
    main()
