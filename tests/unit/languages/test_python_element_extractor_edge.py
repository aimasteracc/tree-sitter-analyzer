"""Python element extractor edge cases and performance tests."""

import time
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor
from tree_sitter_analyzer.models import Class, Function


class TestPythonElementExtractor:
    """Test Python element extractor functionality"""

    @pytest.fixture
    def extractor(self):
        """Create a Python element extractor instance"""
        return PythonElementExtractor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_python_code(self):
        """Sample Python code for testing"""
        return '''
import os
import sys
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class User:
    """User model class"""
    name: str
    age: int
    email: Optional[str] = None

    def __post_init__(self):
        """Post initialization method"""
        if not self.email:
            self.email = f"{self.name.lower()}@example.com"

    @property
    def display_name(self) -> str:
        """Get display name"""
        return f"{self.name} ({self.age})"

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> 'User':
        """Create user from dictionary"""
        return cls(**data)

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        return "@" in email and "." in email

async def fetch_user_data(user_id: int) -> Dict[str, any]:
    """Fetch user data asynchronously"""
    # Simulate async operation
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": "Test User"}

def process_users(users: List[User]) -> List[Dict[str, any]]:
    """Process list of users"""
    result = []
    for user in users:
        if user.age >= 18:
            result.append({
                "name": user.name,
                "email": user.email,
                "is_adult": True
            })
    return result

def _private_helper(data: str) -> str:
    """Private helper function"""
    return data.strip().lower()

def __magic_method__(self, other):
    """Magic method example"""
    return self + other
'''

    def test_traverse_and_extract_iterative(self, extractor):
        """Test iterative traversal and extraction"""
        # Create mock root node with children
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "function_definition"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_definition"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        # Mock extractor functions
        mock_func_extractor = Mock()
        mock_func_extractor.return_value = Function(
            name="test_func",
            start_line=1,
            end_line=3,
            raw_text="def test_func(): pass",
            language="python",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="class TestClass: pass",
            language="python",
        )

        extractors = {
            "function_definition": mock_func_extractor,
            "class_definition": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(self, extractor):
        """Test iterative traversal with caching"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        mock_root.children = [mock_child]

        # Set up cache
        node_id = id(mock_child)
        cache_key = (node_id, "function")
        cached_function = Function(
            name="cached_func",
            start_line=1,
            end_line=2,
            raw_text="def cached_func(): pass",
            language="python",
        )
        extractor._element_cache[cache_key] = cached_function

        extractors = {"function_definition": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "function"
        )

        # Should use cached result
        assert len(results) == 1
        assert results[0] == cached_function
        assert (
            extractors["function_definition"].call_count == 0
        )  # Should not call extractor

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test max depth protection in traversal"""
        # Create deeply nested structure
        root_node = Mock()
        root_node.type = "module"
        root_node.children = []

        current_node = root_node

        # Create 210 levels of nesting (exceeds max_depth of 200)
        for _i in range(210):
            child = Mock()
            child.type = "block"
            child.children = []
            current_node.children = [child]
            current_node = child

        # Add target node at the end
        target_node = Mock()
        target_node.type = "function_definition"
        target_node.children = []
        current_node.children = [target_node]

        extractors = {"function_definition": Mock()}
        results = []

        # Should not process deeply nested nodes
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extractor.log_warning"
        ) as mock_log:
            extractor._traverse_and_extract_iterative(
                root_node, extractors, results, "function"
            )

            # Should log warning about max depth
            mock_log.assert_called()

    def test_performance_with_large_codebase(self, extractor):
        """Test performance with large codebase simulation"""

        # Create large mock tree
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Create many function nodes
        function_nodes = []
        for i in range(100):
            node = Mock()
            node.type = "function_definition"
            node.children = []
            node.start_point = (i, 0)
            node.end_point = (i + 2, 0)
            function_nodes.append(node)

        mock_root.children = function_nodes

        # Create large source code
        large_source = "\n".join([f"def function_{i}(): pass" for i in range(100)])

        # Mock extraction method to return simple functions
        def mock_extract_function(node):
            return Function(
                name=f"function_{node.start_point[0]}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=f"def function_{node.start_point[0]}(): pass",
                language="python",
            )

        with patch.object(
            extractor, "_extract_function_optimized", side_effect=mock_extract_function
        ):
            start_time = time.time()
            functions = extractor.extract_functions(mock_tree, large_source)
            end_time = time.time()

            # Should complete within reasonable time (5 seconds)
            assert end_time - start_time < 5.0
            assert len(functions) == 100

    def test_memory_usage_with_caching(self, extractor):
        """Test memory usage with caching"""
        import gc

        # Perform many operations to populate caches
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["test content"] * 1000

        # Populate caches
        for i in range(1000):
            mock_node_copy = Mock()
            mock_node_copy.start_byte = i
            mock_node_copy.end_byte = i + 10
            mock_node_copy.start_point = (0, 0)
            mock_node_copy.end_point = (0, 10)

            with patch(
                "tree_sitter_analyzer.languages.python_plugin.extractor.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = f"text_{i}"
                extractor._get_node_text_optimized(mock_node_copy)

        # Check cache sizes
        assert len(extractor._node_text_cache) <= 1000

        # Reset caches and force garbage collection
        extractor._reset_caches()
        gc.collect()

        # Caches should be empty
        assert len(extractor._node_text_cache) == 0

    def test_error_handling_in_extraction(self, extractor):
        """Test error handling during extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Mock traversal to raise exception
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            mock_traverse.side_effect = Exception("Test error")

            # Should handle exception gracefully
            functions = extractor.extract_functions(mock_tree, "test code")
            assert isinstance(functions, list)
            assert len(functions) == 0

    def test_unicode_handling(self, extractor):
        """Test Unicode character handling"""
        unicode_code = """
def 関数名(パラメータ: str) -> str:
    \"\"\"日本語のドキュメント\"\"\"
    return f"こんにちは、{パラメータ}さん"

class クラス名:
    \"\"\"日本語のクラス\"\"\"
    属性: str = "値"
"""

        extractor.source_code = unicode_code
        extractor.content_lines = unicode_code.split("\n")

        # Should handle Unicode without errors
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(unicode_code.encode("utf-8"))
        mock_node.start_point = (0, 0)
        mock_node.end_point = (len(extractor.content_lines) - 1, 0)

        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = unicode_code
            result = extractor._get_node_text_optimized(mock_node)
            assert "関数名" in result
            assert "クラス名" in result

    def test_concurrent_extraction(self, extractor):
        """Test concurrent extraction operations"""
        import queue
        import threading

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        results = queue.Queue()

        def extract_worker():
            try:
                functions = extractor.extract_functions(mock_tree, "def test(): pass")
                results.put(("success", functions))
            except Exception as e:
                results.put(("error", str(e)))

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=extract_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert isinstance(result, list)

        # All threads should succeed
        assert success_count == 5
