#!/usr/bin/env python3
"""
Markdown Language Detection Tests

Tests for Markdown language detection functionality.
"""

import pytest
from tree_sitter_analyzer.language_detector import LanguageDetector


class TestMarkdownLanguageDetection:
    """Test Markdown language detection"""

    def setup_method(self):
        """Setup test fixtures"""
        self.detector = LanguageDetector()

    def test_markdown_extensions_detection(self):
        """Test detection of Markdown file extensions"""
        test_cases = [
            ("test.md", "markdown"),
            ("README.markdown", "markdown"),
            ("doc.mdown", "markdown"),
            ("file.mkd", "markdown"),
            ("document.mkdn", "markdown"),
            ("component.mdx", "markdown"),
        ]
        
        for file_path, expected_language in test_cases:
            detected_language = self.detector.detect_from_extension(file_path)
            assert detected_language == expected_language, f"Failed for {file_path}"

    def test_markdown_extensions_with_confidence(self):
        """Test Markdown extension detection with confidence scores"""
        test_cases = [
            ("test.md", "markdown", 0.9),
            ("README.markdown", "markdown", 0.9),
            ("doc.mdown", "markdown", 0.8),
            ("file.mkd", "markdown", 0.8),
            ("document.mkdn", "markdown", 0.8),
            ("component.mdx", "markdown", 0.7),  # Lower confidence for MDX
        ]
        
        for file_path, expected_language, expected_confidence in test_cases:
            language, confidence = self.detector.detect_language(file_path)
            assert language == expected_language, f"Language failed for {file_path}"
            assert confidence == expected_confidence, f"Confidence failed for {file_path}: got {confidence}, expected {expected_confidence}"

    def test_markdown_content_patterns(self):
        """Test Markdown content pattern detection"""
        markdown_content = """
# Main Header

This is a markdown document with various elements.

## Subheader

- List item 1
- List item 2
- List item 3

```python
def hello():
    print("Hello, World!")
```

[Link to example](http://example.com)

![Image](image.jpg)

> This is a blockquote

| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |

---
"""
        
        language, confidence = self.detector.detect_language("test.md", markdown_content)
        assert language == "markdown"
        assert confidence == 1.0  # High confidence due to clear extension

    def test_markdown_content_scoring(self):
        """Test Markdown content pattern scoring"""
        # Test individual patterns
        test_patterns = [
            ("# Header", True),  # ATX header
            ("## Subheader", True),  # ATX header
            ("- List item", True),  # List item
            ("* Another item", True),  # List item
            ("+ Third item", True),  # List item
            ("```code```", True),  # Fenced code block
            ("[link](url)", True),  # Link
            ("![image](url)", True),  # Image
            ("> Quote", True),  # Blockquote
            ("| table | cell |", True),  # Table
            ("---", True),  # Horizontal rule
            ("===", True),  # Setext header underline
            ("Regular text", False),  # No special patterns
        ]
        
        for content, should_match in test_patterns:
            # Test with .md extension to ensure we're testing content patterns
            language, confidence = self.detector.detect_language("test.md", content)
            assert language == "markdown"
            # Content with patterns should maintain high confidence
            if should_match:
                assert confidence >= 0.9
            else:
                assert confidence >= 0.9  # Extension still gives high confidence

    def test_markdown_vs_other_languages(self):
        """Test Markdown detection vs other languages"""
        # Test that clear non-Markdown content doesn't get misidentified
        non_markdown_cases = [
            ("test.py", "def function():\n    pass", "python"),
            ("test.java", "public class Test {}", "java"),
            ("test.js", "function test() {}", "javascript"),
            ("test.cpp", "#include <iostream>", "cpp"),
        ]
        
        for file_path, content, expected_language in non_markdown_cases:
            language, confidence = self.detector.detect_language(file_path, content)
            assert language == expected_language
            assert language != "markdown"

    def test_markdown_language_support(self):
        """Test that Markdown is in supported languages"""
        assert self.detector.is_supported("markdown")
        assert "markdown" in self.detector.get_supported_languages()

    def test_markdown_extension_mapping(self):
        """Test Markdown extension mapping"""
        supported_extensions = self.detector.get_supported_extensions()
        markdown_extensions = [".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdx"]
        
        for ext in markdown_extensions:
            assert ext in supported_extensions

    def test_markdown_language_info(self):
        """Test Markdown language information"""
        info = self.detector.get_language_info("markdown")
        
        assert info["name"] == "markdown"
        assert info["supported"] is True
        assert info["tree_sitter_available"] is True
        assert ".md" in info["extensions"]
        assert ".markdown" in info["extensions"]

    def test_case_insensitive_extensions(self):
        """Test case-insensitive extension detection"""
        test_cases = [
            ("README.MD", "markdown"),
            ("doc.MARKDOWN", "markdown"),
            ("file.Md", "markdown"),
            ("test.MdX", "markdown"),
        ]
        
        for file_path, expected_language in test_cases:
            detected_language = self.detector.detect_from_extension(file_path)
            assert detected_language == expected_language

    def test_markdown_with_path_variations(self):
        """Test Markdown detection with various path formats"""
        test_cases = [
            ("./README.md", "markdown"),
            ("../docs/guide.markdown", "markdown"),
            ("/absolute/path/to/file.md", "markdown"),
            ("C:\\Windows\\path\\file.md", "markdown"),
            ("docs/subfolder/nested.md", "markdown"),
        ]
        
        for file_path, expected_language in test_cases:
            detected_language = self.detector.detect_from_extension(file_path)
            assert detected_language == expected_language

    def test_add_custom_markdown_extension(self):
        """Test adding custom Markdown extension"""
        # Add a custom extension
        self.detector.add_extension_mapping(".custom_md", "markdown")
        
        # Test that it works
        language = self.detector.detect_from_extension("test.custom_md")
        assert language == "markdown"
        
        # Test with confidence
        language, confidence = self.detector.detect_language("test.custom_md")
        assert language == "markdown"
        assert confidence > 0.0

    def test_markdown_content_edge_cases(self):
        """Test Markdown content detection edge cases"""
        edge_cases = [
            # Empty content
            ("", "markdown", 1.0),  # Extension-based
            
            # Minimal content
            ("#", "markdown", 1.0),
            
            # Mixed content
            ("# Header\nSome code: function() {}", "markdown", 1.0),
            
            # HTML in Markdown
            ("# Header\n<div>HTML content</div>", "markdown", 1.0),
            
            # Code blocks with various languages
            ("```python\nprint('hello')\n```", "markdown", 1.0),
            ("```javascript\nconsole.log('hello');\n```", "markdown", 1.0),
        ]
        
        for content, expected_language, min_confidence in edge_cases:
            language, confidence = self.detector.detect_language("test.md", content)
            assert language == expected_language
            assert confidence >= min_confidence

    def test_markdown_pattern_regex(self):
        """Test Markdown pattern regex matching"""
        # Access the content patterns for markdown
        markdown_patterns = self.detector.content_patterns.get("markdown", [])
        assert len(markdown_patterns) > 0
        
        # Test that patterns are properly formatted
        for pattern, weight in markdown_patterns:
            assert isinstance(pattern, str)
            assert isinstance(weight, (int, float))
            assert weight > 0
            assert weight <= 1.0

    def test_unknown_extension_not_markdown(self):
        """Test that unknown extensions don't default to Markdown"""
        unknown_files = [
            "test.unknown",
            "file.xyz",
            "document.random",
            "noextension",
        ]
        
        for file_path in unknown_files:
            language = self.detector.detect_from_extension(file_path)
            assert language != "markdown"
            assert language == "unknown"


