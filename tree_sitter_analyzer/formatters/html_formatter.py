#!/usr/bin/env python3
"""
HTML Table Formatter

Provides specialized table formatting for HTML files, focusing on document structure
rather than programming constructs like classes and methods.
"""

import json
from typing import Dict, List, Any, Optional
from .base_formatter import BaseTableFormatter


class HTMLTableFormatter(BaseTableFormatter):
    """Table formatter specialized for HTML documents"""

    def format(self, data: dict[str, Any], format_type: str = None) -> str:
        """Format data using the configured format type"""
        # Handle None data
        if data is None:
            return "# No data available\n"
        
        # Ensure data is a dictionary
        if not isinstance(data, dict):
            return f"# Invalid data type: {type(data)}\n"
        
        if format_type:
            # Check for supported format types
            supported_formats = ['full', 'compact', 'csv', 'json']
            if format_type not in supported_formats:
                raise ValueError(f"Unsupported format type: {format_type}. Supported formats: {supported_formats}")
            
            # Handle json format separately
            if format_type == 'json':
                return self._format_json(data)
            
            # Temporarily change format type for this call
            original_format = self.format_type
            self.format_type = format_type
            result = self.format_structure(data)
            self.format_type = original_format
            return result
        return self.format_structure(data)

    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data with HTML-specific handling"""
        # Handle None data
        if structure_data is None:
            return "# No data available\n"
        
        # Ensure data is a dictionary
        if not isinstance(structure_data, dict):
            return f"# Invalid data type: {type(structure_data)}\n"
        
        # Handle different format types
        if self.format_type == "full":
            result = self._format_full_table(structure_data)
        elif self.format_type == "compact":
            result = self._format_compact_table(structure_data)
        elif self.format_type == "csv":
            result = self._format_csv(structure_data)
        elif self.format_type == "json":
            result = self._format_json(structure_data)
        else:
            # Default to full format
            result = self._format_full_table(structure_data)
        
        # Add newline if not present
        if self.format_type == "csv":
            return result  # CSV doesn't need extra newline
        elif not result.endswith("\n"):
            result += "\n"
        
        return result

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for HTML"""
        if data is None:
            return "# No data available\n"
        
        file_path = data.get("file_path", "")
        elements = data.get("elements", [])
        
        # Get document title from title element or filename
        title_elements = [e for e in elements if isinstance(e, dict) and e.get('name', '').lower() == 'title']
        title = title_elements[0].get('raw_text', '').strip() if title_elements else file_path.split("/")[-1]
        
        output = [f"# {title}\n"]
        
        # Document Overview
        output.append("## Document Overview\n")
        output.append(f"| Property | Value |")
        output.append(f"|----------|-------|")
        output.append(f"| File | {file_path} |")
        output.append(f"| Language | html |")
        output.append(f"| Total Lines | {data.get('line_count', 0)} |")
        output.append(f"| Total Elements | {len(elements)} |")
        output.append("")
        
        # Organize elements by type
        html_elements = [e for e in elements if isinstance(e, dict) and e.get('type') == "function"]
        attributes = [e for e in elements if isinstance(e, dict) and e.get('type') == "variable"]
        comments = [e for e in elements if isinstance(e, dict) and e.get('type') == "import"]
        scripts = [e for e in elements if isinstance(e, dict) and e.get('type') == "class"]
        
        # Document Structure (HTML Elements organized by type)
        if html_elements:
            output.append("## Document Structure\n")
            
            # Group elements by type for better organization
            structural_elements = ['html', 'head', 'body', 'header', 'footer', 'main', 'section', 'article', 'aside', 'nav']
            content_elements = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span']
            form_elements = ['form', 'input', 'textarea', 'select', 'button', 'label']
            media_elements = ['img', 'video', 'audio', 'picture', 'source']
            list_elements = ['ul', 'ol', 'li', 'dl', 'dt', 'dd']
            table_elements = ['table', 'thead', 'tbody', 'tr', 'th', 'td']
            
            # Show structural elements first
            structural = [e for e in html_elements if isinstance(e, dict) and e.get('name', '').lower() in structural_elements]
            if structural:
                output.append("### Structural Elements\n")
                output.append("| Element | Line | Attributes | Description |")
                output.append("|---------|------|------------|-------------|")
                for element in structural:
                    name = element.get('name', '')
                    line = element.get('start_line', '')
                    raw_text = element.get('raw_text', '')
                    attr_count = self._count_attributes(element)
                    description = self._get_element_description(name, raw_text)
                    output.append(f"| `<{name}>` | {line} | {attr_count} | {description} |")
                output.append("")
            
            # Show content elements
            content = [e for e in html_elements if isinstance(e, dict) and e.get('name', '').lower() in content_elements]
            if content:
                output.append("### Content Elements\n")
                output.append("| Element | Line | Attributes | Description |")
                output.append("|---------|------|------------|-------------|")
                for element in content:
                    name = element.get('name', '')
                    line = element.get('start_line', '')
                    raw_text = element.get('raw_text', '')
                    attr_count = self._count_attributes(element)
                    description = self._get_element_description(name, raw_text)
                    output.append(f"| `<{name}>` | {line} | {attr_count} | {description} |")
                output.append("")
            
            # Show form elements
            forms = [e for e in html_elements if isinstance(e, dict) and e.get('name', '').lower() in form_elements]
            if forms:
                output.append("### Form Elements\n")
                output.append("| Element | Line | Attributes | Description |")
                output.append("|---------|------|------------|-------------|")
                for element in forms:
                    name = element.get('name', '')
                    line = element.get('start_line', '')
                    raw_text = element.get('raw_text', '')
                    attr_count = self._count_attributes(element)
                    description = self._get_element_description(name, raw_text)
                    output.append(f"| `<{name}>` | {line} | {attr_count} | {description} |")
                output.append("")
            
            # Show other elements
            all_categorized = structural_elements + content_elements + form_elements + media_elements + list_elements + table_elements
            other = [e for e in html_elements if isinstance(e, dict) and e.get('name', '').lower() not in all_categorized]
            if other:
                output.append("### Other Elements\n")
                output.append("| Element | Line | Attributes | Description |")
                output.append("|---------|------|------------|-------------|")
                for element in other:
                    name = element.get('name', '')
                    line = element.get('start_line', '')
                    raw_text = element.get('raw_text', '')
                    attr_count = self._count_attributes(element)
                    description = self._get_element_description(name, raw_text)
                    output.append(f"| `<{name}>` | {line} | {attr_count} | {description} |")
                output.append("")
        
        # Attributes Section
        if attributes:
            output.append("## Attributes\n")
            output.append("| Attribute | Value | Line |")
            output.append("|-----------|-------|------|")
            for attr in attributes:
                name = attr.get('name', '')
                value = self._extract_attribute_value(attr.get('raw_text', ''))
                line = attr.get('start_line', '')
                output.append(f"| `{name}` | `{value}` | {line} |")
            output.append("")
        
        # Comments Section
        if comments:
            output.append("## Comments\n")
            output.append("| Content | Line |")
            output.append("|---------|------|")
            for comment in comments:
                content = self._extract_comment_content(comment.get('raw_text', ''))
                line = comment.get('start_line', '')
                output.append(f"| {content} | {line} |")
            output.append("")
        
        # Embedded Content Section
        if scripts:
            output.append("## Embedded Content\n")
            output.append("| Type | Size | Line Range | Description |")
            output.append("|------|------|------------|-------------|")
            for script in scripts:
                script_type = self._get_script_type(script.get('name', ''))
                size = len(script.get('raw_text', ''))
                start = script.get('start_line', '')
                end = script.get('end_line', '')
                range_str = f"{start}-{end}" if start and end else str(start)
                description = self._get_embedded_content_description(script.get('raw_text', ''), script_type)
                output.append(f"| {script_type} | {size} chars | {range_str} | {description} |")
            output.append("")
        
        return "\n".join(output)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for HTML"""
        if data is None:
            return "# No data available\n"
        
        file_path = data.get("file_path", "")
        elements = data.get("elements", [])
        
        # If no elements found, return appropriate message
        if not elements:
            return f"# HTML Analysis: {file_path.split('/')[-1]}\n\nINFO: No results found matching the query.\n"
        
        output = [f"# HTML Analysis: {file_path.split('/')[-1]}\n"]
        
        # For HTML, all elements are typically of type "function"
        # So we use all elements instead of filtering by type
        html_elements = elements
        
        # Calculate total attributes
        total_attributes = sum(self._count_attributes(element) for element in html_elements)
        
        # Summary table
        output.append("## Summary")
        output.append("| Type | Count |")
        output.append("|------|-------|")
        output.append(f"| Elements | {len(html_elements)} |")
        output.append(f"| Attributes | {total_attributes} |")
        output.append(f"| Comments | 0 |")
        output.append(f"| Scripts/Styles | 0 |")
        output.append("")
        
        # Elements (compact)
        if html_elements:
            output.append("## Elements")
            output.append("| Element | Line |")
            output.append("|---------|------|")
            for element in html_elements[:10]:  # Limit to first 10
                name = element.get('name', '')
                line = element.get('start_line', '')
                output.append(f"| `<{name}>` | {line} |")
            if len(html_elements) > 10:
                output.append(f"| ... | ({len(html_elements) - 10} more) |")
            output.append("")
        
        return "\n".join(output)

    def _format_json(self, data: dict[str, Any]) -> str:
        """JSON format for HTML"""
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format specialized for HTML elements"""
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # Header for HTML elements (English)
        writer.writerow([
            "Index", "Element Type", "Name", "Start Line", "End Line", "Attributes", "Description"
        ])

        # Process HTML elements
        elements = data.get("elements", [])
        for i, element in enumerate(elements, 1):
            if not isinstance(element, dict):
                continue  # Skip non-dict elements
            element_type = element.get("element_type", "")
            name = element.get("name", "")
            start_line = element.get("start_line", 0)
            end_line = element.get("end_line", 0)
            raw_text = element.get("raw_text", "")
            
            # Count attributes from element data
            attr_count = self._count_attributes(element)
            
            # Get element description
            description = self._get_element_description(name, raw_text)
            
            writer.writerow([
                i,
                element_type,
                name,
                start_line,
                end_line,
                attr_count,
                self._clean_csv_text(description)
            ])

        csv_content = output.getvalue()
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()

        return csv_content

    def _format_csv_table(self, data: dict[str, Any]) -> str:
        """Format CSV data as a markdown table with CSV block"""
        csv_data = self._format_csv(data)
        
        result = "# HTML Elements CSV Format\n\n"
        result += "```csv\n"
        result += csv_data
        result += "\n```\n"
        
        return result

    # Helper methods for HTML-specific processing
    
    def _count_attributes(self, element: dict) -> int:
        """Count number of attributes in HTML element"""
        # Use actual attributes array if available
        if 'attributes' in element and isinstance(element['attributes'], list):
            return len(element['attributes'])
        
        # Fallback to raw_text parsing
        raw_text = element.get('raw_text', '')
        if not raw_text or '<' not in raw_text:
            return 0
        
        # Simple attribute counting - count = signs
        return raw_text.count('=')

    def _get_element_description(self, tag_name: str, raw_text: str) -> str:
        """Get description for HTML element"""
        descriptions = {
            'html': 'HTML root element',
            'head': 'Document head',
            'body': 'Document body',
            'title': 'Page title',
            'meta': 'Metadata',
            'link': 'External resource link',
            'script': 'JavaScript script',
            'style': 'CSS styles',
            'div': 'Generic container',
            'span': 'Inline container',
            'p': 'Paragraph',
            'h1': 'Level 1 heading',
            'h2': 'Level 2 heading',
            'h3': 'Level 3 heading',
            'h4': 'Level 4 heading',
            'h5': 'Level 5 heading',
            'h6': 'Level 6 heading',
            'a': 'Link',
            'img': 'Image',
            'form': 'Form',
            'input': 'Input field',
            'button': 'Button',
            'table': 'Table',
            'ul': 'Unordered list',
            'ol': 'Ordered list',
            'li': 'List item',
            'header': 'Page header',
            'footer': 'Page footer',
            'main': 'Main content',
            'section': 'Section',
            'article': 'Article',
            'aside': 'Sidebar',
            'nav': 'Navigation',
        }
        
        description = descriptions.get(tag_name.lower(), 'Custom element')
        
        # Add self-closing indicator
        if raw_text and raw_text.strip().endswith('/>'):
            description += ' (self-closing)'
        
        return description

    def _extract_attribute_value(self, raw_text: str) -> str:
        """Extract value from attribute raw text"""
        if not raw_text or '=' not in raw_text:
            return ''
        
        # Extract value from attr="value" pattern
        import re
        match = re.search(r'=\s*["\']([^"\']*)["\']', raw_text)
        if match:
            return match.group(1)
        
        return raw_text.split('=')[-1].strip(' "\'')

    def _extract_comment_content(self, raw_text: str) -> str:
        """Extract content from HTML comment"""
        if not raw_text:
            return ''
        
        # Remove <!-- and -->
        import re
        match = re.search(r'<!--\s*(.*?)\s*-->', raw_text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Truncate long comments
            if len(content) > 100:
                content = content[:100] + '...'
            return content
        
        return raw_text

    def _get_script_type(self, name: str) -> str:
        """Get type of embedded content"""
        if 'script' in name.lower():
            return 'JavaScript'
        elif 'style' in name.lower():
            return 'CSS'
        else:
            return 'Unknown'

    def _get_embedded_content_description(self, raw_text: str, content_type: str) -> str:
        """Get description for embedded script/style content"""
        if not raw_text:
            return 'Empty content'
        
        if content_type == 'JavaScript':
            if 'function' in raw_text:
                func_count = raw_text.count('function')
                return f'Contains {func_count} function(s)'
            elif 'console.log' in raw_text:
                return 'Debug code'
            elif 'addEventListener' in raw_text:
                return 'Event handling code'
            else:
                return 'JavaScript code'
        elif content_type == 'CSS':
            if '{' in raw_text:
                rule_count = raw_text.count('{')
                return f'Contains {rule_count} CSS rule(s)'
            else:
                return 'CSS style code'
        
        return f'{content_type} code'

    def format_table(self, analysis_result: dict[str, Any], table_type: str = "full") -> str:
        """Format table output for HTML files"""
        # Handle None data
        if analysis_result is None:
            return "# No data available\n"
        
        # Ensure data is a dictionary
        if not isinstance(analysis_result, dict):
            return f"# Invalid data type: {type(analysis_result)}\n"
        
        # Check for supported table types
        supported_types = ['full', 'compact', 'csv', 'json']
        if table_type not in supported_types:
            raise ValueError(f"Unsupported table type: {table_type}. Supported types: {supported_types}")
        
        # Handle json format separately
        if table_type == 'json':
            return self._format_json(analysis_result)
        
        # Temporarily change format type for this call
        original_format = self.format_type
        self.format_type = table_type
        result = self.format_structure(analysis_result)
        self.format_type = original_format
        return result


# For backward compatibility, create an alias
HTMLFormatter = HTMLTableFormatter