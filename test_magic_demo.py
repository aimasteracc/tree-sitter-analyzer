#!/usr/bin/env python3
"""
🚀 革命的魔法ツールのデモンストレーション

深夜3時の奇跡を実現する、世界初の完全自動障害解決システムのデモ。
実際のエラーログを使って魔法的な解決を体験します。
"""

import asyncio
import json
import tempfile
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.magic_solve_tool import MagicSolveTool


async def demo_magic_solve():
    """魔法的障害解決のデモンストレーション"""
    
    print("🌟" * 50)
    print("🚀 革命的魔法ツール - 障害解決デモ")
    print("🌟" * 50)
    print()
    
    # テスト用プロジェクトの作成
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        
        # 問題のあるJavaコードを作成
        java_file = project_path / "PaymentService.java"
        java_file.write_text("""
public class PaymentService {
    private List<Order> orders = new ArrayList<>();
    
    public void processLargeOrder(Order order) {
        // メモリリークの原因：オブジェクトが解放されない
        for (int i = 0; i < 1000000; i++) {
            orders.add(new Order(order.getId() + i, order.getAmount()));
        }
        // 処理後にクリアしていない！
    }
    
    public boolean validateUser(String email) {
        // NullPointerExceptionの原因
        return email.contains("@");  // email が null の場合エラー
    }
}
""")
        
        # requirements.txt も作成（プロジェクトの特徴として）
        (project_path / "requirements.txt").write_text("spring-boot-starter>=2.7.0")
        
        print(f"📁 テストプロジェクト作成: {project_path}")
        print(f"📄 問題のあるコード: {java_file.name}")
        print()
        
        # 魔法ツールの初期化
        magic_tool = MagicSolveTool()
        print(f"🔮 {magic_tool.name} 初期化完了")
        print(f"📝 {magic_tool.description}")
        print()
        
        # シナリオ1: メモリリーク問題の解決
        print("🚨 シナリオ1: 本番障害 - メモリリーク")
        print("=" * 40)
        
        memory_error_log = """
java.lang.OutOfMemoryError: Java heap space
    at java.util.ArrayList.grow(ArrayList.java:267)
    at java.util.ArrayList.add(ArrayList.java:441)
    at PaymentService.processLargeOrder(PaymentService.java:7)
    at OrderController.handleLargeOrder(OrderController.java:45)
    at Main.main(Main.java:20)

[ERROR] 2025-08-06 03:42:15 - Memory usage: 8GB/8GB (100%)
[ERROR] 2025-08-06 03:42:15 - System performance degraded
[CRITICAL] 2025-08-06 03:42:16 - Payment service unavailable
"""
        
        arguments1 = {
            "project_path": str(project_path),
            "error_log": memory_error_log,
            "priority": 1  # 緊急
        }
        
        print("🕵️ AI探偵による障害調査開始...")
        result1 = await magic_tool.execute(arguments1)
        
        print("✨ 魔法実行結果:")
        print(f"  成功: {result1['success']}")
        print(f"  実行時間: {result1['execution_time']}")
        print(f"  信頼度: {result1['confidence']}")
        print()
        
        if result1['success']:
            investigation = result1['result']['investigation']
            solution = result1['result']['solution']
            
            print("🔍 調査結果:")
            print(f"  障害タイプ: {investigation['failure_type']}")
            print(f"  深刻度: {investigation['severity']}")
            print(f"  根本原因: {investigation['root_cause']}")
            print(f"  影響ファイル: {len(investigation['affected_files'])}個")
            print()
            
            print("💊 自動修復ソリューション:")
            print(f"  タイプ: {solution['type']}")
            print(f"  説明: {solution['description']}")
            print(f"  成功確率: {solution['success_probability']}")
            print()
            
            print("🛡️ 予防策:")
            for prevention in result1['result']['prevention']:
                print(f"  • {prevention}")
            print()
            
            print("✨ 副次効果:")
            for effect in result1['side_effects']:
                print(f"  • {effect}")
            print()
        
        print("🌟" * 50)
        print()
        
        # シナリオ2: Null参照エラーの解決
        print("🚨 シナリオ2: Null参照エラー")
        print("=" * 40)
        
        null_error_log = """
Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.contains(String)" because "email" is null
    at PaymentService.validateUser(PaymentService.java:14)
    at UserController.authenticate(UserController.java:28)
    at SecurityFilter.doFilter(SecurityFilter.java:67)
    at Main.main(Main.java:15)

[WARN] 2025-08-06 14:30:22 - Authentication failed for null email
[ERROR] 2025-08-06 14:30:22 - User validation error
"""
        
        arguments2 = {
            "project_path": str(project_path),
            "error_log": null_error_log,
            "priority": 2  # 高
        }
        
        print("🕵️ AI探偵による障害調査開始...")
        result2 = await magic_tool.execute(arguments2)
        
        print("✨ 魔法実行結果:")
        print(f"  成功: {result2['success']}")
        print(f"  実行時間: {result2['execution_time']}")
        print(f"  信頼度: {result2['confidence']}")
        print()
        
        if result2['success']:
            investigation = result2['result']['investigation']
            solution = result2['result']['solution']
            
            print("🔍 調査結果:")
            print(f"  障害タイプ: {investigation['failure_type']}")
            print(f"  深刻度: {investigation['severity']}")
            print(f"  根本原因: {investigation['root_cause']}")
            print()
            
            print("💊 自動修復ソリューション:")
            print(f"  説明: {solution['description']}")
            print(f"  成功確率: {solution['success_probability']}")
            print()
            
            print("🎯 推奨事項:")
            for rec in result2['recommendations']:
                print(f"  • {rec}")
            print()
        
        print("🌟" * 50)
        print("🎉 魔法デモンストレーション完了！")
        print("💫 世界を変える革命的システムが動作中...")
        print("🌟" * 50)


if __name__ == "__main__":
    asyncio.run(demo_magic_solve())
