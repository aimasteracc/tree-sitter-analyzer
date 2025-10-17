#!/usr/bin/env python3
"""
バージョンセットアップスクリプト - 高度な自動インストール機能付き

使用方法:
    uv run python setup_versions.py 1.6.1 1.9.2
    uv run python setup_versions.py --list-available
    uv run python setup_versions.py --interactive
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
import logging
import json
import shutil
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import time

# 新しい依存関係のインポート
try:
    import questionary
    from rich.console import Console
    from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from packaging import version
    import yaml
except ImportError as e:
    print(f"必要な依存関係がインストールされていません: {e}")
    print("以下のコマンドで依存関係をインストールしてください:")
    print("pip install questionary rich PyYAML packaging")
    sys.exit(1)

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Richコンソールの初期化
console = Console()


class AsyncVersionSetup:
    """非同期バージョンセットアップクラス"""
    
    def __init__(self):
        self.compatibility_test_dir = Path(__file__).parent
        self.versions_dir = self.compatibility_test_dir / "versions"
        self.config_file = self.compatibility_test_dir / "setup_config.yaml"
        self.max_concurrent_installs = 3  # 同時インストール数の制限
        
    async def setup_version_async(self, version: str, force: bool = False, progress: Optional[Progress] = None, task_id: Optional[TaskID] = None) -> bool:
        """指定されたバージョンを非同期でセットアップ"""
        version_dir = self.versions_dir / f"v{version}"
        venv_dir = version_dir / "venv"
        
        if progress and task_id:
            progress.update(task_id, description=f"[cyan]バージョン {version} セットアップ開始...")
        
        logger.info(f"バージョン {version} のセットアップを開始: {version_dir}")
        
        # ディレクトリが既に存在する場合
        if version_dir.exists() and not force:
            if progress and task_id:
                progress.update(task_id, description=f"[yellow]バージョン {version} は既に存在")
            logger.warning(f"バージョンディレクトリが既に存在します: {version_dir}")
            return False
        
        try:
            # ディレクトリを作成
            version_dir.mkdir(parents=True, exist_ok=True)
            if progress and task_id:
                progress.update(task_id, advance=10, description=f"[cyan]ディレクトリ作成完了: {version}")
            
            # 仮想環境を作成
            if progress and task_id:
                progress.update(task_id, advance=10, description=f"[cyan]仮想環境作成中: {version}")
            
            result = await self._run_subprocess([
                sys.executable, "-m", "venv", str(venv_dir)
            ])
            
            if result.returncode != 0:
                logger.error(f"仮想環境作成に失敗: {result.stderr}")
                if progress and task_id:
                    progress.update(task_id, description=f"[red]仮想環境作成失敗: {version}")
                return False
            
            if progress and task_id:
                progress.update(task_id, advance=20, description=f"[cyan]仮想環境作成完了: {version}")
            
            # Python実行可能ファイルのパスを取得
            python_exe = self._get_python_executable(venv_dir)
            
            if not python_exe.exists():
                logger.error(f"Python実行可能ファイルが見つかりません: {python_exe}")
                if progress and task_id:
                    progress.update(task_id, description=f"[red]Python実行ファイル不明: {version}")
                return False
            
            # tree-sitter-analyzerをインストール
            if progress and task_id:
                progress.update(task_id, advance=20, description=f"[cyan]パッケージインストール中: {version}")
            
            result = await self._run_subprocess([
                str(python_exe), "-m", "pip", "install", 
                f"tree-sitter-analyzer[mcp]=={version}"
            ])
            
            if result.returncode != 0:
                logger.error(f"パッケージインストールに失敗: {result.stderr}")
                if progress and task_id:
                    progress.update(task_id, description=f"[red]パッケージインストール失敗: {version}")
                return False
            
            if progress and task_id:
                progress.update(task_id, advance=30, description=f"[cyan]インストール確認中: {version}")
            
            # バージョンを確認
            result = await self._run_subprocess([
                str(python_exe), "-c", 
                "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
            ])
            
            if result.returncode == 0:
                installed_version = result.stdout.strip()
                logger.info(f"✓ インストール確認: {installed_version}")
                
                if version not in installed_version:
                    logger.warning(f"期待されたバージョン {version} と異なります: {installed_version}")
            else:
                logger.warning("バージョン確認に失敗しましたが、セットアップは完了しました")
            
            if progress and task_id:
                progress.update(task_id, advance=10, description=f"[green]✅ セットアップ完了: {version}")
            
            logger.info(f"✅ バージョン {version} のセットアップが完了しました")
            return True
            
        except Exception as e:
            logger.error(f"セットアップ中にエラーが発生: {e}")
            if progress and task_id:
                progress.update(task_id, description=f"[red]エラー発生: {version}")
            return False
    
    async def setup_multiple_versions_async(self, versions: List[str], force: bool = False) -> Dict[str, bool]:
        """複数バージョンを並列でセットアップ"""
        console.print(Panel(f"[bold cyan]並列インストール開始[/bold cyan]\n対象バージョン: {', '.join(versions)}", 
                          title="🚀 高速セットアップ"))
        
        results = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=False
        ) as progress:
            
            # 各バージョンのタスクを作成
            tasks = {}
            for version in versions:
                task_id = progress.add_task(f"[cyan]準備中: {version}", total=100)
                tasks[version] = task_id
            
            # セマフォを使用して同時実行数を制限
            semaphore = asyncio.Semaphore(self.max_concurrent_installs)
            
            async def setup_with_semaphore(version: str):
                async with semaphore:
                    return await self.setup_version_async(version, force, progress, tasks[version])
            
            # 並列実行
            setup_tasks = [setup_with_semaphore(version) for version in versions]
            setup_results = await asyncio.gather(*setup_tasks, return_exceptions=True)
            
            # 結果をまとめる
            for version, result in zip(versions, setup_results):
                if isinstance(result, Exception):
                    logger.error(f"バージョン {version} でエラー: {result}")
                    results[version] = False
                else:
                    results[version] = result
        
        # 結果サマリーを表示
        self._display_setup_summary(results)
        return results
    
    def _display_setup_summary(self, results: Dict[str, bool]):
        """セットアップ結果のサマリーを表示"""
        table = Table(title="📊 セットアップ結果サマリー")
        table.add_column("バージョン", style="cyan")
        table.add_column("ステータス", style="bold")
        table.add_column("パス", style="dim")
        
        success_count = 0
        for version, success in results.items():
            if success:
                status = "[green]✅ 成功[/green]"
                success_count += 1
            else:
                status = "[red]❌ 失敗[/red]"
            
            version_path = self.versions_dir / f"v{version}"
            table.add_row(version, status, str(version_path))
        
        console.print(table)
        console.print(f"\n[bold]結果: {success_count}/{len(results)} バージョンが正常にセットアップされました[/bold]")
    
    async def _run_subprocess(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """非同期でサブプロセスを実行"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor,
                lambda: subprocess.run(cmd, capture_output=True, text=True)
            )
        return result
    
    def _get_python_executable(self, venv_dir: Path) -> Path:
        """仮想環境のPython実行可能ファイルパスを取得"""
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "python.exe"
        else:
            return venv_dir / "bin" / "python"
    
    async def get_available_versions_from_pypi(self) -> List[str]:
        """PyPIから利用可能なバージョンを非同期で取得"""
        console.print("[cyan]PyPIからバージョン情報を取得中...[/cyan]")
        
        # 複数の方法を順番に試行
        methods = [
            self._get_versions_via_pypi_api,
            self._get_versions_via_pip_index,
            self._get_versions_via_uv_pip_show,
        ]
        
        for method_name, method in [
            ("PyPI API", self._get_versions_via_pypi_api),
            ("pip index", self._get_versions_via_pip_index),
            ("uv pip show", self._get_versions_via_uv_pip_show),
        ]:
            try:
                logger.info(f"方法 '{method_name}' でバージョン取得を試行中...")
                versions = await method()
                if versions:
                    logger.info(f"✓ 方法 '{method_name}' で {len(versions)} バージョンを取得")
                    return versions
                else:
                    logger.warning(f"方法 '{method_name}' ではバージョンが取得できませんでした")
            except Exception as e:
                logger.error(f"方法 '{method_name}' でエラー: {e}")
                continue
        
        # すべての方法が失敗した場合
        console.print("[yellow]⚠ PyPIからのバージョン取得に失敗しました[/yellow]")
        console.print("[dim]ネットワーク接続を確認するか、以下のデフォルトバージョンを使用してください[/dim]")
        logger.warning("WARNING: PyPIからのバージョン取得に失敗、デフォルトリストを使用")
        return ["1.9.2", "1.9.1", "1.8.4", "1.7.7", "1.6.1", "1.5.0"]
    
    async def _get_versions_via_pypi_api(self) -> List[str]:
        """PyPI APIを使用してバージョンを取得"""
        try:
            # urllib.requestを使用してHTTPリクエストを送信
            import urllib.request
            import json
            
            url = "https://pypi.org/pypi/tree-sitter-analyzer/json"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                versions = list(data['releases'].keys())
                # 有効なバージョンのみをフィルタリング
                valid_versions = [v for v in versions if self._is_valid_version(v)]
                return sorted(valid_versions, key=lambda x: version.parse(x), reverse=True)
        except Exception as e:
            logger.debug(f"PyPI API方式でエラー: {e}")
            return []
    
    async def _test_fallback_functionality(self) -> List[str]:
        """フォールバック機能をテストするための一時的なメソッド"""
        # すべての方法を失敗させてフォールバック機能をテスト
        logger.warning("テスト: すべてのバージョン取得方法を失敗させています")
        return []
    
    async def _get_versions_via_pip_index(self) -> List[str]:
        """pip index versionsコマンドを使用してバージョンを取得"""
        try:
            # 標準のpipコマンドを試行
            result = await self._run_subprocess([
                sys.executable, "-m", "pip", "index", "versions", "tree-sitter-analyzer"
            ])
            
            if result.returncode == 0:
                return self._parse_pip_index_output(result.stdout)
            else:
                logger.debug(f"pip index versionsコマンドが失敗: {result.stderr}")
                return []
                
        except Exception as e:
            logger.debug(f"pip index方式でエラー: {e}")
            return []
    
    async def _get_versions_via_uv_pip_show(self) -> List[str]:
        """uv環境でのバージョン取得を試行"""
        try:
            # uvでパッケージ情報を取得
            result = await self._run_subprocess([
                "uv", "pip", "show", "tree-sitter-analyzer"
            ])
            
            if result.returncode == 0:
                # showコマンドからは現在のバージョンのみ取得可能
                # より良い方法を探すか、デフォルトリストを使用
                logger.debug("uv pip showは現在のバージョンのみ表示")
                return []
            else:
                return []
                
        except Exception as e:
            logger.debug(f"uv pip show方式でエラー: {e}")
            return []
    
    def _parse_pip_index_output(self, output: str) -> List[str]:
        """pip index versionsの出力からバージョンを抽出"""
        versions = []
        lines = output.split('\n')
        
        for line in lines:
            if 'Available versions:' in line:
                # バージョンリストを抽出
                version_part = line.split('Available versions:')[1].strip()
                versions = [v.strip() for v in version_part.split(',') if v.strip()]
                break
        
        if not versions:
            # 別の形式で試行
            for line in lines:
                if line.strip() and not line.startswith('WARNING') and not line.startswith('Looking'):
                    # バージョン番号らしい行を探す
                    parts = line.strip().split()
                    for part in parts:
                        if self._is_valid_version(part):
                            versions.append(part)
        
        return sorted(versions, key=lambda x: version.parse(x), reverse=True) if versions else []
    
    def _is_valid_version(self, version_str: str) -> bool:
        """有効なバージョン文字列かチェック"""
        try:
            version.parse(version_str)
            return True
        except:
            return False
    
    async def interactive_setup(self):
        """インタラクティブなセットアップモード"""
        console.print(Panel("[bold cyan]🎯 インタラクティブセットアップモード[/bold cyan]", 
                          title="Welcome"))
        
        # 利用可能なバージョンを取得
        available_versions = await self.get_available_versions_from_pypi()
        
        if not available_versions:
            console.print("[red]利用可能なバージョンを取得できませんでした[/red]")
            return
        
        # インストール済みバージョンを確認
        installed_versions = self.get_installed_versions()
        
        # バージョン選択
        choices = []
        for ver in available_versions[:10]:  # 最新10バージョンのみ表示
            status = " (インストール済み)" if ver in installed_versions else ""
            choices.append(questionary.Choice(f"{ver}{status}", value=ver))
        
        selected_versions = await questionary.checkbox(
            "インストールするバージョンを選択してください:",
            choices=choices
        ).ask_async()
        
        if not selected_versions:
            console.print("[yellow]バージョンが選択されませんでした[/yellow]")
            return
        
        # 強制上書きの確認
        force = False
        if any(ver in installed_versions for ver in selected_versions):
            force = await questionary.confirm(
                "既存のバージョンを上書きしますか？"
            ).ask_async()
        
        # 並列インストール数の設定
        max_concurrent = await questionary.select(
            "同時インストール数を選択してください:",
            choices=[
                questionary.Choice("1 (安全)", 1),
                questionary.Choice("2 (推奨)", 2),
                questionary.Choice("3 (高速)", 3),
                questionary.Choice("4 (最高速)", 4),
            ],
            default=2
        ).ask_async()
        
        self.max_concurrent_installs = max_concurrent
        
        # セットアップ実行
        console.print(f"\n[bold green]選択されたバージョン: {', '.join(selected_versions)}[/bold green]")
        console.print(f"[bold]同時インストール数: {max_concurrent}[/bold]")
        
        if await questionary.confirm("セットアップを開始しますか？").ask_async():
            results = await self.setup_multiple_versions_async(selected_versions, force)
            
            # 次のステップを表示
            success_versions = [ver for ver, success in results.items() if success]
            if success_versions:
                console.print(Panel(
                    f"[green]✅ セットアップ完了![/green]\n\n"
                    f"次のステップ:\n"
                    f"1. セットアップ確認: uv run python test_version_manager.py\n"
                    f"2. テスト実行: uv run python mcp_test_direct.py --version <version>",
                    title="🎉 完了"
                ))
    
    def get_installed_versions(self) -> List[str]:
        """インストール済みバージョンのリストを取得"""
        installed = []
        
        if not self.versions_dir.exists():
            return installed
        
        for item in self.versions_dir.iterdir():
            if item.is_dir() and item.name.startswith("v"):
                version_name = item.name[1:]  # "v"を除去
                python_exe = self._get_python_executable(item / "venv")
                
                if python_exe.exists():
                    installed.append(version_name)
        
        return installed
    
    async def list_available_versions(self):
        """利用可能なバージョンを表示（非同期版）"""
        versions = await self.get_available_versions_from_pypi()
        
        table = Table(title="📦 利用可能なバージョン")
        table.add_column("バージョン", style="cyan")
        table.add_column("ステータス", style="bold")
        
        installed = self.get_installed_versions()
        
        for ver in versions:
            status = "[green]インストール済み[/green]" if ver in installed else "[dim]未インストール[/dim]"
            table.add_row(ver, status)
        
        console.print(table)
    
    def list_installed_versions(self):
        """インストール済みバージョンを表示"""
        console.print("[cyan]インストール済みバージョンを確認中...[/cyan]")
        
        if not self.versions_dir.exists():
            console.print("[yellow]バージョンディレクトリが存在しません[/yellow]")
            return
        
        table = Table(title="💾 インストール済みバージョン")
        table.add_column("バージョン", style="cyan")
        table.add_column("実際のバージョン", style="green")
        table.add_column("パス", style="dim")
        table.add_column("ステータス", style="bold")
        
        installed_count = 0
        for item in self.versions_dir.iterdir():
            if item.is_dir() and item.name.startswith("v"):
                version_name = item.name[1:]  # "v"を除去
                python_exe = self._get_python_executable(item / "venv")
                
                if python_exe.exists():
                    try:
                        result = subprocess.run([
                            str(python_exe), "-c",
                            "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
                        ], capture_output=True, text=True, timeout=5)
                        
                        if result.returncode == 0:
                            actual_version = result.stdout.strip()
                            status = "[green]✅ 正常[/green]"
                            installed_count += 1
                        else:
                            actual_version = "不明"
                            status = "[yellow]⚠ 不完全[/yellow]"
                    except Exception:
                        actual_version = "エラー"
                        status = "[red]❌ エラー[/red]"
                else:
                    actual_version = "N/A"
                    status = "[red]❌ 実行ファイルなし[/red]"
                
                table.add_row(version_name, actual_version, str(item), status)
        
        console.print(table)
        
        if installed_count == 0:
            console.print("[yellow]インストール済みバージョンはありません[/yellow]")
        else:
            console.print(f"\n[bold]合計 {installed_count} バージョンがインストール済みです[/bold]")
    
    def cleanup_version(self, version: str) -> bool:
        """指定されたバージョンを削除"""
        version_dir = self.versions_dir / f"v{version}"
        
        if not version_dir.exists():
            console.print(f"[yellow]バージョンディレクトリが存在しません: {version_dir}[/yellow]")
            return False
        
        try:
            shutil.rmtree(version_dir)
            console.print(f"[green]✓ バージョン {version} を削除しました[/green]")
            return True
        except Exception as e:
            console.print(f"[red]削除中にエラーが発生: {e}[/red]")
            return False


