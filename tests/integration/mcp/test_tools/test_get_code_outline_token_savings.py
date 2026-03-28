#!/usr/bin/env python3
"""
Token savings verification tests for get_code_outline TOON format.

验证 TOON 格式相比 JSON 格式的 Token 节省效果。
使用不同大小的文件（小/中/大）测试，确保至少 40% 的字符数减少。
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

# ---------------------------------------------------------------------------
# 测试用代码片段（小/中/大三种规模）
# ---------------------------------------------------------------------------

SMALL_PYTHON_CODE = '''
"""Small Python module."""


class SimpleClass:
    """A simple class."""

    def method_one(self):
        """First method."""
        pass

    def method_two(self):
        """Second method."""
        pass
'''

MEDIUM_PYTHON_CODE = '''
"""Medium-sized Python module with multiple classes."""

import os
import sys
from typing import Optional, List, Dict


class DataProcessor:
    """数据处理类"""

    def __init__(self, config: Dict[str, str]):
        """初始化处理器"""
        self.config = config
        self.cache = {}

    def process(self, data: List[str]) -> List[str]:
        """处理数据列表"""
        results = []
        for item in data:
            if self._validate(item):
                results.append(self._transform(item))
        return results

    def _validate(self, item: str) -> bool:
        """验证单个数据项"""
        return len(item) > 0 and item.strip()

    def _transform(self, item: str) -> str:
        """转换单个数据项"""
        return item.strip().lower()


class ConfigManager:
    """配置管理类"""

    def __init__(self, config_path: str):
        """初始化配置管理器"""
        self.config_path = config_path
        self.config = {}

    def load(self) -> Dict[str, str]:
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path) as f:
                return self._parse(f.read())
        return {}

    def save(self, config: Dict[str, str]) -> None:
        """保存配置文件"""
        with open(self.config_path, 'w') as f:
            f.write(self._serialize(config))

    def _parse(self, content: str) -> Dict[str, str]:
        """解析配置内容"""
        lines = content.split('\\n')
        result = {}
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                result[key.strip()] = value.strip()
        return result

    def _serialize(self, config: Dict[str, str]) -> str:
        """序列化配置"""
        lines = [f"{k}={v}" for k, v in config.items()]
        return '\\n'.join(lines)


def helper_function(x: int, y: int) -> int:
    """辅助函数：计算两数之和"""
    return x + y
'''

LARGE_JAVA_CODE = '''
package com.example.service;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * 大型业务服务类
 * 包含多个方法和嵌套类
 */
public class EnterpriseService {
    private final Database db;
    private final Cache cache;
    private final Logger logger;
    private final MetricsCollector metrics;

    public EnterpriseService(Database db, Cache cache, Logger logger, MetricsCollector metrics) {
        this.db = db;
        this.cache = cache;
        this.logger = logger;
        this.metrics = metrics;
    }

    /**
     * 获取用户信息
     */
    public Optional<User> getUser(int userId) {
        metrics.increment("getUser.calls");
        String cacheKey = "user:" + userId;
        User cached = cache.get(cacheKey);
        if (cached != null) {
            metrics.increment("getUser.cache_hit");
            return Optional.of(cached);
        }

        metrics.increment("getUser.cache_miss");
        User user = db.query("SELECT * FROM users WHERE id = ?", userId);
        if (user != null) {
            cache.set(cacheKey, user, 300);
        }
        return Optional.ofNullable(user);
    }

    /**
     * 创建新用户
     */
    public int createUser(String username, String email, String password) throws ValidationException {
        metrics.increment("createUser.calls");

        // 验证输入
        if (!validateEmail(email)) {
            throw new ValidationException("Invalid email format");
        }
        if (!validatePassword(password)) {
            throw new ValidationException("Weak password");
        }

        // 检查用户名是否已存在
        if (userExists(username)) {
            throw new ValidationException("Username already taken");
        }

        // 哈希密码
        String hashedPassword = hashPassword(password);

        // 插入数据库
        String query = "INSERT INTO users (username, email, password) VALUES (?, ?, ?)";
        int userId = db.execute(query, username, email, hashedPassword);

        logger.info("Created user: " + username + " with id: " + userId);
        return userId;
    }

    /**
     * 更新用户信息
     */
    public void updateUser(int userId, Map<String, Object> updates) throws ValidationException {
        metrics.increment("updateUser.calls");

        if (!userExistsById(userId)) {
            throw new ValidationException("User not found");
        }

        List<String> setClauses = new ArrayList<>();
        List<Object> params = new ArrayList<>();

        for (Map.Entry<String, Object> entry : updates.entrySet()) {
            String field = entry.getKey();
            Object value = entry.getValue();

            if (field.equals("email") && !validateEmail((String) value)) {
                throw new ValidationException("Invalid email format");
            }

            setClauses.add(field + " = ?");
            params.add(value);
        }

        params.add(userId);
        String query = "UPDATE users SET " + String.join(", ", setClauses) + " WHERE id = ?";
        db.execute(query, params.toArray());

        cache.invalidate("user:" + userId);
        logger.info("Updated user: " + userId);
    }

    /**
     * 删除用户
     */
    public void deleteUser(int userId) throws ValidationException {
        metrics.increment("deleteUser.calls");

        if (!userExistsById(userId)) {
            throw new ValidationException("User not found");
        }

        db.execute("DELETE FROM users WHERE id = ?", userId);
        cache.invalidate("user:" + userId);
        logger.info("Deleted user: " + userId);
    }

    /**
     * 批量获取用户
     */
    public List<User> getUsers(List<Integer> userIds) {
        metrics.increment("getUsers.calls");

        return userIds.stream()
            .map(this::getUser)
            .filter(Optional::isPresent)
            .map(Optional::get)
            .collect(Collectors.toList());
    }

    /**
     * 搜索用户
     */
    public List<User> searchUsers(String query, int limit, int offset) {
        metrics.increment("searchUsers.calls");

        String sql = "SELECT * FROM users WHERE username LIKE ? OR email LIKE ? LIMIT ? OFFSET ?";
        String pattern = "%" + query + "%";
        return db.queryList(sql, pattern, pattern, limit, offset);
    }

    /**
     * 验证邮箱格式
     */
    private boolean validateEmail(String email) {
        String pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$";
        return email.matches(pattern);
    }

    /**
     * 验证密码强度
     */
    private boolean validatePassword(String password) {
        return password.length() >= 8 &&
               password.matches(".*[A-Z].*") &&
               password.matches(".*[a-z].*") &&
               password.matches(".*[0-9].*");
    }

    /**
     * 检查用户名是否存在
     */
    private boolean userExists(String username) {
        Integer count = db.queryOne("SELECT COUNT(*) FROM users WHERE username = ?", username);
        return count != null && count > 0;
    }

    /**
     * 检查用户ID是否存在
     */
    private boolean userExistsById(int userId) {
        Integer count = db.queryOne("SELECT COUNT(*) FROM users WHERE id = ?", userId);
        return count != null && count > 0;
    }

    /**
     * 哈希密码
     */
    private String hashPassword(String password) {
        // 实际应使用 BCrypt 等安全哈希算法
        return "hashed_" + password;
    }

    /**
     * 内部缓存统计类
     */
    public static class CacheStats {
        private long hits;
        private long misses;
        private long size;

        public CacheStats(long hits, long misses, long size) {
            this.hits = hits;
            this.misses = misses;
            this.size = size;
        }

        public long getHits() {
            return hits;
        }

        public long getMisses() {
            return misses;
        }

        public long getSize() {
            return size;
        }

        public double getHitRate() {
            long total = hits + misses;
            return total > 0 ? (double) hits / total : 0.0;
        }
    }
}

/**
 * 验证异常类
 */
class ValidationException extends Exception {
    public ValidationException(String message) {
        super(message);
    }
}
'''


# ---------------------------------------------------------------------------
# Token 节省效果验证测试
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTokenSavingsGetCodeOutline:
    """验证 TOON 格式相比 JSON 格式的 Token 节省效果"""

    @pytest.mark.asyncio
    async def test_small_file_token_savings(self):
        """小文件（~20 行）：TOON 应至少节省 40% 字符"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as f:
            f.write(SMALL_PYTHON_CODE)
            temp_path = f.name

        try:
            # 获取 TOON 格式输出
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            # 获取 JSON 格式输出
            json_result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            toon_length = len(toon_result["content"][0]["text"])
            json_length = len(json_result["content"][0]["text"])

            # 计算减少比例
            reduction = (json_length - toon_length) / json_length

            # 验证至少节省 40%
            assert reduction >= 0.40, (
                f"小文件 Token 节省不足：{reduction:.1%} < 40%\n"
                f"  TOON: {toon_length} chars\n"
                f"  JSON: {json_length} chars"
            )

            print("\n小文件 Token 节省效果:")
            print(f"  TOON: {toon_length} chars")
            print(f"  JSON: {json_length} chars")
            print(f"  节省: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_medium_file_token_savings(self):
        """中文件（~100 行）：TOON 应至少节省 40% 字符"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as f:
            f.write(MEDIUM_PYTHON_CODE)
            temp_path = f.name

        try:
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            json_result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            toon_length = len(toon_result["content"][0]["text"])
            json_length = len(json_result["content"][0]["text"])

            reduction = (json_length - toon_length) / json_length

            assert reduction >= 0.40, (
                f"中文件 Token 节省不足：{reduction:.1%} < 40%\n"
                f"  TOON: {toon_length} chars\n"
                f"  JSON: {json_length} chars"
            )

            print("\n中文件 Token 节省效果:")
            print(f"  TOON: {toon_length} chars")
            print(f"  JSON: {json_length} chars")
            print(f"  节省: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_large_file_token_savings(self):
        """大文件（~250 行）：TOON 应至少节省 40% 字符"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False, encoding='utf-8') as f:
            f.write(LARGE_JAVA_CODE)
            temp_path = f.name

        try:
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            json_result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            toon_length = len(toon_result["content"][0]["text"])
            json_length = len(json_result["content"][0]["text"])

            reduction = (json_length - toon_length) / json_length

            assert reduction >= 0.40, (
                f"大文件 Token 节省不足：{reduction:.1%} < 40%\n"
                f"  TOON: {toon_length} chars\n"
                f"  JSON: {json_length} chars"
            )

            print("\n大文件 Token 节省效果:")
            print(f"  TOON: {toon_length} chars")
            print(f"  JSON: {json_length} chars")
            print(f"  节省: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_token_savings_summary(self):
        """汇总测试：验证所有三种规模文件的平均 Token 节省效果"""
        tool = GetCodeOutlineTool()
        test_cases = [
            ("small", SMALL_PYTHON_CODE, ".py"),
            ("medium", MEDIUM_PYTHON_CODE, ".py"),
            ("large", LARGE_JAVA_CODE, ".java")
        ]

        results = []

        for name, code, suffix in test_cases:
            with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_path = f.name

            try:
                toon_result = await tool.execute(
                    {"file_path": temp_path, "output_format": "toon"}
                )

                json_result = await tool.execute(
                    {"file_path": temp_path, "output_format": "json"}
                )

                toon_length = len(toon_result[0]["text"])
                json_length = len(json_result[0]["text"])
                reduction = (json_length - toon_length) / json_length

                results.append({
                    "name": name,
                    "toon": toon_length,
                    "json": json_length,
                    "reduction": reduction
                })
            finally:
                Path(temp_path).unlink(missing_ok=True)

        # 计算平均节省比例
        avg_reduction = sum(r["reduction"] for r in results) / len(results)

        # 打印汇总报告
        print("\n" + "=" * 60)
        print("Token 节省效果汇总报告")
        print("=" * 60)
        for r in results:
            print(f"\n{r['name'].upper()} 文件:")
            print(f"  TOON: {r['toon']:5d} chars")
            print(f"  JSON: {r['json']:5d} chars")
            print(f"  节省: {r['reduction']:6.1%}")

        print("\n" + "-" * 60)
        print(f"平均 Token 节省: {avg_reduction:.1%}")
        print("=" * 60)

        # 验证平均节省比例至少 40%
        assert avg_reduction >= 0.40, (
            f"平均 Token 节省不足：{avg_reduction:.1%} < 40%"
        )

    @pytest.mark.asyncio
    async def test_character_to_token_approximation(self):
        """验证字符数可作为 Token 数的近似指标"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as f:
            f.write(MEDIUM_PYTHON_CODE)
            temp_path = f.name

        try:
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            toon_text = toon_result[0]["text"]
            char_count = len(toon_text)

            # 近似 Token 计算（英文约 4 chars/token，中文约 1-2 chars/token）
            # 保守估计：取 3 chars/token 作为混合文本的平均值
            approx_tokens = char_count / 3

            print("\nToken 近似估算:")
            print(f"  字符数: {char_count}")
            print(f"  估算 Token 数: {approx_tokens:.0f}")
            print("  (基于 3 chars/token 的保守估计)")

            # 验证这个近似值是合理的（至少有一些字符）
            assert char_count > 0
            assert approx_tokens > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)
