"""
Java import resolution for cross-file call analysis.

This module provides utilities to parse Java import statements and resolve
them to file paths within a project. Supports:
- Single class imports: import com.example.User;
- Wildcard imports: import com.example.*;
- Static imports: import static com.example.Utils.helper;
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JavaImport:
    """
    Represents a Java import statement.

    Examples:
        >>> # Regular import
        >>> JavaImport(package="com.example", class_name="User", is_static=False, is_wildcard=False)

        >>> # Wildcard import
        >>> JavaImport(package="java.util", class_name=None, is_static=False, is_wildcard=True)

        >>> # Static import
        >>> JavaImport(package="com.example.Utils", class_name="helper", is_static=True, is_wildcard=False)
    """

    package: str
    """Package path, e.g., 'com.example' or 'java.util'."""

    class_name: str | None
    """Class name or None for wildcard imports. For static imports, this is the method/field name."""

    is_static: bool = False
    """True if this is a static import (import static ...)."""

    is_wildcard: bool = False
    """True if this is a wildcard import (import pkg.*)."""

    def __str__(self) -> str:
        """String representation of import."""
        if self.is_wildcard:
            return f"import {'static ' if self.is_static else ''}{self.package}.*;"
        else:
            full_path = f"{self.package}.{self.class_name}" if self.class_name else self.package
            return f"import {'static ' if self.is_static else ''}{full_path};"


class JavaImportResolver:
    """
    Resolves Java imports to file paths within a project.

    The resolver builds an index of all Java files in a project by package,
    then uses this index to resolve import statements to actual file paths.

    Example:
        >>> resolver = JavaImportResolver(project_root=Path("src/main/java"))
        >>> imports = resolver.parse_imports(Path("src/main/java/com/example/App.java"))
        >>> for imp in imports:
        ...     files = resolver.resolve_import(imp, Path("com/example/App.java"))
        ...     print(f"{imp} -> {files}")
    """

    def __init__(self, project_root: Path):
        """
        Initialize Java import resolver.

        Args:
            project_root: Root directory of Java project (typically src/main/java)
        """
        self.project_root = Path(project_root)
        self._package_to_files: dict[str, list[Path]] = {}
        self._file_to_package: dict[Path, str] = {}

    def parse_imports(self, java_file: Path) -> list[JavaImport]:
        """
        Parse all import statements from a Java file.

        Args:
            java_file: Path to Java file

        Returns:
            List of JavaImport objects

        Example:
            >>> imports = resolver.parse_imports(Path("App.java"))
            >>> imports[0]
            JavaImport(package='java.util', class_name='List', is_static=False, is_wildcard=False)
        """
        imports: list[JavaImport] = []

        try:
            content = java_file.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            return imports

        # Pattern to match Java import statements:
        # import [static] package.path[.Class][.*];
        # Capture groups:
        # 1. 'static ' or None
        # 2. Full import path (package[.Class])
        # 3. '.*' or None (for wildcard)
        import_pattern = r"import\s+(static\s+)?([\w.]+)(\.\*)?;"

        for match in re.finditer(import_pattern, content):
            is_static = match.group(1) is not None
            full_path = match.group(2)
            is_wildcard = match.group(3) is not None

            if is_wildcard:
                # import package.*;
                imports.append(
                    JavaImport(
                        package=full_path, class_name=None, is_static=is_static, is_wildcard=True
                    )
                )
            else:
                # import package.Class; or import static package.Class.method;
                # Split into package and class/method name
                parts = full_path.rsplit(".", 1)
                if len(parts) == 2:
                    package, class_name = parts
                    imports.append(
                        JavaImport(
                            package=package,
                            class_name=class_name,
                            is_static=is_static,
                            is_wildcard=False,
                        )
                    )
                else:
                    # Single-level import (rare, but handle it)
                    imports.append(
                        JavaImport(
                            package=full_path,
                            class_name=None,
                            is_static=is_static,
                            is_wildcard=False,
                        )
                    )

        return imports

    def build_package_index(self) -> None:
        """
        Build index of package → file mappings for all Java files in project.

        Scans all .java files recursively and extracts their package declarations,
        building a mapping from package names to file paths.

        Example:
            >>> resolver.build_package_index()
            >>> resolver._package_to_files['com.example']
            [Path('src/main/java/com/example/App.java'), Path('src/main/java/com/example/User.java')]
        """
        # Clear existing index
        self._package_to_files.clear()
        self._file_to_package.clear()

        # Find all .java files recursively
        java_files = list(self.project_root.rglob("*.java"))

        # Extract package from each file and build index
        for java_file in java_files:
            package = self._extract_package_from_file(java_file)

            if package:
                # Add to package → files mapping
                if package not in self._package_to_files:
                    self._package_to_files[package] = []
                self._package_to_files[package].append(java_file)

                # Add to file → package mapping
                self._file_to_package[java_file] = package

    def resolve_import(self, java_import: JavaImport, source_file: Path) -> list[Path]:
        """
        Resolve import to file path(s).

        Args:
            java_import: Import to resolve
            source_file: File containing this import (for relative resolution)

        Returns:
            List of matching file paths (multiple for wildcard imports)

        Example:
            >>> imp = JavaImport(package="com.example", class_name="User", is_static=False, is_wildcard=False)
            >>> resolver.resolve_import(imp, Path("com/example/App.java"))
            [Path('src/main/java/com/example/User.java')]
        """
        # Handle static imports: import static com.example.Utils.helper
        # In this case, package is "com.example.Utils" and class_name is "helper"
        # We need to find Utils.java in package "com.example"
        if java_import.is_static and not java_import.is_wildcard and java_import.class_name:
            # Split package to extract class name
            # "com.example.Utils" -> package="com.example", class="Utils"
            package_parts = java_import.package.rsplit(".", 1)
            if len(package_parts) == 2:
                actual_package, class_name = package_parts
                return self._find_class_in_package(actual_package, class_name)
            else:
                # Single-level package (rare)
                return []

        # Handle wildcard imports: import com.example.*
        if java_import.is_wildcard:
            # Return all files in the package
            return self._package_to_files.get(java_import.package, [])

        # Handle regular imports: import com.example.User
        if java_import.class_name:
            return self._find_class_in_package(java_import.package, java_import.class_name)

        return []

    def _find_class_in_package(self, package: str, class_name: str) -> list[Path]:
        """
        Find a specific class file in a package.

        Args:
            package: Package name (e.g., "com.example")
            class_name: Class name (e.g., "User")

        Returns:
            List containing the file path if found, empty list otherwise
        """
        files = self._package_to_files.get(package, [])

        # Filter for the specific class
        for file_path in files:
            if file_path.stem == class_name:  # stem is filename without extension
                return [file_path]

        return []

    def _extract_package_from_file(self, file_path: Path) -> str | None:
        """
        Extract package declaration from Java file.

        Args:
            file_path: Path to Java file

        Returns:
            Package name or None if not found

        Example:
            >>> resolver._extract_package_from_file(Path("User.java"))
            'com.example'
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            return None

        # Pattern to match package declaration: package com.example.package;
        # Capture group: package name
        package_pattern = r"package\s+([\w.]+)\s*;"

        match = re.search(package_pattern, content)
        if match:
            return match.group(1)

        return None
