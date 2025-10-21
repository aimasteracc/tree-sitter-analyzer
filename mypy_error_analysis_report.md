
# tree-sitter-analyzer フェーズ4: 残存mypyエラー詳細分析レポート

## 概要
- **総エラー数**: 100個
- **影響ファイル数**: 16個
- **分析日時**: 2025-10-21 18:24:42

## エラー優先度別分析

### UNKNOWN優先度 (100個)
- **影響ファイル**: javascript_plugin.py, markdown_plugin.py, table_command.py, advanced_command.py, typescript_plugin.py, java_plugin.py, search_content_tool.py, api.py, python_plugin.py, css_plugin.py, table_format_tool.py, list_files_tool.py, server.py, validator.py, query_command.py, html_plugin.py
- **主要エラーコード**: unknown(100)

## ファイル別エラー詳細分析

### markdown_plugin.py (52個)
- **優先度別**: UNKNOWN(52)
- **エラーコード別**: unknown(52)

### server.py (10個)
- **優先度別**: UNKNOWN(10)
- **エラーコード別**: unknown(10)

### javascript_plugin.py (9個)
- **優先度別**: UNKNOWN(9)
- **エラーコード別**: unknown(9)

### python_plugin.py (6個)
- **優先度別**: UNKNOWN(6)
- **エラーコード別**: unknown(6)

### list_files_tool.py (3個)
- **優先度別**: UNKNOWN(3)
- **エラーコード別**: unknown(3)

### css_plugin.py (3個)
- **優先度別**: UNKNOWN(3)
- **エラーコード別**: unknown(3)

### java_plugin.py (3個)
- **優先度別**: UNKNOWN(3)
- **エラーコード別**: unknown(3)

### table_format_tool.py (2個)
- **優先度別**: UNKNOWN(2)
- **エラーコード別**: unknown(2)

### search_content_tool.py (2個)
- **優先度別**: UNKNOWN(2)
- **エラーコード別**: unknown(2)

### api.py (2個)
- **優先度別**: UNKNOWN(2)
- **エラーコード別**: unknown(2)

## 根本原因分析

### MarkdownPluginの型階層問題 (52個)
- **主要問題**:
  - ElementExtractorの継承関係の不整合
  - MarkdownElementとCodeElementの型不整合
  - メソッドシグネチャの不一致

### 属性未定義エラー (0個)
- **主要問題**:
  - ElementExtractorに存在しないメソッドの呼び出し
  - オブジェクトの属性アクセスエラー

### 型注釈不足 (0個)
- **主要問題**:
  - 変数の型注釈不足
  - 関数の型注釈不足

### 到達不能コード (0個)
- **主要問題**:
  - return文後のコード
  - 条件分岐の論理エラー

## フェーズ別修正戦略

### PHASE 5
- **目標**: CRITICAL優先度エラーの修正
- **対象エラー数**: 0個
- **推定工数**: HIGH
- **重点領域**:
  - markdown_plugin.pyの型階層修正
  - 属性未定義エラーの解決

### PHASE 6
- **目標**: HIGH優先度エラーの修正
- **対象エラー数**: 0個
- **推定工数**: MEDIUM
- **重点領域**:
  - メソッドオーバーライドの修正
  - 戻り値型の整合性確保

### PHASE 7
- **目標**: MEDIUM優先度エラーの修正
- **対象エラー数**: 0個
- **推定工数**: MEDIUM
- **重点領域**:
  - 型不整合の解決
  - 引数型の修正

### PHASE 8
- **目標**: LOW優先度エラーの修正
- **対象エラー数**: 0個
- **推定工数**: LOW
- **重点領域**:
  - 到達不能コードの除去
  - 型注釈の追加

### PHASE 9
- **目標**: 最終検証とクリーンアップ
- **対象エラー数**: 100個
- **推定工数**: LOW
- **重点領域**:
  - 残存エラーの確認
  - テスト実行と検証

