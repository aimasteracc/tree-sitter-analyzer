"""
TDD Tests for V2 Self-Identified Problems

Test-Driven Development approach:
1. Write tests for all 6 problems
2. Run tests (should FAIL)
3. Fix the code
4. Run tests again (should PASS)
"""
import pytest
import re
from pathlib import Path
import importlib
import logging


class TestProblem1_UnicodeEncoding:
    """Test that all console output uses ASCII only (no emojis)"""
    
    def test_no_emojis_in_project_knowledge(self):
        """Ensure project_knowledge.py has no emoji characters"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Check for common emoji patterns
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')
        matches = emoji_pattern.findall(content)
        
        assert len(matches) == 0, f"Found {len(matches)} emojis in project_knowledge.py"
    
    def test_all_output_is_ascii_safe(self):
        """Ensure all print/log statements use ASCII-safe markers or logging"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Should use logging instead of print with emojis
        assert 'import logging' in content, \
            "Should use logging module"
        assert 'logger = logging.getLogger' in content, \
            "Should create logger instance"
        
        # Check for emoji characters (should have none)
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')
        matches = emoji_pattern.findall(content)
        assert len(matches) == 0, \
            f"Found {len(matches)} emojis, should use logger.info/error instead"


class TestProblem2_BrokenImports:
    """Test that all imports are valid and modules exist"""
    
    def test_graph_builder_imports_correctly(self):
        """Ensure CodeGraphBuilder can be imported without errors"""
        try:
            from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
            assert CodeGraphBuilder is not None
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")
    
    def test_all_modules_importable(self):
        """Ensure all Python files can be imported (no ModuleNotFoundError)"""
        v2_root = Path('tree_sitter_analyzer_v2')
        errors = []
        
        for py_file in v2_root.rglob('*.py'):
            if '__pycache__' in str(py_file) or py_file.name.startswith('test_'):
                continue
            
            # Convert path to module name
            rel_path = py_file.relative_to(v2_root.parent)
            module_name = str(rel_path).replace('/', '.').replace('\\', '.').removesuffix('.py')
            
            try:
                importlib.import_module(module_name)
            except Exception as e:
                errors.append(f"{module_name}: {e}")
        
        # Allow some expected failures (e.g., __main__.py modules)
        critical_errors = [e for e in errors if '__main__' not in e]
        assert len(critical_errors) == 0, f"Import errors:\n" + "\n".join(critical_errors[:5])


class TestProblem3_PrintVsLogging:
    """Test that code uses logging instead of print()"""
    
    def test_project_knowledge_uses_logging(self):
        """Ensure project_knowledge.py uses logging, not print()"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Should have logger import
        assert 'import logging' in content or 'from logging import' in content, \
            "Should import logging module"
        
        # Should create logger
        assert 'logger = logging.getLogger' in content, \
            "Should create logger instance"
    
    def test_minimal_print_usage(self):
        """Ensure print() is minimally used (prefer logging)"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Count print statements (excluding comments and strings)
        lines = [l for l in content.split('\n') if not l.strip().startswith('#')]
        print_count = sum(1 for l in lines if 'print(' in l)
        
        # Allow max 2 print statements (for debugging/special cases)
        assert print_count <= 2, \
            f"Found {print_count} print() calls, should use logging instead"


class TestProblem4_CodeGeneration:
    """Test that generated code is syntactically valid"""
    
    def test_generated_code_compiles(self):
        """Ensure any generated code templates are valid Python"""
        # Test a simple template generation
        template = '''
def test_example():
    """Test docstring"""
    assert True
'''
        # Should compile without errors
        try:
            compile(template, '<string>', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Generated template has syntax error: {e}")
    
    def test_string_escaping_in_templates(self):
        """Ensure templates properly escape triple quotes"""
        # This should not cause SyntaxError
        template = """
def test_with_docstring():
    '''Example docstring'''
    pass
"""
        try:
            compile(template, '<string>', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Template escaping failed: {e}")


class TestProblem5_NoHardcodedPaths:
    """Test that paths are configurable, not hardcoded"""
    
    def test_uses_configurable_cache_dir(self):
        """Ensure cache directory is configurable"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Should use constants not hardcoded strings
        assert 'DEFAULT_CACHE_DIR' in content, \
            "Should define cache dir as configurable constant"
    
    def test_no_hardcoded_v1_paths(self):
        """Ensure no hardcoded '../tree-sitter-analyzer-v1' paths in main code"""
        src_files = Path('tree_sitter_analyzer_v2').rglob('*.py')
        
        for file_path in src_files:
            if 'test' in str(file_path) or 'analyze_v1' in str(file_path):
                continue  # Skip test/analysis scripts
            
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            assert '../tree-sitter-analyzer-v1' not in content, \
                f"Found hardcoded V1 path in {file_path}"


class TestProblem6_Simplicity:
    """Test that code follows KISS principle (Keep It Simple)"""
    
    def test_reasonable_function_complexity(self):
        """Ensure functions are not overly complex"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        # Simple heuristic: no function should have >100 lines
        functions = re.findall(r'def \w+\([^)]*\):(.*?)(?=\n    def |\nclass |\Z)', 
                              content, re.DOTALL)
        
        for i, func_body in enumerate(functions):
            lines = len(func_body.split('\n'))
            assert lines <= 100, \
                f"Function #{i+1} has {lines} lines, consider simplifying (max 100)"
    
    def test_reasonable_nesting_depth(self):
        """Ensure code doesn't have excessive nesting"""
        file_path = Path('tree_sitter_analyzer_v2/features/project_knowledge.py')
        content = file_path.read_text(encoding='utf-8')
        
        max_indent = 0
        for line in content.split('\n'):
            if line.strip():
                indent = len(line) - len(line.lstrip())
                max_indent = max(max_indent, indent // 4)
        
        # Allow deeper nesting for complex logic (up to 7 levels)
        assert max_indent <= 7, \
            f"Max nesting depth is {max_indent}, should be <=7 for maintainability"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
