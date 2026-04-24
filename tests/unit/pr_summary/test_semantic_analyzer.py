"""
Unit tests for PR Summary Semantic Analyzer
"""


from tree_sitter_analyzer.pr_summary.diff_parser import ChangeType, FileChange
from tree_sitter_analyzer.pr_summary.semantic_analyzer import (
    SemanticAnalysisResult,
    SemanticAnalyzer,
    SemanticChangeType,
)


class TestSemanticAnalyzer:
    """Test semantic analyzer functionality"""

    def test_initialization(self) -> None:
        """Test analyzer can be initialized"""
        analyzer = SemanticAnalyzer()
        assert analyzer is not None

    def test_analyze_python_imports(self) -> None:
        """Test Python import extraction"""
        analyzer = SemanticAnalyzer()

        content = """
import os
import sys
from typing import List, Dict
from collections import defaultdict

def my_function():
    pass
"""

        imports = analyzer._extract_imports(content, "python")
        assert "os" in imports
        assert "sys" in imports
        assert "typing" in imports
        assert "collections" in imports

    def test_analyze_python_import_changes(self) -> None:
        """Test detecting import additions"""
        analyzer = SemanticAnalyzer()

        old_content = """
import os

def foo():
    pass
"""

        new_content = """
import os
import sys

def foo():
    pass
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=2,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        assert len(result.new_imports) == 1
        assert "sys" in result.new_imports
        assert not result.has_breaking_changes

    def test_analyze_python_import_removals(self) -> None:
        """Test detecting import removals"""
        analyzer = SemanticAnalyzer()

        old_content = """
import os
import sys

def foo():
    pass
"""

        new_content = """
import os

def foo():
    pass
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=0,
            deletions=2,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        assert len(result.removed_imports) == 1
        assert "sys" in result.removed_imports

    def test_analyze_javascript_imports(self) -> None:
        """Test JavaScript import extraction"""
        analyzer = SemanticAnalyzer()

        content = """
import React from 'react';
import { useState, useEffect } from 'react';
import axios from 'axios';

export function myComponent() {
    return null;
}
"""

        imports = analyzer._extract_imports(content, "javascript")
        assert "react" in imports
        assert "axios" in imports

    def test_analyze_java_imports(self) -> None:
        """Test Java import extraction"""
        analyzer = SemanticAnalyzer()

        content = """
package com.example;

import java.util.List;
import java.util.ArrayList;

public class MyClass {
    public void myMethod() {
    }
}
"""

        imports = analyzer._extract_imports(content, "java")
        # Java imports include the full package path
        assert "java" in imports or "java.util.List" in imports or "java.util.ArrayList" in imports

    def test_analyze_go_imports(self) -> None:
        """Test Go import extraction"""
        analyzer = SemanticAnalyzer()

        content = """
package main

import (
    "fmt"
    "os"
)

func main() {
    fmt.Println("Hello")
}
"""

        imports = analyzer._extract_imports(content, "go")
        assert "fmt" in imports
        assert "os" in imports

    def test_detect_removed_function(self) -> None:
        """Test detecting removed functions as breaking changes"""
        analyzer = SemanticAnalyzer()

        old_content = """
def old_function():
    pass

def new_function():
    pass
"""

        new_content = """
def new_function():
    pass
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=0,
            deletions=5,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        assert result.has_breaking_changes
        breaking_names = [c.name for c in result.breaking_changes]
        assert "old_function" in breaking_names

    def test_detect_removed_class(self) -> None:
        """Test detecting removed classes as breaking changes"""
        analyzer = SemanticAnalyzer()

        old_content = """
class OldClass:
    pass

class NewClass:
    pass
"""

        new_content = """
class NewClass:
    pass
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=0,
            deletions=5,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        assert result.has_breaking_changes
        breaking_types = [c.change_type for c in result.breaking_changes]
        assert SemanticChangeType.CLASS_SIGNATURE in breaking_types

    def test_unsupported_language(self) -> None:
        """Test handling of unsupported languages"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="test.unknown",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, "old", "new")

        assert len(result.changes) == 0
        assert len(result.languages_used) == 0

    def test_extract_python_functions(self) -> None:
        """Test extracting Python function names"""
        analyzer = SemanticAnalyzer()

        content = """
def function_one():
    pass

def function_two():
    pass

class MyClass:
    def method_one(self):
        pass
"""

        parser = analyzer._loader.create_parser_safely("python")
        if parser:
            tree = parser.parse(bytes(content, "utf-8"))
            functions = analyzer._extract_functions(tree.root_node, "python")
            assert "function_one" in functions
            assert "function_two" in functions

    def test_extract_python_classes(self) -> None:
        """Test extracting Python class names"""
        analyzer = SemanticAnalyzer()

        content = """
class MyClass:
    pass

class AnotherClass:
    pass