## 詳細エラーリスト


### UNKNOWN優先度エラー

#### advanced_command.py:114:47 [unknown]
```
Right
```
- operand of "and" is never evaluated  [unreachable]
- elif in_multiline_comment and "-->" in stripped:
- ^~~~~~~~~~~~~~~~~

#### advanced_command.py:115:21 [unknown]
```
Statement
```
- is unreachable  [unreachable]
- comment_lines += 1
- ^~~~~~~~~~~~~~~~~~

#### api.py:148:17 [unknown]
```
"object" has no attribute "append" 
```
- [attr-defined]
- result["elements"].append(elem_dict)
- ^~~~~~~~~~~~~~~~~~~~~~~~~

#### api.py:282:17 [unknown]
```
"object" has no attribute "append" 
```
- [attr-defined]
- result["elements"].append(elem_dict)
- ^~~~~~~~~~~~~~~~~~~~~~~~~

#### css_plugin.py:103:9 [unknown]
```
Need type annotation
```
- for "elements" (hint: "elements: list[<type>] = ...")  [var-annotated]
- elements = []
- ^~~~~~~~

#### css_plugin.py:299:50 [unknown]
```
Argument "key" to
```
- "max" has incompatible type overloaded function; expected
- "Callable[[str], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
- best_category = max(category_scores, key=category_scores.get)
- ^~~~~~~~~~~~~~~~~~~

