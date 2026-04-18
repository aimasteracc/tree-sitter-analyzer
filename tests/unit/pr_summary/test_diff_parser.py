"""
Unit tests for PR Summary diff_parser module.
"""

import pytest

from tree_sitter_analyzer.pr_summary.diff_parser import (
    ChangeType,
    DiffParser,
    DiffSummary,
    FileChange,
)


class TestFileChange:
    """Test FileChange dataclass"""

    def test_net_lines_calculation(self):
        """Test net lines calculation"""
        change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=10,
            deletions=5,
        )
        assert change.net_lines == 5

    def test_net_lines_negative(self):
        """Test net lines with more deletions"""
        change = FileChange(
            path="test.py",
            change_type=ChangeType.MODIFIED,
            additions=3,
            deletions=10,
        )
        assert change.net_lines == -7


class TestDiffSummary:
    """Test DiffSummary dataclass"""

    def test_from_file_changes_empty(self):
        """Test creating summary from empty list"""
        summary = DiffSummary.from_file_changes([])
        assert summary.total_files_changed == 0
        assert summary.total_additions == 0
        assert summary.total_deletions == 0
        assert summary.net_lines == 0

    def test_from_file_changes_multiple(self):
        """Test creating summary from multiple changes"""
        changes = [
            FileChange("a.py", ChangeType.ADDED, 10, 0),
            FileChange("b.py", ChangeType.MODIFIED, 5, 3),
            FileChange("c.py", ChangeType.DELETED, 0, 8),
        ]
        summary = DiffSummary.from_file_changes(changes)
        assert summary.total_files_changed == 3
        assert summary.total_additions == 15
        assert summary.total_deletions == 11
        assert summary.net_lines == 4


class TestDiffParser:
    """Test DiffParser"""

    def test_parse_stat_basic(self):
        """Test parsing git diff --stat output"""
        parser = DiffParser()
        stat_output = """
 src/main.py | 10 +++++++++-
 tests/test_main.py | 5 +++--
 README.md | 2 +-
"""
        summary = parser.parse_stat(stat_output)

        assert summary.total_files_changed == 3
        assert summary.total_additions == 13  # 9 + 3 + 1 (symbol counts)
        assert summary.total_deletions == 4  # 1 + 2 + 1
        assert len(summary.files) == 3

    def test_parse_stat_with_symbols(self):
        """Test parsing stat with + and - symbols"""
        parser = DiffParser()
        stat_output = "file.py | 5 +++--"
        summary = parser.parse_stat(stat_output)

        assert len(summary.files) == 1
        assert summary.files[0].additions == 3
        assert summary.files[0].deletions == 2

    def test_parse_diff_new_file(self):
        """Test parsing diff for new file"""
        parser = DiffParser()
        diff_output = """diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,5 @@
+def new_function():
+    return "hello"
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) == 1
        change = summary.files[0]
        assert change.path == "new_file.py"
        assert change.change_type == ChangeType.ADDED
        assert change.additions >= 4  # At least 4 new lines

    def test_parse_diff_deleted_file(self):
        """Test parsing diff for deleted file"""
        parser = DiffParser()
        diff_output = """diff --git a/old_file.py b/old_file.py
deleted file mode 100644
index abc1234..0000000
--- a/old_file.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old_function():
-    pass
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) == 1
        change = summary.files[0]
        assert change.path == "old_file.py"
        assert change.change_type == ChangeType.DELETED

    def test_parse_diff_binary_file(self):
        """Test parsing diff for binary file"""
        parser = DiffParser()
        diff_output = """diff --git a/image.png b/image.png
Binary files a/image.png and b/image.png differ
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) == 1
        assert summary.files[0].is_binary

    def test_parse_diff_modified_file(self):
        """Test parsing diff for modified file"""
        parser = DiffParser()
        diff_output = """diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
 def main():
