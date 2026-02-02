"""
Unit tests for JavaImportResolver.

Tests the parsing and resolution of Java import statements.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.graph.java_imports import JavaImport, JavaImportResolver


@pytest.fixture
def temp_java_file(tmp_path):
    """Create a temporary Java file for testing."""

    def _create_file(content: str, filename: str = "Test.java") -> Path:
        file_path = tmp_path / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path

    return _create_file


@pytest.fixture
def resolver(tmp_path):
    """Create JavaImportResolver with temp directory."""
    return JavaImportResolver(project_root=tmp_path)


# T3.2: Parse Java Imports


def test_parse_single_class_import(temp_java_file, resolver):
    """Test parsing single class import: import com.example.User;"""
    code = """
package com.example;

import java.util.List;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 1
    assert imports[0].package == "java.util"
    assert imports[0].class_name == "List"
    assert imports[0].is_static is False
    assert imports[0].is_wildcard is False


def test_parse_wildcard_import(temp_java_file, resolver):
    """Test parsing wildcard import: import java.util.*;"""
    code = """
package com.example;

import java.util.*;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 1
    assert imports[0].package == "java.util"
    assert imports[0].class_name is None
    assert imports[0].is_static is False
    assert imports[0].is_wildcard is True


def test_parse_static_import(temp_java_file, resolver):
    """Test parsing static import: import static com.example.Utils.helper;"""
    code = """
package com.example;

import static com.example.Utils.helper;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 1
    assert imports[0].package == "com.example.Utils"
    assert imports[0].class_name == "helper"
    assert imports[0].is_static is True
    assert imports[0].is_wildcard is False


def test_parse_static_wildcard_import(temp_java_file, resolver):
    """Test parsing static wildcard import: import static com.example.Utils.*;"""
    code = """
package com.example;

import static com.example.Utils.*;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 1
    assert imports[0].package == "com.example.Utils"
    assert imports[0].class_name is None
    assert imports[0].is_static is True
    assert imports[0].is_wildcard is True


def test_parse_multiple_imports(temp_java_file, resolver):
    """Test parsing multiple import statements."""
    code = """
package com.example;

import java.util.List;
import java.util.ArrayList;
import java.io.*;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 3

    # First import
    assert imports[0].package == "java.util"
    assert imports[0].class_name == "List"

    # Second import
    assert imports[1].package == "java.util"
    assert imports[1].class_name == "ArrayList"

    # Third import (wildcard)
    assert imports[2].package == "java.io"
    assert imports[2].is_wildcard is True


def test_parse_no_imports(temp_java_file, resolver):
    """Test parsing Java file with no imports."""
    code = """
package com.example;

class Test {
}
"""
    java_file = temp_java_file(code)
    imports = resolver.parse_imports(java_file)

    assert len(imports) == 0


# T3.3: Build Package Index


def test_extract_package_from_file(temp_java_file, resolver):
    """Test extracting package declaration from Java file."""
    code = """
package com.example.service;

import java.util.List;

class UserService {
}
"""
    java_file = temp_java_file(code)
    package = resolver._extract_package_from_file(java_file)

    assert package == "com.example.service"


def test_extract_package_no_package(temp_java_file, resolver):
    """Test extracting package when file has no package declaration (default package)."""
    code = """
import java.util.List;

class Test {
}
"""
    java_file = temp_java_file(code)
    package = resolver._extract_package_from_file(java_file)

    assert package is None


def test_build_package_index_single_package(tmp_path, resolver):
    """Test building package index with files in single package."""
    # Create directory structure: com/example/
    package_dir = tmp_path / "com" / "example"
    package_dir.mkdir(parents=True)

    # Create Java files
    (package_dir / "User.java").write_text(
        """
package com.example;

class User {
}
""",
        encoding="utf-8",
    )

    (package_dir / "Service.java").write_text(
        """
package com.example;

class Service {
}
""",
        encoding="utf-8",
    )

    resolver.build_package_index()

    # Verify index
    assert "com.example" in resolver._package_to_files
    files = resolver._package_to_files["com.example"]
    assert len(files) == 2
    file_names = [f.name for f in files]
    assert "User.java" in file_names
    assert "Service.java" in file_names


