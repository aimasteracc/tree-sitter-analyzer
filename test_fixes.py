#!/usr/bin/env python3
"""
简单测试脚本验证修复结果
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def test_mcp_async_integration():
    """测试MCP异步集成修复"""
    print("测试MCP异步集成...")
    try:
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        async def test_validation():
            tool = QueryTool(project_root=os.getcwd())

            # 测试缺少file_path参数
            result = await tool.execute({})
            assert result["success"] is False
            assert "file_path" in result["error"].lower()
            print("✓ MCP异步集成测试通过")
            return True

        return asyncio.run(test_validation())
    except Exception as e:
        print(f"✗ MCP异步集成测试失败: {e}")
        return False


def test_output_manager():
    """测试OutputManager修复"""
    print("测试OutputManager...")
    try:
        import sys
        from io import StringIO

        from tree_sitter_analyzer.output_manager import OutputManager

        # 模拟stdout和stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        mock_stdout = StringIO()
        mock_stderr = StringIO()
        sys.stdout = mock_stdout
        sys.stderr = mock_stderr

        try:
            manager = OutputManager(quiet=True)
            manager.output_info("This should not appear")
            manager.output_warning("This warning should not appear")
            manager.output_success("This success should not appear")

            stdout_output = mock_stdout.getvalue()
            stderr_output = mock_stderr.getvalue()

            # 在安静模式下，输出应该为空
            if stdout_output == "" and stderr_output == "":
                print("✓ OutputManager测试通过")
                return True
            else:
                print(
                    f"✗ OutputManager测试失败: stdout='{stdout_output}', stderr='{stderr_output}'"
                )
                return False
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    except Exception as e:
        print(f"✗ OutputManager测试失败: {e}")
        return False


def test_query_service():
    """测试QueryService修复"""
    print("测试QueryService...")
    try:
        from unittest.mock import Mock

        from tree_sitter_analyzer.core.query_service import QueryService

        service = QueryService()

        # 创建mock节点
        mock_function_node = Mock()
        mock_function_node.type = "function_definition"
        mock_function_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_function_node]

        # 测试functions查询（复数形式）
        result = service._fallback_query_execution(mock_root_node, "functions")

        if (
            len(result) == 1
            and result[0][0] == mock_function_node
            and result[0][1] == "functions"
        ):
            print("✓ QueryService测试通过")
            return True
        else:
            print(f"✗ QueryService测试失败: 结果长度={len(result)}")
            return False

    except Exception as e:
        print(f"✗ QueryService测试失败: {e}")
        return False


def test_logging():
    """测试日志修复"""
    print("测试日志功能...")
    try:
        import logging

        from tree_sitter_analyzer.utils import LoggingContext, setup_logger

        # 测试setup_logger
        logger = setup_logger("test_logger", level=logging.INFO)
        if logger.level == logging.INFO:
            print("✓ setup_logger测试通过")
        else:
            print(f"✗ setup_logger测试失败: 期望{logging.INFO}, 实际{logger.level}")
            return False

        # 测试LoggingContext
        test_logger = logging.getLogger("test_context")

        context = LoggingContext(enabled=True, level=logging.WARNING)
        context.target_logger = test_logger

        with context:
            if test_logger.level == logging.WARNING:
                print("✓ LoggingContext测试通过")
                return True
            else:
                print(
                    f"✗ LoggingContext测试失败: 期望{logging.WARNING}, 实际{test_logger.level}"
                )
                return False

    except Exception as e:
        print(f"✗ 日志测试失败: {e}")
        return False


def test_utils_extended():
    """测试utils_extended修复"""
    print("测试utils_extended...")
    try:
        from tree_sitter_analyzer.utils import safe_print

        # 测试safe_print函数
        safe_print("test info", level="info")
        safe_print("test debug", level="debug")
        safe_print("test error", level="error")
        safe_print("test warning", level="warning")
        safe_print("test", level="INVALID")  # 无效级别
        safe_print("test info", level="info", quiet=True)  # 安静模式

        print("✓ utils_extended测试通过")
        return True

    except Exception as e:
        print(f"✗ utils_extended测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("开始验证修复结果...\n")

    tests = [
        test_output_manager,
        test_query_service,
        test_logging,
        test_utils_extended,
        test_mcp_async_integration,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"测试异常: {e}")
        print()

    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有修复验证通过！")
        return True
    else:
        print("❌ 部分测试仍然失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
