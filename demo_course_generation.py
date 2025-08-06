#!/usr/bin/env python3
"""
🎓 革命的教育コンテンツ生成デモ

我々のTree-sitter Analyzerプロジェクト自体から
Udemy級コースを自動生成するデモンストレーション。

実際のプロジェクトを分析し、商用レベルの教育コンテンツを
Trainingフォルダに生成します。
"""

import asyncio
import json
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.magic_course_tool import MagicCourseGeneratorTool


async def demo_course_generation():
    """我々のプロジェクトからUdemy級コース生成デモ"""
    
    print("🌟" * 60)
    print("🎓 革命的教育コンテンツ生成魔法 - 実践デモ")
    print("🌟" * 60)
    print()
    
    # 現在のプロジェクトパス（相対パス使用）
    project_path = "."  # 相対パス
    current_dir = Path.cwd()
    print(f"📁 対象プロジェクト: {current_dir}")
    print(f"📊 プロジェクト名: Tree-sitter Analyzer Revolution")
    print(f"🛡️ セキュリティ: 相対パス使用 ({project_path})")
    print()

    # 魔法ツールの初期化
    magic_tool = MagicCourseGeneratorTool()
    print(f"🔮 {magic_tool.name} 初期化完了")
    print(f"📝 {magic_tool.description}")
    print()

    # コース生成パラメータ
    print("⚙️ コース生成設定:")
    arguments = {
        "project_path": project_path,
        "target_level": "intermediate",  # 中級レベル
        "language": "japanese",          # 日本語
        "output_dir": "Training",        # Trainingフォルダに出力
        "include_marketing": True        # マーケティング戦略も含める
    }
    
    for key, value in arguments.items():
        print(f"  • {key}: {value}")
    print()
    
    print("🚀 Udemy級コース自動生成開始...")
    print("=" * 50)
    
    try:
        # 魔法実行
        result = await magic_tool.execute(arguments)
        
        if result["success"]:
            print("✨ 魔法実行成功！")
            print()
            
            # 基本情報の表示
            course_info = result["result"]["course_info"]
            print("📚 生成されたコース情報:")
            print(f"  🎯 タイトル: {course_info['title']}")
            print(f"  ⏱️ 総時間: {course_info['duration_hours']}時間")
            print(f"  🎬 講義数: {course_info['total_lectures']}講義")
            print(f"  🎮 演習数: {course_info['total_exercises']}演習")
            print(f"  📖 モジュール数: {course_info['modules_count']}モジュール")
            print(f"  🎓 対象レベル: {course_info['target_level']}")
            print(f"  🌍 言語: {course_info['language']}")
            print(f"  📊 信頼度: {course_info['confidence_score']}")
            print()
            
            # 生成コンテンツの詳細
            content = result["result"]["content_generated"]
            print("🎬 生成されたコンテンツ:")
            print(f"  📹 動画スクリプト: {content['video_scripts']}本")
            print(f"  📚 テキスト教材: {content['text_materials']}個")
            print(f"  🎮 演習問題: {content['exercises']}個")
            print(f"  📄 総ページ数: {content['total_pages']}ページ")
            print()
            
            # 出力ファイルの表示
            output_files = result["result"]["output_files"]
            print(f"📁 生成されたファイル ({len(output_files)}個):")
            
            # ファイルを種類別に分類して表示
            overview_files = [f for f in output_files if "overview" in Path(f).name]
            module_files = [f for f in output_files if "module_" in Path(f).parent.name]
            guide_files = [f for f in output_files if "guide" in Path(f).name or "strategy" in Path(f).name]
            
            if overview_files:
                print("  📋 概要ファイル:")
                for file_path in overview_files:
                    rel_path = Path(file_path).relative_to(current_dir)
                    print(f"    • {rel_path}")
            
            if guide_files:
                print("  📖 ガイド・戦略ファイル:")
                for file_path in guide_files:
                    rel_path = Path(file_path).relative_to(current_dir)
                    print(f"    • {rel_path}")
            
            # モジュール別ファイル数の表示
            module_dirs = {}
            for file_path in module_files:
                module_dir = Path(file_path).parent.name
                if module_dir not in module_dirs:
                    module_dirs[module_dir] = []
                module_dirs[module_dir].append(file_path)
            
            if module_dirs:
                print("  📚 モジュール別ファイル:")
                for module_name, files in module_dirs.items():
                    print(f"    📁 {module_name}: {len(files)}ファイル")
            
            print()
            
            # マーケティング戦略の表示
            marketing = result["result"]["marketing_strategy"]
            if marketing:
                print("💰 マーケティング戦略:")
                pricing = marketing["pricing"]
                revenue = marketing["revenue_projection"]
                print(f"  💵 推奨価格: {pricing['recommended_price']}")
                print(f"  🚀 ローンチ価格: {pricing['launch_price']}")
                print(f"  📈 現実的収益予測: {revenue['realistic_estimate']}")
                print(f"  📊 楽観的収益予測: {revenue['optimistic_estimate']}")
                print()
            
            # 副次効果の表示
            print("✨ 副次効果:")
            for effect in result["side_effects"]:
                print(f"  • {effect}")
            print()
            
            # 推奨事項の表示
            print("🎯 推奨事項:")
            for recommendation in result["recommendations"]:
                print(f"  • {recommendation}")
            print()
            
            # 実行統計
            print("📊 実行統計:")
            print(f"  ⏱️ 実行時間: {result['execution_time']}")
            print(f"  📊 信頼度: {result['confidence']}")
            print(f"  ✅ 成功: {result['success']}")
            print()
            
            # Trainingフォルダの確認
            training_path = current_dir / "Training"
            if training_path.exists():
                print("📁 Trainingフォルダの内容確認:")
                
                # 主要ファイルの存在確認
                main_files = [
                    "course_overview.md",
                    "learning_guide.md", 
                    "marketing_strategy.json"
                ]
                
                for file_name in main_files:
                    file_path = training_path / file_name
                    if file_path.exists():
                        size = file_path.stat().st_size
                        print(f"  ✅ {file_name} ({size:,} bytes)")
                    else:
                        print(f"  ❌ {file_name} (見つかりません)")
                
                # モジュールディレクトリの確認
                module_dirs = [d for d in training_path.iterdir() if d.is_dir() and d.name.startswith("module_")]
                print(f"  📚 モジュールディレクトリ: {len(module_dirs)}個")
                
                for module_dir in sorted(module_dirs):
                    files_count = len(list(module_dir.glob("*.md")))
                    print(f"    📁 {module_dir.name}: {files_count}ファイル")
                
                print()
            
            # サンプルコンテンツの表示
            print("📖 サンプルコンテンツ (course_overview.md の冒頭):")
            print("-" * 50)
            
            overview_file = training_path / "course_overview.md"
            if overview_file.exists():
                with open(overview_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[:15]  # 最初の15行
                    for line in lines:
                        print(f"  {line.rstrip()}")
                if len(lines) >= 15:
                    print("  ...")
            
            print("-" * 50)
            print()
            
        else:
            print("💥 魔法実行失敗:")
            print(f"  エラー: {result.get('error', '不明なエラー')}")
            if 'suggestions' in result:
                print("  提案:")
                for suggestion in result['suggestions']:
                    print(f"    • {suggestion}")
    
    except Exception as e:
        print(f"💥 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
    
    print("🌟" * 60)
    print("🎉 教育コンテンツ生成デモ完了！")
    print("💫 世界初のプロジェクト→Udemy級コース自動生成が実現...")
    print("🌟" * 60)


if __name__ == "__main__":
    asyncio.run(demo_course_generation())
