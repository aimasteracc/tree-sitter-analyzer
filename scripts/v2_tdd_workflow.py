#!/usr/bin/env python3
"""
V2 TDD Workflow Script - 双角色 TDD 工作流

Usage:
    python scripts/v2_tdd_workflow.py --module core --tdd
    python scripts/v2_tdd_workflow.py --role critic --task "review core parser"
    python scripts/v2_tdd_workflow.py --role worker --task "implement token optimization"

Features:
- Red-Green-Refactor TDD cycle
- Automatic test running
- Type checking integration
- Linting integration
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


class Colors:
    """终端颜色"""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class V2TDDWorkflow:
    """V2 TDD 工作流管理器"""
    
    def __init__(self, v2_path: str = "D:/git/tree-sitter-analyzer-v2"):
        self.v2_path = Path(v2_path)
        self.module_path = self.v2_path / "v2" / "tree_sitter_analyzer_v2"
        self.tests_path = self.v2_path / "v2" / "tests"
        
    def run_command(self, cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
        """运行命令"""
        print(f"{Colors.CYAN}Running: {' '.join(cmd)}{Colors.RESET}")
        result = subprocess.run(
            cmd,
            cwd=self.v2_path,
            capture_output=True,
            text=True
        )
        return result
        
    def red_phase(self, module: str) -> None:
        """🔴 Red Phase: 写测试"""
        print(f"\n{Colors.RED}{'='*60}")
        print("🔴 RED PHASE: 编写测试")
        print(f"{'='*60}{Colors.RESET}\n")
        
        test_file = self.tests_path / "unit" / f"test_{module}.py"
        
        if test_file.exists():
            print(f"📝 测试文件已存在: {test_file}")
            print("\n当前测试内容:")
            print("-" * 40)
            print(test_file.read_text()[:500])
            print("-" * 40)
        else:
            print(f"📝 需要创建测试文件: {test_file}")
            
        print(f"\n运行测试（预期失败）:")
        result = self.run_command([
            "uv", "run", "pytest", 
            f"v2/tests/unit/test_{module}.py",
            "-v", "--tb=short"
        ])
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        
    def green_phase(self, module: str) -> bool:
        """🟢 Green Phase: 实现代码"""
        print(f"\n{Colors.GREEN}{'='*60}")
        print("🟢 GREEN PHASE: 实现代码")
        print(f"{'='*60}{Colors.RESET}\n")
        
        result = self.run_command([
            "uv", "run", "pytest",
            f"v2/tests/unit/test_{module}.py",
            "-v", "--tb=short"
        ])
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ 测试通过！{Colors.RESET}")
            return True
        else:
            print(f"{Colors.RED}❌ 测试失败，需要实现代码{Colors.RESET}")
            print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
            return False
            
    def refactor_phase(self, module: str) -> tuple[bool, bool, bool]:
        """🟡 Refactor Phase: 重构检查"""
        print(f"\n{Colors.YELLOW}{'='*60}")
        print("🟡 REFACTOR PHASE: 代码质量检查")
        print(f"{'='*60}{Colors.RESET}\n")
        
        checks = [
            ("Type Check", ["uv", "run", "mypy", f"v2/tree_sitter_analyzer_v2/{module}/"]),
            ("Linter", ["uv", "run", "ruff", "check", f"v2/tree_sitter_analyzer_v2/{module}/"]),
            ("Formatter", ["uv", "run", "ruff", "format", "--check", f"v2/tree_sitter_analyzer_v2/{module}/"]),
        ]
        
        results = []
        for name, cmd in checks:
            result = self.run_command(cmd)
            if result.returncode == 0:
                print(f"{Colors.GREEN}✅ {name} 通过{Colors.RESET}")
                results.append(True)
            else:
                print(f"{Colors.RED}❌ {name} 失败{Colors.RESET}")
                if result.stdout:
                    print(result.stdout[:500])
                results.append(False)
                
        return tuple(results)
        
    def critic_review(self, task: str) -> None:
        """🦅 Critic Review: 代码审查"""
        print(f"\n{Colors.BLUE}{'='*60}")
        print(f"🦅 CRITIC REVIEW: {task}")
        print(f"{'='*60}{Colors.RESET}\n")
        
        review_questions = [
            "1. 这个功能的核心需求是什么？",
            "2. 边界条件是否都覆盖了？",
            "3. 错误处理是否完善？",
            "4. 性能影响如何？",
            "5. 是否与现有代码兼容？",
            "6. 是否有安全风险？",
            "7. 是否容易测试？",
            "8. API 设计是否合理？",
        ]
        
        print("批评者问题清单:")
        for q in review_questions:
            print(f"  {Colors.YELLOW}{q}{Colors.RESET}")
            
        print("\n建议输出格式:")
        print("""
## Critic Review: [功能名称]

### 问题
- [列出潜在问题]

### 建议
- [改进建议]

