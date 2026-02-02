"""
Unit tests for Java cyclomatic complexity calculation.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 5: Complexity Calculation (5 tests)
"""


class TestCyclomaticComplexity:
    """Tests for cyclomatic complexity calculation."""

    def test_simple_method_complexity(self):
        """Test simple method has complexity of 1."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Simple {
    public void straightLine() {
        int x = 1;
        int y = 2;
        int z = x + y;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Simple.java")

        method = result["classes"][0]["methods"][0]
        assert "complexity" in method
        assert method["complexity"] == 1  # Base complexity

    def test_if_statement_complexity(self):
        """Test if statement increases complexity."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Conditional {
    public void checkValue(int x) {
        if (x > 0) {
            System.out.println("Positive");
        } else {
            System.out.println("Non-positive");
        }
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Conditional.java")

        method = result["classes"][0]["methods"][0]
        assert method["complexity"] == 2  # 1 base + 1 if

    def test_loop_complexity(self):
        """Test loops increase complexity."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Loops {
    public void iterate(int n) {
        for (int i = 0; i < n; i++) {
            System.out.println(i);
        }

        while (n > 0) {
            n--;
        }
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Loops.java")

        method = result["classes"][0]["methods"][0]
        assert method["complexity"] == 3  # 1 base + 1 for + 1 while

    def test_switch_complexity(self):
        """Test switch statement increases complexity."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class SwitchCase {
    public String getDayName(int day) {
        switch (day) {
            case 1:
                return "Monday";
            case 2:
                return "Tuesday";
            case 3:
                return "Wednesday";
            default:
                return "Unknown";
        }
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "SwitchCase.java")

        method = result["classes"][0]["methods"][0]
        # switch adds 1 for the statement itself
        assert method["complexity"] == 2  # 1 base + 1 switch

    def test_complex_nested_control_flow(self):
        """Test complex nested control flow."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Complex {
    public void processData(int[] data) {
        if (data != null && data.length > 0) {  // +2 (if + &&)
            for (int i = 0; i < data.length; i++) {  // +1
                if (data[i] > 0) {  // +1
                    System.out.println("Positive");
                } else if (data[i] < 0) {  // +1
                    System.out.println("Negative");
                }
            }
        }
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Complex.java")

        method = result["classes"][0]["methods"][0]
        # 1 base + 1 outer if + 1 && + 1 for + 1 inner if + 1 else if = 6
        assert method["complexity"] >= 5  # At least 5 decision points
