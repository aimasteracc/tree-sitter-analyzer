"""Python plugin integration tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)


class TestPythonPlugin:
    """Test Python plugin main class"""

    @pytest.fixture
    def plugin(self):
        """Create a Python plugin instance"""
        return PythonPlugin()

    def test_plugin_initialization(self, plugin):
        """Test plugin initialization"""
        assert plugin.language == "python"
        assert hasattr(plugin, "extractor")
        assert isinstance(plugin.extractor, PythonElementExtractor)

    def test_plugin_extract_functions(self, plugin):
        """Test plugin function extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_functions") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_functions(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_classes(self, plugin):
        """Test plugin class extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_classes") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_classes(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_variables(self, plugin):
        """Test plugin variable extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_variables") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_variables(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_imports(self, plugin):
        """Test plugin import extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_imports") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_imports(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_with_real_python_code(self, plugin):
        """Test plugin with realistic Python code"""
        python_code = '''
import asyncio
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class User:
    """User data model"""
    name: str
    email: str
    age: Optional[int] = None

    def __post_init__(self):
        """Validate user data"""
        if not self.email or "@" not in self.email:
            raise ValueError("Invalid email")

    @property
    def is_adult(self) -> bool:
        """Check if user is adult"""
        return self.age is not None and self.age >= 18

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create user from dictionary"""
        return cls(**data)

async def fetch_users() -> List[User]:
    """Fetch users asynchronously"""
    await asyncio.sleep(0.1)
    return [
        User("Alice", "alice@example.com", 25),
        User("Bob", "bob@example.com", 17)
    ]

def process_users(users: List[User]) -> dict:
    """Process users and return statistics"""
    adults = sum(1 for user in users if user.is_adult)
    return {
        "total": len(users),
        "adults": adults,
        "minors": len(users) - adults
    }
'''

        # Mock tree-sitter components
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Test that plugin can handle real code without errors
        with patch.object(plugin.extractor, "_traverse_and_extract_iterative"):
            functions = plugin.extract_functions(mock_tree, python_code)
            classes = plugin.extract_classes(mock_tree, python_code)
            variables = plugin.extract_variables(mock_tree, python_code)
            imports = plugin.extract_imports(mock_tree, python_code)

            # Should return lists without errors
            assert isinstance(functions, list)
            assert isinstance(classes, list)
            assert isinstance(variables, list)
            assert isinstance(imports, list)


class TestPythonPluginIntegration:
    """Integration tests for Python plugin"""

    def test_full_extraction_workflow(self):
        """Test complete extraction workflow"""
        plugin = PythonPlugin()

        # Complex Python code with various features
        complex_code = '''
#!/usr/bin/env python3
"""
Module docstring
"""

import os
import sys
from typing import Dict, List, Optional, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

class Status(Enum):
    """Status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

@dataclass
class Config:
    """Configuration class"""
    name: str
    value: Union[str, int, float]
    metadata: Dict[str, any] = field(default_factory=dict)

class BaseProcessor(ABC):
    """Abstract base processor"""

    def __init__(self, config: Config):
        self.config = config
        self._status = Status.PENDING

    @property
    def status(self) -> Status:
        """Get current status"""
        return self._status

    @status.setter
    def status(self, value: Status) -> None:
        """Set status"""
        self._status = value

    @abstractmethod
    def process(self, data: any) -> any:
        """Process data - must be implemented by subclasses"""
        pass

    @classmethod
    def create_default(cls) -> 'BaseProcessor':
        """Create default processor"""
        config = Config("default", "value")
        return cls(config)

    @staticmethod
    def validate_data(data: any) -> bool:
        """Validate input data"""
        return data is not None

class DataProcessor(BaseProcessor):
    """Concrete data processor"""

    def __init__(self, config: Config, batch_size: int = 100):
        super().__init__(config)
        self.batch_size = batch_size
        self._processed_count = 0

    def process(self, data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process data in batches"""
        results = []
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            processed_batch = self._process_batch(batch)
            results.extend(processed_batch)
            self._processed_count += len(batch)
        return results

    def _process_batch(self, batch: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process a single batch"""
        return [self._process_item(item) for item in batch]

    def _process_item(self, item: Dict[str, any]) -> Dict[str, any]:
        """Process a single item"""
        return {**item, "processed": True, "processor": self.config.name}

    async def process_async(self, data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process data asynchronously"""
        import asyncio

        tasks = []
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            task = asyncio.create_task(self._process_batch_async(batch))
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return [item for batch_result in results for item in batch_result]

    async def _process_batch_async(self, batch: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process batch asynchronously"""
        await asyncio.sleep(0.01)  # Simulate async work
        return self._process_batch(batch)

def create_processor(processor_type: str = "data") -> BaseProcessor:
    """Factory function for creating processors"""
    config = Config("default_processor", "default_value")

    if processor_type == "data":
        return DataProcessor(config)
    else:
        raise ValueError(f"Unknown processor type: {processor_type}")

async def main():
    """Main application entry point"""
    processor = create_processor("data")

    sample_data = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"},
        {"id": 3, "name": "Item 3"}
    ]

    # Synchronous processing
    sync_results = processor.process(sample_data)
    print(f"Sync results: {sync_results}")

    # Asynchronous processing
    async_results = await processor.process_async(sample_data)
    print(f"Async results: {async_results}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''

        # Mock tree-sitter components for integration test
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Mock query functionality
        mock_query = Mock()
        mock_query.captures.return_value = {}
        mock_tree.language.query.return_value = mock_query

        # Test extraction without errors
        functions = plugin.extract_functions(mock_tree, complex_code)
        classes = plugin.extract_classes(mock_tree, complex_code)
        variables = plugin.extract_variables(mock_tree, complex_code)
        imports = plugin.extract_imports(mock_tree, complex_code)

        # Should handle complex code without errors
        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)

    def test_framework_detection_integration(self):
        """Test framework detection in integration scenario"""
        plugin = PythonPlugin()

        # Django code
        django_code = """
from django.db import models
from django.contrib.auth.models import User

class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
"""

        plugin.extractor.source_code = django_code
        plugin.extractor._detect_file_characteristics()

        assert plugin.extractor.framework_type == "django"
        assert plugin.extractor.is_module is True

    def test_error_recovery_integration(self):
        """Test error recovery in integration scenario"""
        plugin = PythonPlugin()

        # Malformed Python code
        malformed_code = """
def incomplete_function(
    # Missing closing parenthesis and body

class IncompleteClass
    # Missing colon and body

import
# Incomplete import statement
"""

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Should handle malformed code gracefully
        functions = plugin.extract_functions(mock_tree, malformed_code)
        classes = plugin.extract_classes(mock_tree, malformed_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
