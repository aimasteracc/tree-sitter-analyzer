#!/usr/bin/env python3
"""
HTML-specific table formatter.

Provides specialized formatting for HTML code analysis results,
handling HTML elements, attributes, text content, and embedded scripts/styles.
Designed to complement the HTML language plugin for comprehensive HTML analysis.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class HTMLTableFormatter(BaseTableFormatter):
    """Table formatter specialized for HTML"""

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

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for HTML"""
        if data is None:
            return "# No data available\n"
        
        result = []
        
        # Add title
        result.append("# HTML 文件结构分析")
        result.append("")
        
        # File information section
        result.append("## 📄 文件信息")
        result.append("")
        result.append("| 属性 | 值 |")
        result.append("|------|-----|")
        result.append(f"| 文件路径 | `{data.get('file_path', 'N/A')}` |")
        result.append(f"| 语言类型 | `{data.get('language', 'html')}` |")
        
        # Metrics section
        metrics = data.get('metrics', {})
        if metrics:
            result.append("")
            result.append("## 📊 代码度量")
            result.append("")
            result.append("| 度量项 | 数值 | 描述 |")
            result.append("|--------|------|------|")
            result.append(f"| 总行数 | {metrics.get('lines_total', 0)} | HTML文档总行数 |")
            result.append(f"| 代码行数 | {metrics.get('lines_code', 0)} | 包含标签和内容的行数 |")
            result.append(f"| 注释行数 | {metrics.get('lines_comment', 0)} | HTML注释行数 |")
            result.append(f"| 空白行数 | {metrics.get('lines_blank', 0)} | 空行数量 |")
            
            # Element counts
            elements = metrics.get('elements', {})
            if elements:
                result.append("")
                result.append("### 🏷️ 元素统计")
                result.append("")
                result.append("| 元素类型 | 数量 | 说明 |")
                result.append("|----------|------|------|")
                result.append(f"| HTML元素 | {elements.get('elements', 0)} | 所有HTML标签元素 |")
                result.append(f"| 属性 | {elements.get('attributes', 0)} | HTML元素属性 |")
                result.append(f"| 文本节点 | {elements.get('text_nodes', 0)} | 文本内容节点 |")
                result.append(f"| 注释 | {elements.get('comments', 0)} | HTML注释 |")
                result.append(f"| 脚本块 | {elements.get('scripts', 0)} | `<script>` 标签数量 |")
                result.append(f"| 样式块 | {elements.get('styles', 0)} | `<style>` 标签数量 |")
                result.append(f"| 总计 | {elements.get('total', 0)} | 所有元素总数 |")

        # Elements section - organized by type
        elements_list = data.get('elements', [])
        if elements_list:
            # Group elements by type
            element_groups = {}
            for element in elements_list:
                element_type = element.get('element_type', 'unknown')
                if element_type not in element_groups:
                    element_groups[element_type] = []
                element_groups[element_type].append(element)
            
            result.append("")
            result.append("## 🏗️ HTML 结构详情")
            
            # HTML Elements (Functions)
            if 'function' in element_groups:
                result.append("")
                result.append("### 🏷️ HTML 元素 (标签)")
                result.append("")
                result.append("| 序号 | 标签名 | 位置 | 属性数 | 描述 |")
                result.append("|------|--------|------|--------|------|")
                
                for i, element in enumerate(element_groups['function'], 1):
                    name = element.get('name', 'unnamed')
                    start_line = element.get('start_line', 0)
                    end_line = element.get('end_line', 0)
                    
                    # Extract HTML-specific information
                    raw_text = element.get('raw_text', '')
                    attr_count = self._count_attributes(raw_text)
                    description = self._get_element_description(name, raw_text)
                    
                    result.append(f"| {i} | `<{name}>` | {start_line}-{end_line} | {attr_count} | {description} |")
            
            # HTML Attributes (Variables)
            if 'variable' in element_groups:
                result.append("")
                result.append("### 🏷️ HTML 属性")
                result.append("")
                result.append("| 序号 | 属性名 | 位置 | 值 | 所属元素 |")
                result.append("|------|--------|------|-----|----------|")
                
                for i, element in enumerate(element_groups['variable'], 1):
                    name = element.get('name', 'unnamed')
                    start_line = element.get('start_line', 0)
                    end_line = element.get('end_line', 0)
                    
                    # Extract attribute value and parent element
                    raw_text = element.get('raw_text', '')
                    attr_value = self._extract_attribute_value(raw_text)
                    parent_element = self._find_parent_element(element, element_groups.get('function', []))
                    
                    result.append(f"| {i} | `{name}` | {start_line}-{end_line} | `{attr_value}` | {parent_element} |")
            
            # Text Content
            text_elements = [e for e in elements_list if 'text' in e.get('name', '').lower()]
            if text_elements:
                result.append("")
                result.append("### 📝 文本内容")
                result.append("")
                result.append("| 序号 | 位置 | 长度 | 预览 |")
                result.append("|------|------|------|------|")
                
                for i, element in enumerate(text_elements, 1):
                    start_line = element.get('start_line', 0)
                    end_line = element.get('end_line', 0)
                    raw_text = element.get('raw_text', '')
                    preview = self._get_text_preview(raw_text)
                    
                    result.append(f"| {i} | {start_line}-{end_line} | {len(raw_text)} | {preview} |")
            
            # Comments (Imports)
            if 'import' in element_groups:
                result.append("")
                result.append("### 💬 HTML 注释")
                result.append("")
                result.append("| 序号 | 位置 | 内容 |")
                result.append("|------|------|------|")
                
                for i, element in enumerate(element_groups['import'], 1):
                    start_line = element.get('start_line', 0)
                    end_line = element.get('end_line', 0)
                    raw_text = element.get('raw_text', '')
                    comment_content = self._extract_comment_content(raw_text)
                    
                    result.append(f"| {i} | {start_line}-{end_line} | {comment_content} |")
            
            # Embedded Scripts/Styles (Classes)
            if 'class' in element_groups:
                result.append("")
                result.append("### 📜 嵌入内容 (脚本/样式)")
                result.append("")
                result.append("| 序号 | 类型 | 位置 | 大小 | 描述 |")
                result.append("|------|------|------|------|------|")
                
                for i, element in enumerate(element_groups['class'], 1):
                    name = element.get('name', 'unnamed')
                    start_line = element.get('start_line', 0)
                    end_line = element.get('end_line', 0)
                    raw_text = element.get('raw_text', '')
                    
                    content_type = 'JavaScript' if 'script' in name.lower() else 'CSS' if 'style' in name.lower() else '未知'
                    content_size = len(raw_text)
                    description = self._get_embedded_content_description(raw_text, content_type)
                    
                    result.append(f"| {i} | {content_type} | {start_line}-{end_line} | {content_size}字符 | {description} |")

        # Analysis summary
        if elements_list:
            result.append("")
            result.append("## 📋 分析摘要")
            result.append("")
            
            # Element type distribution
            type_counts = {}
            for element in elements_list:
                element_type = element.get('element_type', 'unknown')
                type_counts[element_type] = type_counts.get(element_type, 0) + 1
            
            result.append("### 元素类型分布")
            result.append("")
            for element_type, count in type_counts.items():
                type_name = self._get_element_type_name(element_type)
                result.append(f"- **{type_name}**: {count}个")
            
            # HTML structure insights
            result.append("")
            result.append("### 结构特征")
            result.append("")
            
            # Check for common HTML patterns
            html_elements = element_groups.get('function', [])
            semantic_count = sum(1 for e in html_elements if e.get('name', '').lower() in 
                               ['header', 'footer', 'main', 'section', 'article', 'aside', 'nav'])
            form_count = sum(1 for e in html_elements if e.get('name', '').lower() in 
                           ['form', 'input', 'textarea', 'select', 'button'])
            media_count = sum(1 for e in html_elements if e.get('name', '').lower() in 
                            ['img', 'video', 'audio', 'picture', 'source'])
            
            if semantic_count > 0:
                result.append(f"- 🏗️ **语义化结构**: 使用了{semantic_count}个语义化标签，结构清晰")
            if form_count > 0:
                result.append(f"- 📝 **交互表单**: 包含{form_count}个表单相关元素")
            if media_count > 0:
                result.append(f"- 🎬 **多媒体内容**: 包含{media_count}个媒体元素")
            
            # Check for accessibility features
            attributes = element_groups.get('variable', [])
            alt_attrs = sum(1 for a in attributes if a.get('name', '') == 'alt')
            aria_attrs = sum(1 for a in attributes if a.get('name', '').startswith('aria-'))
            role_attrs = sum(1 for a in attributes if a.get('name', '') == 'role')
            
            if alt_attrs > 0 or aria_attrs > 0 or role_attrs > 0:
                result.append("")
                result.append("### 无障碍特征")
                result.append("")
                if alt_attrs > 0:
                    result.append(f"- ♿ **替代文本**: {alt_attrs}个alt属性")
                if aria_attrs > 0:
                    result.append(f"- ♿ **ARIA标签**: {aria_attrs}个ARIA属性")
                if role_attrs > 0:
                    result.append(f"- ♿ **角色定义**: {role_attrs}个role属性")

        return "\n".join(result)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for HTML"""
        if data is None:
            return "# No data available\n"
        
        result = []
        result.append("# HTML 结构概览")
        result.append("")
        
        # File and metrics info
        metrics = data.get('metrics', {})
        elements = metrics.get('elements', {})
        
        result.append("| 项目 | 值 |")
        result.append("|------|-----|")
        result.append(f"| 文件 | `{data.get('file_path', 'N/A')}` |")
        result.append(f"| 总行数 | {metrics.get('lines_total', 0)} |")
        result.append(f"| HTML元素 | {elements.get('elements', 0)} |")
        result.append(f"| 属性 | {elements.get('attributes', 0)} |")
        result.append(f"| 注释 | {elements.get('comments', 0)} |")
        
        # Top-level elements
        elements_list = data.get('elements', [])
        html_elements = [e for e in elements_list if e.get('element_type') == 'function']
        
        if html_elements:
            result.append("")
            result.append("## 主要元素")
            result.append("")
            result.append("| 标签 | 位置 | 属性数 |")
            result.append("|------|------|--------|")
            
            for element in html_elements[:10]:  # Show top 10
                name = element.get('name', 'unnamed')
                start_line = element.get('start_line', 0)
                raw_text = element.get('raw_text', '')
                attr_count = self._count_attributes(raw_text)
                
                result.append(f"| `<{name}>` | {start_line} | {attr_count} |")
            
            if len(html_elements) > 10:
                result.append(f"| ... | ... | ... |")
                result.append(f"| *共{len(html_elements)}个元素* | | |")
        
        return "\n".join(result)

    def _format_csv_table(self, data: dict[str, Any]) -> str:
        """CSV format for HTML elements"""
        if data is None:
            return "# No data available\n"
        
        result = []
        result.append("# HTML 元素 CSV 格式")
        result.append("")
        result.append("```csv")
        result.append("序号,元素类型,名称,开始行,结束行,属性数,描述")
        
        elements_list = data.get('elements', [])
        for i, element in enumerate(elements_list, 1):
            element_type = element.get('element_type', 'unknown')
            name = element.get('name', 'unnamed')
            start_line = element.get('start_line', 0)
            end_line = element.get('end_line', 0)
            
            raw_text = element.get('raw_text', '')
            if element_type == 'function':  # HTML elements
                attr_count = self._count_attributes(raw_text)
                description = self._get_element_description(name, raw_text)
                result.append(f"{i},HTML元素,{name},{start_line},{end_line},{attr_count},{description}")
            elif element_type == 'variable':  # Attributes
                attr_value = self._extract_attribute_value(raw_text)
                result.append(f"{i},属性,{name},{start_line},{end_line},0,值: {attr_value}")
            elif element_type == 'import':  # Comments
                comment_content = self._extract_comment_content(raw_text)
                result.append(f"{i},注释,{name},{start_line},{end_line},0,{comment_content}")
            else:
                result.append(f"{i},{element_type},{name},{start_line},{end_line},0,其他")
        
        result.append("```")
        return "\n".join(result)

    # Helper methods for HTML-specific processing
    
    def _count_attributes(self, raw_text: str) -> int:
        """Count number of attributes in HTML element"""
        if not raw_text or '<' not in raw_text:
            return 0
        
        # Simple attribute counting - count = signs
        return raw_text.count('=')

    def _get_element_description(self, tag_name: str, raw_text: str) -> str:
        """Get description for HTML element"""
        descriptions = {
            'html': 'HTML根元素',
            'head': '文档头部',
            'body': '文档主体',
            'title': '页面标题',
            'meta': '元数据',
            'link': '外部资源链接',
            'script': 'JavaScript脚本',
            'style': 'CSS样式',
            'div': '通用容器',
            'span': '内联容器',
            'p': '段落',
            'h1': '一级标题',
            'h2': '二级标题',
            'h3': '三级标题',
            'h4': '四级标题',
            'h5': '五级标题',
            'h6': '六级标题',
            'a': '链接',
            'img': '图片',
            'form': '表单',
            'input': '输入框',
            'button': '按钮',
            'table': '表格',
            'ul': '无序列表',
            'ol': '有序列表',
            'li': '列表项',
            'header': '页面头部',
            'footer': '页面底部',
            'main': '主要内容',
            'section': '章节',
            'article': '文章',
            'aside': '侧边栏',
            'nav': '导航',
        }
        
        description = descriptions.get(tag_name.lower(), '自定义元素')
        
        # Add self-closing indicator
        if raw_text and raw_text.strip().endswith('/>'):
            description += ' (自闭合)'
        
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

    def _find_parent_element(self, attribute, html_elements) -> str:
        """Find parent element for attribute"""
        attr_line = attribute.get('start_line', 0)
        
        # Find element that contains this attribute
        for element in html_elements:
            elem_start = element.get('start_line', 0)
            elem_end = element.get('end_line', 0)
            
            if elem_start <= attr_line <= elem_end:
                return f"`<{element.get('name', 'unknown')}>`"
        
        return '未知元素'

    def _get_text_preview(self, text: str, max_length: int = 50) -> str:
        """Get preview of text content"""
        if not text:
            return '空'
        
        # Clean up whitespace
        cleaned = ' '.join(text.split())
        
        if len(cleaned) <= max_length:
            return f'"{cleaned}"'
        
        return f'"{cleaned[:max_length]}..."'

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

    def _get_embedded_content_description(self, raw_text: str, content_type: str) -> str:
        """Get description for embedded script/style content"""
        if not raw_text:
            return '空内容'
        
        if content_type == 'JavaScript':
            if 'function' in raw_text:
                func_count = raw_text.count('function')
                return f'包含{func_count}个函数'
            elif 'console.log' in raw_text:
                return '调试代码'
            elif 'addEventListener' in raw_text:
                return '事件处理代码'
            else:
                return 'JavaScript代码'
        elif content_type == 'CSS':
            if '{' in raw_text:
                rule_count = raw_text.count('{')
                return f'包含{rule_count}个样式规则'
            else:
                return 'CSS样式代码'
        
        return f'{content_type}代码'

    def _get_element_type_name(self, element_type: str) -> str:
        """Get Chinese name for element type"""
        type_names = {
            'function': 'HTML元素',
            'variable': '属性',
            'import': '注释',
            'class': '嵌入内容',
            'package': '文档信息',
            'unknown': '未知'
        }
        return type_names.get(element_type, element_type)