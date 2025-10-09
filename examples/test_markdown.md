# Comprehensive Markdown Test Document

This document contains various Markdown elements for testing the tree-sitter-analyzer.

## Headers

### Level 3 Header
#### Level 4 Header
##### Level 5 Header
###### Level 6 Header

## Text Formatting

This paragraph contains **bold text**, *italic text*, ***bold and italic***, and `inline code`.

You can also use ~~strikethrough~~ text.

## Links

Here are different types of links:

- [Inline link](https://example.com)
- [Link with title](https://example.com "Example Website")
- [Reference link][ref1]
- <https://autolink.example.com>
- <mailto:test@example.com>

[ref1]: https://reference.example.com "Reference Link"

## Images

![Alt text](image.png)
![Image with title](image.png "Image Title")
![Reference image][img1]

[img1]: reference-image.png "Reference Image"

## Lists

### Unordered Lists
- Item 1
- Item 2
  - Nested item 2.1
  - Nested item 2.2
- Item 3

### Ordered Lists
1. First item
2. Second item
   1. Nested item 2.1
   2. Nested item 2.2
3. Third item

### Task Lists
- [x] Completed task
- [ ] Incomplete task
- [x] Another completed task

## Code Blocks

### Fenced Code Block with Language
```python
def hello_world():
    print("Hello, World!")
    return True

class Example:
    def __init__(self):
        self.value = 42
```

### Fenced Code Block without Language
```
This is a code block
without language specification
```

### Indented Code Block

    This is an indented code block
    It uses 4 spaces for indentation
    def example():
        return "indented"

## Blockquotes

> This is a blockquote.
> It can span multiple lines.
>
> > This is a nested blockquote.

## Tables

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Row 1    | Data 1   | Value 1  |
| Row 2    | Data 2   | Value 2  |
| Row 3    | Data 3   | Value 3  |

## Horizontal Rules

---

***

___

## HTML Elements

<div>This is an HTML div element</div>

<p>HTML paragraph with <strong>strong</strong> and <em>emphasis</em></p>

<!-- This is an HTML comment -->

## Special Characters and Escaping

Here are some special characters: \* \_ \` \# \[ \] \( \) \\ \!

## Line Breaks

This line ends with two spaces  
And this creates a line break.

This paragraph has a hard line break.

## Footnotes

Here's a sentence with a footnote[^1].

[^1]: This is the footnote content.

## Definition Lists

Term 1
:   Definition 1

Term 2
:   Definition 2a
:   Definition 2b

## Abbreviations

*[HTML]: Hyper Text Markup Language
*[W3C]: World Wide Web Consortium

The HTML specification is maintained by the W3C.

## Math (if supported)

Inline math: $E = mc^2$

Block math:
$$
\sum_{i=1}^{n} x_i = x_1 + x_2 + \cdots + x_n
$$

## Conclusion

This document demonstrates various Markdown features for comprehensive testing.