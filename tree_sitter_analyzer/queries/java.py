#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java Language Queries

Tree-sitter queries specific to Java language constructs.
Covers classes, methods, annotations, imports, and other Java-specific elements.
"""

from typing import Dict

# Java専用クエリライブラリ
JAVA_QUERIES: Dict[str, str] = {
    # --- 基本構造 ---
    "class": """
    (class_declaration) @class
    """,
    "interface": """
    (interface_declaration) @interface
    """,
    "enum": """
    (enum_declaration) @enum
    """,
    "annotation_type": """
    (annotation_type_declaration) @annotation_type
    """,
    # --- メソッドと構築子 ---
    "method": """
    (method_declaration) @method
    """,
    "constructor": """
    (constructor_declaration) @constructor
    """,
    "abstract_method": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "abstract")) @abstract_method
    """,
    # --- フィールドと変数 ---
    "field": """
    (field_declaration) @field
    """,
    "static_field": """
    (field_declaration
      (modifiers) @mod
      (#match? @mod "static")) @static_field
    """,
    "final_field": """
    (field_declaration
      (modifiers) @mod
      (#match? @mod "final")) @final_field
    """,
    # --- インポートとパッケージ ---
    "import": """
    (import_declaration) @import
    """,
    "static_import": """
    (import_declaration
      "static") @static_import
    """,
    "package": """
    (package_declaration) @package
    """,
    # --- アノテーション ---
    "annotation": """
    (annotation) @annotation
    """,
    "marker_annotation": """
    (marker_annotation) @marker_annotation
    """,
    "annotation_with_params": """
    (annotation
      (annotation_argument_list)) @annotation_with_params
    """,
    # --- Java特有のコンストラクト ---
    "lambda": """
    (lambda_expression) @lambda
    """,
    "try_catch": """
    (try_statement) @try_catch
    """,
    "synchronized_block": """
    (synchronized_statement) @synchronized_block
    """,
    "generic_type": """
    (generic_type) @generic_type
    """,
    # --- 名前のみ抽出 ---
    "class_name": """
    (class_declaration
      name: (identifier) @class_name)
    """,
    "method_name": """
    (method_declaration
      name: (identifier) @method_name)
    """,
    "field_name": """
    (field_declaration
      declarator: (variable_declarator
        name: (identifier) @field_name))
    """,
    # --- 詳細付きクエリ ---
    "class_with_body": """
    (class_declaration
      name: (identifier) @name
      body: (class_body) @body) @class_with_body
    """,
    "method_with_body": """
    (method_declaration
      name: (identifier) @name
      body: (block) @body) @method_with_body
    """,
    "method_with_annotations": """
    (method_declaration
      (modifiers (annotation) @annotation)*
      name: (identifier) @name) @method_with_annotations
    """,
    # --- 継承関係 ---
    "extends_clause": """
    (class_declaration
      (superclass) @extends_clause)
    """,
    "implements_clause": """
    (class_declaration
      (super_interfaces) @implements_clause)
    """,
    # --- 修飾子別 ---
    "public_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "public")
      name: (identifier) @name) @public_methods
    """,
    "private_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "private")
      name: (identifier) @name) @private_methods
    """,
    "static_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "static")
      name: (identifier) @name) @static_methods
    """,
    # --- Spring Framework アノテーション ---
    "spring_controller": """
    (class_declaration
      (modifiers (annotation
        name: (identifier) @annotation_name
        (#match? @annotation_name "Controller|RestController")))
      name: (identifier) @controller_name) @spring_controller
    """,
    "spring_service": """
    (class_declaration
      (modifiers (annotation
        name: (identifier) @annotation_name
        (#match? @annotation_name "Service")))
      name: (identifier) @service_name) @spring_service
    """,
    "spring_repository": """
    (class_declaration
      (modifiers (annotation
        name: (identifier) @annotation_name
        (#match? @annotation_name "Repository")))
      name: (identifier) @repository_name) @spring_repository
    """,
    # --- JPA アノテーション ---
    "jpa_entity": """
    (class_declaration
      (modifiers (annotation
        name: (identifier) @annotation_name
        (#match? @annotation_name "Entity")))
      name: (identifier) @entity_name) @jpa_entity
    """,
    "jpa_id_field": """
    (field_declaration
      (modifiers (annotation
        name: (identifier) @annotation_name
        (#match? @annotation_name "Id")))
      declarator: (variable_declarator
        name: (identifier) @field_name)) @jpa_id_field
    """,
    # --- 構造情報抽出用クエリ ---
    "javadoc_comment": """
    (block_comment) @javadoc_comment
    (#match? @javadoc_comment "^/\\*\\*")
    """,
    "class_with_javadoc": """
    (class_declaration
      name: (identifier) @class_name
      body: (class_body) @class_body) @class_with_javadoc
    """,
    "method_with_javadoc": """
    (method_declaration
      name: (identifier) @method_name
      parameters: (formal_parameters) @parameters
      body: (block) @method_body) @method_with_javadoc
    """,
    "field_with_javadoc": """
    (field_declaration
      type: (_) @field_type
      declarator: (variable_declarator
        name: (identifier) @field_name)) @field_with_javadoc
    """,
    "method_parameters_detailed": """
    (method_declaration
      name: (identifier) @method_name
      parameters: (formal_parameters
        (formal_parameter
          type: (_) @param_type
          name: (identifier) @param_name)*) @parameters) @method_parameters_detailed
    """,
    "class_inheritance_detailed": """
    (class_declaration
      name: (identifier) @class_name
      (superclass
        (type_identifier) @extends_class)?
      (super_interfaces
        (interface_type_list
          (type_identifier) @implements_interface)*)?
      body: (class_body) @class_body) @class_inheritance_detailed
    """,
    "annotation_detailed": """
    (annotation
      name: (identifier) @annotation_name
      (annotation_argument_list
        (element_value_pair
          key: (identifier) @param_key
          value: (_) @param_value)*)?
      ) @annotation_detailed
    """,
    "import_detailed": """
    (import_declaration
      "static"? @static_modifier
      (scoped_identifier) @import_path) @import_detailed
    """,
    "package_detailed": """
    (package_declaration
      (scoped_identifier) @package_name) @package_detailed
    """,
    "constructor_detailed": """
    (constructor_declaration
      name: (identifier) @constructor_name
      parameters: (formal_parameters) @parameters
      body: (constructor_body) @constructor_body) @constructor_detailed
    """,
    "enum_constant": """
    (enum_declaration
      body: (enum_body
        (enum_constant
          name: (identifier) @constant_name)*)) @enum_constant
    """,
    "interface_method": """
    (interface_declaration
      body: (interface_body
        (method_declaration
          name: (identifier) @method_name
          parameters: (formal_parameters) @parameters)*)) @interface_method
    """,
}

# クエリの説明
JAVA_QUERY_DESCRIPTIONS: Dict[str, str] = {
    "class": "Javaクラス宣言を抽出",
    "interface": "Javaインターフェース宣言を抽出",
    "enum": "Java列挙型宣言を抽出",
    "annotation_type": "Javaアノテーション型宣言を抽出",
    "method": "Javaメソッド宣言を抽出",
    "constructor": "Javaコンストラクタ宣言を抽出",
    "field": "Javaフィールド宣言を抽出",
    "import": "Javaインポート文を抽出",
    "package": "Javaパッケージ宣言を抽出",
    "annotation": "Javaアノテーションを抽出",
    "lambda": "Javaラムダ式を抽出",
    "try_catch": "Java try-catch文を抽出",
    "class_name": "クラス名のみを抽出",
    "method_name": "メソッド名のみを抽出",
    "field_name": "フィールド名のみを抽出",
    "class_with_body": "クラス宣言と本体を抽出",
    "method_with_body": "メソッド宣言と本体を抽出",
    "extends_clause": "クラスの継承句を抽出",
    "implements_clause": "クラスの実装句を抽出",
    "public_methods": "publicメソッドを抽出",
    "private_methods": "privateメソッドを抽出",
    "static_methods": "staticメソッドを抽出",
    # 構造情報抽出用クエリの説明
    "javadoc_comment": "JavaDocコメントを抽出",
    "class_with_javadoc": "JavaDoc付きクラスを抽出",
    "method_with_javadoc": "JavaDoc付きメソッドを抽出",
    "field_with_javadoc": "JavaDoc付きフィールドを抽出",
    "method_parameters_detailed": "メソッドパラメータの詳細情報を抽出",
    "class_inheritance_detailed": "クラスの継承関係詳細を抽出",
    "annotation_detailed": "アノテーションの詳細情報を抽出",
    "import_detailed": "インポート文の詳細情報を抽出",
    "package_detailed": "パッケージ宣言の詳細情報を抽出",
    "constructor_detailed": "コンストラクタの詳細情報を抽出",
    "enum_constant": "列挙型定数を抽出",
    "interface_method": "インターフェースメソッドを抽出",
    "spring_controller": "Spring Controllerクラスを抽出",
    "spring_service": "Spring Serviceクラスを抽出",
    "spring_repository": "Spring Repositoryクラスを抽出",
    "jpa_entity": "JPA Entityクラスを抽出",
    "abstract_method": "抽象メソッドを抽出",
    "static_field": "静的フィールドを抽出",
    "final_field": "finalフィールドを抽出",
    "static_import": "静的インポート文を抽出",
    "marker_annotation": "マーカーアノテーションを抽出",
    "annotation_with_params": "パラメータ付きアノテーションを抽出",
    "synchronized_block": "synchronized文を抽出",
    "generic_type": "ジェネリック型を抽出",
    "method_with_annotations": "アノテーション付きメソッドを抽出",
    "jpa_id_field": "JPA IDフィールドを抽出",
}


def get_java_query(name: str) -> str:
    """
    指定されたJavaクエリを取得

    Args:
        name: クエリ名

    Returns:
        クエリ文字列

    Raises:
        ValueError: クエリが見つからない場合
    """
    if name not in JAVA_QUERIES:
        available = list(JAVA_QUERIES.keys())
        raise ValueError(f"Javaクエリ '{name}' は存在しません。利用可能: {available}")

    return JAVA_QUERIES[name]


def get_java_query_description(name: str) -> str:
    """
    指定されたJavaクエリの説明を取得

    Args:
        name: クエリ名

    Returns:
        クエリの説明
    """
    return JAVA_QUERY_DESCRIPTIONS.get(name, "説明なし")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in JAVA_QUERIES.items():
    description = JAVA_QUERY_DESCRIPTIONS.get(query_name, "説明なし")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": JAVA_QUERIES["method"],
    "description": "すべての関数/メソッド宣言を検索（methodのエイリアス）",
}

ALL_QUERIES["classes"] = {
    "query": JAVA_QUERIES["class"],
    "description": "すべてのクラス宣言を検索（classのエイリアス）",
}


def get_query(name: str) -> str:
    """Get a specific query by name."""
    if name in ALL_QUERIES:
        return ALL_QUERIES[name]["query"]
    raise ValueError(
        f"Query '{name}' not found. Available queries: {list(ALL_QUERIES.keys())}"
    )


def get_all_queries() -> dict:
    """Get all available queries."""
    return ALL_QUERIES


def list_queries() -> list:
    """List all available query names."""
    return list(ALL_QUERIES.keys())


def get_available_java_queries() -> list[str]:
    """
    利用可能なJavaクエリ一覧を取得

    Returns:
        クエリ名のリスト
    """
    return list(JAVA_QUERIES.keys())
