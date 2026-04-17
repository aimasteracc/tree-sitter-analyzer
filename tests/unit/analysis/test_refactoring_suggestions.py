"""
Unit tests for refactoring_suggestions module.
"""


from tree_sitter_analyzer.analysis.refactoring_suggestions import (
    CodeDiff,
    RefactoringAdvisor,
    RefactoringReport,
    RefactoringSuggestion,
    RefactoringType,
    SeverityLevel,
)


class TestRefactoringSuggestion:
    """Tests for RefactoringSuggestion dataclass."""

    def test_create_suggestion(self) -> None:
        """Test creating a basic refactoring suggestion."""
        suggestion = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Method is too long",
            severity=SeverityLevel.MEDIUM,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
        )

        assert suggestion.type == RefactoringType.EXTRACT_METHOD
        assert suggestion.title == "Extract Method"
        assert suggestion.severity == SeverityLevel.MEDIUM
        assert suggestion.file_path == "test.py"
        assert suggestion.line_start == 10
        assert suggestion.line_end == 50
        assert suggestion.code_diff is None
        assert suggestion.estimated_effort == "moderate"

    def test_suggestion_with_code_diff(self) -> None:
        """Test creating a suggestion with code diff."""
        diff = CodeDiff(
            before="def long(): ...",
            after="def short(): ...",
            language="python",
            line_start=10,
            line_end=50,
        )

        suggestion = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Method is too long",
            severity=SeverityLevel.HIGH,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
            code_diff=diff,
        )

        assert suggestion.code_diff is not None
        assert suggestion.code_diff.before == "def long(): ..."
        assert suggestion.code_diff.after == "def short(): ..."
        assert suggestion.code_diff.language == "python"

    def test_suggestion_to_dict(self) -> None:
        """Test converting suggestion to dictionary."""
        suggestion = RefactoringSuggestion(
            type=RefactoringType.GUARD_CLAUSE,
            title="Guard Clause",
            description="Reduce nesting",
            severity=SeverityLevel.MEDIUM,
            file_path="test.py",
            line_start=20,
            line_end=30,
            language="python",
        )

        result = suggestion.to_dict()

        assert result["type"] == "guard_clause"
        assert result["title"] == "Guard Clause"
        assert result["severity"] == "medium"
        assert result["file_path"] == "test.py"
        assert result["line_start"] == 20
        assert result["line_end"] == 30
        assert result["code_diff"] is None
        assert result["estimated_effort"] == "moderate"


class TestRefactoringReport:
    """Tests for RefactoringReport dataclass."""

    def test_create_empty_report(self) -> None:
        """Test creating an empty report."""
        report = RefactoringReport(file_path="test.py")

        assert report.file_path == "test.py"
        assert report.total_suggestions == 0
        assert report.critical_count == 0
        assert report.high_count == 0
        assert report.medium_count == 0
        assert report.suggestions == []

    def test_add_suggestion(self) -> None:
        """Test adding suggestions to report."""
        report = RefactoringReport(file_path="test.py")

        suggestion1 = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Too long",
            severity=SeverityLevel.HIGH,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
        )

        suggestion2 = RefactoringSuggestion(
            type=RefactoringType.GUARD_CLAUSE,
            title="Guard Clause",
            description="Deep nesting",
            severity=SeverityLevel.MEDIUM,
            file_path="test.py",
            line_start=20,
            line_end=30,
            language="python",
        )

        report.add_suggestion(suggestion1)
        report.add_suggestion(suggestion2)

        assert report.total_suggestions == 2
        assert report.high_count == 1
        assert report.medium_count == 1
        assert len(report.suggestions) == 2

    def test_severity_counts(self) -> None:
        """Test severity count tracking."""
        report = RefactoringReport(file_path="test.py")

        severities = [
            SeverityLevel.CRITICAL,
            SeverityLevel.HIGH,
            SeverityLevel.HIGH,
            SeverityLevel.MEDIUM,
            SeverityLevel.MEDIUM,
            SeverityLevel.MEDIUM,
            SeverityLevel.LOW,
        ]

        for severity in severities:
            suggestion = RefactoringSuggestion(
                type=RefactoringType.EXTRACT_METHOD,
                title="Test",
                description="Test",
                severity=severity,
                file_path="test.py",
                line_start=1,
                line_end=10,
                language="python",
            )
            report.add_suggestion(suggestion)

        assert report.total_suggestions == 7
        assert report.critical_count == 1
        assert report.high_count == 2
        assert report.medium_count == 3

    def test_report_to_dict(self) -> None:
        """Test converting report to dictionary."""
        report = RefactoringReport(file_path="test.py")

        suggestion = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Too long",
            severity=SeverityLevel.HIGH,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
        )

        report.add_suggestion(suggestion)

        result = report.to_dict()

        assert result["file_path"] == "test.py"
        assert result["total_suggestions"] == 1
        assert result["high_count"] == 1
        assert len(result["suggestions"]) == 1