"""

        parser = analyzer._loader.create_parser_safely("python")
        if parser:
            tree = parser.parse(bytes(content, "utf-8"))
            classes = analyzer._extract_classes(tree.root_node, "python")
            assert "MyClass" in classes
            assert "AnotherClass" in classes

    def test_analyze_batch(self) -> None:
        """Test batch analysis of multiple files"""
        analyzer = SemanticAnalyzer()

        file_changes = [
            FileChange(
                path="file1.py",
                change_type=ChangeType.MODIFIED,
                additions=2,
                deletions=0,
            ),
            FileChange(
                path="file2.py",
                change_type=ChangeType.MODIFIED,
                additions=0,
                deletions=1,
            ),
        ]

        contents_map = {
            "file1.py": ("import os\n", "import os\nimport sys\n"),
            "file2.py": ("import json\n", "\n"),
        }

        result = analyzer.analyze_batch(file_changes, contents_map)

        assert len(result.new_imports) > 0
        assert len(result.removed_imports) > 0
        assert "python" in result.languages_used

    def test_modified_function_detection(self) -> None:
        """Test detecting modified functions"""
        analyzer = SemanticAnalyzer()

        old_content = """
def my_function():
    return 1
"""

        new_content = """
def my_function():
    return 2
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=1,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        # Should detect modification
        func_changes = [
            c for c in result.changes
            if c.change_type == SemanticChangeType.FUNCTION_SIGNATURE
        ]
        assert len(func_changes) > 0

    def test_api_changes_property(self) -> None:
        """Test api_changes property filters correctly"""
        analyzer = SemanticAnalyzer()

        old_content = """
def api_function():
    pass

def internal_function():
    pass
"""

        new_content = """
def internal_function():
    pass
"""

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=0,
            deletions=5,
        )

        result = analyzer.analyze_diff(file_change, old_content, new_content)

        # API changes should include function_signature changes
        api_changes = result.api_changes
        assert len(api_changes) > 0

    def test_empty_content_handling(self) -> None:
        """Test handling of empty content"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.ADDED,
            additions=10,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, "", "def foo(): pass")

        # Should handle gracefully
        assert result is not None

    def test_syntax_error_handling(self) -> None:
        """Test handling of syntax errors"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        # Invalid Python syntax
        result = analyzer.analyze_diff(file_change, "def foo(", "def bar(")

        # Should handle gracefully without crashing
        assert result is not None


class TestSemanticAnalysisResult:
    """Test SemanticAnalysisResult dataclass"""

    def test_has_breaking_changes_property(self) -> None:
        """Test has_breaking_changes property"""
        from tree_sitter_analyzer.pr_summary.semantic_analyzer import SemanticChange

        result_with_breaking = SemanticAnalysisResult(
            changes=[],
            breaking_changes=[
                SemanticChange(
                    change_type=SemanticChangeType.FUNCTION_SIGNATURE,
                    language="python",
                    name="removed_func",
                    file_path="test.py",
                    is_breaking=True,
                    description="Removed function",
                )
            ],
            new_imports=[],
            removed_imports=[],
            languages_used={"python"},
        )

        assert result_with_breaking.has_breaking_changes is True

    def test_api_changes_filters(self) -> None:
        """Test api_changes filters correctly"""
        from tree_sitter_analyzer.pr_summary.semantic_analyzer import SemanticChange

        result = SemanticAnalysisResult(
            changes=[
                SemanticChange(
                    change_type=SemanticChangeType.IMPORT_ADDED,
                    language="python",
                    name="os",
                    file_path="test.py",
                    is_breaking=False,
                    description="Added import",
                ),
                SemanticChange(
                    change_type=SemanticChangeType.CLASS_SIGNATURE,
                    language="python",
                    name="MyClass",
                    file_path="test.py",
                    is_breaking=True,
                    description="Removed class",
                ),
            ],
            breaking_changes=[],
            new_imports=[],
            removed_imports=[],
            languages_used={"python"},
        )

        api_changes = result.api_changes
        assert len(api_changes) == 1
        assert api_changes[0].name == "MyClass"


class TestLanguageSupport:
    """Test multi-language support"""

    def test_python_language_detection(self) -> None:
        """Test Python file is detected correctly"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="module.py",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, "pass", "pass")
        assert "python" in result.languages_used

    def test_javascript_language_detection(self) -> None:
        """Test JavaScript file is detected correctly"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="script.js",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, "const x = 1;", "const x = 1;")
        assert "javascript" in result.languages_used

    def test_typescript_language_detection(self) -> None:
        """Test TypeScript file is detected correctly"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="module.ts",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        result = analyzer.analyze_diff(file_change, "let x: number = 1;", "let x: number = 1;")
        assert "typescript" in result.languages_used

    def test_java_language_detection(self) -> None:
        """Test Java file is detected correctly"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="MyClass.java",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        content = "public class MyClass {}"
        result = analyzer.analyze_diff(file_change, content, content)
        assert "java" in result.languages_used

    def test_go_language_detection(self) -> None:
        """Test Go file is detected correctly"""
        analyzer = SemanticAnalyzer()

        file_change = FileChange(
            path="main.go",
            change_type=ChangeType.MODIFIED,
            additions=1,
            deletions=0,
        )

        content = "package main"
        result = analyzer.analyze_diff(file_change, content, content)
        assert "go" in result.languages_used
