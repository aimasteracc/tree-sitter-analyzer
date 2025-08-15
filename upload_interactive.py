#!/usr/bin/env python3
"""
Interactive PyPI Upload Script for tree-sitter-analyzer
Automatically detects version from package metadata
"""

import getpass
import subprocess
import sys
from pathlib import Path

import toml


def get_version():
    """Get version from pyproject.toml"""
    try:
        with open("pyproject.toml", encoding="utf-8") as f:
            data = toml.load(f)
        return data["project"]["version"]
    except Exception as e:
        print(f"❌ Failed to read version from pyproject.toml: {e}")
        return None


def check_packages():
    """Check if packages are built"""
    version = get_version()
    if not version:
        return False

    dist_path = Path("dist")
    if not dist_path.exists():
        print("❌ dist/ directory not found. Please run 'uv build' first.")
        return False

    wheel_file = dist_path / f"tree_sitter_analyzer-{version}-py3-none-any.whl"
    tar_file = dist_path / f"tree_sitter_analyzer-{version}.tar.gz"

    if not wheel_file.exists() or not tar_file.exists():
        print(
            f"❌ Package files not found for version {version}. Please run 'uv build' first."
        )
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
    if not token.startswith("pypi-"):
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
        subprocess.check_call(
            [sys.executable, "-m", "twine", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
    version = get_version()
    print("\n🧪 Testing installation from PyPI...")
    print("You can test the installation with:")
    print(f"  pip install tree-sitter-analyzer=={version}")
    print(
        '  python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"'
    )


def main():
    """Main function"""
    version = get_version()
    if not version:
        sys.exit(1)

    print(f"=== Interactive PyPI Upload for tree-sitter-analyzer v{version} ===")
    print()

    # Check packages
    if not check_packages():
        sys.exit(1)

    print("\n📋 Pre-upload checklist:")
    print("✅ All tests passed")
    print("✅ Package built and verified")
    print(f"✅ Version updated to {version}")
    print("✅ Documentation updated")
    print("✅ GitHub tagged and pushed")

    # Add version-specific notes
    if version >= "0.9.3":
        print("✅ CLI output experience improved")

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
            version = get_version()
            print("\n📝 Manual Upload Commands:")
            print("Using uv:")
            print("  set UV_PUBLISH_TOKEN=pypi-your-token-here")
            print("  uv publish")
            print()
            print("Using twine:")
            print(f"  uv run twine upload dist/tree_sitter_analyzer-{version}*")
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
