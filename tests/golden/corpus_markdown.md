---
title: "Tree-Sitter Grammar Coverage Guide"
version: "1.0.0"
author: "Grammar Test Suite"
tags: [testing, markdown, tree-sitter, coverage]
draft: false
---

# Tree-Sitter Markdown Grammar Coverage

This document exercises every named node type in the tree-sitter-markdown grammar.
It is structured as a realistic technical reference guide covering Markdown features,
parsers, and formatting conventions.

---

## Table of Contents

- [Introduction](#introduction)
- [Headings](#headings)
- [Paragraphs and Inline Content](#paragraphs-and-inline-content)
- [Code Blocks](#code-blocks)
- [Lists](#lists)
- [Block Quotes](#block-quotes)
- [Tables](#tables)
- [Links and References](#links-and-references)
- [HTML Blocks](#html-blocks)
- [Special Characters](#special-characters)
- [Thematic Breaks](#thematic-breaks)

---

## Introduction

Tree-sitter is a parser generator tool and incremental parsing library. It can build
a concrete syntax tree for a source file and efficiently update the syntax tree as the
source file is edited. It supports backslash escapes like \* and \# in inline content,
as well as HTML entity references such as &amp;, &copy;, &lt;, and &gt;.

Numeric character references are also supported: &#169; is the copyright symbol,
&#8212; is an em dash, and &#x2603; is a snowman using hexadecimal notation.

***

## Headings

Tree-sitter-markdown supports both ATX-style and setext-style headings.

### ATX Headings

ATX headings use hash markers at the start of the line:

#### Fourth Level Heading

##### Fifth Level Heading

###### Sixth Level Heading

ATX headings may include inline content with special characters. Use \[ to escape
brackets, or reference entities like &mdash; for typographic dashes.

### Setext Headings

Setext First Level
==================

Setext Second Level
-------------------

Setext headings underline the text with `=` or `-` characters. They only support
levels 1 and 2.

___

## Paragraphs and Inline Content

Paragraphs are sequences of non-blank lines that do not begin with special block
markers. They may contain any inline content including backslash escapes and
character references.

A paragraph can span multiple lines as long as there is no blank line between them.
This is still the same paragraph because there is no blank break above. Inline
content includes emphasis, links, code spans, and raw HTML, along with entity
references like &nbsp; and &hellip; for typographic purposes.

Use backslash escapes to include literal punctuation: \* \_ \` \\ \[ \] \( \) \{ \}
\# \+ \- \. \! \< \> These are all valid escape sequences in CommonMark.

---

## Code Blocks

Code blocks come in two forms: fenced and indented.

### Fenced Code Blocks

Fenced code blocks begin and end with a delimiter of three or more backticks or tildes,
and may include an info string specifying the language.

```python
def parse_document(source: str) -> Node:
    """Parse a Markdown document and return the root node."""
    parser = Parser()
    parser.set_language(MARKDOWN)
    tree = parser.parse(bytes(source, "utf8"))
    return tree.root_node
```

```javascript
// Traverse a tree-sitter syntax tree
function traverse(node, depth = 0) {
    const indent = "  ".repeat(depth);
    console.log(`${indent}${node.type} [${node.startIndex}, ${node.endIndex}]`);
    for (const child of node.children) {
        traverse(child, depth + 1);
    }
}
```

```bash
#!/usr/bin/env bash
# Run tree-sitter tests
tree-sitter generate
tree-sitter test --filter "markdown"
tree-sitter highlight --scope text.md corpus_markdown.md
```

```json
{
  "name": "tree-sitter-markdown",
  "version": "0.7.0",
  "dependencies": {
    "tree-sitter": "^0.20.0"
  }
}
```

Fenced code blocks without a language specifier are also valid:

```
This is a plain fenced code block.
No language info string is required.
The parser treats content as literal text.
```

### Indented Code Blocks

An indented code block is created by indenting every line by four or more spaces:

    // Indented code block example
    function greet(name) {
        return "Hello, " + name + "!";
    }
    greet("World");

    # Another indented code segment
    result = 42 * (a + b)

Indented code blocks do not support info strings and are terminated by a blank line
or a line with less indentation.

***

## Lists

### Unordered Lists

Unordered lists can use three different markers: minus, star, or plus.

Minus markers:

- First item using minus marker
- Second item with continuation
- Third item containing inline content with &amp; entity

Star markers:

* Alpha item using star marker
* Beta item in the list
* Gamma item closing the list

Plus markers:

+ Red item using plus marker
+ Green item in the list
+ Blue item closing the list

### Ordered Lists

Ordered lists support both dot and parenthesis delimiters:

Dot notation:

1. First step: install dependencies
2. Second step: configure the parser
3. Third step: run the test suite
4. Fourth step: review the output

Parenthesis notation:

1) Clone the repository
2) Install Node.js dependencies
3) Build the native module
4) Run integration tests

### Nested Lists

- Top-level item A
  - Nested item under A
  - Another nested item
    - Deeply nested item
- Top-level item B
  1. Ordered sub-item one
  2. Ordered sub-item two
- Top-level item C

### Task Lists

Task lists use checked and unchecked markers:

- [x] Install tree-sitter CLI
- [x] Generate the grammar
- [x] Write unit tests
- [ ] Add CI/CD pipeline
- [ ] Publish to npm registry
- [ ] Write comprehensive documentation

Mixed task list with other list items:

* [x] Completed feature: fenced code block parsing
* [x] Completed feature: ATX heading detection
* [ ] Pending feature: extended table alignment
* [ ] Pending feature: footnote support

---

## Block Quotes

Block quotes prefix lines with the `>` marker.

### Simple Block Quote

> This is a simple block quote. It contains a single paragraph of text.
> The content continues on the next line, still within the same quote block.
> Block quotes can contain any block-level content.

### Block Quote with Nested Content

> ## Heading Inside a Block Quote
>
> Block quotes can contain other block elements including headings,
> lists, and even nested block quotes.
>
> - List item inside a block quote
> - Another item with inline content
>
> ```python
> # Code block inside a block quote
> x = tree.root_node
> ```

### Nested Block Quotes

> Outer block quote begins here.
> This is still in the outer quote.
>
> > Inner nested block quote.
> > This is one level deeper.
> >
> > > Doubly nested block quote at the third level.
> > > Tree-sitter handles these with block_continuation nodes.
> >
> > Back to the second level.
>
> Back to the outer level.

### Block Quote with Continuation

> First line of the block quote establishes context.
> Second line continues with more information.
> Third line rounds out the thought.

---

## Tables

Pipe tables support alignment through the delimiter row.

### Basic Table with Alignment

| Feature                  | Status    | Priority |
|:-------------------------|:----------|:---------|
| ATX headings             | Complete  | High     |
| Setext headings          | Complete  | High     |
| Fenced code blocks       | Complete  | High     |
| Indented code blocks     | Complete  | Medium   |
| Unordered lists          | Complete  | High     |
| Ordered lists            | Complete  | High     |
| Task lists               | Complete  | Medium   |
| Block quotes             | Complete  | High     |
| Pipe tables              | Complete  | Medium   |
| Link references          | Complete  | Low      |

### Table with Right Alignment

| Node Type                  |   Count | Coverage |
|:---------------------------|--------:|---------:|
| atx_heading                |       7 |     100% |
| setext_heading             |       2 |     100% |
| fenced_code_block          |       6 |     100% |
| indented_code_block        |       2 |     100% |
| list                       |       8 |     100% |
| block_quote                |       4 |     100% |
| pipe_table                 |       3 |     100% |
| thematic_break             |       5 |     100% |
| html_block                 |       2 |     100% |
| link_reference_definition  |       4 |     100% |

### Mixed Alignment Table

| Left Column          | Center Text          |      Right Value |
|:---------------------|:--------------------:|-----------------:|
| Alpha                | Description of alpha |              1.0 |
| Beta                 | Description of beta  |             42.5 |
| Gamma                | Description of gamma |          1024.00 |
| Delta                | Description of delta |         65536.00 |

---

## Links and References

### Link Reference Definitions

Link reference definitions associate labels with URLs and optional titles.

[tree-sitter]: https://tree-sitter.github.io/tree-sitter/ "Tree-sitter Homepage"
[grammar-guide]: https://tree-sitter.github.io/tree-sitter/creating-parsers "Creating Parsers Guide"
[node-types]: https://tree-sitter.github.io/tree-sitter/using-parsers#named-vs-anonymous-nodes "Named vs Anonymous Nodes"
[markdown-spec]: https://spec.commonmark.org/ "CommonMark Specification"

These definitions can be referenced elsewhere in the document using `[label]` syntax.
For example, visit [tree-sitter] for the official documentation, or read the
[grammar-guide] for information on creating new grammars.

The [markdown-spec] provides the formal specification for CommonMark, which is the
basis for many Markdown parsers including this one. Consult [node-types] for details
on how tree-sitter distinguishes named from anonymous nodes.

---

## HTML Blocks

Raw HTML blocks are passed through the parser without interpretation.

<div class="note">
  <p>This is an HTML block embedded in a Markdown document.</p>
  <p>Tree-sitter preserves it as an <code>html_block</code> node.</p>
</div>

<table>
  <thead>
    <tr>
      <th>HTML Column A</th>
      <th>HTML Column B</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Row 1, Cell A</td>
      <td>Row 1, Cell B</td>
    </tr>
    <tr>
      <td>Row 2, Cell A</td>
      <td>Row 2, Cell B</td>
    </tr>
  </tbody>
</table>

After an HTML block, normal Markdown processing resumes. The parser correctly
identifies the boundary between `html_block` nodes and regular `paragraph` nodes.

<!-- This is an HTML comment block. It is invisible in rendered output. -->

---

## Special Characters

### Backslash Escapes

The following characters can be escaped with a backslash to prevent special
treatment by the Markdown parser:

- \* asterisk (would start emphasis or list)
- \_ underscore (would start emphasis)
- \` backtick (would start code span)
- \\ backslash (literal backslash)
- \[ open bracket (would start link)
- \] close bracket (would end link)
- \( open paren (would start link destination)
- \) close paren (would end link destination)
- \# hash (would start ATX heading)
- \+ plus (would start list item)
- \- minus (would start list item or setext underline)
- \. period (used in ordered list markers like 1\.)
- \! exclamation (would start image link)
- \< less-than (would start HTML tag or autolink)
- \> greater-than (would start block quote)

### HTML Entity References

Named entity references include common symbols:

- Copyright symbol: &copy;
- Registered trademark: &reg;
- Trademark: &trade;
- Ampersand literal: &amp;
- Less-than literal: &lt;
- Greater-than literal: &gt;
- Non-breaking space: &nbsp; between words
- Em dash: &mdash; used in prose
- En dash: &ndash; used in ranges
- Left double quote: &ldquo;quoted text&rdquo;
- Ellipsis: &hellip; at the end of a thought
- Section sign: &sect; 4.2 of the specification
- Degree symbol: 90&deg; rotation

### Numeric Character References

Decimal character references:

- &#169; copyright (decimal 169)
- &#174; registered trademark (decimal 174)
- &#8212; em dash (decimal 8212)
- &#8211; en dash (decimal 8211)
- &#8220; left double quotation mark
- &#8221; right double quotation mark
- &#9733; black star symbol

Hexadecimal character references:

- &#x00A9; copyright (hex A9)
- &#x2014; em dash (hex 2014)
- &#x2603; snowman (hex 2603)
- &#x1F600; grinning face emoji (hex 1F600)
- &#x0041; capital letter A (hex 41)

---

## Thematic Breaks

Thematic breaks are horizontal rules that separate content visually and structurally.

A thematic break using dashes (three or more):

---

A thematic break using asterisks:

***

A thematic break using underscores:

___

Multiple thematic breaks can appear in the document. They produce `thematic_break`
nodes in the syntax tree and are distinct from setext heading underlines, which are
`setext_h1_underline` or `setext_h2_underline` nodes that immediately follow text.

---

## Summary

This document has exercised the following tree-sitter-markdown node types:

| Node Type                      | Location in Document              |
|:-------------------------------|:----------------------------------|
| `document`                     | Entire file (root node)           |
| `section`                      | Implicit structural grouping      |
| `minus_metadata`               | YAML front matter at top          |
| `atx_h1_marker`                | `#` in ATX headings               |
| `atx_h2_marker`                | `##` in ATX headings              |
| `atx_h3_marker`                | `###` in ATX headings             |
| `atx_h4_marker`                | `####` in ATX headings            |
| `atx_h5_marker`                | `#####` in ATX headings           |
| `atx_h6_marker`                | `######` in ATX headings          |
| `atx_heading`                  | All `#`-prefixed headings         |
| `setext_heading`               | Underlined headings               |
| `setext_h1_underline`          | `===` underlines                  |
| `setext_h2_underline`          | `---` underlines                  |
| `paragraph`                    | Body text throughout              |
| `inline`                       | Content inside paragraphs         |
| `fenced_code_block`            | Backtick code blocks              |
| `fenced_code_block_delimiter`  | Opening/closing ` ``` `           |
| `code_fence_content`           | Code inside fenced blocks         |
| `info_string`                  | Language after ` ``` `            |
| `language`                     | `python`, `bash`, `javascript`    |
| `indented_code_block`          | Four-space indented code          |
| `list`                         | All list containers               |
| `list_item`                    | Individual list entries           |
| `list_marker_minus`            | `-` unordered markers             |
| `list_marker_star`             | `*` unordered markers             |
| `list_marker_plus`             | `+` unordered markers             |
| `list_marker_dot`              | `1.` ordered markers              |
| `list_marker_parenthesis`      | `1)` ordered markers              |
| `task_list_marker_checked`     | `[x]` checked tasks               |
| `task_list_marker_unchecked`   | `[ ]` unchecked tasks             |
| `block_quote`                  | `>` quoted blocks                 |
| `block_quote_marker`           | `>` prefix character              |
| `block_continuation`           | Continuation in block quotes      |
| `pipe_table`                   | All pipe-delimited tables         |
| `pipe_table_header`            | First row of tables               |
| `pipe_table_delimiter_row`     | Separator row with `---`          |
| `pipe_table_delimiter_cell`    | Each cell in delimiter row        |
| `pipe_table_align_left`        | `:---` alignment                  |
| `pipe_table_align_right`       | `---:` alignment                  |
| `pipe_table_row`               | Data rows in tables               |
| `pipe_table_cell`              | Individual table cells            |
| `link_reference_definition`    | `[label]: url "title"` lines      |
| `link_label`                   | `[tree-sitter]` labels            |
| `link_destination`             | URL in reference definition       |
| `link_title`                   | `"title"` in reference definition |
| `html_block`                   | Raw HTML sections                 |
| `thematic_break`               | `---`, `***`, `___` rules         |
| `backslash_escape`             | `\*`, `\_`, `\#`, etc.            |
| `entity_reference`             | `&amp;`, `&copy;`, `&mdash;`      |
| `numeric_character_reference`  | `&#169;`, `&#x2603;`, etc.        |

[tree-sitter]: https://tree-sitter.github.io/tree-sitter/ "Tree-sitter Homepage"
[grammar-guide]: https://tree-sitter.github.io/tree-sitter/creating-parsers "Creating Parsers Guide"
[node-types]: https://tree-sitter.github.io/tree-sitter/using-parsers#named-vs-anonymous-nodes "Named vs Anonymous Nodes"
[markdown-spec]: https://spec.commonmark.org/ "CommonMark Specification"