class TestRefactoringAdvisor:
    """Tests for RefactoringAdvisor class."""

    def test_advisor_initialization(self) -> None:
        """Test advisor initialization with default thresholds."""
        advisor = RefactoringAdvisor()

        assert advisor._thresholds["method_length"] == 50
        assert advisor._thresholds["nesting_depth"] == 4
        assert advisor._thresholds["magic_number_min"] == 3
        assert advisor._thresholds["magic_number_max"] == 1000

    def test_suggest_fixes_empty_content(self) -> None:
        """Test analyzing empty content."""
        advisor = RefactoringAdvisor()
        report = advisor.suggest_fixes("test.py", "", "python")

        assert report.file_path == "test.py"
        assert report.total_suggestions == 0

    def test_suggest_fixes_with_smell_results(self) -> None:
        """Test generating suggestions from pre-computed smell results."""
        advisor = RefactoringAdvisor()

        smell_results = {
            "smells": [
                {
                    "type": "long_method",
                    "line": 10,
                    "length": 60,
                },
                {
                    "type": "magic_number",
                    "line": 25,
                    "value": 42,
                },
            ]
        }

        report = advisor.suggest_fixes(
            "test.py",
            "def long_method(): ...",
            "python",
            smell_results,
        )

        assert report.total_suggestions == 2
        assert report.medium_count == 1  # long_method (60 lines is MEDIUM)
        # Check that one suggestion has LOW severity
        assert any(s.severity == SeverityLevel.LOW for s in report.suggestions)

    def test_generate_extract_method_suggestion(self) -> None:
        """Test Extract Method suggestion generation."""
        advisor = RefactoringAdvisor()

        smell = {"type": "long_method", "line": 10, "length": 60}
        suggestion = advisor._generate_extract_method(
            "test.py",
            "def long_method(): ...",
            "python",
            10,
            smell,
        )

        assert suggestion.type == RefactoringType.EXTRACT_METHOD
        assert suggestion.title == "Extract Method"
        assert "60 lines" in suggestion.description
        assert suggestion.severity == SeverityLevel.MEDIUM
        assert suggestion.code_diff is not None
        assert suggestion.estimated_effort == "moderate"

    def test_generate_extract_method_high_severity(self) -> None:
        """Test Extract Method with high severity for very long methods."""
        advisor = RefactoringAdvisor()

        smell = {"type": "long_method", "line": 10, "length": 80}
        suggestion = advisor._generate_extract_method(
            "test.py",
            "def very_long_method(): ...",
            "python",
            10,
            smell,
        )

        assert suggestion.severity == SeverityLevel.HIGH
        assert suggestion.estimated_effort == "complex"

    def test_generate_guard_clause_suggestion(self) -> None:
        """Test Guard Clause suggestion generation."""
        advisor = RefactoringAdvisor()

        smell = {"type": "deep_nesting", "line": 20, "depth": 5}
        suggestion = advisor._generate_guard_clause(
            "test.py",
            "def nested(): ...",
            "python",
            20,
            smell,
        )

        assert suggestion.type == RefactoringType.GUARD_CLAUSE
        assert suggestion.title == "Introduce Guard Clause"
        assert "5 levels" in suggestion.description
        assert suggestion.code_diff is not None
        assert suggestion.estimated_effort == "simple"

    def test_generate_constant_extraction_suggestion(self) -> None:
        """Test Extract Constant suggestion generation."""
        advisor = RefactoringAdvisor()

        smell = {"type": "magic_number", "line": 15, "value": 42}
        suggestion = advisor._generate_constant_extraction(
            "test.py",
            "if x < 42:",
            "python",
            15,
            smell,
        )

        assert suggestion.type == RefactoringType.REPLACE_MAGIC_NUMBER
        assert suggestion.title == "Extract Constant"
        assert "42" in suggestion.description
        assert suggestion.severity == SeverityLevel.LOW
        assert suggestion.estimated_effort == "simple"

    def test_generate_extract_class_suggestion(self) -> None:
        """Test Extract Class suggestion generation."""
        advisor = RefactoringAdvisor()

        smell = {"type": "large_class", "line": 1, "size": 600}
        suggestion = advisor._generate_extract_class(
            "test.py",
            "class LargeClass: ...",
            "python",
            1,
            smell,
        )

        assert suggestion.type == RefactoringType.EXTRACT_CLASS
        assert suggestion.title == "Extract Class"
        assert "600 lines" in suggestion.description
        assert suggestion.severity == SeverityLevel.HIGH
        assert suggestion.estimated_effort == "complex"

    def test_analyze_content_deep_nesting_python(self) -> None:
        """Test detecting deep nesting in Python code."""
        advisor = RefactoringAdvisor()

        content = """
def process(data):
    if data:
        if data.valid():
            if data.permission():
                if data.ready():
                    return True
        return False
"""

        report = advisor._analyze_content("test.py", content, "python")

        # Should detect 16+ space indentation (4 levels deep)
        assert report.total_suggestions > 0
        assert any(
            s.type == RefactoringType.GUARD_CLAUSE
            for s in report.suggestions
        )

    def test_analyze_content_deep_nesting_javascript(self) -> None:
        """Test detecting deep nesting in JavaScript code."""
        advisor = RefactoringAdvisor()

        content = """
function process(data) {
    if (data) {
        if (data.valid) {
            if (data.permission) {
                return true;
            }
        }
    }
    return false;
}
"""

        report = advisor._analyze_content("test.js", content, "javascript")

        # Should detect deep nesting
        assert report.total_suggestions > 0