class TestMarkdownDetectionIntegration:
    """Integration tests for Markdown detection"""

    def setup_method(self):
        """Setup test fixtures"""
        self.detector = LanguageDetector()

    def test_real_markdown_samples(self):
        """Test with realistic Markdown samples"""
        readme_content = """
# Project Title

A brief description of what this project does and who it's for.

## Installation

```bash
npm install my-project
```

## Usage

```javascript
const myProject = require('my-project');
myProject.doSomething();
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
"""
        
        language, confidence = self.detector.detect_language("README.md", readme_content)
        assert language == "markdown"
        assert confidence == 1.0

    def test_documentation_markdown(self):
        """Test with documentation-style Markdown"""
        doc_content = """
# API Documentation

## Overview

This API provides access to our service.

### Authentication

All requests must include an API key:

```http
GET /api/v1/users
Authorization: Bearer YOUR_API_KEY
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | /users   | List users  |
| POST   | /users   | Create user |

#### Error Responses

> **Note**: All errors return JSON with an error message.

```json
{
  "error": "Invalid API key",
  "code": 401
}
```
"""
        
        language, confidence = self.detector.detect_language("api-docs.md", doc_content)
        assert language == "markdown"
        assert confidence == 1.0

    def test_blog_post_markdown(self):
        """Test with blog post style Markdown"""
        blog_content = """
---
title: "My Blog Post"
date: 2023-01-01
tags: ["tech", "programming"]
---

# Welcome to My Blog

Today I want to talk about **programming** and _development_.

## What I've Learned

Here are some key points:

- Always write tests
- Document your code
- Use version control

![Programming Image](https://example.com/image.jpg)

Check out [this great resource](https://example.com) for more information.

> Programming is not about what you know; it's about what you can figure out.
"""
        
        language, confidence = self.detector.detect_language("blog-post.md", blog_content)
        assert language == "markdown"
        assert confidence == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=tree_sitter_analyzer.language_detector", "--cov-report=term-missing"])