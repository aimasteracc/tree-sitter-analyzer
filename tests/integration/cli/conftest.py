import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_java_file():
    """Fixture providing a temporary Java file for testing."""
    java_code = """
package com.example.test;

import java.util.List;

/**
 * Sample class for testing
 */
public class TestClass {
    private String field1;

    /**
     * Constructor
     */
    public TestClass(String field1) {
        this.field1 = field1;
    }

    /**
     * Public method
     */
    public String getField1() {
        return field1;
    }
}
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(java_code)
        temp_path = f.name

    yield temp_path

    if Path(temp_path).exists():
        Path(temp_path).unlink()