def test_build_package_index_multiple_packages(tmp_path, resolver):
    """Test building package index with files in multiple packages."""
    # Create directory structure
    pkg1_dir = tmp_path / "com" / "example"
    pkg1_dir.mkdir(parents=True)

    pkg2_dir = tmp_path / "com" / "example" / "service"
    pkg2_dir.mkdir(parents=True)

    # Create Java files in different packages
    (pkg1_dir / "App.java").write_text(
        """
package com.example;

class App {
}
""",
        encoding="utf-8",
    )

    (pkg2_dir / "UserService.java").write_text(
        """
package com.example.service;

class UserService {
}
""",
        encoding="utf-8",
    )

    resolver.build_package_index()

    # Verify index has both packages
    assert "com.example" in resolver._package_to_files
    assert "com.example.service" in resolver._package_to_files

    assert len(resolver._package_to_files["com.example"]) == 1
    assert len(resolver._package_to_files["com.example.service"]) == 1


# T3.4: Resolve Imports to Files


def test_resolve_single_class_import(tmp_path, resolver):
    """Test resolving single class import to file path."""
    # Create directory structure
    pkg_dir = tmp_path / "com" / "example"
    pkg_dir.mkdir(parents=True)

    # Create target Java file
    user_file = pkg_dir / "User.java"
    user_file.write_text(
        """
package com.example;

class User {
}
""",
        encoding="utf-8",
    )

    # Build index
    resolver.build_package_index()

    # Create import
    java_import = JavaImport(
        package="com.example", class_name="User", is_static=False, is_wildcard=False
    )

    # Resolve import
    source_file = tmp_path / "App.java"
    resolved = resolver.resolve_import(java_import, source_file)

    assert len(resolved) == 1
    assert resolved[0].name == "User.java"


def test_resolve_wildcard_import(tmp_path, resolver):
    """Test resolving wildcard import returns all files in package."""
    # Create directory structure
    pkg_dir = tmp_path / "com" / "example"
    pkg_dir.mkdir(parents=True)

    # Create multiple Java files
    (pkg_dir / "User.java").write_text("package com.example;\nclass User {}", encoding="utf-8")
    (pkg_dir / "Service.java").write_text(
        "package com.example;\nclass Service {}", encoding="utf-8"
    )
    (pkg_dir / "Helper.java").write_text("package com.example;\nclass Helper {}", encoding="utf-8")

    # Build index
    resolver.build_package_index()

    # Create wildcard import
    java_import = JavaImport(
        package="com.example", class_name=None, is_static=False, is_wildcard=True
    )

    # Resolve import
    source_file = tmp_path / "App.java"
    resolved = resolver.resolve_import(java_import, source_file)

    assert len(resolved) == 3
    file_names = {f.name for f in resolved}
    assert file_names == {"User.java", "Service.java", "Helper.java"}


def test_resolve_import_not_found(tmp_path, resolver):
    """Test resolving import when class doesn't exist returns empty list."""
    # Create directory structure
    pkg_dir = tmp_path / "com" / "example"
    pkg_dir.mkdir(parents=True)

    (pkg_dir / "User.java").write_text("package com.example;\nclass User {}", encoding="utf-8")

    # Build index
    resolver.build_package_index()

    # Create import for non-existent class
    java_import = JavaImport(
        package="com.example", class_name="NonExistent", is_static=False, is_wildcard=False
    )

    # Resolve import
    source_file = tmp_path / "App.java"
    resolved = resolver.resolve_import(java_import, source_file)

    assert len(resolved) == 0


def test_resolve_static_import(tmp_path, resolver):
    """Test resolving static import (import static com.example.Utils.helper)."""
    # Create directory structure
    pkg_dir = tmp_path / "com" / "example"
    pkg_dir.mkdir(parents=True)

    # Create Utils.java with static method
    utils_file = pkg_dir / "Utils.java"
    utils_file.write_text(
        """
package com.example;

class Utils {
    static void helper() {}
}
""",
        encoding="utf-8",
    )

    # Build index
    resolver.build_package_index()

    # Create static import
    java_import = JavaImport(
        package="com.example.Utils", class_name="helper", is_static=True, is_wildcard=False
    )

    # Resolve import (should find Utils.java by package name)
    source_file = tmp_path / "App.java"
    resolved = resolver.resolve_import(java_import, source_file)

    assert len(resolved) == 1
    assert resolved[0].name == "Utils.java"


def test_resolve_import_package_not_found(tmp_path, resolver):
    """Test resolving import when package doesn't exist returns empty list."""
    # Build empty index
    resolver.build_package_index()

    # Create import for non-existent package
    java_import = JavaImport(
        package="com.nonexistent", class_name="User", is_static=False, is_wildcard=False
    )

    # Resolve import
    source_file = tmp_path / "App.java"
    resolved = resolver.resolve_import(java_import, source_file)

    assert len(resolved) == 0
