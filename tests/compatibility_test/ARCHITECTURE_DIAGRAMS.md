# Tree-sitter Analyzer 互換性テストシステム アーキテクチャ図

## 概要

このドキュメントでは、Tree-sitter Analyzer互換性テストシステムのアーキテクチャを視覚的に説明します。システムの構成要素、データフロー、処理フロー、ファイル関連図を含みます。

---

## 1. システム全体アーキテクチャ

```mermaid
graph TB
    subgraph "互換性テストシステム"
        subgraph "テスト実行層"
            MCP["MCPテスト実行
            mcp_test_direct.py"]
            CLI["CLIテスト実行
            cli_test.py"]
        end
        
        subgraph "設定管理層"
            CONFIG["設定管理
            config_manager.py"]
            TESTCASES["テストケース
            *_test_cases.json"]
            VERSION["バージョン管理
            version_manager.py"]
        end
        
        subgraph "分析・比較層"
            COMPARE_MCP["MCP比較
            compare_mcp.py"]
            COMPARE_CLI["CLI比較
            compare_cli.py"]
            UNIFIED["統合レポート
            unified_report.py"]
        end
        
        subgraph "ユーティリティ層"
            LOGGER["色付きログ
            colored_logger.py"]
            CLIENT["MCPクライアント
            mcp_client.py"]
            UTILS["共通ユーティリティ
            utils.py"]
        end
    end
    
    subgraph "外部システム"
        TSA_CURRENT["Tree-sitter Analyzer
        v1.9.2 (current)"]
        TSA_OLD["Tree-sitter Analyzer
        v1.6.1"]
        MCP_SERVER["MCPサーバー"]
        CLI_INTERFACE["CLIインターフェース"]
    end
    
    subgraph "出力"
        RESULTS["テスト結果
        result/"]
        COMPARISON["比較レポート
        comparison/"]
        UNIFIED_REPORT["統合レポート
        unified_report/"]
    end
    
    MCP --> MCP_SERVER
    CLI --> CLI_INTERFACE
    MCP_SERVER --> TSA_CURRENT
    MCP_SERVER --> TSA_OLD
    CLI_INTERFACE --> TSA_CURRENT
    CLI_INTERFACE --> TSA_OLD
    
    CONFIG --> MCP
    CONFIG --> CLI
    TESTCASES --> MCP
    TESTCASES --> CLI
    VERSION --> MCP
    VERSION --> CLI
    
    MCP --> RESULTS
    CLI --> RESULTS
    RESULTS --> COMPARE_MCP
    RESULTS --> COMPARE_CLI
    COMPARE_MCP --> COMPARISON
    COMPARE_CLI --> COMPARISON
    COMPARISON --> UNIFIED
    UNIFIED --> UNIFIED_REPORT
    
    LOGGER --> MCP
    LOGGER --> CLI
    CLIENT --> MCP
    UTILS --> MCP
    UTILS --> CLI
```

---

## 2. データフロー図

```mermaid
flowchart TD
    subgraph "入力データ"
        A[config.json<br/>システム設定]
        B[mcp_test_cases.json<br/>MCPテストケース]
        C[cli_test_cases.json<br/>CLIテストケース]
        D[versions/<br/>バージョン環境]
    end
    
    subgraph "処理エンジン"
        E[テストケースローダー<br/>test_case_loader.py]
        F[バージョンマネージャー<br/>version_manager.py]
        G[MCPテスト実行器<br/>mcp_test_direct.py]
        H[CLIテスト実行器<br/>cli_test.py]
    end
    
    subgraph "中間データ"
        I[個別テスト結果<br/>result/mcp/v-*/]
        J[個別テスト結果<br/>result/cli/v-*/]
        K[実行ログ<br/>*.log]
    end
    
    subgraph "分析処理"
        L[MCP比較分析<br/>compare_mcp.py]
        M[CLI比較分析<br/>compare_cli.py]
        N[統合分析<br/>unified_report.py]
    end
    
    subgraph "出力データ"
        O[比較レポート<br/>comparison/]
        P[統合レポート<br/>unified_report/]
        Q[WinMergeファイル<br/>winmerge/]
    end
    
    A --> E
    B --> E
    C --> E
    D --> F
    
    E --> G
    E --> H
    F --> G
    F --> H
    
    G --> I
    H --> J
    G --> K
    H --> K
    
    I --> L
    J --> M
    L --> N
    M --> N
    
    L --> O
    M --> O
    N --> P
    O --> Q
```