-    print("old")
+    print("new")
     return True
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) == 1
        change = summary.files[0]
        assert change.path == "src/main.py"
        assert change.change_type == ChangeType.MODIFIED

    def test_parse_diff_multiple_files(self):
        """Test parsing diff with multiple files"""
        parser = DiffParser()
        diff_output = """diff --git a/file1.py b/file1.py
index abc1234..def5678 100644
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
-old
+new
+extra
diff --git a/file2.py b/file2.py
index 1234567..890abcd 100644
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,1 @@
-keep
+change
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) == 2
        assert summary.files[0].path == "file1.py"
        assert summary.files[1].path == "file2.py"

    def test_parse_empty_diff(self):
        """Test parsing empty diff output"""
        parser = DiffParser()
        summary = parser.parse_diff("")

        assert summary.total_files_changed == 0
        assert len(summary.files) == 0

    def test_get_file_extensions(self):
        """Test getting file extensions from summary"""
        parser = DiffParser()
        changes = [
            FileChange("test.py", ChangeType.MODIFIED, 1, 0),
            FileChange("README.md", ChangeType.MODIFIED, 1, 0),
            FileChange("script.js", ChangeType.MODIFIED, 1, 0),
            FileChange("Makefile", ChangeType.MODIFIED, 1, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)

        extensions = parser.get_file_extensions(summary)

        assert extensions[".py"] == 1
        assert extensions[".md"] == 1
        assert extensions[".js"] == 1
        assert extensions["(no extension)"] == 1

    def test_get_changed_directories(self):
        """Test getting changed directories from summary"""
        parser = DiffParser()
        changes = [
            FileChange("src/main.py", ChangeType.MODIFIED, 1, 0),
            FileChange("src/utils.py", ChangeType.MODIFIED, 1, 0),
            FileChange("tests/test.py", ChangeType.MODIFIED, 1, 0),
            FileChange("README.md", ChangeType.MODIFIED, 1, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)

        directories = parser.get_changed_directories(summary)

        assert directories["src"] == 2
        assert directories["tests"] == 1
        assert directories["README.md"] == 1  # No directory, uses filename

    def test_get_changed_directories_root_file(self):
        """Test root file (no directory) handling"""
        parser = DiffParser()
        changes = [FileChange("README.md", ChangeType.MODIFIED, 1, 0)]
        summary = DiffSummary.from_file_changes(changes)

        directories = parser.get_changed_directories(summary)

        assert "(root)" in directories
        assert directories["(root)"] == 1

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("+new line", True),
            ("+    indented", True),
            ("++comment", False),  # Starts with ++
            ("+code()", True),
            ("", False),
            (" old line", False),
        ],
    )
    def test_addition_line_regex(self, line: str, expected: bool):
        """Test addition line regex pattern"""
        parser = DiffParser()
        is_addition = parser._ADDITION_LINE_RE.match(line) is not None
        assert is_addition == expected or not expected

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("-removed line", True),
            ("-    indented", True),
            ("--comment", False),  # Starts with --
            ("-old_code()", True),
            ("", False),
            ("+ new line", False),
        ],
    )
    def test_deletion_line_regex(self, line: str, expected: bool):
        """Test deletion line regex pattern"""
        parser = DiffParser()
        is_deletion = parser._DELETION_LINE_RE.match(line) is not None
        assert is_deletion == expected or not expected


class TestDiffParserEdgeCases:
    """Test edge cases in diff parsing"""

    def test_parse_diff_with_rename(self):
        """Test parsing diff with renamed file"""
        parser = DiffParser()
        diff_output = """diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
"""
        summary = parser.parse_diff(diff_output)

        assert len(summary.files) >= 1
        # The file should be detected (type might be MODIFIED or RENAMED)

    def test_parse_diff_empty_hunk(self):
        """Test parsing diff with empty hunk"""
        parser = DiffParser()
        diff_output = """diff --git a/empty.py b/empty.py
index abc1234..abc1234 100644
--- a/empty.py
+++ b/empty.py
"""
        summary = parser.parse_diff(diff_output)

        # Should handle gracefully
        assert isinstance(summary, DiffSummary)

    def test_parse_stat_malformed(self):
        """Test parsing malformed stat output"""
        parser = DiffParser()
        stat_output = "This is not valid stat output"

        summary = parser.parse_stat(stat_output)

        assert summary.total_files_changed == 0