#### css_plugin.py:388:28 [unknown]
```
"ElementExtractor"
```
- has no attribute "extract_css_rules"; maybe "extract_classes"?  [attr-defined]
- elements = extractor.extract_css_rules(tree, content)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### html_plugin.py:429:28 [unknown]
```
"ElementExtractor"
```
- has no attribute "extract_html_elements"; maybe "extract_all_elements"?
- [attr-defined]
- elements = extractor.extract_html_elements(tree, conte...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### java_plugin.py:262:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- log_debug("Tree or root_node is None, returning empty pack...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~...
- "type: ignore" comment  [unused-ignore]
- elements.extend(self.extract_functions(tree, source_code))...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~...

#### java_plugin.py:262:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- log_debug("Tree or root_node is None, returning empty pack...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~...
- "type: ignore" comment  [unused-ignore]
- elements.extend(self.extract_functions(tree, source_code))...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~...

#### java_plugin.py:1394:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return {
- ^

#### javascript_plugin.py:215:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return
- ^~~~~~

#### javascript_plugin.py:940:20 [unknown]
```
Unexpected
```
- keyword argument "import_type" for "Import"  [call-arg]
- return Import(
- ^

#### javascript_plugin.py:940:20 [unknown]
```
Unexpected
```
- keyword argument "is_default" for "Import"  [call-arg]
- return Import(
- ^

#### javascript_plugin.py:940:20 [unknown]
```
Unexpected
```
- keyword argument "is_namespace" for "Import"  [call-arg]
- return Import(
- ^

#### javascript_plugin.py:940:20 [unknown]
```
Unexpected
```
- keyword argument "is_dynamic" for "Import"  [call-arg]
- return Import(
- ^

#### javascript_plugin.py:1222:29 [unknown]
```
Argument 1
```
- to "extend" of "list" has incompatible type "list[Class]"; expected
- "Iterable[Function]"  [arg-type]
- elements.extend(self.extract_classes(tree, source_code))
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### javascript_plugin.py:1223:29 [unknown]
```
Argument 1
```
- to "extend" of "list" has incompatible type "list[Variable]"; expected
- "Iterable[Function]"  [arg-type]
- elements.extend(self.extract_variables(tree, source_code))
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### javascript_plugin.py:1224:29 [unknown]
```
Argument 1
```
- to "extend" of "list" has incompatible type "list[Import]"; expected
- "Iterable[Function]"  [arg-type]
- elements.extend(self.extract_imports(tree, source_code))
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### javascript_plugin.py:1445:5 [unknown]
```
Function is
```
- missing a type annotation for one or more arguments  [no-untyped-def]
- def _get_node_type_for_element(self, element) -> str:
- ^

#### list_files_tool.py:353:9 [unknown]
```
Name "result"
```
- already defined on line 265  [no-redef]
- result: dict[str, Any] = {
- ^~~~~~

#### list_files_tool.py:399:41 [unknown]
```
Incompatible
```
- types in assignment (expression has type "str", target has type "int")
- [assignment]
- result["output_file"] = saved_path
- ^~~~~~~~~~

#### list_files_tool.py:411:47 [unknown]
```
Incompatible
```
- types in assignment (expression has type "str", target has type "int")
- [assignment]
- result["output_file_error"] = str(e)
- ^~~~~~

#### markdown_plugin.py:91:5 [unknown]
```
Return type
```
- "list[CodeElement]" of "extract_functions" incompatible with return type
- "list[Function]" in supertype
- "tree_sitter_analyzer.plugins.base.ElementExtractor"  [override]
- def extract_functions(
- ^

#### markdown_plugin.py:95:16 [unknown]
```
Incompatible
```
- return value type (got "list[MarkdownElement]", expected "list[CodeElement]")
- [return-value]
- return self.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:97:5 [unknown]
```
Return type
```
- "list[CodeElement]" of "extract_classes" incompatible with return type
- "list[Class]" in supertype "tree_sitter_analyzer.plugins.base.ElementExtractor"
- [override]
- def extract_classes(
- ^

#### markdown_plugin.py:101:16 [unknown]
```
Incompatible
```
- return value type (got "list[MarkdownElement]", expected "list[CodeElement]")
- [return-value]
- return self.extract_code_blocks(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:103:5 [unknown]
```
Return type
```
- "list[CodeElement]" of "extract_variables" incompatible with return type
- "list[Variable]" in supertype
- "tree_sitter_analyzer.plugins.base.ElementExtractor"  [override]
- def extract_variables(
- ^

#### markdown_plugin.py:110:16 [unknown]
```
Incompatible
```
- return value type (got "list[MarkdownElement]", expected "list[CodeElement]")
- [return-value]
- return elements
- ^~~~~~~~

#### markdown_plugin.py:112:5 [unknown]
```
Return type
```
- "list[CodeElement]" of "extract_imports" incompatible with return type
- "list[Import]" in supertype "tree_sitter_analyzer.plugins.base.ElementExtractor"
- [override]
- def extract_imports(
- ^

#### markdown_plugin.py:116:16 [unknown]
```
Incompatible
```
- return value type (got "list[MarkdownElement]", expected "list[CodeElement]")
- [return-value]
- return self.extract_references(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:129:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return headers
- ^~~~~~~~~~~~~~

#### markdown_plugin.py:154:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return code_blocks
- ^~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:177:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return links
- ^~~~~~~~~~~~

#### markdown_plugin.py:220:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return images
- ^~~~~~~~~~~~~

#### markdown_plugin.py:255:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return references
- ^~~~~~~~~~~~~~~~~

#### markdown_plugin.py:277:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return blockquotes
- ^~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:299:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return horizontal_rules
- ^~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:321:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return html_elements
- ^~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:344:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return formatting_elements
- ^~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:368:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return footnotes
- ^~~~~~~~~~~~~~~~

#### markdown_plugin.py:390:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return lists
- ^~~~~~~~~~~~

#### markdown_plugin.py:412:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return tables
- ^~~~~~~~~~~~~

#### markdown_plugin.py:929:29 [unknown]
```
Incompatible
```
- types in assignment (expression has type "Match[str] | None", variable has type
- "Match[str]")  [assignment]
- match = re.match(ref_pattern, raw_text.strip())
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1403:29 [unknown]
```
Incompatible
```
- types in assignment (expression has type "Match[str] | None", variable has type
- "Match[str]")  [assignment]
- match = re.match(
- ^

#### markdown_plugin.py:1427:5 [unknown]
```
Function is
```
- missing a return type annotation  [no-untyped-def]
- def _traverse_nodes(self, node: "tree_sitter.Node"):
- ^

#### markdown_plugin.py:1504:16 [unknown]
```
Incompatible
```
- return value type (got "list[Function]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_functions(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1511:16 [unknown]
```
Incompatible
```
- return value type (got "list[Class]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_classes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1518:16 [unknown]
```
Incompatible
```
- return value type (got "list[Variable]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_variables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1525:16 [unknown]
```
Incompatible
```
- return value type (got "list[Import]", expected "list[CodeElement]")
- [return-value]
- return extractor.extract_imports(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- headers = extractor.extract_headers(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- code_blocks = extractor.extract_code_blocks(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- links = extractor.extract_links(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- images = extractor.extract_images(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- references = extractor.extract_references(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- lists = extractor.extract_lists(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- tables = extractor.extract_tables(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- blockquotes = extractor.extract_blockquotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- horizontal_rules = extractor.extract_horizontal_rules(tree...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- html_elements = extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- text_formatting = extractor.extract_text_formatting(tree, ...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- footnotes = extractor.extract_footnotes(tree, source_code)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_headers"  [attr-defined]
- elements.extend(extractor.extract_headers(tree, source_cod...
- ^~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_code_blocks"  [attr-defined]
- elements.extend(extractor.extract_code_blocks(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_links"  [attr-defined]
- elements.extend(extractor.extract_links(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_images"; maybe "extract_packages",
- "extract_variables", or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_images(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_references"  [attr-defined]
- elements.extend(extractor.extract_references(tree, source_...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_lists"; maybe "extract_classes" or
- "extract_imports"?  [attr-defined]
- elements.extend(extractor.extract_lists(tree, source_code)...
- ^~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_tables"; maybe "extract_variables"
- or "extract_classes"?  [attr-defined]
- elements.extend(extractor.extract_tables(tree, source_code...
- ^~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_blockquotes"  [attr-defined]
- elements.extend(extractor.extract_blockquotes(tree, source...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_horizontal_rules"  [attr-defined]
- elements.extend(extractor.extract_horizontal_rules(tree, s...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_html_elements"; maybe
- "extract_all_elements"?  [attr-defined]
- elements.extend(extractor.extract_html_elements(tree, sour...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_text_formatting"  [attr-defined]
- elements.extend(extractor.extract_text_formatting(tree, so...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- "ElementExtractor" has no attribute "extract_footnotes"  [attr-defined]
- elements.extend(extractor.extract_footnotes(tree, source_c...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### markdown_plugin.py:1746:5 [unknown]
```
Signature of
```
- "execute_query_strategy" incompatible with supertype
- "tree_sitter_analyzer.plugins.base.LanguagePlugin"  [override]
- def execute_query_strategy(
- ^

#### python_plugin.py:73:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return functions
- ^~~~~~~~~~~~~~~~

#### python_plugin.py:103:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return classes
- ^~~~~~~~~~~~~~

#### python_plugin.py:186:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return
- ^~~~~~

#### python_plugin.py:266:36 [unknown]
```
Incompatible
```
- types in assignment (expression has type "list[Node]", variable has type
- "reversed[Node]")  [assignment]
- children = list(current_node.children)
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### python_plugin.py:269:36 [unknown]
```
Incompatible
```
- types in assignment (expression has type "list[Never]", variable has type
- "reversed[Node]")  [assignment]
- children = []
- ^~

#### python_plugin.py:749:25 [unknown]
```
Need type
```
- annotation for "captures_dict" (hint:
- "captures_dict: dict[<type>, <type>] = ...")  [var-annotated]
- captures_dict = {}
- ^~~~~~~~~~~~~

#### query_command.py:16:5 [unknown]
```
Function is
```
- missing a type annotation  [no-untyped-def]
- def __init__(self, args):
- ^

#### search_content_tool.py:352:25 [unknown]
```
Returning
```
- Any from function declared to return "dict[str, Any] | int"  [no-any-return]
- return cached_result["total_matches"]
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### search_content_tool.py:354:25 [unknown]
```
Returning
```
- Any from function declared to return "dict[str, Any] | int"  [no-any-return]
- return cached_result["count"]
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### server.py:119:17 [unknown]
```
Attribute
```
- "universal_analyze_tool" already defined on line 117  [no-redef]
- self.universal_analyze_tool: Any = None
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### server.py:119:52 [unknown]
```
Incompatible types in
```
- assignment (expression has type "None", variable has type
- "UniversalAnalyzeTool")  [assignment]
- self.universal_analyze_tool: Any = None
- ^~~~

#### server.py:121:13 [unknown]
```
Attribute
```
- "universal_analyze_tool" already defined on line 117  [no-redef]
- self.universal_analyze_tool: Any = None
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~

#### server.py:121:13 [unknown]
```
Statement is unreachable 
```
- [unreachable]
- self.universal_analyze_tool: Any = None
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### server.py:167:21 [unknown]
```
Returning Any from function
```
- declared to return "dict[str, Any]"  [no-any-return]
- return await self.universal_analyze_tool.execute(a...
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~...

#### server.py:403:47 [unknown]
```
Right operand of "and" is
```
- never evaluated  [unreachable]
- elif in_multiline_comment and "-->" in stripped:
- ^~~~~~~~~~~~~~~~~

#### server.py:404:21 [unknown]
```
Statement is unreachable 
```
- [unreachable]
- comment_lines += 1
- ^~~~~~~~~~~~~~~~~~

#### server.py:447:10 [unknown]
```
Untyped decorator makes
```
- function "handle_list_tools" untyped  [misc]
- @server.list_tools()
- ^~~~~~~~~~~~~~~~~~~

#### server.py:480:10 [unknown]
```
Untyped decorator makes
```
- function "handle_call_tool" untyped  [misc]
- @server.call_tool()
- ^~~~~~~~~~~~~~~~~~
- [unused-ignore]
- from mcp.types import Prompt  # type: ignore
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### server.py:480:10 [unknown]
```
Untyped decorator makes
```
- function "handle_call_tool" untyped  [misc]
- @server.call_tool()
- ^~~~~~~~~~~~~~~~~~
- [unused-ignore]
- from mcp.types import Prompt  # type: ignore
- ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#### table_command.py:28:5 [unknown]
```
Function is
```
- missing a type annotation  [no-untyped-def]
- def __init__(self, args):
- ^

#### table_command.py:59:25 [unknown]
```
Incompatible
```
- types in assignment (expression has type "TableFormatter", variable has type
- "BaseFormatter")  [assignment]
- formatter = create_table_formatter(
- ^

#### table_format_tool.py:478:25 [unknown]
```
Name
```
- "formatter" already defined on line 474  [no-redef]
- formatter: Any = TableFormatter(format_type)
- ^~~~~~~~~

#### table_format_tool.py:485:21 [unknown]
```
Name
```
- "formatter" already defined on line 474  [no-redef]
- formatter: Any = TableFormatter(format_type)
- ^~~~~~~~~

#### typescript_plugin.py:199:13 [unknown]
```
Statement is
```
- unreachable  [unreachable]
- return
- ^~~~~~

#### validator.py:493:54 [unknown]
```
Item "dict[Any, Any]"
```
- of "Any | dict[Any, Any]" has no attribute "argv"  [union-attr]
- ...                "test" in arg.lower() for arg in getattr(os, "sys", {}...
- ^~~~~~~~~~~~~~~~~~~~~...