def parse_arguments():
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(description="tree-sitter-analyzer高度なバージョンセットアップ")
    parser.add_argument("versions", nargs="*", help="セットアップするバージョン")
    parser.add_argument("--list-available", action="store_true", help="利用可能なバージョンを表示")
    parser.add_argument("--list-installed", action="store_true", help="インストール済みバージョンを表示")
    parser.add_argument("--cleanup", help="指定されたバージョンを削除")
    parser.add_argument("--force", action="store_true", help="既存のバージョンを上書き")
    parser.add_argument("--interactive", action="store_true", help="インタラクティブモードで実行")
    parser.add_argument("--max-concurrent", type=int, default=3, help="最大同時インストール数 (デフォルト: 3)")
    
    return parser.parse_args()


async def main_async():
    """非同期メイン関数"""
    args = parse_arguments()
    setup = AsyncVersionSetup()
    setup.max_concurrent_installs = args.max_concurrent
    
    if args.interactive:
        await setup.interactive_setup()
        return 0
    
    if args.list_available:
        await setup.list_available_versions()
        return 0
    
    if args.list_installed:
        setup.list_installed_versions()
        return 0
    
    if args.cleanup:
        success = setup.cleanup_version(args.cleanup)
        return 0 if success else 1
    
    if not args.versions:
        console.print("[red]セットアップするバージョンを指定してください[/red]")
        console.print("[dim]使用例:[/dim]")
        console.print("  uv run python setup_versions.py 1.6.1 1.6.0")
        console.print("  uv run python setup_versions.py --interactive")
        console.print("  uv run python setup_versions.py --list-available")
        return 1
    
    # バージョンをセットアップ（並列実行）
    results = await setup.setup_multiple_versions_async(args.versions, args.force)
    
    success_count = sum(1 for success in results.values() if success)
    
    if success_count > 0:
        console.print(Panel(
            f"[green]✅ セットアップ完了![/green]\n\n"
            f"次のステップ:\n"
            f"1. セットアップ確認: uv run python test_version_manager.py\n"
            f"2. テスト実行: uv run python mcp_test_direct.py --version <version>",
            title="🎉 完了"
        ))
    
    return 0 if success_count == len(args.versions) else 1


def main():
    """メイン関数"""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[yellow]ユーザーによって中断されました[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]予期しないエラーが発生しました: {e}[/red]")
        logger.exception("詳細なエラー情報:")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)