---

## 3. 処理フロー図

### 3.1 MCPテスト処理フロー

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant MCP as mcp_test_direct.py
    participant VM as version_manager.py
    participant TC as test_case_loader.py
    participant Server as MCPサーバー
    participant TSA as Tree-sitter Analyzer
    
    User->>MCP: テスト実行開始
    MCP->>VM: バージョン情報取得
    VM-->>MCP: 利用可能バージョン一覧
    MCP->>TC: テストケース読み込み
    TC-->>MCP: テストケース一覧
    
    loop 各バージョン
        loop 各テストケース
            MCP->>Server: MCPサーバー初期化
            Server->>TSA: ツール実行
            TSA-->>Server: 実行結果
            Server-->>MCP: レスポンス
            MCP->>MCP: 結果保存
        end
    end
    
    MCP-->>User: テスト完了
```

### 3.2 CLIテスト処理フロー

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant CLI as cli_test.py
    participant VM as version_manager.py
    participant TC as test_case_loader.py
    participant Proc as プロセス実行
    participant TSA as Tree-sitter Analyzer CLI
    
    User->>CLI: テスト実行開始
    CLI->>VM: バージョン情報取得
    VM-->>CLI: Python実行可能ファイルパス
    CLI->>TC: テストケース読み込み
    TC-->>CLI: テストケース一覧
    
    loop 各バージョン
        loop 各テストケース
            CLI->>Proc: コマンド実行
            Proc->>TSA: CLIコマンド
            TSA-->>Proc: 標準出力/エラー
            Proc-->>CLI: 実行結果
            CLI->>CLI: 結果保存
        end
    end
    
    CLI-->>User: テスト完了
```

### 3.3 比較・レポート生成フロー

```mermaid
flowchart TD
    A[テスト結果収集] --> B{結果タイプ}
    B -->|MCP| C[MCP比較処理]
    B -->|CLI| D[CLI比較処理]
    
    C --> E[差分分析]
    D --> F[差分分析]
    
    E --> G[互換性評価]
    F --> H[互換性評価]
    
    G --> I[HTMLレポート生成]
    H --> J[HTMLレポート生成]
    
    I --> K[WinMergeファイル生成]
    J --> L[WinMergeファイル生成]
    
    K --> M[統合レポート処理]
    L --> M
    
    M --> N[重み付き評価<br/>MCP: 70%, CLI: 30%]
    N --> O[最終レポート出力]
```

---

## 4. ファイル関連図

### 4.1 設定ファイル関係

```mermaid
graph LR
    subgraph "設定ファイル"
        A[config.json<br/>システム設定]
        B[mcp_test_cases.json<br/>MCPテストケース]
        C[cli_test_cases.json<br/>CLIテストケース]
    end
    
    subgraph "読み込みモジュール"
        D[config_manager.py]
        E[test_case_loader.py]
    end
    
    subgraph "実行モジュール"
        F[mcp_test_direct.py]
        G[cli_test.py]
        H[compare_*.py]
        I[unified_report.py]
    end
    
    A --> D
    B --> E
    C --> E
    
    D --> F
    D --> G
    D --> H
    D --> I
    
    E --> F
    E --> G
```

### 4.2 結果ファイル構造

```mermaid
graph TD
    subgraph "result/"
        subgraph "mcp/"
            A[v-current/<br/>現在バージョン結果]
            B[v-1.6.1/<br/>1.6.1バージョン結果]
        end
        
        subgraph "cli/"
            C[v-current/<br/>現在バージョン結果]
            D[v-1.6.1/<br/>1.6.1バージョン結果]
        end
    end
    
    subgraph "comparison/"
        E[mcp_current_vs_1.6.1/<br/>MCP比較結果]
        F[cli_current_vs_1.6.1/<br/>CLI比較結果]
    end
    
    subgraph "unified_report/"
        G[current_vs_1.6.1/<br/>統合レポート]
    end
    
    A --> E
    B --> E
    C --> F
    D --> F
    
    E --> G
    F --> G
```

---

## 5. コンポーネント詳細図

### 5.1 MCPテストコンポーネント