class TestCodeDiff:
    """Tests for CodeDiff dataclass."""

    def test_create_code_diff(self) -> None:
        """Test creating a code diff."""
        diff = CodeDiff(
            before="old code",
            after="new code",
            language="python",
            line_start=10,
            line_end=20,
        )

        assert diff.before == "old code"
        assert diff.after == "new code"
        assert diff.language == "python"
        assert diff.line_start == 10
        assert diff.line_end == 20


class TestLanguageSpecificSuggestions:
    """Tests for language-specific refactoring suggestions."""

    def test_generate_javascript_arrow_function_suggestion(self) -> None:
        """Test JavaScript arrow function conversion suggestion."""
        advisor = RefactoringAdvisor()

        content = "array.map(function(x) { return x * 2; });"
        suggestion = advisor._generate_javascript_arrow_function(
            "test.js",
            content,
            10,
            {},
        )

        assert suggestion.type == RefactoringType.EXTRACT_METHOD
        assert suggestion.title == "Convert to Arrow Function"
        assert "arrow function" in suggestion.description.lower()
        assert suggestion.language == "javascript"
        assert suggestion.estimated_effort == "simple"

    def test_generate_java_extract_interface_suggestion(self) -> None:
        """Test Java Extract Interface suggestion."""
        advisor = RefactoringAdvisor()

        content = "public class Service { public void execute() {} }"
        suggestion = advisor._generate_java_extract_interface(
            "Service.java",
            content,
            1,
            {},
        )

        assert suggestion.type == RefactoringType.EXTRACT_CLASS
        assert suggestion.title == "Extract Interface"
        assert "interface" in suggestion.description.lower()
        assert suggestion.language == "java"
        assert suggestion.estimated_effort == "moderate"

    def test_generate_go_extract_interface_suggestion(self) -> None:
        """Test Go Extract Interface suggestion."""
        advisor = RefactoringAdvisor()

        content = "type Database struct {}\nfunc (d *Database) Save() {}"
        suggestion = advisor._generate_go_extract_interface(
            "database.go",
            content,
            1,
            {},
        )

        assert suggestion.type == RefactoringType.EXTRACT_CLASS
        assert suggestion.title == "Extract Interface"
        assert "interface" in suggestion.description.lower()
        assert suggestion.language == "go"
        assert suggestion.estimated_effort == "moderate"

    def test_generate_csharp_async_await_suggestion(self) -> None:
        """Test C# async/await improvement suggestion."""
        advisor = RefactoringAdvisor()

        content = "public async void Process() { await Task.Delay(100); }"
        suggestion = advisor._generate_csharp_async_await(
            "Service.cs",
            content,
            1,
            {},
        )

        assert suggestion.type == RefactoringType.EXTRACT_METHOD
        assert suggestion.title == "Modernize Async Pattern"
        assert "async" in suggestion.description.lower()
        assert suggestion.severity == SeverityLevel.HIGH
        assert suggestion.language == "csharp"

    def test_generate_language_specific_javascript(self) -> None:
        """Test language-specific suggestions for JavaScript."""
        advisor = RefactoringAdvisor()

        content = "array.map(function(x) { return x * 2; });"
        suggestions = advisor.generate_language_specific_suggestions(
            "test.js",
            content,
            "javascript",
        )

        assert len(suggestions) > 0
        assert any(
            s.title == "Convert to Arrow Function"
            for s in suggestions
        )

    def test_generate_language_specific_java(self) -> None:
        """Test language-specific suggestions for Java."""
        advisor = RefactoringAdvisor()

        content = "public class Service { public void execute() {} }"
        suggestions = advisor.generate_language_specific_suggestions(
            "Service.java",
            content,
            "java",
        )

        # Should suggest interface extraction for classes without implements
        assert len(suggestions) > 0

    def test_generate_language_specific_go(self) -> None:
        """Test language-specific suggestions for Go."""
        advisor = RefactoringAdvisor()

        content = "type Database struct {}\nfunc (d *Database) Save() {}"
        suggestions = advisor.generate_language_specific_suggestions(
            "database.go",
            content,
            "go",
        )

        assert len(suggestions) > 0
        assert any(
            s.title == "Extract Interface"
            for s in suggestions
        )

    def test_generate_language_specific_csharp(self) -> None:
        """Test language-specific suggestions for C#."""
        advisor = RefactoringAdvisor()

        content = "public async void Process() { await Task.Delay(100); }"
        suggestions = advisor.generate_language_specific_suggestions(
            "Service.cs",
            content,
            "csharp",
        )

        assert len(suggestions) > 0
        assert any(
            s.title == "Modernize Async Pattern"
            for s in suggestions
        )

    def test_generate_language_specific_python_no_suggestions(self) -> None:
        """Test Python returns no language-specific suggestions (handled elsewhere)."""
        advisor = RefactoringAdvisor()

        content = "def process(): pass"
        suggestions = advisor.generate_language_specific_suggestions(
            "test.py",
            content,
            "python",
        )

        # Python doesn't have language-specific patterns in this method
        assert len(suggestions) == 0

    def test_generate_language_specific_javascript_with_arrow(self) -> None:
        """Test JavaScript with arrow functions returns no suggestion."""
        advisor = RefactoringAdvisor()

        content = "array.map(x => x * 2);"
        suggestions = advisor.generate_language_specific_suggestions(
            "test.js",
            content,
            "javascript",
        )

        # Already using arrow functions, no suggestion needed
        assert len(suggestions) == 0
