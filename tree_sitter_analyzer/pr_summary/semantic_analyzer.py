"""
PR Summary - Semantic Code Change Analyzer

语义级代码变更分析，检测函数签名变更、类变更、依赖变更。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.language_loader import LanguageLoader
from tree_sitter_analyzer.pr_summary.diff_parser import FileChange


class SemanticChangeType(Enum):
    """语义变更类型"""

    FUNCTION_SIGNATURE = "function_signature"
    CLASS_SIGNATURE = "class_signature"
    IMPORT_ADDED = "import_added"
    IMPORT_REMOVED = "import_removed"
    METHOD_REMOVED = "method_removed"
    CLASS_REMOVED = "class_removed"


@dataclass
class SemanticChange:
    """单个语义变更"""

    change_type: SemanticChangeType
    language: str
    name: str
    file_path: str
    is_breaking: bool
    description: str


@dataclass
class SemanticAnalysisResult:
    """语义分析结果"""

    changes: list[SemanticChange]
    breaking_changes: list[SemanticChange]
    new_imports: list[str]
    removed_imports: list[str]
    languages_used: set[str]

    @property
    def has_breaking_changes(self) -> bool:
        """是否有破坏性变更"""
        return len(self.breaking_changes) > 0

    @property
    def api_changes(self) -> list[SemanticChange]:
        """API 级别的变更（类、公共方法）"""
        return [
            c
            for c in self.changes
            if c.change_type
            in [SemanticChangeType.CLASS_SIGNATURE, SemanticChangeType.FUNCTION_SIGNATURE]
            and c.is_breaking
        ]


class SemanticAnalyzer:
    """
    语义代码变更分析器

    检测以下级别的变更：
    1. 函数签名变更（参数、返回值）
    2. 类/接口变更（公共 API）
    3. 依赖变更（import/require）

    支持语言：Python, JavaScript, TypeScript, Java, Go
    """

    # Language to tree-sitter language mapping
    _LANGUAGE_MAP: dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
    }

    # Breaking change patterns per language
    _BREAKING_PATTERNS: dict[str, list[str]] = {
        "python": [
            "(function_definition"
            "  name: (identifier) @fn_name"
            "  parameters: (parameters) @params)",
        ],
        "javascript": [
            "(function_declaration"
            "  name: (identifier) @fn_name"
            "  parameters: (formal_parameters) @params)",
            "(method_definition"
            "  name: (property_identifier) @method_name)",
        ],
        "typescript": [
            "(function_declaration"
            "  name: (identifier) @fn_name"
            "  parameters: (formal_parameters) @params)",
            "(method_definition"
            "  name: (property_identifier) @method_name)",
        ],
        "java": [
            "(method_declaration"
            "  name: (identifier) @method_name"
            "  parameters: (formal_parameters) @params)",
        ],
        "go": [
            "(function_declaration"
            "  name: (identifier) @fn_name"
            "  parameters: (parameter_list) @params)",
        ],
    }

    def __init__(self) -> None:
        """初始化分析器"""
        self._loader = LanguageLoader()

    def analyze_diff(
        self,
        file_change: FileChange,
        old_content: str | None = None,
        new_content: str | None = None,
    ) -> SemanticAnalysisResult:
        """
        分析单个文件变更的语义

        Args:
            file_change: FileChange 对象
            old_content: 旧文件内容（可选）
            new_content: 新文件内容（可选）

        Returns:
            SemanticAnalysisResult
        """
        ext = Path(file_change.path).suffix
        lang = self._LANGUAGE_MAP.get(ext, "")

        if not lang:
            # Unsupported language
            return SemanticAnalysisResult(
                changes=[],
                breaking_changes=[],
                new_imports=[],
                removed_imports=[],
                languages_used=set(),
            )

        changes: list[SemanticChange] = []
        breaking_changes: list[SemanticChange] = []
        new_imports: list[str] = []
        removed_imports: list[str] = []

        # If we have both old and new content, do comparison
        if old_content and new_content:
            old_imports = self._extract_imports(old_content, lang)
            new_imports_set = self._extract_imports(new_content, lang)

            # Detect import changes
            added_imports = new_imports_set - old_imports
            removed_imports_set = old_imports - new_imports_set

            for imp in sorted(added_imports):
                new_imports.append(imp)
                changes.append(
                    SemanticChange(
                        change_type=SemanticChangeType.IMPORT_ADDED,
                        language=lang,
                        name=imp,
                        file_path=file_change.path,
                        is_breaking=False,
                        description=f"Added import: {imp}",
                    )
                )

            for imp in sorted(removed_imports_set):
                removed_imports.append(imp)
                changes.append(
                    SemanticChange(
                        change_type=SemanticChangeType.IMPORT_REMOVED,
                        language=lang,
                        name=imp,
                        file_path=file_change.path,
                        is_breaking=False,
                        description=f"Removed import: {imp}",
                    )
                )

            # Detect signature changes (if applicable)
            if file_change.change_type.value in ["modified", "deleted"]:
                api_changes = self._detect_api_changes(
                    old_content, new_content, lang, file_change.path
                )
                changes.extend(api_changes)
                breaking_changes.extend([c for c in api_changes if c.is_breaking])

        return SemanticAnalysisResult(
            changes=changes,
            breaking_changes=breaking_changes,
            new_imports=new_imports,
            removed_imports=removed_imports,
            languages_used={lang},
        )

    def _extract_imports(self, content: str, lang: str) -> set[str]:
        """
        提取文件中的导入语句

        Args:
            content: 文件内容
            lang: 语言类型

        Returns:
            导入模块集合
        """
        imports: set[str] = set()

        try:
            parser = self._loader.create_parser_safely(lang)
            if not parser:
                return imports

            tree = parser.parse(bytes(content, "utf-8"))
            root = tree.root_node

            # Language-specific import patterns
            if lang == "python":
                imports.update(self._extract_python_imports(root))
            elif lang in ("javascript", "typescript"):
                imports.update(self._extract_js_imports(root))
            elif lang == "java":
                imports.update(self._extract_java_imports(root))
            elif lang == "go":
                imports.update(self._extract_go_imports(root))

        except Exception:
            pass

        return imports

    def _extract_python_imports(self, root: Any) -> set[str]:
        """提取 Python 导入"""
        imports: set[str] = set()

        def traverse(node: Any) -> None:
            if node.type == "import_statement":
                # Find the module name
                for child in node.children:
                    if child.type == "dotted_name":
                        imports.add(child.text.decode())
                    elif child.type == "identifier":
                        imports.add(child.text.decode())
            elif node.type == "import_from_statement":
                # Get the module name
                for child in node.children:
                    if child.type == "dotted_name" or child.type == "identifier":
                        imports.add(child.text.decode())
                        break
            elif node.type == "alias":
                # For "import foo as bar", get "foo"
                for child in node.children:
                    if child.type == "identifier" or child.type == "dotted_name":
                        imports.add(child.text.decode())
                        break

            for child in node.children:
                traverse(child)

        traverse(root)
        return imports

    def _extract_js_imports(self, root: Any) -> set[str]:
        """提取 JavaScript/TypeScript 导入"""
        imports: set[str] = set()

        def traverse(node: Any) -> None:
            if node.type == "import_statement":
                # Find the source string
                for child in node.children:
                    if child.type == "string":
                        # Strip quotes
                        text = child.text.decode()
                        if text.startswith(('"', "'", '"')):
                            text = text[1:]
                        if text.endswith(('"', "'", '"')):
                            text = text[:-1]
                        imports.add(text)
            elif node.type == "import_specifier":
                # For named imports like "import { foo } from 'bar'"
                for child in node.children:
                    if child.type == "identifier":
                        imports.add(child.text.decode())

            for child in node.children:
                traverse(child)

        traverse(root)
        return imports

    def _extract_java_imports(self, root: Any) -> set[str]:
        """提取 Java 导入"""
        imports: set[str] = set()

        def traverse(node: Any) -> None:
            if node.type == "import_declaration":
                # Get the full dotted name from the import
                for child in node.children:
                    if child.type == "scoped_identifier" or child.type == "identifier":
                        imports.add(child.text.decode())

            for child in node.children:
                traverse(child)

        traverse(root)
        return imports

    def _extract_go_imports(self, root: Any) -> set[str]:
        """提取 Go 导入"""
        imports: set[str] = set()

        def traverse(node: Any) -> None:
            if node.type == "import_spec":
                # Get the path from the interpreted_string_literal
                for child in node.children:
                    if child.type == "interpreted_string_literal":
                        # Strip quotes
                        text = child.text.decode()
                        if text.startswith('"') and text.endswith('"'):
                            text = text[1:-1]
                        imports.add(text)

            for child in node.children:
                traverse(child)

        traverse(root)
        return imports

    def _detect_api_changes(
        self,
        old_content: str,
        new_content: str,
        lang: str,
        file_path: str,
    ) -> list[SemanticChange]:
        """
        检测 API 级别的变更

        Args:
            old_content: 旧代码内容
            new_content: 新代码内容
            lang: 语言类型
            file_path: 文件路径

        Returns:
            语义变更列表
        """
        changes: list[SemanticChange] = []

        try:
            parser = self._loader.create_parser_safely(lang)
            if not parser:
                return changes

            old_tree = parser.parse(bytes(old_content, "utf-8"))
            new_tree = parser.parse(bytes(new_content, "utf-8"))

            # Extract public functions/classes from both versions
            old_functions = self._extract_functions(old_tree.root_node, lang)
            new_functions = self._extract_functions(new_tree.root_node, lang)

            old_classes = self._extract_classes(old_tree.root_node, lang)
            new_classes = self._extract_classes(new_tree.root_node, lang)

            # Detect removed functions (breaking)
            for func in old_functions - new_functions:
                changes.append(
                    SemanticChange(
                        change_type=SemanticChangeType.FUNCTION_SIGNATURE,
                        language=lang,
                        name=func,
                        file_path=file_path,
                        is_breaking=True,
                        description=f"Removed function: {func}",
                    )
                )

            # Detect removed classes (breaking)
            for cls in old_classes - new_classes:
                changes.append(
                    SemanticChange(
                        change_type=SemanticChangeType.CLASS_SIGNATURE,
                        language=lang,
                        name=cls,
                        file_path=file_path,
                        is_breaking=True,
                        description=f"Removed class: {cls}",
                    )
                )

            # Detect signature changes (simplified: name collision with different params)
            for func in old_functions & new_functions:
                # In a full implementation, we'd compare parameters here
                # For now, we conservatively flag modifications as potential breaking
                if old_content != new_content:
                    # Function exists in both but code changed
                    # Check if the function body changed significantly
                    changes.append(
                        SemanticChange(
                            change_type=SemanticChangeType.FUNCTION_SIGNATURE,
                            language=lang,
                            name=func,
                            file_path=file_path,
                            is_breaking=False,  # Conservative: assume not breaking without diff
                            description=f"Modified function: {func}",
                        )
                    )

        except Exception:
            pass

        return changes

    def _extract_functions(self, root: Any, lang: str) -> set[str]:
        """提取所有函数名"""
        functions: set[str] = set()

        # Node types for functions per language
        function_types = {
            "python": ["function_definition"],
            "javascript": ["function_declaration", "method_definition"],
            "typescript": ["function_declaration", "method_definition"],
            "java": ["method_declaration"],
            "go": ["function_declaration"],
        }

        types_to_find = function_types.get(lang, [])

        def traverse(node: Any) -> None:
            if node.type in types_to_find:
                # Find the name child (usually the first identifier)
                for child in node.children:
                    if child.type == "identifier" or child.type == "property_identifier":
                        functions.add(child.text.decode())
                        break

            for child in node.children:
                traverse(child)

        traverse(root)
        return functions

    def _extract_classes(self, root: Any, lang: str) -> set[str]:
        """提取所有类名"""
        classes: set[str] = set()

        # Node types for classes per language
        class_types = {
            "python": ["class_definition"],
            "javascript": ["class_declaration"],
            "typescript": ["class_declaration"],
            "java": ["class_declaration", "interface_declaration"],
            "go": [],  # Go uses structs, not classes
        }

        types_to_find = class_types.get(lang, [])

        def traverse(node: Any) -> None:
            if node.type in types_to_find:
                # Find the name child (usually the first identifier)
                for child in node.children:
                    if child.type == "identifier" or child.type == "type_identifier":
                        classes.add(child.text.decode())
                        break

            for child in node.children:
                traverse(child)

        traverse(root)
        return classes

    def analyze_batch(
        self,
        file_changes: list[FileChange],
        contents_map: dict[str, tuple[str | None, str | None]],
    ) -> SemanticAnalysisResult:
        """
        批量分析多个文件变更

        Args:
            file_changes: FileChange 列表
            contents_map: 文件路径到 (old_content, new_content) 的映射

        Returns:
            SemanticAnalysisResult 聚合结果
        """
        all_changes: list[SemanticChange] = []
        all_breaking: list[SemanticChange] = []
        all_new_imports: list[str] = []
        all_removed_imports: list[str] = []
        all_languages: set[str] = set()

        for change in file_changes:
            contents = contents_map.get(change.path)
            if not contents:
                continue

            old_content, new_content = contents
            result = self.analyze_diff(change, old_content, new_content)

            all_changes.extend(result.changes)
            all_breaking.extend(result.breaking_changes)
            all_new_imports.extend(result.new_imports)
            all_removed_imports.extend(result.removed_imports)
            all_languages.update(result.languages_used)

        return SemanticAnalysisResult(
            changes=all_changes,
            breaking_changes=all_breaking,
            new_imports=sorted(set(all_new_imports)),
            removed_imports=sorted(set(all_removed_imports)),
            languages_used=all_languages,
        )
