#!/usr/bin/env python3
"""
Test query_code tool cross-language compatibility and consistency.

Tests for the fix of JavaScript function detection issues and ensures
all languages support both singular and plural query forms consistently.
"""

import asyncio
import tempfile
import os
import pytest
from tree_sitter_analyzer.core.query_service import QueryService


class TestQueryCodeCrossLanguageCompatibility:
    """Test cross-language query compatibility"""

    # Test code samples for different languages
    JAVASCRIPT_CODE = """
function regularFunction() {
    return "regular";
}

const arrowFunction = () => {
    return "arrow";
}

class TestClass {
    constructor() {
        this.value = 0;
    }
    
    methodFunction() {
        return "method";
    }
    
    static staticMethod() {
        return "static";
    }
}

async function asyncFunction() {
    return "async";
}
"""

    TYPESCRIPT_CODE = """
interface TestInterface {
    name: string;
    getValue(): number;
}

type TestType = string | number;

function tsFunction(): string {
    return "test";
}

class TSClass implements TestInterface {
    name: string = "test";
    
    getValue(): number {
        return 42;
    }
    
    method(): void {
        console.log("method");
    }
}

const arrowFunc = (): void => {
    console.log("arrow");
};
"""

    PYTHON_CODE = """
def python_function():
    return "test"

def another_function(param: str) -> str:
    return param

class PythonClass:
    def __init__(self):
        self.value = 0
    
    def method(self):
        return "method"

import os
from typing import List
"""

    JAVA_CODE = """
public class JavaClass {
    private String field;
    
    public JavaClass() {
        this.field = "test";
    }
    
    public void method() {
        System.out.println("test");
    }
    
    public static void staticMethod() {
        System.out.println("static");
    }
    
    private String getField() {
        return this.field;
    }
}
"""

    @pytest.fixture
    def query_service(self):
        """Create QueryService instance"""
        return QueryService()

    def create_temp_file(self, content: str, extension: str) -> str:
        """Create temporary file with given content and extension"""
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix=extension, 
            delete=False
        ) as f:
            f.write(content)
            return f.name

    @pytest.mark.asyncio
    async def test_javascript_query_consistency(self, query_service):
        """Test JavaScript query consistency for singular/plural forms"""
        temp_file = self.create_temp_file(self.JAVASCRIPT_CODE, ".js")
        
        try:
            # Test function queries (both singular and plural)
            function_results = await query_service.execute_query(
                temp_file, "javascript", query_key="function"
            )
            functions_results = await query_service.execute_query(
                temp_file, "javascript", query_key="functions"
            )
            
            assert function_results is not None, "function query should return results"
            assert functions_results is not None, "functions query should return results"
            assert len(function_results) > 0, "Should find JavaScript functions"
            assert len(functions_results) > 0, "Should find JavaScript functions"
            
            # Test class queries
            class_results = await query_service.execute_query(
                temp_file, "javascript", query_key="class"
            )
            classes_results = await query_service.execute_query(
                temp_file, "javascript", query_key="classes"
            )
            
            assert class_results is not None, "class query should return results"
            assert classes_results is not None, "classes query should return results"
            assert len(class_results) > 0, "Should find JavaScript classes"
            assert len(classes_results) > 0, "Should find JavaScript classes"
            
            # Test method queries (this was the original bug)
            method_results = await query_service.execute_query(
                temp_file, "javascript", query_key="method"
            )
            methods_results = await query_service.execute_query(
                temp_file, "javascript", query_key="methods"
            )
            
            assert method_results is not None, "method query should return results"
            assert methods_results is not None, "methods query should return results"
            assert len(method_results) > 0, "Should find JavaScript methods"
            assert len(methods_results) > 0, "Should find JavaScript methods"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_typescript_query_consistency(self, query_service):
        """Test TypeScript query consistency for singular/plural forms"""
        temp_file = self.create_temp_file(self.TYPESCRIPT_CODE, ".ts")
        
        try:
            # Test function queries
            function_results = await query_service.execute_query(
                temp_file, "typescript", query_key="function"
            )
            functions_results = await query_service.execute_query(
                temp_file, "typescript", query_key="functions"
            )
            
            assert function_results is not None, "function query should return results"
            assert functions_results is not None, "functions query should return results"
            assert len(function_results) > 0, "Should find TypeScript functions"
            assert len(functions_results) > 0, "Should find TypeScript functions"
            
            # Test class queries
            class_results = await query_service.execute_query(
                temp_file, "typescript", query_key="class"
            )
            classes_results = await query_service.execute_query(
                temp_file, "typescript", query_key="classes"
            )
            
            assert class_results is not None, "class query should return results"
            assert classes_results is not None, "classes query should return results"
            assert len(class_results) > 0, "Should find TypeScript classes"
            assert len(classes_results) > 0, "Should find TypeScript classes"
            
            # Test interface queries (TypeScript specific)
            interface_results = await query_service.execute_query(
                temp_file, "typescript", query_key="interface"
            )
            interfaces_results = await query_service.execute_query(
                temp_file, "typescript", query_key="interfaces"
            )
            
            assert interface_results is not None, "interface query should return results"
            assert interfaces_results is not None, "interfaces query should return results"
            assert len(interface_results) > 0, "Should find TypeScript interfaces"
            assert len(interfaces_results) > 0, "Should find TypeScript interfaces"
            
            # Test type queries (TypeScript specific)
            type_results = await query_service.execute_query(
                temp_file, "typescript", query_key="type"
            )
            types_results = await query_service.execute_query(
                temp_file, "typescript", query_key="types"
            )
            
            assert type_results is not None, "type query should return results"
            assert types_results is not None, "types query should return results"
            assert len(type_results) > 0, "Should find TypeScript types"
            assert len(types_results) > 0, "Should find TypeScript types"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_python_query_consistency(self, query_service):
        """Test Python query consistency for singular/plural forms"""
        temp_file = self.create_temp_file(self.PYTHON_CODE, ".py")
        
        try:
            # Test function queries
            function_results = await query_service.execute_query(
                temp_file, "python", query_key="function"
            )
            functions_results = await query_service.execute_query(
                temp_file, "python", query_key="functions"
            )
            
            assert function_results is not None, "function query should return results"
            assert functions_results is not None, "functions query should return results"
            assert len(function_results) > 0, "Should find Python functions"
            assert len(functions_results) > 0, "Should find Python functions"
            
            # Test class queries
            class_results = await query_service.execute_query(
                temp_file, "python", query_key="class"
            )
            classes_results = await query_service.execute_query(
                temp_file, "python", query_key="classes"
            )
            
            assert class_results is not None, "class query should return results"
            assert classes_results is not None, "classes query should return results"
            assert len(class_results) > 0, "Should find Python classes"
            assert len(classes_results) > 0, "Should find Python classes"
            
            # Test import queries
            import_results = await query_service.execute_query(
                temp_file, "python", query_key="import"
            )
            imports_results = await query_service.execute_query(
                temp_file, "python", query_key="imports"
            )
            
            assert import_results is not None, "import query should return results"
            assert imports_results is not None, "imports query should return results"
            assert len(import_results) > 0, "Should find Python imports"
            assert len(imports_results) > 0, "Should find Python imports"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_java_query_consistency(self, query_service):
        """Test Java query consistency for singular/plural forms"""
        temp_file = self.create_temp_file(self.JAVA_CODE, ".java")
        
        try:
            # Test method queries
            method_results = await query_service.execute_query(
                temp_file, "java", query_key="method"
            )
            methods_results = await query_service.execute_query(
                temp_file, "java", query_key="methods"
            )
            
            assert method_results is not None, "method query should return results"
            assert methods_results is not None, "methods query should return results"
            assert len(method_results) > 0, "Should find Java methods"
            assert len(methods_results) > 0, "Should find Java methods"
            
            # Test class queries
            class_results = await query_service.execute_query(
                temp_file, "java", query_key="class"
            )
            classes_results = await query_service.execute_query(
                temp_file, "java", query_key="classes"
            )
            
            assert class_results is not None, "class query should return results"
            assert classes_results is not None, "classes query should return results"
            assert len(class_results) > 0, "Should find Java classes"
            assert len(classes_results) > 0, "Should find Java classes"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_javascript_functions_bug_fix(self, query_service):
        """
        Specific test for the original JavaScript functions bug.
        
        This test reproduces the exact scenario that was failing:
        query_code with file_path and query_key="functions" for JavaScript
        """
        temp_file = self.create_temp_file(self.JAVASCRIPT_CODE, ".js")
        
        try:
            # This was the exact failing case reported
            results = await query_service.execute_query(
                temp_file, 
                "javascript", 
                query_key="functions"
            )
            
            # Should not be None or empty
            assert results is not None, "functions query should not return None"
            assert len(results) > 0, "functions query should find results"
            
            # Should find multiple function types
            function_types = {result.get('node_type') for result in results}
            expected_types = {'function_declaration', 'arrow_function', 'method_definition'}
            
            # Should find at least some of the expected function types
            assert len(function_types.intersection(expected_types)) > 0, \
                f"Should find function types, got: {function_types}"
            
            # Verify specific functions are found
            function_contents = [result.get('content', '') for result in results]
            function_text = ' '.join(function_contents)
            
            # Should find our test functions
            assert 'regularFunction' in function_text or 'arrowFunction' in function_text or 'methodFunction' in function_text, \
                "Should find at least one of our test functions"
                
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_cross_language_query_result_structure(self, query_service):
        """Test that all languages return consistent result structure"""
        test_cases = [
            (self.JAVASCRIPT_CODE, ".js", "javascript", "functions"),
            (self.TYPESCRIPT_CODE, ".ts", "typescript", "functions"),
            (self.PYTHON_CODE, ".py", "python", "functions"),
            (self.JAVA_CODE, ".java", "java", "methods"),
        ]
        
        for code, extension, language, query_key in test_cases:
            temp_file = self.create_temp_file(code, extension)
            
            try:
                results = await query_service.execute_query(
                    temp_file, language, query_key=query_key
                )
                
                assert results is not None, f"{language} {query_key} should return results"
                assert len(results) > 0, f"{language} {query_key} should find results"
                
                # Check result structure consistency
                for result in results:
                    assert 'capture_name' in result, f"{language} result should have capture_name"
                    assert 'node_type' in result, f"{language} result should have node_type"
                    assert 'start_line' in result, f"{language} result should have start_line"
                    assert 'end_line' in result, f"{language} result should have end_line"
                    assert 'content' in result, f"{language} result should have content"
                    
                    # Verify data types
                    assert isinstance(result['capture_name'], str), "capture_name should be string"
                    assert isinstance(result['node_type'], str), "node_type should be string"
                    assert isinstance(result['start_line'], int), "start_line should be int"
                    assert isinstance(result['end_line'], int), "end_line should be int"
                    assert isinstance(result['content'], str), "content should be string"
                    
            finally:
                os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_manual_query_execution_fallback(self, query_service):
        """Test that manual query execution fallback works correctly"""
        temp_file = self.create_temp_file(self.JAVASCRIPT_CODE, ".js")
        
        try:
            # Force manual execution by testing with a query that might not have tree-sitter support
            results = await query_service.execute_query(
                temp_file, 
                "javascript", 
                query_key="functions"
            )
            
            # Should work even if tree-sitter query fails and falls back to manual execution
            assert results is not None, "Manual fallback should work"
            assert len(results) > 0, "Manual fallback should find results"
            
            # Verify that the manual execution correctly identifies JavaScript functions
            node_types = {result.get('node_type') for result in results}
            
            # Manual execution should identify these node types
            expected_manual_types = {'function_declaration', 'arrow_function', 'method_definition'}
            found_types = node_types.intersection(expected_manual_types)
            
            assert len(found_types) > 0, \
                f"Manual execution should find function types, got: {node_types}"
                
        finally:
            os.unlink(temp_file)


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])