```mermaid
classDiagram
    class MCPTestDirect {
        +main()
        +run_tests()
        +execute_test_case()
        +save_result()
    }
    
    class MCPClient {
        +initialize_server()
        +call_tool()
        +handle_response()
    }
    
    class VersionManager {
        +list_available_versions()
        +get_version_info()
        +get_python_executable()
    }
    
    class TestCaseLoader {
        +load_mcp_test_cases()
        +validate_test_case()
        +get_categories()
    }
    
    class ColoredLogger {
        +info()
        +warning()
        +error()
        +success()
    }
    
    MCPTestDirect --> MCPClient
    MCPTestDirect --> VersionManager
    MCPTestDirect --> TestCaseLoader
    MCPTestDirect --> ColoredLogger
```

### 5.2 比較・レポートコンポーネント

```mermaid
classDiagram
    class ComparisonEngine {
        +compare_results()
        +calculate_compatibility()
        +generate_diff()
    }
    
    class ReportGenerator {
        +generate_html()
        +generate_json()
        +create_winmerge_files()
    }
    
    class UnifiedReport {
        +merge_comparisons()
        +calculate_weighted_score()
        +generate_final_report()
    }
    
    class ConfigManager {
        +get_thresholds()
        +get_report_settings()
        +get_comparison_settings()
    }
    
    ComparisonEngine --> ConfigManager
    ReportGenerator --> ConfigManager
    UnifiedReport --> ComparisonEngine
    UnifiedReport --> ReportGenerator
```

---

## 6. データモデル図

### 6.1 テストケースデータモデル

```mermaid
erDiagram
    MCPTestCase {
        string id
        string tool
        string category
        string description
        object parameters
        string expected_error
    }
    
    CLITestCase {
        string test_id
        string name
        string description
        string template
        object parameters
        boolean expected_success
        string category
        int timeout
    }
    
    TestResult {
        string test_id
        string version
        boolean success
        object result_data
        float execution_time
        string error_message
    }
    
    ComparisonResult {
        string version1
        string version2
        float compatibility_score
        array differences
        object metadata
    }
    
    MCPTestCase ||--o{ TestResult : generates
    CLITestCase ||--o{ TestResult : generates
    TestResult ||--o{ ComparisonResult : compared_in
```

---

## 7. 実行環境図

```mermaid
graph TB
    subgraph "開発環境"
        A["プロジェクトルート
        c:/git-public/tree-sitter-analyzer"]
        B["互換性テスト
        tests/compatibility_test/"]
    end
    
    subgraph "バージョン環境"
        C["v1.9.2 (current)
        システムインストール"]
        D["v1.6.1
        versions/v1.6.1/venv/"]
        E["v1.9.2
        versions/v1.9.2/venv/"]
    end
    
    subgraph "実行ツール"
        F["uv
        パッケージマネージャー"]
        G["Python 3.10+
        実行環境"]
    end
    
    subgraph "外部依存"
        H["tree-sitter
        パーサー"]
        I["MCP
        プロトコル"]
        J["colorama
        色付きログ"]
    end
    
    A --> B
    B --> C
    B --> D
    B --> E
    
    F --> G
    G --> H
    G --> I
    G --> J
    
    C --> H
    D --> H
    E --> H
```

---

## 8. セキュリティ・エラーハンドリング図

```mermaid
flowchart TD
    A[テスト実行開始] --> B{バージョン検証}
    B -->|OK| C[テストケース検証]
    B -->|NG| D[バージョンエラー]
    
    C -->|OK| E[個別テスト実行]
    C -->|NG| F[設定エラー]
    
    E --> G{実行結果}
    G -->|成功| H[結果保存]
    G -->|失敗| I{期待されたエラー?}
    
    I -->|Yes| J[エラーケース成功]
    I -->|No| K[予期しないエラー]
    
    H --> L[次のテスト]
    J --> L
    K --> M[エラーログ記録]
    M --> N{継続設定?}
    N -->|Yes| L
    N -->|No| O[テスト中断]
    
    D --> P[エラーレポート]
    F --> P
    O --> P
    
    L --> Q{全テスト完了?}
    Q -->|No| E
    Q -->|Yes| R[最終レポート生成]
```

---

## まとめ

このアーキテクチャ図は、Tree-sitter Analyzer互換性テストシステムの全体像を示しています。システムは以下の特徴を持ちます：

1. **モジュラー設計**: 各コンポーネントが独立して動作
2. **拡張性**: 新しいバージョンやテストケースの追加が容易
3. **堅牢性**: エラーハンドリングと継続実行機能
4. **可視性**: 詳細なログとレポート機能
5. **自動化**: 設定ベースの自動テスト実行

これらの図を参考に、システムの理解と保守を効率的に行うことができます。