### 测试场景建议
- [应该覆盖的测试用例]
        """)
        
    def worker_task(self, task: str) -> None:
        """🔨 Worker Task: 执行开发任务"""
        print(f"\n{Colors.CYAN}{'='*60}")
        print(f"🔨 WORKER TASK: {task}")
        print(f"{'='*60}{Colors.RESET}\n")
        
        worker_steps = [
            "1. 理解需求，明确输入输出",
            "2. 设计接口，定义数据结构",
            "3. 编写测试（Red）",
            "4. 实现代码（Green）",
            "5. 重构优化（Refactor）",
            "6. 运行完整测试套件",
            "7. 提交代码",
        ]
        
        print("Worker 工作步骤:")
        for step in worker_steps:
            print(f"  {Colors.GREEN}{step}{Colors.RESET}")
            
    def run_tdd_cycle(self, module: str) -> bool:
        """运行完整的 TDD 循环"""
        print(f"\n{Colors.BOLD}{'='*60}")
        print(f"🚀 开始 TDD 循环: {module}")
        print(f"{'='*60}{Colors.RESET}\n")
        
        # Red
        self.red_phase(module)
        input(f"\n{Colors.YELLOW}实现代码后按回车继续...{Colors.RESET}")
        
        # Green
        if not self.green_phase(module):
            print(f"\n{Colors.RED}❌ TDD 循环失败：测试未通过{Colors.RESET}")
            return False
            
        # Refactor
        type_ok, lint_ok, format_ok = self.refactor_phase(module)
        
        if not all([type_ok, lint_ok, format_ok]):
            print(f"\n{Colors.YELLOW}⚠️  代码质量有问题，请修复{Colors.RESET}")
            input(f"修复后按回车继续...")
            type_ok, lint_ok, format_ok = self.refactor_phase(module)
            
        print(f"\n{Colors.GREEN}{'='*60}")
        print(f"✅ TDD 循环完成: {module}")
        print(f"{'='*60}{Colors.RESET}\n")
        return True
        
    def run_full_tests(self) -> None:
        """运行完整测试套件"""
        print(f"\n{Colors.BOLD}{'='*60}")
        print("🧪 运行完整测试套件")
        print(f"{'='*60}{Colors.RESET}\n")
        
        result = self.run_command([
            "uv", "run", "pytest",
            "v2/tests/",
            "-v", "--tb=short", "-x"
        ])
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ 所有测试通过！{Colors.RESET}")
        else:
            print(f"{Colors.RED}❌ 测试失败{Colors.RESET}")
            print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
            
    def sync_with_v1(self) -> None:
        """同步 v1 的改动"""
        print(f"\n{Colors.BOLD}{'='*60}")
        print("🔄 同步 v1 改动")
        print(f"{'='*60}{Colors.RESET}\n")
        
        print("1. 在 v1 目录:")
        print("   cd D:/git/tree-sitter-analyzer")
        print("   git fetch origin")
        print("   git pull origin main")
        print()
        print("2. 在 v2 目录:")
        print("   cd D:/git/tree-sitter-analyzer-v2")
        print("   git fetch origin")
        print("   git pull origin feature/v2-rewrite")
        print()
        print("3. 检查 v1 的 bugfix 是否需要移植到 v2")


def main():
    parser = argparse.ArgumentParser(
        description="V2 TDD Workflow - 双角色 TDD 工作流"
    )
    parser.add_argument(
        "--module", "-m",
        help="模块名称（如: core, api, formatters）"
    )
    parser.add_argument(
        "--role", "-r",
        choices=["critic", "worker"],
        help="角色模式"
    )
    parser.add_argument(
        "--task", "-t",
        help="任务描述"
    )
    parser.add_argument(
        "--tdd",
        action="store_true",
        help="运行完整 TDD 循环"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="运行完整测试套件"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="同步 v1 改动"
    )
    
    args = parser.parse_args()
    
    workflow = V2TDDWorkflow()
    
    if args.tdd and args.module:
        workflow.run_tdd_cycle(args.module)
    elif args.role == "critic" and args.task:
        workflow.critic_review(args.task)
    elif args.role == "worker" and args.task:
        workflow.worker_task(args.task)
    elif args.test:
        workflow.run_full_tests()
    elif args.sync:
        workflow.sync_with_v1()
    else:
        parser.print_help()
        print("\n示例用法:")
        print("  # 运行完整 TDD 循环")
        print("  python scripts/v2_tdd_workflow.py --module core --tdd")
        print()
        print("  # Critic 模式审查")
        print("  python scripts/v2_tdd_workflow.py --role critic --task 'review token optimization'")
        print()
        print("  # Worker 模式开发")
        print("  python scripts/v2_tdd_workflow.py --role worker --task 'implement caching'")
        print()
        print("  # 运行测试")
        print("  python scripts/v2_tdd_workflow.py --test")
        print()
        print("  # 同步 v1")
        print("  python scripts/v2_tdd_workflow.py --sync")


if __name__ == "__main__":
    main()
