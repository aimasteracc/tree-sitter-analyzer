#!/usr/bin/env python3
"""
FileOutputManager Factory Pattern Demo

This demo demonstrates the new Managed Singleton Factory Pattern
for FileOutputManager, showing how it prevents duplicate initialization
and ensures consistent instance management across MCP tools.
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer.mcp.utils.file_output_factory import (
    FileOutputManagerFactory,
    get_file_output_manager,
)
from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager


def demo_backward_compatibility():
    """Demonstrate that existing code continues to work unchanged."""
    print("=== Backward Compatibility Demo ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")

        # Existing pattern - direct instantiation
        manager1 = FileOutputManager(temp_dir)
        manager2 = FileOutputManager(temp_dir)

        print(
            f"Direct instantiation creates separate instances: {manager1 is manager2}"
        )
        print("Both managers work correctly:")
        print(f"  Manager1 project_root: {manager1.project_root}")
        print(f"  Manager2 project_root: {manager2.project_root}")

        # Test file operations
        content = '{"message": "Hello from backward compatibility demo"}'
        file_path1 = manager1.save_to_file(content, base_name="demo1")
        file_path2 = manager2.save_to_file(content, base_name="demo2")

        print(f"  Manager1 saved file: {Path(file_path1).name}")
        print(f"  Manager2 saved file: {Path(file_path2).name}")
        print()


def demo_factory_pattern():
    """Demonstrate the new factory pattern benefits."""
    print("=== Factory Pattern Demo ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")

        # New pattern - factory managed instances
        manager1 = FileOutputManager.get_managed_instance(temp_dir)
        manager2 = FileOutputManager.get_managed_instance(temp_dir)

        print(
            f"Factory returns same instance for same project root: {manager1 is manager2}"
        )
        print(
            f"Instance count in factory: {FileOutputManagerFactory.get_instance_count()}"
        )

        # Test with different project root
        with tempfile.TemporaryDirectory() as temp_dir2:
            manager3 = FileOutputManager.get_managed_instance(temp_dir2)
            print(
                f"Different project root gets different instance: {manager1 is manager3}"
            )
            print(
                f"Instance count in factory: {FileOutputManagerFactory.get_instance_count()}"
            )

            # Show managed project roots
            roots = FileOutputManagerFactory.get_managed_project_roots()
            print(f"Managed project roots: {len(roots)} roots")

        # Clean up
        FileOutputManagerFactory.clear_all_instances()
        print(
            f"After cleanup, instance count: {FileOutputManagerFactory.get_instance_count()}"
        )
        print()


def demo_convenience_function():
    """Demonstrate the convenience function."""
    print("=== Convenience Function Demo ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")

        # Using convenience function
        manager1 = get_file_output_manager(temp_dir)
        manager2 = get_file_output_manager(temp_dir)

        print(f"Convenience function returns same instance: {manager1 is manager2}")

        # Test file operations
        content = '{"message": "Hello from convenience function demo"}'
        file_path = manager1.save_to_file(content, base_name="convenience_demo")
        print(f"Saved file: {Path(file_path).name}")

        # Clean up
        FileOutputManagerFactory.clear_all_instances()
        print()


def demo_mcp_tool_simulation():
    """Simulate multiple MCP tools using FileOutputManager."""
    print("=== MCP Tool Simulation Demo ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")

        # Simulate existing MCP tools (old pattern)
        class OldMCPTool:
            def __init__(self, name, project_root):
                self.name = name
                self.project_root = project_root
                self.file_output_manager = FileOutputManager(project_root)

            def save_result(self, content):
                return self.file_output_manager.save_to_file(
                    content, base_name=f"{self.name}_result"
                )

        # Simulate new MCP tools (factory pattern)
        class NewMCPTool:
            def __init__(self, name, project_root):
                self.name = name
                self.project_root = project_root
                self.file_output_manager = FileOutputManager.get_managed_instance(
                    project_root
                )

            def save_result(self, content):
                return self.file_output_manager.save_to_file(
                    content, base_name=f"{self.name}_result"
                )

        print("Creating old-style MCP tools:")
        old_tool1 = OldMCPTool("query_tool", temp_dir)
        old_tool2 = OldMCPTool("search_tool", temp_dir)
        print(
            f"  Old tools share same FileOutputManager: {old_tool1.file_output_manager is old_tool2.file_output_manager}"
        )

        print("Creating new-style MCP tools:")
        new_tool1 = NewMCPTool("query_tool", temp_dir)
        new_tool2 = NewMCPTool("search_tool", temp_dir)
        print(
            f"  New tools share same FileOutputManager: {new_tool1.file_output_manager is new_tool2.file_output_manager}"
        )

        # Test file operations
        content1 = '{"tool": "query_tool", "result": "analysis complete"}'
        content2 = '{"tool": "search_tool", "result": "search complete"}'

        file1 = new_tool1.save_result(content1)
        file2 = new_tool2.save_result(content2)

        print(f"  Tool1 saved: {Path(file1).name}")
        print(f"  Tool2 saved: {Path(file2).name}")
        print(
            f"  Factory instance count: {FileOutputManagerFactory.get_instance_count()}"
        )

        # Clean up
        FileOutputManagerFactory.clear_all_instances()
        print()


def demo_thread_safety():
    """Demonstrate thread safety of the factory."""
    print("=== Thread Safety Demo ===")

    import threading
    import time

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")

        instances = []
        errors = []

        def get_instance_worker():
            try:
                instance = FileOutputManager.get_managed_instance(temp_dir)
                instances.append(instance)
                time.sleep(0.01)  # Simulate some work
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _i in range(10):
            thread = threading.Thread(target=get_instance_worker)
            threads.append(thread)

        print("Starting 10 concurrent threads...")
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        print(f"Threads completed. Errors: {len(errors)}")
        print(f"Instances retrieved: {len(instances)}")

        # All instances should be the same
        if instances:
            first_instance = instances[0]
            all_same = all(instance is first_instance for instance in instances)
            print(f"All instances are the same object: {all_same}")

        # Clean up
        FileOutputManagerFactory.clear_all_instances()
        print()


def main():
    """Run all demos."""
    print("FileOutputManager Factory Pattern Demo")
    print("=" * 50)
    print()

    demo_backward_compatibility()
    demo_factory_pattern()
    demo_convenience_function()
    demo_mcp_tool_simulation()
    demo_thread_safety()

    print("Demo completed successfully!")
    print()
    print("Key Benefits:")
    print("- 100% backward compatibility with existing code")
    print("- Managed singleton pattern prevents duplicate initialization")
    print("- Thread-safe implementation")
    print("- Memory efficiency through instance reuse")
    print("- Consistent configuration across MCP tools")


if __name__ == "__main__":
    main()
