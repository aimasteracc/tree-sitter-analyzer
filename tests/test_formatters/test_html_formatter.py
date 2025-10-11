"""
Comprehensive tests for HTML formatter.
Tests HTML-specific formatting functionality including elements, attributes,
text content, comments, and embedded scripts/styles formatting.
"""

import pytest
from tree_sitter_analyzer.formatters.html_formatter import HTMLTableFormatter


class TestHTMLTableFormatter:
    """Test HTML table formatter functionality"""
    
    @pytest.fixture
    def formatter(self):
        """Create HTML table formatter instance"""
        return HTMLTableFormatter()

    @pytest.fixture
    def sample_html_data(self):
        """Sample HTML analysis data for testing"""
        return {
            "file_path": "test.html",
            "language": "html",
            "metrics": {
                "lines_total": 50,
                "lines_code": 35,
                "lines_comment": 8,
                "lines_blank": 7,
                "elements": {
                    "elements": 15,
                    "attributes": 25,
                    "text_nodes": 8,
                    "comments": 3,
                    "scripts": 2,
                    "styles": 1,
                    "total": 54
                }
            },
            "elements": [
                {
                    "element_type": "function",
                    "name": "html",
                    "start_line": 2,
                    "end_line": 50,
                    "raw_text": '<html lang="en">...</html>'
                },
                {
                    "element_type": "function", 
                    "name": "head",
                    "start_line": 3,
                    "end_line": 10,
                    "raw_text": '<head>...</head>'
                },
                {
                    "element_type": "function",
                    "name": "body",
                    "start_line": 11,
                    "end_line": 49,
                    "raw_text": '<body>...</body>'
                },
                {
                    "element_type": "function",
                    "name": "div",
                    "start_line": 12,
                    "end_line": 20,
                    "raw_text": '<div class="container" id="main">...</div>'
                },
                {
                    "element_type": "function",
                    "name": "p",
                    "start_line": 13,
                    "end_line": 13,
                    "raw_text": '<p>Hello world</p>'
                },
                {
                    "element_type": "variable",
                    "name": "class",
                    "start_line": 12,
                    "end_line": 12,
                    "raw_text": 'class="container"'
                },
                {
                    "element_type": "variable",
                    "name": "id", 
                    "start_line": 12,
                    "end_line": 12,
                    "raw_text": 'id="main"'
                },
                {
                    "element_type": "variable",
                    "name": "lang",
                    "start_line": 2,
                    "end_line": 2,
                    "raw_text": 'lang="en"'
                },
                {
                    "element_type": "import",
                    "name": "comment_1",
                    "start_line": 5,
                    "end_line": 5,
                    "raw_text": "<!-- This is a comment -->"
                },
                {
                    "element_type": "import",
                    "name": "comment_2",
                    "start_line": 15,
                    "end_line": 15,
                    "raw_text": "<!-- Another comment -->"
                },
                {
                    "element_type": "class",
                    "name": "script_block",
                    "start_line": 21,
                    "end_line": 25,
                    "raw_text": '<script>console.log("Hello");</script>'
                },
                {
                    "element_type": "class",
                    "name": "style_block",
                    "start_line": 6,
                    "end_line": 9,
                    "raw_text": '<style>body { margin: 0; }</style>'
                }
            ]
        }

    @pytest.fixture
    def complex_html_data(self):
        """Complex HTML data with semantic elements"""
        return {
            "file_path": "complex.html", 
            "language": "html",
            "metrics": {
                "lines_total": 120,
                "lines_code": 95,
                "lines_comment": 12,
                "lines_blank": 13,
                "elements": {
                    "elements": 45,
                    "attributes": 67,
                    "text_nodes": 23,
                    "comments": 5,
                    "scripts": 3,
                    "styles": 2,
                    "total": 145
                }
            },
            "elements": [
                {
                    "element_type": "function",
                    "name": "header",
                    "start_line": 10,
                    "end_line": 15,
                    "raw_text": '<header role="banner">...</header>'
                },
                {
                    "element_type": "function",
                    "name": "main",
                    "start_line": 16,
                    "end_line": 80,
                    "raw_text": '<main role="main">...</main>'
                },
                {
                    "element_type": "function",
                    "name": "footer",
                    "start_line": 81,
                    "end_line": 85,
                    "raw_text": '<footer role="contentinfo">...</footer>'
                },
                {
                    "element_type": "function",
                    "name": "form",
                    "start_line": 20,
                    "end_line": 40,
                    "raw_text": '<form action="/submit" method="post">...</form>'
                },
                {
                    "element_type": "function",
                    "name": "input",
                    "start_line": 25,
                    "end_line": 25,
                    "raw_text": '<input type="email" name="email" required>'
                },
                {
                    "element_type": "function",
                    "name": "img",
                    "start_line": 50,
                    "end_line": 50,
                    "raw_text": '<img src="photo.jpg" alt="A beautiful photo" loading="lazy">'
                },
                {
                    "element_type": "variable",
                    "name": "role",
                    "start_line": 10,
                    "end_line": 10,
                    "raw_text": 'role="banner"'
                },
                {
                    "element_type": "variable",
                    "name": "alt",
                    "start_line": 50,
                    "end_line": 50,
                    "raw_text": 'alt="A beautiful photo"'
                },
                {
                    "element_type": "variable",
                    "name": "aria-label",
                    "start_line": 30,
                    "end_line": 30,
                    "raw_text": 'aria-label="Contact form"'
                }
            ]
        }

    def test_formatter_initialization(self, formatter):
        """Test HTML formatter initialization"""
        assert formatter is not None
        assert isinstance(formatter, HTMLTableFormatter)

    def test_format_full_table(self, formatter, sample_html_data):
        """Test full table format for HTML"""
        result = formatter._format_full_table(sample_html_data)
        
        assert isinstance(result, str)
        assert "# HTML 文件结构分析" in result
        assert "## 📄 文件信息" in result
        assert "## 📊 代码度量" in result
        assert "### 🏷️ 元素统计" in result
        assert "## 🏗️ HTML 结构详情" in result
        
        # Check metrics section
        assert "总行数 | 50" in result
        assert "代码行数 | 35" in result  
        assert "注释行数 | 8" in result
        assert "HTML元素 | 15" in result
        assert "属性 | 25" in result
        assert "脚本块 | 2" in result
        assert "样式块 | 1" in result
        
        # Check elements sections
        assert "### 🏷️ HTML 元素 (标签)" in result
        assert "### 🏷️ HTML 属性" in result
        assert "### 💬 HTML 注释" in result
        assert "### 📜 嵌入内容 (脚本/样式)" in result

    def test_format_compact_table(self, formatter, sample_html_data):
        """Test compact table format for HTML"""
        result = formatter._format_compact_table(sample_html_data)
        
        assert isinstance(result, str)
        assert "# HTML 结构概览" in result
        assert "| 项目 | 值 |" in result
        assert "| 文件 | `test.html`" in result
        assert "| 总行数 | 50 |" in result
        assert "| HTML元素 | 15 |" in result
        assert "| 属性 | 25 |" in result
        assert "| 注释 | 3 |" in result
        
        # Should contain main elements table
        assert "## 主要元素" in result
        assert "| 标签 | 位置 | 属性数 |" in result

    def test_format_csv_table(self, formatter, sample_html_data):
        """Test CSV format for HTML elements"""
        result = formatter._format_csv_table(sample_html_data)
        
        assert isinstance(result, str)
        assert "# HTML 元素 CSV 格式" in result
        assert "```csv" in result
        assert "```" in result
        assert "序号,元素类型,名称,开始行,结束行,属性数,描述" in result
        
        # Check that elements are included
        lines = result.split('\n')
        csv_lines = [line for line in lines if ',' in line and not line.startswith('#')]
        assert len(csv_lines) > 0

    def test_format_with_format_type_parameter(self, formatter, sample_html_data):
        """Test format with different format types"""
        # Test full format
        full_result = formatter.format(sample_html_data, "full")
        assert "# HTML 文件结构分析" in full_result
        
        # Test compact format
        compact_result = formatter.format(sample_html_data, "compact")
        assert "# HTML 结构概览" in compact_result
        
        # Test CSV format
        csv_result = formatter.format(sample_html_data, "csv")
        assert "# HTML 元素 CSV 格式" in csv_result
        
        # Test JSON format
        json_result = formatter.format(sample_html_data, "json")
        assert '"file_path": "test.html"' in json_result

    def test_count_attributes_helper(self, formatter):
        """Test attribute counting helper method"""
        # Test with attributes
        html_with_attrs = '<div class="container" id="main" data-value="test">'
        count = formatter._count_attributes(html_with_attrs)
        assert count == 3  # Three = signs
        
        # Test without attributes
        html_no_attrs = '<div>'
        count = formatter._count_attributes(html_no_attrs)
        assert count == 0
        
        # Test empty string
        count = formatter._count_attributes("")
        assert count == 0

    def test_get_element_description_helper(self, formatter):
        """Test element description helper method"""
        # Test common HTML elements
        assert formatter._get_element_description("div", "<div>") == "通用容器"
        assert formatter._get_element_description("p", "<p>") == "段落"
        assert formatter._get_element_description("h1", "<h1>") == "一级标题"
        assert formatter._get_element_description("a", "<a>") == "链接"
        assert formatter._get_element_description("img", "<img>") == "图片"
        assert formatter._get_element_description("form", "<form>") == "表单"
        assert formatter._get_element_description("script", "<script>") == "JavaScript脚本"
        assert formatter._get_element_description("style", "<style>") == "CSS样式"
        
        # Test self-closing elements
        self_closing = formatter._get_element_description("img", "<img />")
        assert "自闭合" in self_closing
        
        # Test custom elements
        custom = formatter._get_element_description("custom-element", "<custom-element>")
        assert custom == "自定义元素"

    def test_extract_attribute_value_helper(self, formatter):
        """Test attribute value extraction helper"""
        # Test with double quotes
        value = formatter._extract_attribute_value('class="container"')
        assert value == "container"
        
        # Test with single quotes
        value = formatter._extract_attribute_value("id='main'")
        assert value == "main"
        
        # Test without quotes (edge case)
        value = formatter._extract_attribute_value("checked")
        assert value == ""
        
        # Test empty value
        value = formatter._extract_attribute_value('placeholder=""')
        assert value == ""

    def test_find_parent_element_helper(self, formatter):
        """Test finding parent element for attribute"""
        attribute = {
            "start_line": 15,
            "end_line": 15
        }
        
        html_elements = [
            {
                "name": "div",
                "start_line": 10,
                "end_line": 20
            },
            {
                "name": "p", 
                "start_line": 25,
                "end_line": 30
            }
        ]
        
        parent = formatter._find_parent_element(attribute, html_elements)
        assert parent == "`<div>`"
        
        # Test with no parent found
        attribute_orphan = {"start_line": 35, "end_line": 35}
        parent = formatter._find_parent_element(attribute_orphan, html_elements)
        assert parent == "未知元素"

    def test_get_text_preview_helper(self, formatter):
        """Test text preview generation helper"""
        # Test short text
        short_text = "Hello world"
        preview = formatter._get_text_preview(short_text)
        assert preview == '"Hello world"'
        
        # Test long text
        long_text = "This is a very long text that should be truncated because it exceeds the maximum length"
        preview = formatter._get_text_preview(long_text, max_length=20)
        assert preview == '"This is a very long..."'
        
        # Test empty text
        preview = formatter._get_text_preview("")
        assert preview == "空"
        
        # Test whitespace normalization
        messy_text = "  Multiple   spaces\n\nand   newlines  "
        preview = formatter._get_text_preview(messy_text)
        assert preview == '"Multiple spaces and newlines"'

    def test_extract_comment_content_helper(self, formatter):
        """Test HTML comment content extraction"""
        # Test normal comment
        comment = "<!-- This is a test comment -->"
        content = formatter._extract_comment_content(comment)
        assert content == "This is a test comment"
        
        # Test multiline comment
        multiline_comment = "<!--\n  Multiline\n  comment\n-->"
        content = formatter._extract_comment_content(multiline_comment)
        assert "Multiline" in content and "comment" in content
        
        # Test long comment (should be truncated)
        long_comment = "<!-- " + "x" * 150 + " -->"
        content = formatter._extract_comment_content(long_comment)
        assert len(content) <= 103  # 100 chars + "..."
        assert content.endswith("...")
        
        # Test malformed comment
        malformed = "This is not a comment"
        content = formatter._extract_comment_content(malformed)
        assert content == malformed

    def test_get_embedded_content_description_helper(self, formatter):
        """Test embedded content description generation"""
        # Test JavaScript with functions
        js_with_functions = "function test() { return true; } function another() {}"
        desc = formatter._get_embedded_content_description(js_with_functions, "JavaScript")
        assert "包含2个函数" in desc
        
        # Test JavaScript with console.log
        js_with_console = "console.log('debug message');"
        desc = formatter._get_embedded_content_description(js_with_console, "JavaScript")
        assert desc == "调试代码"
        
        # Test JavaScript with event listeners
        js_with_events = "element.addEventListener('click', handler);"
        desc = formatter._get_embedded_content_description(js_with_events, "JavaScript")
        assert desc == "事件处理代码"
        
        # Test CSS with rules
        css_with_rules = ".class1 {} .class2 {} #id1 {}"
        desc = formatter._get_embedded_content_description(css_with_rules, "CSS")
        assert "包含3个样式规则" in desc
        
        # Test empty content
        desc = formatter._get_embedded_content_description("", "JavaScript")
        assert desc == "空内容"

    def test_get_element_type_name_helper(self, formatter):
        """Test element type name mapping"""
        assert formatter._get_element_type_name("function") == "HTML元素"
        assert formatter._get_element_type_name("variable") == "属性"
        assert formatter._get_element_type_name("import") == "注释"
        assert formatter._get_element_type_name("class") == "嵌入内容"
        assert formatter._get_element_type_name("package") == "文档信息"
        assert formatter._get_element_type_name("unknown") == "未知"
        assert formatter._get_element_type_name("custom") == "custom"

    def test_format_structure_with_complex_data(self, formatter, complex_html_data):
        """Test formatting with complex HTML data including semantic elements"""
        result = formatter._format_full_table(complex_html_data)
        
        # Should handle semantic elements
        assert "header" in result
        assert "main" in result
        assert "footer" in result
        
        # Should handle form elements
        assert "form" in result
        assert "input" in result
        
        # Should handle media elements  
        assert "img" in result
        
        # Should include accessibility analysis
        assert "无障碍特征" in result
        assert "ARIA标签" in result

    def test_format_with_none_data(self, formatter):
        """Test formatting with None data"""
        result = formatter.format(None)
        assert result == "# No data available\n"
        
        result = formatter._format_full_table(None)
        assert result == "# No data available\n"
        
        result = formatter._format_compact_table(None)
        assert result == "# No data available\n"

    def test_format_with_invalid_data_type(self, formatter):
        """Test formatting with invalid data type"""
        result = formatter.format("invalid string data")
        assert "Invalid data type" in result
        
        result = formatter.format(12345)
        assert "Invalid data type" in result

    def test_format_with_empty_elements(self, formatter):
        """Test formatting with empty elements list"""
        empty_data = {
            "file_path": "empty.html",
            "language": "html",
            "metrics": {
                "lines_total": 5,
                "lines_code": 3,
                "lines_comment": 0,
                "lines_blank": 2,
                "elements": {
                    "elements": 0,
                    "attributes": 0,
                    "text_nodes": 0,
                    "comments": 0,
                    "scripts": 0,
                    "styles": 0,
                    "total": 0
                }
            },
            "elements": []
        }
        
        result = formatter._format_full_table(empty_data)
        
        # Should handle empty elements gracefully
        assert "# HTML 文件结构分析" in result
        assert "| HTML元素 | 0" in result
        assert "| 属性 | 0" in result

    def test_unsupported_format_type_error(self, formatter, sample_html_data):
        """Test error handling for unsupported format types"""
        with pytest.raises(ValueError) as exc_info:
            formatter.format(sample_html_data, "unsupported_format")
        
        assert "Unsupported format type" in str(exc_info.value)
        assert "unsupported_format" in str(exc_info.value)
        assert "Supported formats: ['full', 'compact', 'csv', 'json']" in str(exc_info.value)

    def test_format_structure_integration(self, formatter, sample_html_data):
        """Test format_structure method integration"""
        # Test with default format type
        result = formatter.format_structure(sample_html_data)
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Should delegate to appropriate format method based on format_type
        formatter.format_type = "full"
        result_full = formatter.format_structure(sample_html_data)
        assert "# HTML 文件结构分析" in result_full
        
        formatter.format_type = "compact"
        result_compact = formatter.format_structure(sample_html_data)
        assert "# HTML 结构概览" in result_compact


if __name__ == "__main__":
    pytest.main([__file__])